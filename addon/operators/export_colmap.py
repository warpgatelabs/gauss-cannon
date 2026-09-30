import bpy
import os
import numpy as np
from ..utils.camera_eval import (
    angle_based_intrinsics,
    camera_matrices_for_frames,
    iter_action_fcurves,
)
from ..utils.colmap import (
    SPARSE_FOLDER,
    colmap_pose,
    write_cameras_bin,
    write_images_bin,
    write_points3d_bin,
)
from ..utils.output_paths import render_image_extension


def pinhole_params(cam_data, width, height):
    """COLMAP PINHOLE parameters (fx, fy, cx, cy) for the rendered image size."""
    fx, fy, _, _ = angle_based_intrinsics(cam_data, width, height)
    return (fx, fy, width / 2.0, height / 2.0)


class EXPORT_OT_colmap(bpy.types.Operator):
    """Export cameras as a COLMAP sparse model (sparse/0/*.bin)"""

    bl_idname = "export.colmap"
    bl_label = "Export COLMAP Model"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return (
            context.scene.camera
            and context.scene.frame_end >= context.scene.frame_start
            and context.scene.output_folder.strip()
        )

    def execute(self, context):
        scene = context.scene
        camera = scene.camera
        render = scene.render

        # Same frames and file names Render Animation produces
        frames = list(range(scene.frame_start, scene.frame_end + 1, scene.frame_step))
        width = render.resolution_x * render.resolution_percentage // 100
        height = render.resolution_y * render.resolution_percentage // 100
        ext = render_image_extension(scene)

        if any(True for _ in iter_action_fcurves(camera.data.animation_data)):
            # Animated lens/sensor: evaluate intrinsics per frame
            orig_frame = scene.frame_current
            matrices, intrinsics = {}, {}
            for frame_idx in frames:
                scene.frame_set(frame_idx)
                matrices[frame_idx] = camera.matrix_world.copy()
                intrinsics[frame_idx] = pinhole_params(camera.data, width, height)
            scene.frame_set(orig_frame)
        else:
            matrices = camera_matrices_for_frames(scene, camera, frames)
            params = pinhole_params(camera.data, width, height)
            intrinsics = dict.fromkeys(frames, params)

        # One COLMAP camera per distinct set of intrinsics (usually just one)
        cameras = []
        camera_ids = {}
        images = []
        for image_id, frame_idx in enumerate(frames, start=1):
            params = intrinsics[frame_idx]
            key = tuple(round(p, 6) for p in params)
            if key not in camera_ids:
                camera_ids[key] = len(camera_ids) + 1
                cameras.append((camera_ids[key], width, height, params))
            qvec, tvec = colmap_pose(matrices[frame_idx])
            images.append((image_id, qvec, tvec, camera_ids[key], f"{frame_idx:04d}{ext}"))

        sparse_dir = os.path.join(bpy.path.abspath(scene.output_folder), SPARSE_FOLDER)
        os.makedirs(sparse_dir, exist_ok=True)
        write_cameras_bin(os.path.join(sparse_dir, "cameras.bin"), cameras)
        write_images_bin(os.path.join(sparse_dir, "images.bin"), images)

        # Keep a model valid before the point cloud exists, without clobbering
        # points written by Generate Point Cloud
        points_path = os.path.join(sparse_dir, "points3D.bin")
        if not os.path.exists(points_path):
            write_points3d_bin(points_path, np.empty((0, 3)), np.empty((0, 3)))

        if ext == ".exr":
            self.report(
                {"WARNING"},
                f"Exported {len(images)} images to {sparse_dir}, but most COLMAP trainers can't read EXR frames",
            )
        else:
            self.report(
                {"INFO"},
                f"Exported {len(images)} images, {len(cameras)} camera(s) to {sparse_dir}",
            )
        return {"FINISHED"}
