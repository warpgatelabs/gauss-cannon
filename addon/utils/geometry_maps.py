"""
Convert rendered depth/normal EXR passes into trainer-ready PNGs.

Output format (read by LichtFeld Studio and Spirula Studio):
- depths/NNNN.png: 1-channel uint16, planar z-depth * scale, 0 = invalid
- normals/NNNN.png: 3-channel uint8, camera-space OpenCV axes (x right,
  y down, z forward), facing the camera, round(127.5 + 127.5 * n), invalid =
  (128, 128, 128). Mid-grey decodes to a zero vector, which both trainers
  skip; black would decode to a valid normal in LichtFeld.
"""
import os
import re
import numpy as np
import OpenImageIO as oiio


_FRAME_RE = re.compile(r"(\d+)\.exr$", re.IGNORECASE)

# Blender's Z pass holds a far value on background pixels (1e10 in Cycles,
# about clip_end in EEVEE); treat anything this close to clip_end as empty.
_FAR_FRACTION = 0.999

# Normal pass samples averaged across a silhouette (Cycles anti-aliasing)
# shrink below unit length; skip those mixed pixels.
_MIN_NORMAL_LENGTH = 0.9

INVALID_NORMAL = 128


def scan_pass_frames(passes_dir, subfolders=("depth", "normal")):
    """
    Map frame numbers to pass EXRs, e.g. depth/depth0001.exr.

    Returns:
        dict: frame -> {subfolder: path}
    """
    frames = {}
    for subfolder in subfolders:
        folder = os.path.join(passes_dir, subfolder)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            match = _FRAME_RE.search(name)
            if match:
                frames.setdefault(int(match.group(1)), {})[subfolder] = os.path.join(folder, name)
    return frames


def read_exr(path, channels):
    """Read the first ``channels`` channels of an EXR as float32 (H, W, C),
    rows top-down."""
    inp = oiio.ImageInput.open(path)
    if inp is None:
        raise OSError(f"Cannot open {path}: {oiio.geterror()}")
    try:
        pixels = inp.read_image(format="float")
    finally:
        inp.close()
    if pixels is None:
        raise OSError(f"Cannot read {path}")
    return np.asarray(pixels, dtype=np.float32)[..., :channels]


def write_png(path, pixels):
    """Write a uint8 or uint16 (H, W) or (H, W, C) array as PNG with no color
    management."""
    height, width = pixels.shape[:2]
    channels = 1 if pixels.ndim == 2 else pixels.shape[2]
    fmt = oiio.UINT16 if pixels.dtype == np.uint16 else oiio.UINT8
    out = oiio.ImageOutput.create(path)
    if out is None:
        raise OSError(f"Cannot create {path}: {oiio.geterror()}")
    try:
        if not out.open(path, oiio.ImageSpec(width, height, channels, fmt)):
            raise OSError(f"Cannot open {path}: {out.geterror()}")
        if not out.write_image(pixels.reshape(height, width, channels)):
            raise OSError(f"Cannot write {path}: {out.geterror()}")
    finally:
        out.close()


def depth_valid_mask(depth, clip_end):
    with np.errstate(invalid="ignore"):
        return np.isfinite(depth) & (depth > 0.0) & (depth < _FAR_FRACTION * clip_end)


def max_valid_depth(depth, clip_end):
    """Largest valid depth in a frame, or None if the frame is empty."""
    valid = depth_valid_mask(depth, clip_end)
    return float(depth[valid].max()) if valid.any() else None


def convert_frame(depth, normal_world, cam_to_world, intrinsics, depth_scale, clip_end):
    """
    Encode one frame's passes.

    Args:
        depth: (H, W) planar z-depth from Blender's Z pass
        normal_world: (H, W, 3) world-space normals from Blender's Normal pass
        cam_to_world: (3, 3) camera-to-world rotation (Blender/OpenGL camera axes)
        intrinsics: (fx, fy, cx, cy) in pixels
        depth_scale: Multiplier mapping depth to uint16 values
        clip_end: Camera far clip, for detecting background

    Returns:
        tuple: (uint16 (H, W) depth PNG data, uint8 (H, W, 3) normal PNG data)
    """
    height, width = depth.shape
    lengths = np.linalg.norm(normal_world, axis=-1)
    valid = depth_valid_mask(depth, clip_end) & (lengths >= _MIN_NORMAL_LENGTH)

    depth_out = np.zeros((height, width), dtype=np.uint16)
    depth_out[valid] = np.clip(np.rint(depth[valid] * depth_scale), 1, 65535)

    # World -> camera (row vectors: n @ R == R.T @ n), then OpenGL -> OpenCV
    # camera axes by flipping y and z.
    normals = (normal_world @ np.asarray(cam_to_world, dtype=np.float32)) * np.array(
        [1.0, -1.0, -1.0], dtype=np.float32
    )
    normals[valid] /= lengths[valid, None]

    # Face the camera: flip any normal pointing along its pixel's view ray
    fx, fy, cx, cy = intrinsics
    ray_x = (np.arange(width, dtype=np.float32) + 0.5 - cx) / fx
    ray_y = (np.arange(height, dtype=np.float32) + 0.5 - cy) / fy
    facing_away = (
        normals[..., 0] * ray_x[None, :] + normals[..., 1] * ray_y[:, None] + normals[..., 2]
    ) > 0.0
    normals[facing_away] *= -1.0

    normal_out = np.clip(np.rint(127.5 + 127.5 * normals), 0, 255).astype(np.uint8)
    normal_out[~valid] = INVALID_NORMAL
    return depth_out, normal_out
