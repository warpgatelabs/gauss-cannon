import bpy
from ..operators.export_geometry_maps import conversion_progress
from ..operators.export_pointcloud import scannable_meshes


VERSION = "1.3.0"

# Below this many rays per frame the point cloud is too sparse for depth
# priors (LichtFeld Studio skips depth supervision for cameras with too few
# projected points)
MIN_RAYS_PER_FRAME_FOR_DEPTH = 1024


def _plural(count, noun):
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _helper_face_count(item):
    """Face count of a helper mesh, or None if its object is unusable."""
    try:
        obj = item.mesh_object
        if obj and obj.type == "MESH" and obj.data:
            return len(obj.data.polygons)
    except (AttributeError, ReferenceError):
        pass
    return None


class VIEW3D_PT_helper_mesh_panel(bpy.types.Panel):
    """Creates a Panel in the 3D viewport N-panel"""

    bl_label = f"Gauss Cannon v{VERSION}"
    bl_idname = "VIEW3D_PT_helper_mesh_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Gauss Cannon"

    def draw(self, context):
        layout = self.layout
        # Blender's property-panel style: label column on the left, values on
        # the right, no animation decorators
        layout.use_property_split = True
        layout.use_property_decorate = False
        scene = context.scene

        self.draw_helper_meshes(layout, scene)
        self.draw_output(layout, scene)

        if not scene.output_folder.strip():
            layout.label(text="Set an output folder to continue", icon="INFO")
            return

        # COLMAP export comes last: it records the image file extension and
        # resolution percentage from the render settings, so it must run
        # after those are final
        self.draw_camera_path(layout, scene)
        self.draw_point_cloud(layout, context)
        self.draw_render(layout, scene)
        self.draw_colmap(layout)

    def draw_helper_meshes(self, layout, scene):
        header, body = layout.panel("gauss_cannon_helper_meshes")
        items = scene.helper_meshes
        title = "Helper Meshes"
        if len(items) > 0:
            faces = sum(_helper_face_count(item) or 0 for item in items)
            # One label: two in a header split the width evenly and truncate
            title += f" ({_plural(faces, 'camera')})"
        header.label(text=title, icon="OUTLINER_OB_MESH")
        if body is None:
            return

        row = body.row(align=True)
        row.operator("mesh.add_helper", text="Add Selected", icon="ADD")
        row.operator("mesh.clear_helpers", text="Clear All", icon="TRASH")

        if len(items) == 0:
            col = body.column(align=True)
            col.label(text="One camera per face, looking in", icon="INFO")
            col.label(text="Select a mesh, then Add Selected")
            return

        col = body.column(align=True)
        for i, item in enumerate(items):
            row = col.row(align=True)
            if item.mesh_object is None:
                row.label(text=f"{item.name} (Missing)", icon="ERROR")
            else:
                face_count = _helper_face_count(item)
                if face_count is None:
                    row.label(text=f"{item.name} (Invalid)", icon="ERROR")
                else:
                    try:
                        visible = item.mesh_object.visible_get()
                    except (AttributeError, ReferenceError):
                        visible = True
                    icon = "OUTLINER_OB_MESH" if visible else "HIDE_ON"
                    row.label(text=f"{item.name} ({face_count})", icon=icon)
            op = row.operator("mesh.remove_helper", text="", icon="X")
            op.index = i

    def draw_output(self, layout, scene):
        header, body = layout.panel("gauss_cannon_output")
        header.label(text="Output", icon="FILE_FOLDER")
        if body is None:
            return

        body.prop(scene, "output_folder")

        # Same layout Blender uses for view layer passes: a heading with
        # independent checkboxes, so both can be on at once
        col = body.column(heading="Also Render", align=True)
        col.prop(scene, "export_depth_maps")
        col.prop(scene, "export_normal_maps")

    def draw_camera_path(self, layout, scene):
        header, body = layout.panel("gauss_cannon_camera_path")
        header.label(text="Step 1: Camera Path", icon="CAMERA_DATA")
        if body is None:
            return

        body.prop(scene, "camera_focal_length")
        col = body.column(align=True)
        col.prop(scene, "output_width", text="Resolution X")
        col.prop(scene, "output_height", text="Y")
        col = body.column(heading="Cameras")
        col.prop(scene, "skip_interior_cameras", text="Skip Interior")

        row = body.row()
        row.scale_y = 1.3
        row.operator("camera.generate_from_faces", text="Generate Camera Path", icon="CAMERA_DATA")

    def draw_point_cloud(self, layout, context):
        scene = context.scene
        header, body = layout.panel("gauss_cannon_point_cloud")
        header.label(text="Step 2: Point Cloud", icon="OUTLINER_OB_POINTCLOUD")
        if body is None:
            return

        col = body.column(align=True)
        col.prop(scene, "pointcloud_resolution")
        col.prop(scene, "pointcloud_stride")
        body.prop(scene, "use_gpu_acceleration", text="GPU Acceleration")

        # Ray Density is the side of an NxN grid, which is easy to misread
        rays_per_frame = scene.pointcloud_resolution ** 2
        frames = len(range(scene.frame_start, scene.frame_end + 1, scene.pointcloud_stride))
        col = body.column(align=True)
        col.label(text=f"{rays_per_frame:,} rays per frame", icon="INFO")
        col.label(text=f"Up to {rays_per_frame * frames:,} points")
        if scene.export_depth_maps and rays_per_frame < MIN_RAYS_PER_FRAME_FOR_DEPTH:
            col.label(text="Too sparse for depth priors", icon="ERROR")
            col.label(text="Use Ray Density 32+")

        row = body.row()
        row.scale_y = 1.3
        row.operator("export.pointcloud_ply", text="Generate Point Cloud", icon="OUTLINER_OB_POINTCLOUD")

        # Same filter as the operator, so the count never promises a run
        # the operator would refuse
        selected = scannable_meshes(context)
        if selected:
            body.label(text=f"{_plural(len(selected), 'mesh')} selected", icon="CHECKMARK")
        else:
            body.label(text="Select the meshes to scan", icon="INFO")

    def draw_render(self, layout, scene):
        header, body = layout.panel("gauss_cannon_render")
        header.label(text="Step 3: Render Animation", icon="RENDER_ANIMATION")
        if body is None:
            return

        body.prop(scene.render, "engine")
        if scene.render.engine == 'CYCLES':
            body.prop(scene.cycles, "device")
            body.prop(scene.render, "use_persistent_data")

        maps_enabled = scene.export_depth_maps or scene.export_normal_maps
        workbench_blocked = maps_enabled and scene.render.engine == "BLENDER_WORKBENCH"
        if workbench_blocked:
            body.label(text="Maps need Cycles or EEVEE", icon="ERROR")

        row = body.row()
        row.scale_y = 1.3
        row.enabled = not workbench_blocked
        row.operator("render.animation_to_export", text="Render Animation", icon="RENDER_ANIMATION")

        progress = conversion_progress()
        if progress is not None:
            fraction, label = progress
            row = body.row(align=True)
            row.progress(factor=fraction, type="BAR", text=label)
            row.operator("export.geometry_maps_cancel", text="", icon="X")
        elif maps_enabled:
            # Render Animation converts the passes itself; this is for
            # frames rendered elsewhere
            col = body.column(align=True)
            col.operator("export.geometry_maps", text="Convert Rendered Passes", icon="IMAGE_DATA")
            col.label(text="Only needed for farm renders", icon="INFO")

    def draw_colmap(self, layout):
        header, body = layout.panel("gauss_cannon_colmap")
        header.label(text="Step 4: Export COLMAP", icon="EXPORT")
        if body is None:
            return

        row = body.row()
        row.scale_y = 1.3
        row.operator("export.colmap", text="Export COLMAP Model", icon="FILE_3D")
