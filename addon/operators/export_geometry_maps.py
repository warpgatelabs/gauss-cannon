import bpy
import os
import json
import threading
import types
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..utils.camera_eval import angle_based_intrinsics, camera_matrices_for_frames
from ..utils.compositor_passes import PASSES_FOLDER
from ..utils.geometry_maps import (
    convert_frame,
    max_valid_depth,
    read_exr,
    scan_pass_frames,
    write_png,
)

# EXR decoding and PNG encoding run inside OpenImageIO with the GIL released,
# so frames convert in parallel on threads. Each worker holds about one
# frame's passes in memory (~100 MB at 4K), hence the cap.
_MAX_WORKERS = min(8, os.cpu_count() or 1)

# Share of the progress bar for the depth scan, which only reads EXRs and
# takes about a tenth of the conversion's time
_SCAN_SHARE = 0.1

# The conversion running in the background, if any (read by the panel)
_active_job = None


class ConversionCancelled(Exception):
    pass


class ConversionJob:
    """
    Converts every frame's passes on a thread pool.

    Holds no bpy data, so run() is safe off the main thread: the modal
    operator runs it on a background thread and polls the progress fields.
    """

    def __init__(self, frames, complete, matrices, cam_data, output_dir, want_depth, want_normals):
        self.frames = frames
        self.complete = complete
        # Main-thread snapshots of the bpy data the workers need
        self.cam_to_world = {
            f: np.array(matrices[f].to_3x3().normalized()) for f in complete
        }
        self.camera = types.SimpleNamespace(sensor_fit=cam_data.sensor_fit, angle=cam_data.angle)
        self.clip_end = cam_data.clip_end
        self.output_dir = output_dir
        self.depths_dir = os.path.join(output_dir, "depths")
        self.normals_dir = os.path.join(output_dir, "normals")
        self.metadata_path = os.path.join(output_dir, "geometry_maps.json")
        self.want_depth = want_depth
        self.want_normals = want_normals

        self.depth_scale = 1.0
        self.max_depth = None

        # Progress, written by the job thread and read by the main thread
        self.phase = "Scanning depth" if want_depth else "Converting"
        self.phase_done = 0
        self.cancel_requested = False

        self.error = None
        self._thread = None

    def run(self):
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            if self.want_depth:
                # One scale for the whole scene keeps depth consistent across views
                maxes = [m for m in self._map(pool, self._frame_max_depth) if m is not None]
                if not maxes:
                    raise ValueError("Depth passes contain no geometry")
                self.max_depth = max(maxes)
                self.depth_scale = 65535.0 / self.max_depth

            for folder, wanted in (
                (self.depths_dir, self.want_depth),
                (self.normals_dir, self.want_normals),
            ):
                if wanted:
                    os.makedirs(folder, exist_ok=True)

            # Rewriting the maps invalidates any earlier run's metadata (its
            # depth scale may differ), so don't leave it behind if this run
            # is cancelled or fails
            try:
                os.remove(self.metadata_path)
            except FileNotFoundError:
                pass

            self.phase = "Converting"
            self.phase_done = 0
            self._map(pool, self._convert_frame)

        self._write_metadata()

    def start(self):
        self._thread = threading.Thread(target=self._run_in_background, daemon=True)
        self._thread.start()

    def _run_in_background(self):
        try:
            self.run()
        except Exception as e:
            self.error = e

    @property
    def fraction(self):
        converted = self.phase_done / len(self.complete)
        if not self.want_depth:
            return converted
        if self.phase != "Converting":
            return _SCAN_SHARE * converted
        return _SCAN_SHARE + (1.0 - _SCAN_SHARE) * converted

    @property
    def finished(self):
        return self._thread is not None and not self._thread.is_alive()

    def cancel(self):
        """Stop after the frames in flight, and wait for them."""
        self.cancel_requested = True
        if self._thread is not None:
            self._thread.join()

    def _map(self, pool, fn):
        futures = [pool.submit(fn, frame_idx) for frame_idx in self.complete]
        results = []
        try:
            for future in as_completed(futures):
                if self.cancel_requested:
                    raise ConversionCancelled()
                results.append(future.result())
                self.phase_done += 1
        except BaseException:
            for future in futures:
                future.cancel()
            raise
        return results

    def _frame_max_depth(self, frame_idx):
        depth = read_exr(self.frames[frame_idx]["depth"], 1)[..., 0]
        return max_valid_depth(depth, self.clip_end)

    def _convert_frame(self, frame_idx):
        depth = read_exr(self.frames[frame_idx]["depth"], 1)[..., 0]
        normal = read_exr(self.frames[frame_idx]["normal"], 3)
        height, width = depth.shape
        fx, fy, _, _ = angle_based_intrinsics(self.camera, width, height)

        depth_png, normal_png = convert_frame(
            depth,
            normal,
            self.cam_to_world[frame_idx],
            (fx, fy, width / 2.0, height / 2.0),
            self.depth_scale,
            self.clip_end,
        )

        # Same naming as the rendered images/ and images.bin
        name = f"{frame_idx:04d}.png"
        if self.want_depth:
            write_png(os.path.join(self.depths_dir, name), depth_png)
        if self.want_normals:
            write_png(os.path.join(self.normals_dir, name), normal_png)

    def _write_metadata(self):
        meta = {"frames": len(self.complete)}
        if self.want_depth:
            meta["depth"] = {
                "folder": "depths",
                "format": "png_uint16",
                "type": "z_depth",
                "scale": self.depth_scale,
                "max_depth": self.max_depth,
                "invalid_value": 0,
                "note": "depth in Blender units = value / scale",
            }
        if self.want_normals:
            meta["normals"] = {
                "folder": "normals",
                "format": "png_uint8",
                "space": "camera_opencv",
                "orientation": "facing_camera",
                "encoding": "round(127.5 + 127.5 * n)",
                "invalid_value": [128, 128, 128],
            }
        with open(self.metadata_path, "w") as f:
            json.dump(meta, f, indent=2)


