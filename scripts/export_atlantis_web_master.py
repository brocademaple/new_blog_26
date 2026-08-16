#!/usr/bin/env python3
"""Export the current Atlantis review master as modular web GLBs.

The modules share Blender's world origin.  Three.js can therefore add every
module at ``(0, 0, 0)`` and reproduce the authored master layout without the
per-asset offsets that caused the old palace/upper-floor mismatch.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import bpy


MODULES = {
    "atlantis-environment": "00_ENVIRONMENT",
    "atlantis-route": "01_PROCESSIONAL_ROUTE",
    "atlantis-archive": "02_ARCHIVE_OF_TIDES",
    "atlantis-cliff-gallery": "03_CLIFF_GALLERY",
    "atlantis-palace-complex": "04_PALACE_COMPLEX",
    "atlantis-ecology": "05_ECOLOGY_AND_RUINS",
}

# Blender volume/procedural transparency nodes do not have a faithful glTF
# representation.  Exporting these meshes produced an opaque pale ceiling in
# Three.js.  The web runtime recreates water haze, caustics and shafts, while
# the authored seabed, architecture, coral and particles remain in the GLBs.
WEB_INCOMPATIBLE_NAMES = {
    "WaterSurface",
    "UnderwaterAtmosphere",
}
WEB_INCOMPATIBLE_PREFIXES = (
    "SoftShaft_",
    "CausticProjection_",
)
LEGACY_PALACE_PREFIXES = (
    "PalaceNaveLeftWall_mesh",
    "PalaceNaveRightWall_mesh",
    "PalaceNaveRearWall_mesh",
    "PalaceNaveRoof_mesh",
    "PalaceRearSanctum_mesh",
    "PalaceSanctum",
)


def arguments() -> argparse.Namespace:
    argv = os.sys.argv
    values = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    return parser.parse_args(values)


def collection_objects(name: str) -> list[bpy.types.Object]:
    collection = bpy.data.collections.get(name)
    if collection is None:
        raise RuntimeError(f"Missing master collection: {name}")
    return [
        obj
        for obj in collection.all_objects
        if obj.type in {"MESH", "CURVE", "FONT", "EMPTY"}
        and not obj.hide_render
        and obj.name not in WEB_INCOMPATIBLE_NAMES
        and not obj.name.startswith(WEB_INCOMPATIBLE_PREFIXES)
    ]


def export_module(asset_id: str, collection_name: str, output: Path) -> dict:
    objects = collection_objects(collection_name)
    exportable = [obj for obj in objects if obj.type in {"MESH", "CURVE", "FONT", "EMPTY"}]
    if not exportable:
        raise RuntimeError(f"No exportable objects in {collection_name}")

    bpy.ops.object.select_all(action="DESELECT")
    for obj in exportable:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = exportable[0]

    bpy.ops.export_scene.gltf(
        filepath=str(output),
        export_format="GLB",
        use_selection=True,
        export_yup=True,
        export_apply=True,
        export_texcoords=True,
        export_normals=True,
        export_tangents=True,
        export_materials="EXPORT",
        export_cameras=False,
        export_lights=False,
        export_extras=True,
    )

    return {
        "asset": asset_id,
        "collection": collection_name,
        "glb": output.name,
        "bytes": output.stat().st_size,
        "objects": len(exportable),
        "meshes": sum(obj.type == "MESH" for obj in exportable),
        "curves": sum(obj.type == "CURVE" for obj in exportable),
        "origin": "blender-master-world",
        "units": "meter",
        "up_axis": "+Y",
    }


def main() -> None:
    repo = Path(arguments().repo).expanduser().resolve()
    expected = repo / "assets/gallery/blender/atlantis-gallery-master-v1.blend"
    if Path(bpy.data.filepath).resolve() != expected:
        raise RuntimeError(f"Load the master file before export: {expected}")

    legacy = sorted(
        obj.name
        for obj in bpy.data.objects
        if any(obj.name.startswith(prefix) for prefix in LEGACY_PALACE_PREFIXES)
    )
    if legacy:
        raise RuntimeError(
            "Legacy palace interior objects are still present in the master: "
            + ", ".join(legacy)
        )

    output_dir = repo / "static/assets/gallery/models/master-v1"
    output_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for asset_id, collection_name in MODULES.items():
        report.append(export_module(asset_id, collection_name, output_dir / f"{asset_id}.glb"))

    manifest = {
        "version": "master-v1",
        "source": str(expected),
        "source_mtime": expected.stat().st_mtime,
        "modules": report,
        "total_bytes": sum(item["bytes"] for item in report),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CODEX_WEB_MASTER=" + json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
