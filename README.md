![Gauss Cannon Logo](gauss-cannon-logo.webp)

> A powerful Blender add-on for Gaussian Splatting workflows. Generate COLMAP camera models and point clouds with ease!

[![Blender Version](https://img.shields.io/badge/Blender-5.0.0%2B-orange.svg)](https://www.blender.org/)
[![License](https://img.shields.io/badge/License-GPL_v3.0-blue.svg)](LICENSE)

![Interface Screenshot](gauss-cannon-screenshot.webp)

# Overview

**Gauss Cannon** is a comprehensive Blender add-on that streamlines the creation of camera paths and point clouds for Gaussian Splatting and photogrammetry workflows. It provides an intuitive interface for defining camera positions based on mesh faces and exports data in formats compatible with popular 3D reconstruction pipelines.

Created/Maintained by [Arash Keshmirian](https://github.com/keshmirian)

# Features

## Camera Path Generation
- **Helper Mesh System**: Use any mesh object as a template for camera positions
- **Face-Based Camera Placement**: Automatically generates camera keyframes at each face center
- **Smart Camera Orientation**: Cameras face opposite to face normals for optimal coverage
- **Interior Camera Detection**: Option to skip cameras detected inside scene meshes using ray casting
- **Near Clipping Protection**: Automatically skips cameras too close to geometry

## Export Capabilities
- **COLMAP Sparse Model**: Exports a binary COLMAP model (`sparse/0/*.bin`), which LichtFeld Studio, Brush, Postshot and other COLMAP-based trainers load directly
- **Camera Parameters**: Pinhole intrinsics at the rendered image size and a pose for every rendered frame
- **One Coordinate Frame**: Cameras and points stay in Blender's world frame, so no up-axis settings are needed

## Point Cloud Generation
- **Ray-Traced Point Clouds**: Converts selected meshes to accurately-colored PLY point clouds
- **GPU Acceleration**: Fast BVH-accelerated ray casting for improved performance
- **Multi-Frame Sampling**: Generates dense point clouds from multiple camera views
- **Stride Control**: Use every Nth frame for faster generation with fewer points
- **Color Preservation**: Captures rendered colors including lighting and materials
- **Ray Density Control**: Adjustable NxN ray grid per frame (4-1024)

## Render Animation
- **Integrated Rendering**: Render animation directly from the Gauss Cannon panel
- **Engine Selection**: Choose render engine with Cycles-specific device and persistent data options
- **Native Render Window**: Opens Blender's render progress window with ESC-to-cancel
- **Render Farm Ready**: The render output path is stored relative to the saved .blend, so farm nodes write frames to the same `images/` folder
- **Depth & Normal Maps**: Optional exact depth and camera-space normal maps for depth/normal-supervised training in LichtFeld Studio and Spirula Studio

## User Interface
- **Step-by-Step Workflow**: Collapsible Steps 1–4 guide you through the full pipeline
- **Unified Output Folder**: Single folder for all exports (`sparse/0/`, `pointcloud.ply`, `images/`)
- **Integrated Panel**: Clean UI in the 3D viewport's N-panel under "Gauss Cannon" tab
- **Real-time Feedback**: Shows face counts, camera positions, and selected objects
- **Visual Status Indicators**: Icons show mesh visibility and selection status

# Requirements

- **Blender**: 5.0.0 or higher

# Installation

1. Download the latest release from [GitHub Releases](https://github.com/keshmirian/gauss-cannon/releases)
2. In Blender, go to `Edit > Preferences > Get Extensions`
3. Click the dropdown menu in the top-right of the panel and choose `Install from Disk...`
4. Select the downloaded `.zip` file
5. Enable the add-on by checking the box next to "Gauss Cannon"

To uninstall or update later, find Gauss Cannon under `Edit > Preferences > Get Extensions` (or the Add-ons tab) and use the dropdown arrow next to the entry.

# Usage

### Basic Workflow

### 1. Setup Helper Meshes
```
1. Select mesh objects to use as camera position templates
2. Click "Add Selected" in the Gauss Cannon panel
3. Helper meshes are automatically hidden from render
4. View face counts and mesh status in the list
```

### 2. Configure Output
```
1. Set the output folder (all exports go here)
2. Optionally tick "Depth Maps" and/or "Normal Maps" under "Also Render"
```

### 3. Generate Camera Path (Step 1)
```
1. Configure focal length, resolution, and interior camera detection
2. Click "Generate Camera Path"
3. The active camera is keyframed at each face center (its existing
   animation is replaced)
4. Timeline and render settings are updated automatically
```

### 4. Generate Point Cloud (Step 2)
```
1. Select target meshes in the viewport (helper meshes are ignored)
2. Configure settings:
   - Ray Density: 4-1024 (default: 8), the side of an NxN ray grid per frame
   - Stride: Use every Nth frame (default: 1)
   - GPU acceleration: Enable for faster processing
3. Click "Generate Point Cloud"
4. pointcloud.ply and sparse/0/points3D.bin are saved to your output folder
```

The panel shows the rays per frame and the maximum number of points the
current settings can produce.

### 5. Render Animation (Step 3)
```
1. Choose render engine (Cycles/EEVEE)
2. For Cycles: select device and persistent data options
3. Click "Render Animation"
4. Frames are rendered to the images/ subfolder
```

To render on a farm instead, save the .blend and submit it. The output path is
stored relative to the .blend (e.g. `//output/images/`) whenever the file is saved,
as long as the output folder is on the same drive.

### 6. Export COLMAP Model (Step 4)
```
1. Click "Export COLMAP Model"
2. sparse/0/cameras.bin and images.bin are saved to your output folder
```

This is the last step because the model records the rendered image size and
file extension from the render settings. Re-run it if you change those.
Until "Generate Point Cloud" has run, the export leaves an empty
`sparse/0/points3D.bin` so the model is always loadable; it never overwrites
an existing one.

### 7. Depth & Normal Maps (optional)
```
1. Under "Output", tick "Depth Maps" and/or "Normal Maps"
2. Click "Render Animation": passes are saved as EXRs in _passes/, then
   converted to depths/ and normals/ PNGs when the render finishes
```

The pass setup is saved in the .blend (view-layer passes plus compositor File
Output nodes), so a render farm produces the `_passes/` EXRs without the add-on
installed. After the farm finishes, click "Convert Rendered Passes".
Unticking both removes the compositor nodes again.

For depth supervision in LichtFeld Studio, the point cloud also needs to be dense
enough: at least 1024 rays per frame (Ray Density 32+). The panel warns when it
isn't.

# Technical Details

## COLMAP Sparse Model
Written to `sparse/0/` in COLMAP's binary format, next to `images/`:
- **cameras.bin**: `PINHOLE` model (`fx, fy, cx, cy`) at the rendered image size, including the render resolution percentage. There is one camera unless the lens is animated.
- **images.bin**: world-to-camera poses with OpenCV camera axes (x right, y down, z forward), one per rendered frame (respecting frame step), named like the rendered images (`0001.png`). There are no 2D observations.
- **points3D.bin**: the generated point cloud with empty tracks, which trainers accept because they only read positions and colors.
- **Coordinate System**: Blender's world frame (Z-up) for both cameras and points. COLMAP has no fixed up axis, and trainers orient the scene themselves.

## Point Cloud PLY Format
`pointcloud.ply` holds the same points as `points3D.bin`:
- **Format**: Binary little-endian PLY
- **Properties**: x, y, z positions + RGB colors
- **Coordinate System**: Blender's world frame (Z-up), matching the COLMAP model
- **Color Range**: 0-255 per channel

## Depth & Normal Map Format
Written next to `images/` with matching filenames, where both LichtFeld Studio and
Spirula Studio look for them:

| | `depths/0001.png` | `normals/0001.png` |
|---|---|---|
| Format | 1-channel 16-bit PNG | 3-channel 8-bit PNG |
| Values | Planar z-depth × scale (one scale per scene) | Camera-space OpenCV axes (x right, y down, z forward), facing the camera, `round(127.5 + 127.5·n)` |
| Invalid / background | `0` | `(128, 128, 128)` |

`geometry_maps.json` records the depth scale (`depth = value / scale`, in Blender
units) and the encodings. Both trainers treat depth as scale-invariant, so the
scale only matters for your own tooling.

Enabling them in the trainers:
- **LichtFeld Studio**: `--use-depth-loss --use-normal-loss --normal-loss-space camera-opencv`.
  The depth loss is fitted to the initial point cloud, so export a dense
  `pointcloud.ply`. These losses are skipped with `--gut`.
- **Spirula Studio**: normals are used automatically; set `depth_supervision_weight`
  above 0 to use depth.

## Algorithm Details

### Interior Camera Detection
- Uses odd-even ray casting rule
- Counts mesh intersections along ray
- Odd count = inside mesh
- Excludes helper meshes from detection

### GPU Acceleration
- Utilizes Blender's BVH tree structures
- Batch ray processing for efficiency
- Falls back to CPU if GPU unavailable
- Up to 10x performance improvement

# Tips & Best Practices

## Performance Optimization
- Use low-poly meshes as helpers for faster processing. Icospheres work great.
- Enable GPU acceleration for point cloud generation
- Start with low ray density (8-16)
- Use stride to skip frames during point cloud generation
- Enable "Persistent Data" in the render animation step for faster Cycles rendering

## Quality Considerations
- Higher ray density = better quality but slower
- Helper face count - invalid cameras = camera count
- Interior detection may slow generation on complex scenes
- Helper meshes should encompass the target object

## Workflow Tips
- Plan camera coverage with simple helper geometry
- Use icospheres or cylinders for 360° coverage
- Preview camera path before exporting
- Test with small datasets first

# Troubleshooting

## Common Issues

**No cameras generated**
- Ensure helper meshes are added
- Check that meshes have faces (not just vertices/edges)
- Verify helper meshes are not deleted
- Verify cameras are not intersecting meshes

**GPU acceleration not working**
- Check Blender GPU compute settings
- Ensure compatible GPU drivers
- Falls back to CPU automatically

**Interior cameras still appearing**
- Enable "Skip Interior Cameras" option
- Check mesh normals are correct
- Ensure meshes are manifold (watertight)

# Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

# License

This project is licensed under the GPL v3.0 License - see the [LICENSE](LICENSE) file for details.

# Acknowledgments

- Blender Foundation for Blender and the amazing Blender Python API
- The Gaussian Splatting community for inspiration and feedback
- The creators of COLMAP, LichtFeld Studio, Brush and Postshot
- All contributors and users of Gauss Cannon

# Contact

Arash Keshmirian - [GitHub](https://github.com/keshmirian)

Project Link: [https://github.com/keshmirian/gauss-cannon](https://github.com/keshmirian/gauss-cannon)

---

<p>Made with ❤️ for the 3D reconstruction community!</p>