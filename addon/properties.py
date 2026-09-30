import bpy
from .utils.output_paths import sync_pass_outputs


class HelperMeshItem(bpy.types.PropertyGroup):
    """Property group to store helper mesh reference"""
    mesh_object: bpy.props.PointerProperty(
        name="Mesh Object",
        type=bpy.types.Object,
        poll=lambda self, obj: obj.type == "MESH",
    )
    name: bpy.props.StringProperty(name="Name")


def _update_pass_outputs(self, context):
    """Keep the compositor depth/normal outputs in step with the settings."""
    sync_pass_outputs(self)


def register_properties():
    """Register all scene properties"""
    # Helper mesh collection
    bpy.types.Scene.helper_meshes = bpy.props.CollectionProperty(type=HelperMeshItem)
    bpy.types.Scene.helper_mesh_index = bpy.props.IntProperty(default=0)

    # Shared output folder
    bpy.types.Scene.output_folder = bpy.props.StringProperty(
        name="Output Folder",
        description="Folder for all exports (transforms.json or sparse/0/, pointcloud.ply, images/)",
        default="",
        subtype="DIR_PATH",
        update=_update_pass_outputs,
    )

    bpy.types.Scene.output_width = bpy.props.IntProperty(
        name="Width",
        description="Render width in pixels",
        default=1024,
        min=256,
        max=4096,
    )

    bpy.types.Scene.output_height = bpy.props.IntProperty(
        name="Height",
        description="Render height in pixels",
        default=1024,
        min=256,
        max=4096,
    )

    bpy.types.Scene.camera_focal_length = bpy.props.FloatProperty(
        name="Focal Length (mm)",
        description="Camera lens focal length",
        default=35.0,
        min=1.0,
        max=500.0,
        precision=1,
    )

    bpy.types.Scene.export_mode = bpy.props.EnumProperty(
        name="Export Mode",
        description="Choose export format compatibility",
        items=[
            ("LICHTFELD", "LichtFeld Studio", "Compatible with LichtFeld Studio"),
            ("POSTSHOT", "Postshot", "Compatible with Postshot"),
            ("BRUSH", "Brush", "Compatible with Brush"),
            ("COLMAP", "COLMAP", "COLMAP binary sparse model (sparse/0/*.bin), read by most Gaussian Splatting trainers"),
        ],
        default="LICHTFELD",
    )

    bpy.types.Scene.skip_interior_cameras = bpy.props.BoolProperty(
        name="Skip Interior Cameras",
        description="Skip camera positions detected to be inside meshes using ray casting",
        default=False,
    )

    bpy.types.Scene.coordinate_system = bpy.props.EnumProperty(
        name="Coordinate System",
        description="Output coordinate system for transforms and point cloud",
        items=[
            ("Y_UP", "Y-up", "Y-up coordinate system (Standard for most applications)"),
            ("Z_UP", "Z-up", "Z-up coordinate system (Blender native)")
        ],
        default="Y_UP",
    )

    # Point cloud export settings
    bpy.types.Scene.pointcloud_resolution = bpy.props.IntProperty(
        name="Ray Density",
        description="NxN grid of rays cast per camera frame for point cloud generation",
        default=8,
        min=4,
        max=1024,
    )

    bpy.types.Scene.pointcloud_stride = bpy.props.IntProperty(
        name="Stride",
        description="Use every Nth frame for point cloud generation (higher values = faster, fewer points)",
        default=1,
        min=1,
        max=100,
    )

    bpy.types.Scene.use_gpu_acceleration = bpy.props.BoolProperty(
        name="Use GPU Acceleration",
        description="Use GPU-accelerated BVH for ray casting (much faster)",
        default=True,
    )

    # Depth/normal map export (rendered as compositor passes, then converted)
    bpy.types.Scene.export_depth_maps = bpy.props.BoolProperty(
        name="Depth Maps",
        description="Also render depth maps (16-bit PNG in depths/) for depth-supervised training",
        default=False,
        update=_update_pass_outputs,
    )

    bpy.types.Scene.export_normal_maps = bpy.props.BoolProperty(
        name="Normal Maps",
        description="Also render camera-space normal maps (PNG in normals/) for normal-supervised training",
        default=False,
        update=_update_pass_outputs,
    )


def unregister_properties():
    """Unregister all scene properties"""
    del bpy.types.Scene.helper_meshes
    del bpy.types.Scene.helper_mesh_index
    del bpy.types.Scene.output_folder
    del bpy.types.Scene.output_width
    del bpy.types.Scene.output_height
    del bpy.types.Scene.camera_focal_length
    del bpy.types.Scene.export_mode
    del bpy.types.Scene.pointcloud_resolution
    del bpy.types.Scene.use_gpu_acceleration
    del bpy.types.Scene.pointcloud_stride
    del bpy.types.Scene.skip_interior_cameras
    del bpy.types.Scene.coordinate_system
    del bpy.types.Scene.export_depth_maps
    del bpy.types.Scene.export_normal_maps