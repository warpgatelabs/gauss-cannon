import bpy
import os
import json
import numpy as np
from ..utils.camera_eval import angle_based_intrinsics, camera_matrices_for_frames
from ..utils.compositor_passes import PASSES_FOLDER
from ..utils.geometry_maps import (
    convert_frame,
    max_valid_depth,
    read_exr,
    scan_pass_frames,
    write_png,
)


class EXPORT_OT_geometry_maps(bpy.types.Operator):
    """Convert rendered depth/normal passes (EXR) into depths/ and normals/ PNGs"""

    bl_idname = "export.geometry_maps"
    bl_label = "Convert Depth/Normal Passes"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        return (
            scene.camera
            and scene.output_folder.strip()
            and (scene.export_depth_maps or scene.export_normal_maps)
        )

    def execute(self, context):
        scene = context.scene
        camera = scene.camera
        output_dir = bpy.path.abspath(scene.output_folder)
        passes_dir = os.path.join(output_dir, PASSES_FOLDER)

        frames = scan_pass_frames(passes_dir)
        complete = sorted(f for f, paths in frames.items() if len(paths) == 2)
        if not complete:
            self.report({"ERROR"}, f"No rendered depth/normal passes found in {passes_dir}")
            return {"CANCELLED"}

        cam_data = camera.data
        clip_end = cam_data.clip_end
        want_depth = scene.export_depth_maps
        want_normals = scene.export_normal_maps

        try:
            # One scale for the whole scene keeps depth consistent across views
            depth_scale = 1.0
            max_depth = None
            if want_depth:
                for frame_idx in complete:
                    depth = read_exr(frames[frame_idx]["depth"], 1)[..., 0]
                    frame_max = max_valid_depth(depth, clip_end)
                    if frame_max is not None:
                        max_depth = frame_max if max_depth is None else max(max_depth, frame_max)
                if max_depth is None:
                    self.report({"ERROR"}, "Depth passes contain no geometry")
                    return {"CANCELLED"}
                depth_scale = 65535.0 / max_depth

            matrices = camera_matrices_for_frames(scene, camera, complete)

            depths_dir = os.path.join(output_dir, "depths")
            normals_dir = os.path.join(output_dir, "normals")
            for folder, wanted in ((depths_dir, want_depth), (normals_dir, want_normals)):
                if wanted:
                    os.makedirs(folder, exist_ok=True)

            wm = context.window_manager
            wm.progress_begin(0, len(complete))
            try:
                for i, frame_idx in enumerate(complete):
                    depth = read_exr(frames[frame_idx]["depth"], 1)[..., 0]
                    normal = read_exr(frames[frame_idx]["normal"], 3)
                    height, width = depth.shape
                    fx, fy, _, _ = angle_based_intrinsics(cam_data, width, height)
                    cam_to_world = np.array(matrices[frame_idx].to_3x3().normalized())

                    depth_png, normal_png = convert_frame(
                        depth,
                        normal,
                        cam_to_world,
                        (fx, fy, width / 2.0, height / 2.0),
                        depth_scale,
                        clip_end,
                    )

                    # Same naming as the rendered images/ and transforms.json
                    name = f"{frame_idx:04d}.png"
                    if want_depth:
                        write_png(os.path.join(depths_dir, name), depth_png)
                    if want_normals:
                        write_png(os.path.join(normals_dir, name), normal_png)
                    wm.progress_update(i + 1)
            finally:
                wm.progress_end()
        except OSError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}

        meta = {"frames": len(complete)}
        if want_depth:
            meta["depth"] = {
                "folder": "depths",
                "format": "png_uint16",
                "type": "z_depth",
                "scale": depth_scale,
                "max_depth": max_depth,
                "invalid_value": 0,
                "note": "depth in Blender units = value / scale",
            }
        if want_normals:
            meta["normals"] = {
                "folder": "normals",
                "format": "png_uint8",
                "space": "camera_opencv",
                "orientation": "facing_camera",
                "encoding": "round(127.5 + 127.5 * n)",
                "invalid_value": [128, 128, 128],
            }
        with open(os.path.join(output_dir, "geometry_maps.json"), "w") as f:
            json.dump(meta, f, indent=2)

        written = " and ".join(
            label for label, wanted in (("depth", want_depth), ("normal", want_normals)) if wanted
        )
        skipped = len(frames) - len(complete)
        skipped_msg = f" ({skipped} frame(s) missing a pass were skipped)" if skipped else ""
        self.report(
            {"WARNING" if skipped else "INFO"},
            f"Wrote {written} maps for {len(complete)} frames to {output_dir}{skipped_msg}",
        )
        return {"FINISHED"}
