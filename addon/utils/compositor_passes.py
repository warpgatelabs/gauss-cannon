"""
Persistent depth/normal pass outputs in the scene's compositor.

The setup is stored in the .blend (view-layer passes plus File Output nodes
writing float EXRs), so a render farm rendering the file with `blender -b -a`
produces the passes without any add-on code running. The EXRs are converted
to the trainer-ready PNGs afterwards (see geometry_maps.py).
"""
import os
import bpy


# Subfolder of the output folder holding the raw EXR passes. Kept away from
# depth/ and normal/, which LichtFeld Studio scans for priors at the root.
PASSES_FOLDER = "_passes"

# Render Layers output name -> subfolder (and File Output item name)
PASS_OUTPUTS = {"Depth": "depth", "Normal": "normal"}

_NODE_PREFIX = "Gauss Cannon"
_RLAYERS_NODE = f"{_NODE_PREFIX} Render Layers"
_GROUP_NAME = "Gauss Cannon Passes"
# ID property tagging a compositor group created by us (safe to delete)
_OWNED_GROUP_KEY = "gauss_cannon_owned"
# Scene ID property recording pass toggles before we enabled them
_PRIOR_PASSES_KEY = "gauss_cannon_prior_passes"


def maps_enabled(scene):
    return scene.export_depth_maps or scene.export_normal_maps


def _file_output_name(pass_name):
    return f"{_NODE_PREFIX} {pass_name}"


def _target_view_layer(scene):
    context_layer = getattr(bpy.context, "view_layer", None)
    if bpy.context.scene == scene and context_layer is not None:
        return context_layer
    return scene.view_layers[0]


def _enable_passes(scene, view_layer):
    if _PRIOR_PASSES_KEY not in scene:
        scene[_PRIOR_PASSES_KEY] = {
            "view_layer": view_layer.name,
            "use_pass_z": view_layer.use_pass_z,
            "use_pass_normal": view_layer.use_pass_normal,
        }
    # Always both: depth masking relies on the normal pass
    view_layer.use_pass_z = True
    view_layer.use_pass_normal = True


def _restore_passes(scene):
    prior = scene.get(_PRIOR_PASSES_KEY)
    if prior is None:
        return
    view_layer = scene.view_layers.get(prior["view_layer"])
    if view_layer is not None:
        view_layer.use_pass_z = bool(prior["use_pass_z"])
        view_layer.use_pass_normal = bool(prior["use_pass_normal"])
    del scene[_PRIOR_PASSES_KEY]


def apply(scene, passes_dir):
    """
    Create or update the pass outputs when depth or normal maps are enabled,
    and remove them otherwise.

    Args:
        scene: Scene to configure
        passes_dir: Render path for the passes folder, ideally .blend-relative
                    ("//output/_passes/")
    """
    if not maps_enabled(scene):
        remove(scene)
        return
    if not scene.output_folder.strip():
        return

    tree = scene.compositing_node_group
    if tree is None:
        tree = bpy.data.node_groups.new(_GROUP_NAME, "CompositorNodeTree")
        tree[_OWNED_GROUP_KEY] = True
        scene.compositing_node_group = tree

    rlayers = tree.nodes.get(_RLAYERS_NODE)
    if rlayers is None:
        view_layer = _target_view_layer(scene)
        _enable_passes(scene, view_layer)
        rlayers = tree.nodes.new("CompositorNodeRLayers")
        rlayers.name = _RLAYERS_NODE
        rlayers.label = _NODE_PREFIX
        rlayers.scene = scene
        rlayers.layer = view_layer.name
        rlayers.location = (-400, -600)
    else:
        view_layer = scene.view_layers.get(rlayers.layer) or _target_view_layer(scene)
        _enable_passes(scene, view_layer)

    for i, (pass_name, subfolder) in enumerate(PASS_OUTPUTS.items()):
        node = tree.nodes.get(_file_output_name(pass_name))
        if node is None:
            node = tree.nodes.new("CompositorNodeOutputFile")
            node.name = _file_output_name(pass_name)
            node.label = f"{_NODE_PREFIX} {subfolder}"
            node.location = (0, -600 - 200 * i)
            node.format.media_type = "IMAGE"
            node.format.file_format = "OPEN_EXR"
            node.format.color_depth = "32"
            node.format.exr_codec = "ZIP"
            # Files are named <subfolder><frame>.exr, e.g. depth0001.exr
            node.file_name = ""
            socket_type = "FLOAT" if pass_name == "Depth" else "VECTOR"
            node.file_output_items.new(socket_type, subfolder)
        if not node.inputs[0].is_linked:
            tree.links.new(rlayers.outputs[pass_name], node.inputs[0])
        node.directory = os.path.join(passes_dir, subfolder, "")


def remove(scene):
    """Remove our nodes (and our group, if we created it) and restore passes."""
    tree = scene.compositing_node_group
    if tree is not None:
        for name in [_RLAYERS_NODE] + [_file_output_name(p) for p in PASS_OUTPUTS]:
            node = tree.nodes.get(name)
            if node is not None:
                tree.nodes.remove(node)
        if tree.get(_OWNED_GROUP_KEY) and len(tree.nodes) == 0:
            scene.compositing_node_group = None
            if tree.users == 0:
                bpy.data.node_groups.remove(tree)
    _restore_passes(scene)
