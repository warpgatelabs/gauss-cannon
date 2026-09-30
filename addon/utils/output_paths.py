import os
import bpy
from bpy.app.handlers import persistent


def to_blend_relative(path, blend_path=None):
    """
    Express an absolute path relative to the .blend ("//...") so the file
    renders correctly on a render farm.

    Returns ``path`` unchanged when it is already relative, when there is no
    saved .blend to be relative to, or when no relative path exists (Windows:
    different drive).

    Args:
        path: Absolute path to convert
        blend_path: .blend the result is relative to; defaults to the open file
    """
    if not path or path.startswith("//") or not os.path.isabs(path):
        return path
    blend_path = blend_path or bpy.data.filepath
    if not blend_path:
        return path
    try:
        rel = bpy.path.relpath(path, start=os.path.dirname(blend_path))
    except ValueError:
        return path
    # relpath drops the trailing separator, which Blender needs to treat the
    # render path as a directory rather than a filename prefix.
    if path.endswith(("/", "\\")) and not rel.endswith(("/", "\\")):
        rel += os.sep
    return rel


def images_render_path(scene, blend_path=None):
    """Render output path for the images/ subfolder of the output folder."""
    return to_blend_relative(
        os.path.join(scene.output_folder, "images", ""), blend_path
    )


def sync_render_outputs(scene, blend_path=None):
    """Point the scene's render output at <output_folder>/images/."""
    scene.render.filepath = images_render_path(scene, blend_path)


def _renders_to_images_folder(scene):
    """True if the render output currently resolves to our images/ folder, so
    re-expressing it is safe and a user's custom render path is left alone."""
    current = bpy.path.abspath(scene.render.filepath)
    target = bpy.path.abspath(os.path.join(scene.output_folder, "images", ""))
    return os.path.normcase(os.path.normpath(current)) == os.path.normcase(
        os.path.normpath(target)
    )


# Scenes whose render path was rewritten in save_pre, re-synced in save_post
_synced_on_save = []


@persistent
def on_save_pre(filepath="", *args):
    """Make render paths relative to the .blend being written, including its
    first save and Save As, so the saved file works on a render farm."""
    _synced_on_save.clear()
    if not isinstance(filepath, str) or not filepath:
        return
    for scene in bpy.data.scenes:
        if scene.output_folder.strip() and _renders_to_images_folder(scene):
            sync_render_outputs(scene, blend_path=filepath)
            _synced_on_save.append(scene.name)


@persistent
def on_save_post(*args):
    """Save Copy leaves the session on the original .blend, so re-derive the
    paths against it; for a regular save this is a no-op."""
    for name in _synced_on_save:
        scene = bpy.data.scenes.get(name)
        if scene is not None:
            sync_render_outputs(scene)
    _synced_on_save.clear()


def register_handlers():
    if on_save_pre not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(on_save_pre)
    if on_save_post not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(on_save_post)


def unregister_handlers():
    if on_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(on_save_pre)
    if on_save_post in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(on_save_post)
