import bpy

# Import property classes and registration functions
from .properties import HelperMeshItem, register_properties, unregister_properties
from .utils.output_paths import register_handlers, unregister_handlers

# Import all operators
from .operators import (
    MESH_OT_add_helper,
    MESH_OT_remove_helper,
    MESH_OT_clear_helpers,
    CAMERA_OT_generate_from_faces,
    RENDER_OT_animation_to_export,
    EXPORT_OT_colmap,
    EXPORT_OT_pointcloud_ply,
    EXPORT_OT_geometry_maps,
    EXPORT_OT_geometry_maps_cancel,
)

# Import UI panels
from .ui import VIEW3D_PT_helper_mesh_panel

# Classes to register
classes = [
    # Property groups
    HelperMeshItem,

    # Operators
    MESH_OT_add_helper,
    MESH_OT_remove_helper,
    MESH_OT_clear_helpers,
    CAMERA_OT_generate_from_faces,
    RENDER_OT_animation_to_export,
    EXPORT_OT_colmap,
    EXPORT_OT_pointcloud_ply,
    EXPORT_OT_geometry_maps,
    EXPORT_OT_geometry_maps_cancel,

    # UI panels
    VIEW3D_PT_helper_mesh_panel,
]


def register():
    """Register all addon classes and properties"""
    # Register all classes
    for cls in classes:
        bpy.utils.register_class(cls)

    # Register scene properties
    register_properties()

    # Keep render output paths relative to the .blend on save (render farms)
    register_handlers()


def unregister():
    """Unregister all addon classes and properties"""
    unregister_handlers()

    # Unregister scene properties first
    unregister_properties()

    # Unregister all classes in reverse order
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()