def conversion_progress():
    """(fraction, label) of the running conversion, or None."""
    job = _active_job
    if job is None:
        return None
    label = f"{job.phase} {job.phase_done}/{len(job.complete)}"
    return job.fraction, label


def _tag_panel_redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


class EXPORT_OT_geometry_maps(bpy.types.Operator):
    """Convert rendered depth/normal passes (EXR) into depths/ and normals/ PNGs"""

    bl_idname = "export.geometry_maps"
    bl_label = "Convert Rendered Passes"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return (
            _active_job is None
            and scene.camera
            and scene.output_folder.strip()
            and (scene.export_depth_maps or scene.export_normal_maps)
        )

    def _prepare(self, context):
        """Scan the passes and snapshot what the job needs, or report and
        return None."""
        scene = context.scene
        camera = scene.camera
        output_dir = bpy.path.abspath(scene.output_folder)
        passes_dir = os.path.join(output_dir, PASSES_FOLDER)

        frames = scan_pass_frames(passes_dir)
        complete = sorted(f for f, paths in frames.items() if len(paths) == 2)
        if not complete:
            self.report({"ERROR"}, f"No rendered depth/normal passes found in {passes_dir}")
            return None

        return ConversionJob(
            frames,
            complete,
            camera_matrices_for_frames(scene, camera, complete),
            camera.data,
            output_dir,
            scene.export_depth_maps,
            scene.export_normal_maps,
        )

    def _finish(self, job):
        if isinstance(job.error, ConversionCancelled):
            self.report(
                {"WARNING"},
                f"Conversion cancelled; maps in {job.output_dir} are incomplete",
            )
            return {"CANCELLED"}
        if job.error is not None:
            self.report({"ERROR"}, str(job.error))
            return {"CANCELLED"}

        written = " and ".join(
            label
            for label, wanted in (("depth", job.want_depth), ("normal", job.want_normals))
            if wanted
        )
        skipped = len(job.frames) - len(job.complete)
        skipped_msg = f" ({skipped} frame(s) missing a pass were skipped)" if skipped else ""
        self.report(
            {"WARNING" if skipped else "INFO"},
            f"Wrote {written} maps for {len(job.complete)} frames to {job.output_dir}{skipped_msg}",
        )
        return {"FINISHED"}

    def execute(self, context):
        # Blocking path, for scripts and background (-b) runs
        job = self._prepare(context)
        if job is None:
            return {"CANCELLED"}
        try:
            job.run()
        except (OSError, ValueError) as e:
            job.error = e
        return self._finish(job)

    def invoke(self, context, event):
        # Convert in the background so the UI stays responsive and can show
        # progress
        global _active_job
        job = self._prepare(context)
        if job is None:
            return {"CANCELLED"}
        _active_job = job
        job.start()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        self._workspace = context.workspace
        self._last_progress = None
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        job = _active_job
        if job.finished:
            self._cleanup(context)
            return self._finish(job)
        fraction, label = conversion_progress()
        if label != self._last_progress:
            self._last_progress = label
            self._workspace.status_text_set(
                f"Gauss Cannon depth/normal maps: {label} ({fraction:.0%})"
            )
            _tag_panel_redraw(context)
        return {"PASS_THROUGH"}

    def cancel(self, context):
        # Blender is quitting or loading another file
        _active_job.cancel()
        self._cleanup(context)

    def _cleanup(self, context):
        global _active_job
        _active_job = None
        context.window_manager.event_timer_remove(self._timer)
        self._workspace.status_text_set(None)
        _tag_panel_redraw(context)


class EXPORT_OT_geometry_maps_cancel(bpy.types.Operator):
    """Stop converting depth/normal passes after the frames in progress"""

    bl_idname = "export.geometry_maps_cancel"
    bl_label = "Cancel Conversion"
    bl_options = {"INTERNAL"}

    @classmethod
    def poll(cls, context):
        return _active_job is not None and not _active_job.cancel_requested

    def execute(self, context):
        _active_job.cancel_requested = True
        return {"FINISHED"}
