import numpy as np


def write_ply_header(num_points):
    """Generate PLY file header for colored point cloud"""
    return f"""ply
format binary_little_endian 1.0
element vertex {num_points}
property float x
property float y
property float z
property uchar red
property uchar green
property uchar blue
end_header
"""


def write_ply_bulk(filepath, points, colors):
    """
    Write an entire colored point cloud to PLY in a single bulk operation.

    ``points`` and ``colors`` are numpy arrays of shape ``(N, 3)``. Color
    quantization is vectorized; the binary body is laid out into a structured
    array (12-byte position + 3-byte RGB per record, matching the PLY spec
    exactly) and written with one ``tofile`` call — significantly faster
    than per-point writes for large clouds.

    Args:
        filepath: Output .ply path
        points: (N, 3) numpy array of XYZ in Blender's Z-up world space, the
                same frame as the COLMAP model
        colors: (N, 3) numpy array of RGB in 0..1 range
    """
    num_points = points.shape[0]
    header = write_ply_header(num_points).encode("ascii")
    out_points = points.astype(np.float32, copy=False)

    rgb = np.clip(colors * 255.0, 0.0, 255.0).astype(np.uint8)

    record_dtype = np.dtype([("pos", "<f4", 3), ("rgb", "u1", 3)])
    records = np.empty(num_points, dtype=record_dtype)
    records["pos"] = out_points
    records["rgb"] = rgb

    with open(filepath, "wb") as f:
        f.write(header)
        records.tofile(f)