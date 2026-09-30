# CLAUDE.md

## Development Commands

### Installation and Testing
- **Install in Blender**: Copy the `addon` folder to Blender's addons directory or use Edit > Preferences > Add-ons > Install from File
- **Enable Developer Extras**: Edit > Preferences > Interface > Developer Extras (required for addon reload)
- **Reload Addon**: F3 > "Reload Scripts" in Blender after code changes
- **Debug Output**: Window > Toggle System Console (Windows) or run Blender from terminal to see print statements

## Versioning

**Never bump the version unless explicitly asked** — the maintainer controls
release cadence. Even a meaningful behavior fix ships without a bump; if one
seems warranted, ask first.

When asked to bump, the version lives in **two** places and both must change:
1. `addon/blender_manifest.toml` — the `version = "x.y.z"` line (read by
   Blender's extensions system)
2. `addon/ui/panels.py` — the `VERSION = "x.y.z"` constant (drives the N-panel
   title "Gauss Cannon vX.Y.Z")

Grep for the old version string first; don't edit the manifest alone.

## Blender manifest constraints

`blender_manifest.toml` is validated by Blender at **install time only** — the
GitHub Actions release build does not validate it, so these fail silently in CI:
- `tagline`: max 64 chars, must not end in `.`, `!`, or `?`
- `schema_version`: must be exactly `"1.0.0"` (the manifest format version, not
  the addon version)

## Key Algorithms

**Coordinate frame** (`utils/colmap.py`): COLMAP is the only export. Cameras and
points both stay in Blender's Z-up world frame, with no up-axis conversion
(COLMAP has none, and trainers orient the scene themselves).
- Poses are world-to-camera with OpenCV camera axes: right-multiply the Blender
  camera matrix by `diag(1, -1, -1, 1)`, then invert
- Depth/normal maps use the same OpenCV camera axes
