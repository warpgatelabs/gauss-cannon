"""
COLMAP sparse model writer (binary: cameras.bin, images.bin, points3D.bin).

Layout matches COLMAP's read_write_model.py. Poses are world-to-camera with
OpenCV camera axes (x right, y down, z forward), in Blender's world frame.
COLMAP has no fixed up axis, and cameras and points must share one frame.
"""
import os
import struct
import numpy as np
from mathutils import Matrix


# Where COLMAP-based trainers look for the model, relative to the dataset root
SPARSE_FOLDER = os.path.join("sparse", "0")

CAMERA_MODEL_PINHOLE = 1

# Blender/OpenGL camera axes (looks down -Z, Y up) -> OpenCV (looks down +Z, Y down)
_GL_TO_CV = Matrix.Diagonal((1.0, -1.0, -1.0, 1.0))

# points3D.bin record with an empty track: 51 bytes, no padding
_POINT_RECORD = np.dtype(
    [
        ("id", "<u8"),
        ("xyz", "<f8", 3),
        ("rgb", "u1", 3),
        ("error", "<f8"),
        ("track_length", "<u8"),
    ]
)


def colmap_pose(matrix_world):
    """
    Blender camera world matrix -> COLMAP world-to-camera pose.

    Returns:
        tuple: ((qw, qx, qy, qz), (tx, ty, tz))
    """
    loc, rot, _scale = matrix_world.decompose()
    cam_to_world = Matrix.LocRotScale(loc, rot, None) @ _GL_TO_CV
    world_to_cam = cam_to_world.inverted()
    q = world_to_cam.to_quaternion().normalized()
    return (q.w, q.x, q.y, q.z), tuple(world_to_cam.translation)


def write_cameras_bin(path, cameras):
    """
    Args:
        cameras: list of (camera_id, width, height, (fx, fy, cx, cy))
    """
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(cameras)))
        for camera_id, width, height, params in cameras:
            f.write(struct.pack("<IiQQ", camera_id, CAMERA_MODEL_PINHOLE, width, height))
            f.write(struct.pack("<4d", *params))


def write_images_bin(path, images):
    """
    Args:
        images: list of (image_id, (qw, qx, qy, qz), (tx, ty, tz), camera_id, name),
                name relative to the images/ folder
    """
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", len(images)))
        for image_id, qvec, tvec, camera_id, name in images:
            f.write(struct.pack("<I4d3dI", image_id, *qvec, *tvec, camera_id))
            f.write(name.encode("utf-8") + b"\x00")
            # No 2D observations: trainers only use the poses and 3D points
            f.write(struct.pack("<Q", 0))


def write_points3d_bin(path, points, colors):
    """
    Write points with empty tracks, which 3DGS trainers accept (they only
    read xyz and rgb).

    Args:
        points: (N, 3) array in Blender world space
        colors: (N, 3) array of RGB in 0..1 range
    """
    count = len(points)
    records = np.empty(count, dtype=_POINT_RECORD)
    records["id"] = np.arange(1, count + 1, dtype=np.uint64)
    records["xyz"] = points
    # Same quantization as write_ply_bulk
    records["rgb"] = np.clip(colors * 255.0, 0.0, 255.0).astype(np.uint8)
    records["error"] = 0.0
    records["track_length"] = 0
    with open(path, "wb") as f:
        f.write(struct.pack("<Q", count))
        records.tofile(f)
