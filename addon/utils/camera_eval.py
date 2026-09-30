from mathutils import Matrix, Vector, Euler
import numpy as np


def iter_action_fcurves(animation_data):
    """
    Yield F-curves from animation_data.

    F-curves live in Channelbags inside Strips inside Layers (Slotted
    Actions), keyed by the animation_data's action_slot.
    """
    if not animation_data or not animation_data.action:
        return
    action = animation_data.action

    slot = getattr(animation_data, "action_slot", None)
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            cb = None
            if slot is not None and hasattr(strip, "channelbag"):
                try:
                    cb = strip.channelbag(slot)
                except Exception:
                    cb = None
            if cb is None:
                # No slot match — fall back to any channelbags on the strip
                for cb_alt in getattr(strip, "channelbags", []):
                    for fc in cb_alt.fcurves:
                        yield fc
                continue
            for fc in cb.fcurves:
                yield fc


def build_fast_path_evaluator(camera):
    """
    Build a frame -> world-matrix evaluator that bypasses scene.frame_set.

    Reads keyframe values directly from the camera's location/rotation_euler
    F-curves so we don't trigger a full depsgraph evaluation for every frame
    (which is slow when the scene has rigged characters, simulations, etc.).

    Returns a callable on success, or None when the camera transform can't
    be reconstructed in isolation — caller should then fall back to
    scene.frame_set + camera.matrix_world.
    """
    # Anything that makes matrix_world depend on more than the camera's own
    # local transform forces the slow path.
    if camera.parent is not None:
        return None
    if len(camera.constraints) > 0:
        return None
    if camera.rotation_mode != "XYZ":
        return None
    cam_anim = camera.data.animation_data
    if cam_anim and any(True for _ in iter_action_fcurves(cam_anim)):
        # Animated intrinsics (lens, sensor, clip): we'd need depsgraph eval
        return None
    if not camera.animation_data or not camera.animation_data.action:
        return None

    needed = {
        ("location", 0): None,
        ("location", 1): None,
        ("location", 2): None,
        ("rotation_euler", 0): None,
        ("rotation_euler", 1): None,
        ("rotation_euler", 2): None,
    }
    for fc in iter_action_fcurves(camera.animation_data):
        key = (fc.data_path, fc.array_index)
        if key in needed:
            needed[key] = fc
    if any(fc is None for fc in needed.values()):
        return None

    def to_dict(fc):
        return {int(round(kp.co.x)): kp.co.y for kp in fc.keyframe_points}

    loc_maps = [to_dict(needed[("location", i)]) for i in range(3)]
    rot_maps = [to_dict(needed[("rotation_euler", i)]) for i in range(3)]

    scale_mat = Matrix.Diagonal(camera.scale).to_4x4()

    def evaluate(frame_idx):
        try:
            loc = Vector(
                (loc_maps[0][frame_idx], loc_maps[1][frame_idx], loc_maps[2][frame_idx])
            )
            rot = Euler(
                (rot_maps[0][frame_idx], rot_maps[1][frame_idx], rot_maps[2][frame_idx]),
                "XYZ",
            )
        except KeyError:
            # Frame missing from keyframes for any channel; let caller fall back.
            return None
        return Matrix.Translation(loc) @ rot.to_matrix().to_4x4() @ scale_mat

    return evaluate


def camera_matrices_for_frames(scene, camera, frames):
    """
    Camera world matrices for each frame, via the fast path when possible.

    Falls back to scene.frame_set per frame and restores the current frame
    afterwards.

    Returns:
        dict: frame -> Matrix (4x4 world matrix)
    """
    fast_eval = build_fast_path_evaluator(camera)
    orig_frame = scene.frame_current
    moved = False
    matrices = {}
    for frame_idx in frames:
        matrix = fast_eval(frame_idx) if fast_eval is not None else None
        if matrix is None:
            scene.frame_set(frame_idx)
            moved = True
            matrix = camera.matrix_world.copy()
        matrices[frame_idx] = matrix
    if moved:
        scene.frame_set(orig_frame)
    return matrices


def angle_based_intrinsics(cam_data, width, height):
    """
    Pixel focal lengths and FOVs from Blender's actual camera angle.

    Honors sensor_fit, unlike deriving fy from sensor_height (which Blender
    ignores under AUTO/HORIZONTAL fit). Matches LichtFeld's convention:
    focal = 0.5 * resolution / tan(0.5 * fov).

    Returns:
        tuple: (fx, fy, fov_x, fov_y)
    """
    if cam_data.sensor_fit == 'HORIZONTAL' or (cam_data.sensor_fit == 'AUTO' and width >= height):
        # Horizontal FOV is the reference
        fov_x = cam_data.angle
        # Calculate vertical FOV from horizontal
        aspect_ratio = height / width
        fov_y = 2.0 * np.arctan(np.tan(fov_x / 2.0) * aspect_ratio)
    else:
        # Vertical FOV is the reference
        fov_y = cam_data.angle
        # Calculate horizontal FOV from vertical
        aspect_ratio = width / height
        fov_x = 2.0 * np.arctan(np.tan(fov_y / 2.0) * aspect_ratio)

    fx = 0.5 * width / np.tan(0.5 * fov_x)
    fy = 0.5 * height / np.tan(0.5 * fov_y)
    return fx, fy, fov_x, fov_y
