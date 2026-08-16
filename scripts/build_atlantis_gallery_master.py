#!/usr/bin/env python3
"""Assemble the six Atlantis assets into a reviewable Blender master scene.

Run with Blender:
  Blender --background --python build_atlantis_gallery_master.py -- \
    --repo /path/to/brocade-portfolio

The master scene is intended for spatial review and lighting iteration. The web
runtime continues to load the six small GLB modules independently.
"""

from __future__ import annotations

import argparse
import math
import os
import random
from pathlib import Path

import bpy
from mathutils import Vector


ASSET_FILES = {
    "platform": "lobby-platform.blend",
    "arch": "room-archway.blend",
    "column": "corridor-column.blend",
    "relief": "wall-relief-panel.blend",
    "vault": "ceiling-vault.blend",
    "tile": "floor-tile-unit.blend",
    "palace": "sunken-palace.blend",
}

ASSET_OBJECT_FILTERS = {
    "platform": (("LobbyPlatform",), {"Lobby_Platform"}),
    "arch": (("Arch",), {"Room_Archway"}),
    "column": (("Column",), {"Corridor_Column"}),
    "relief": (("WallRelief",), {"Wall_Relief_Panel"}),
    "vault": (("CeilingVault",), {"Ceiling_Vault"}),
    "tile": (("FloorTile",), {"Floor_Tile_Unit"}),
    "palace": (("Palace",), {"Sunken_Palace"}),
}


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument(
        "--skip-renders",
        action="store_true",
        help="Build and save the editable master scene without producing review renders.",
    )
    argv = os.sys.argv
    return parser.parse_args(argv[argv.index("--") + 1 :] if "--" in argv else [])


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.name != "Collection":
            bpy.data.collections.remove(collection)


def material(name: str, color: tuple[float, float, float, float], metallic=0.0, roughness=0.75):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def append_asset_library(blend_root: Path) -> dict[str, bpy.types.Collection]:
    library: dict[str, bpy.types.Collection] = {}
    for asset_id, filename in ASSET_FILES.items():
        path = blend_root / filename
        prefixes, exact_names = ASSET_OBJECT_FILTERS[asset_id]
        with bpy.data.libraries.load(str(path), link=False) as (source, target):
            selected_names = [
                name
                for name in source.objects
                if name in exact_names or any(name.startswith(prefix) for prefix in prefixes)
            ]
            if not selected_names:
                raise RuntimeError(f"No matching {asset_id} objects in {path}")
            target.objects = selected_names
        objects = [obj for obj in target.objects if obj is not None]
        collection = bpy.data.collections.new(f"LIB_{asset_id.upper()}")
        for obj in objects:
            collection.objects.link(obj)
        library[asset_id] = collection
    return library


def filtered_asset_collection(
    source: bpy.types.Collection,
    name: str,
    excluded_prefixes: tuple[str, ...],
) -> bpy.types.Collection:
    """Create an instancing collection with selected source pieces omitted.

    The generated palace asset contains its own compact nave.  The master scene
    replaces that nave with a larger museum interior, so the old internal shell
    must not sit between the entrance camera and the new focal gallery.
    """
    collection = bpy.data.collections.new(name)
    for obj in source.objects:
        if any(obj.name.startswith(prefix) for prefix in excluded_prefixes):
            continue
        collection.objects.link(obj)
    return collection


def instance(
    collection: bpy.types.Collection,
    name: str,
    location=(0.0, 0.0, 0.0),
    rotation=(0.0, 0.0, 0.0),
    scale=(1.0, 1.0, 1.0),
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = collection
    obj.location = location
    obj.rotation_euler = rotation
    obj.scale = scale
    bpy.context.scene.collection.objects.link(obj)
    return obj


def add_box(name, size, location, mat, rotation=(0.0, 0.0, 0.0), bevel=0.08):
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("ErodedEdges", "BEVEL")
        mod.width = bevel
        mod.segments = 2
    return obj


def add_curve_tube(name, points, radius, mat, resolution=1):
    """Create a lightweight tubular trim following a list of 3D points."""
    curve = bpy.data.curves.new(name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = resolution
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for spline_point, coordinate in zip(spline.points, points):
        spline_point.co = (*coordinate, 1.0)
    obj = bpy.data.objects.new(name, curve)
    obj.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def add_wayfinding_text(name, body, location, facing, mat, size=0.22):
    """Add compact, embedded 3D lettering that remains editable in Blender."""
    bpy.ops.object.text_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.body = body
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.012
    obj.data.bevel_depth = 0.004
    obj.data.bevel_resolution = 2
    obj.data.materials.append(mat)
    obj.rotation_euler = Vector(facing).to_track_quat("Z", "Y").to_euler()
    return obj


def emissive_material(name: str, color, strength=2.5):
    mat = material(name, (*color, 1.0), metallic=0.1, roughness=0.34)
    bsdf = next(node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def add_barrel_vault(name, center, width, depth, base_z, rise, mat):
    """Create a lightweight half-cylinder roof with a readable vaulted silhouette."""
    segments = 16
    verts, faces = [], []
    for y_offset in (-depth / 2, depth / 2):
        for index in range(segments + 1):
            angle = math.pi * index / segments
            x = center[0] + width * 0.5 * math.cos(angle)
            z = base_z + rise * math.sin(angle)
            verts.append((x, center[1] + y_offset, z))
    stride = segments + 1
    for index in range(segments):
        faces.append((index, index + 1, stride + index + 1, stride + index))
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    roof = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(roof)
    roof.data.materials.append(mat)
    solidify = roof.modifiers.new("VaultThickness", "SOLIDIFY")
    solidify.thickness = 0.20
    bevel = roof.modifiers.new("VaultEdgeSoftening", "BEVEL")
    bevel.width = 0.055
    bevel.segments = 2
    return roof


def add_vault_endcap(
    name,
    center,
    width,
    y,
    base_z,
    rise,
    stone,
    gold,
    glow_mat,
    outward_sign,
    window_glow_mat=None,
):
    """Close a barrel-vault end with a stone tympanum and luminous oculus."""
    cx, _ = center
    segments = 16
    verts = [(cx, y, base_z)]
    for index in range(segments + 1):
        angle = math.pi * index / segments
        verts.append((cx + width * 0.5 * math.cos(angle), y, base_z + rise * math.sin(angle)))
    faces = [(0, index + 1, index + 2) for index in range(segments)]
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    tympanum = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(tympanum)
    tympanum.data.materials.append(stone)
    solidify = tympanum.modifiers.new("TympanumThickness", "SOLIDIFY")
    solidify.thickness = 0.22
    bevel = tympanum.modifiers.new("TympanumEdgeSoftening", "BEVEL")
    bevel.width = 0.045
    bevel.segments = 2

    oculus_y = y + outward_sign * 0.14
    oculus_z = base_z + rise * 0.48
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32,
        radius=0.58,
        depth=0.13,
        location=(cx, oculus_y, oculus_z),
        rotation=(math.pi / 2, 0, 0),
    )
    oculus = bpy.context.object
    oculus.name = name + "_OculusGlow"
    oculus.data.materials.append(glow_mat)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.68,
        minor_radius=0.07,
        major_segments=32,
        minor_segments=8,
        location=(cx, oculus_y + outward_sign * 0.02, oculus_z),
        rotation=(math.pi / 2, 0, 0),
    )
    rim = bpy.context.object
    rim.name = name + "_OculusGoldRim"
    rim.data.materials.append(gold)

    # Three tall windows animate the otherwise heavy end wall. Their warm light
    # also distinguishes inhabited museum architecture from distant ruins.
    window_mat = window_glow_mat or glow_mat
    for window_index, x_offset in enumerate((-1.48, 0.0, 1.48)):
        window_x = cx + x_offset
        window_y = y + outward_sign * 0.15
        window_z = base_z - 1.82
        add_box(
            name + f"_WindowFrame_{window_index:02d}",
            (0.76, 0.18, 1.78),
            (window_x, window_y, window_z),
            gold,
            bevel=0.055,
        )
        add_box(
            name + f"_WindowGlow_{window_index:02d}",
            (0.57, 0.20, 1.53),
            (window_x, window_y + outward_sign * 0.02, window_z),
            window_mat,
            bevel=0.035,
        )


def add_pavilion_lantern(name, center, base_z, stone, stone_dark, gold, glow_mat):
    """Crown a side gallery with a museum lantern so it reads as a pavilion."""
    cx, cy = center
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=1.42, depth=0.58, location=(cx, cy, base_z + 0.29))
    drum = bpy.context.object
    drum.name = name + "_LanternDrum"
    drum.data.materials.append(stone)
    bevel = drum.modifiers.new("LanternDrumBevel", "BEVEL")
    bevel.width = 0.07
    bevel.segments = 2
    bpy.ops.mesh.primitive_torus_add(
        major_radius=1.25,
        minor_radius=0.08,
        major_segments=32,
        minor_segments=8,
        location=(cx, cy, base_z + 0.58),
    )
    rim = bpy.context.object
    rim.name = name + "_LanternGoldRim"
    rim.data.materials.append(gold)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=(cx, cy, base_z + 1.08))
    dome = bpy.context.object
    dome.name = name + "_LanternDome"
    dome.scale = (1.42, 1.42, 0.72)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    dome.data.materials.append(stone_dark)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.16, location=(cx, cy, base_z + 1.76))
    beacon = bpy.context.object
    beacon.name = name + "_LanternBeacon"
    beacon.data.materials.append(glow_mat)


def fit_artwork_size(path: Path, max_width: float, max_height: float) -> tuple[float, float]:
    """Fit an image inside a frame without stretching its source aspect ratio."""
    image = bpy.data.images.load(str(path), check_existing=True)
    width, height = image.size
    aspect = width / max(1, height)
    if max_width / max_height > aspect:
        return max_height * aspect, max_height
    return max_width, max_width / max(aspect, 0.001)


def add_artwork_quad(name, path, verts, face, emission_strength=0.18):
    """Create a rotation-free artwork mesh with UVs bound by vertex identity."""
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], [face])
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    uv_by_vertex = {
        0: (0.0, 0.0),
        1: (1.0, 0.0),
        2: (1.0, 1.0),
        3: (0.0, 1.0),
    }
    for loop in mesh.loops:
        uv_layer.data[loop.index].uv = uv_by_vertex[loop.vertex_index]
    art = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(art)
    art.data.materials.append(image_material(path, name + "_mat", emission_strength=emission_strength))
    tag_gallery_artwork(art, path)
    return art


def add_gallery_art_panel(name, path, x, y, z, inward_sign, gold, stone_dark):
    """Mount one undistorted framed artwork facing the central causeway."""
    art_width, art_height = fit_artwork_size(path, 1.82, 1.55)
    add_box(name + "_Backing", (0.24, art_width + 0.46, art_height + 0.42), (x, y, z), stone_dark, bevel=0.07)
    add_box(name + "_Frame", (0.18, art_width + 0.22, art_height + 0.22), (x + inward_sign * 0.08, y, z), gold, bevel=0.035)
    plane_x = x + inward_sign * 0.181
    half_width, half_height = art_width * 0.5, art_height * 0.5
    if inward_sign > 0:
        verts = [
            (plane_x, y - half_width, z - half_height),
            (plane_x, y + half_width, z - half_height),
            (plane_x, y + half_width, z + half_height),
            (plane_x, y - half_width, z + half_height),
        ]
    else:
        verts = [
            (plane_x, y + half_width, z - half_height),
            (plane_x, y - half_width, z - half_height),
            (plane_x, y - half_width, z + half_height),
            (plane_x, y + half_width, z + half_height),
        ]
    add_artwork_quad(name + "_Image", path, verts, (0, 1, 2, 3))


def add_side_gallery_relics(name, cx, cy, inward_sign, floor_z, stone_dark, gold, glow_mat):
    """Add two compact displays while preserving the gallery's central aisle."""
    display_x = cx - inward_sign * 1.65
    for index, y in enumerate((cy - 2.15, cy + 2.15)):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=24,
            radius=0.48,
            depth=0.44,
            location=(display_x, y, floor_z + 0.22),
        )
        plinth = bpy.context.object
        plinth.name = f"{name}_RelicPlinth_{index:02d}"
        plinth.data.materials.append(stone_dark)
        bevel = plinth.modifiers.new("RelicPlinthBevel", "BEVEL")
        bevel.width = 0.06
        bevel.segments = 2
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.39,
            minor_radius=0.04,
            major_segments=24,
            minor_segments=6,
            location=(display_x, y, floor_z + 0.46),
        )
        rim = bpy.context.object
        rim.name = f"{name}_RelicRim_{index:02d}"
        rim.data.materials.append(gold)
        relic_z = floor_z + 0.92
        if index == 0:
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.31,
                minor_radius=0.055,
                major_segments=24,
                minor_segments=7,
                location=(display_x, y, relic_z),
                rotation=(math.pi / 2, 0, 0),
            )
            relic = bpy.context.object
            relic.name = f"{name}_TidalAstrolabe"
            relic.data.materials.append(gold)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.14, location=(display_x, y, relic_z))
            core = bpy.context.object
            core.name = f"{name}_TidalAstrolabeCore"
            core.data.materials.append(glow_mat)
        else:
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.26, location=(display_x, y, relic_z))
            relic = bpy.context.object
            relic.name = f"{name}_MemoryPearl"
            relic.scale = (0.78, 0.78, 1.18)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            relic.data.materials.append(glow_mat)
            for angle in (0.0, math.pi / 2):
                bpy.ops.mesh.primitive_torus_add(
                    major_radius=0.34,
                    minor_radius=0.028,
                    major_segments=24,
                    minor_segments=6,
                    location=(display_x, y, relic_z),
                    rotation=(angle, 0, 0),
                )
                cage = bpy.context.object
                cage.name = f"{name}_MemoryPearlCage_{angle:.2f}"
                cage.data.materials.append(gold)


def add_side_gallery_shell(
    name,
    center,
    library,
    art_paths,
    stone,
    stone_dark,
    floor_mat,
    gold,
    glow_mat,
    relic_glow_mat=None,
    window_glow_mat=None,
    stepped_foundation=False,
):
    """Build a complete side gallery with an open entrance and visible interior."""
    cx, cy = center
    inward_sign = 1 if cx < 0 else -1
    width_x, depth_y = 7.6, 10.8
    inner_x = cx + inward_sign * width_x * 0.5
    outer_x = cx - inward_sign * width_x * 0.5

    # Broad, level thresholds replace the previous unexplained raised ramps.
    if stepped_foundation:
        add_box(name + "_LowerRockTerrace", (9.2, 12.3, 0.34), (cx, cy, 0.12), stone_dark, bevel=0.18)
        add_box(name + "_UpperFoundation", (8.3, 11.4, 0.28), (cx, cy, 0.36), stone, bevel=0.12)
        floor_z = 0.54
    else:
        add_box(name + "_Foundation", (8.3, 11.5, 0.30), (cx, cy, 0.15), stone_dark, bevel=0.14)
        floor_z = 0.32
    add_box(name + "_InteriorFloor", (7.2, 10.15, 0.12), (cx, cy, floor_z), floor_mat, bevel=0.04)

    wall_base = floor_z + 0.10
    wall_height = 4.35
    wall_z = wall_base + wall_height * 0.5
    add_box(name + "_RearWall", (0.38, 10.15, wall_height), (outer_x, cy, wall_z), stone, bevel=0.10)
    for side_index, side_y in enumerate((cy - depth_y * 0.5, cy + depth_y * 0.5)):
        if side_index == 0:
            # The south wall faces the palace. Split it around a real rear
            # doorway so visitors can continue from the side exhibition into
            # the connecting cloister instead of returning to the causeway.
            rear_door_width = 2.70
            wall_segment = (width_x - rear_door_width) * 0.5
            for segment_index, segment_x in enumerate(
                (cx - (rear_door_width + wall_segment) * 0.5, cx + (rear_door_width + wall_segment) * 0.5)
            ):
                add_box(
                    name + f"_RearWallSegment_{segment_index}",
                    (wall_segment, 0.38, wall_height),
                    (segment_x, side_y, wall_z),
                    stone,
                    bevel=0.10,
                )
            add_box(
                name + "_RearDoorSpandrel",
                (rear_door_width, 0.42, 0.88),
                (cx, side_y, wall_base + wall_height - 0.44),
                stone_dark,
                bevel=0.07,
            )
            # The reusable ruin arch contains deep decorative members that
            # block an eye-level view when used as a narrow interior doorway.
            # A purpose-built portal keeps the full 2.7 m connection clear.
            portal_y = side_y - 0.18
            for jamb_index, jamb_x in enumerate((cx - 1.52, cx + 1.52)):
                add_box(
                    name + f"_RearPortalJamb_{jamb_index}",
                    (0.34, 0.46, 3.42),
                    (jamb_x, portal_y, floor_z + 1.73),
                    stone,
                    bevel=0.075,
                )
                add_box(
                    name + f"_RearPortalJambBronze_{jamb_index}",
                    (0.40, 0.50, 0.075),
                    (jamb_x, portal_y - 0.02, floor_z + 3.42),
                    gold,
                    bevel=0.014,
                )
            add_box(
                name + "_RearPortalLintel",
                (3.38, 0.48, 0.36),
                (cx, portal_y, floor_z + 3.52),
                stone_dark,
                bevel=0.07,
            )
            add_box(
                name + "_RearPortalLintelBronze",
                (3.10, 0.52, 0.065),
                (cx, portal_y - 0.02, floor_z + 3.72),
                gold,
                bevel=0.012,
            )
        else:
            add_box(name + f"_SideWall_{side_index}", (7.6, 0.38, wall_height), (cx, side_y, wall_z), stone, bevel=0.10)

    entrance_width = 4.0
    pier_length = (depth_y - entrance_width) * 0.5
    for side_index, side_y in enumerate((cy - (entrance_width + pier_length) * 0.5, cy + (entrance_width + pier_length) * 0.5)):
        add_box(name + f"_FacadePier_{side_index}", (0.42, pier_length, wall_height), (inner_x, side_y, wall_z), stone, bevel=0.10)
    add_box(name + "_EntranceSpandrel", (0.44, entrance_width, 0.92), (inner_x, cy, wall_base + wall_height - 0.46), stone_dark, bevel=0.08)
    add_box(name + "_GoldCornice", (0.54, depth_y + 0.2, 0.16), (inner_x + inward_sign * 0.03, cy, wall_base + wall_height + 0.02), gold, bevel=0.03)
    instance(
        library["arch"],
        name + "_EntranceArch",
        (inner_x + inward_sign * 0.24, cy, floor_z + 0.02),
        rotation=(0, 0, math.pi / 2),
        scale=(0.92, 0.92, 0.92),
    )

    # Four facade pilasters, corner buttresses and a crowned vault turn the shell
    # into a proper museum pavilion rather than a freestanding rain canopy.
    for index, y_offset in enumerate((-4.55, -2.28, 2.28, 4.55)):
        if name == "CliffGallery" and index == 0:
            # One fractured facade support immediately distinguishes the cliff
            # museum from the intact archival pavilion across the axis.
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=18,
                radius=0.27,
                depth=1.18,
                location=(inner_x + inward_sign * 0.52, cy + y_offset, floor_z + 0.61),
            )
            stump = bpy.context.object
            stump.name = name + "_BrokenFacadeColumnStump"
            stump.rotation_euler = (0.08, -0.05, 0.04)
            stump.data.materials.append(stone)
            continue
        instance(
            library["column"],
            name + f"_FacadeColumn_{index}",
            (inner_x + inward_sign * 0.52, cy + y_offset, floor_z + 0.02),
            scale=(0.72, 0.72, 0.78),
        )
    add_barrel_vault(name + "_BarrelRoof", center, 8.0, 11.0, wall_base + wall_height, 2.15, stone_dark)
    # The south end faces the palace cloister and remains open. A full vault
    # endcap here previously sealed the rear doorway with decorative windows.
    add_vault_endcap(
        name + "_NorthTympanum",
        center,
        8.0,
        cy + 5.50,
        wall_base + wall_height,
        2.15,
        stone,
        gold,
        glow_mat,
        1,
        window_glow_mat,
    )
    for rail_x in (cx - 3.3, cx + 3.3):
        if name == "CliffGallery" and rail_x > cx:
            continue
        add_box(name + f"_RoofGoldRib_{rail_x:+.1f}", (0.08, 10.85, 0.08), (rail_x, cy, wall_base + wall_height + 0.10), gold, bevel=0.02)
    for corner_index, (corner_x, corner_y) in enumerate(
        (
            (cx - 3.72, cy - 5.25),
            (cx - 3.72, cy + 5.25),
            (cx + 3.72, cy - 5.25),
            (cx + 3.72, cy + 5.25),
        )
    ):
        add_box(
            name + f"_CornerButtress_{corner_index:02d}",
            (0.62, 0.62, wall_height + 0.48),
            (corner_x, corner_y, wall_z + 0.20),
            stone_dark,
            bevel=0.09,
        )
        add_box(
            name + f"_CornerGoldCap_{corner_index:02d}",
            (0.74, 0.74, 0.12),
            (corner_x, corner_y, wall_base + wall_height + 0.45),
            gold,
            bevel=0.025,
        )
    add_pavilion_lantern(
        name,
        center,
        wall_base + wall_height + 1.20,
        stone,
        stone_dark,
        gold,
        glow_mat,
    )

    # Artwork sits inside on the rear wall, visible through the open entrance.
    for index, path in enumerate(art_paths[:3]):
        add_gallery_art_panel(
            name + f"_Artwork_{index:02d}",
            path,
            outer_x + inward_sign * 0.24,
            cy + (index - 1) * 2.85,
            floor_z + 2.15,
            inward_sign,
            gold,
            stone_dark,
        )
    add_box(name + "_InteriorLightBand", (0.10, 7.0, 0.10), (outer_x + inward_sign * 0.28, cy, floor_z + 3.85), glow_mat, bevel=0.02)
    add_side_gallery_relics(
        name,
        cx,
        cy,
        inward_sign,
        floor_z,
        stone_dark,
        gold,
        relic_glow_mat or glow_mat,
    )

    # A horizontal bridge meets the level threshold without the old kicked-up lip.
    # Connect each pavilion to the nearest edge of the central causeway. The
    # previous sign pointed both bridges across the opposite lane, which made
    # the museum plan look accidental from above.
    path_edge = -inward_sign * 2.08
    bridge_center_x = (path_edge + inner_x) * 0.5
    bridge_length = abs(inner_x - path_edge)
    add_box(name + "_Bridge", (bridge_length, 3.35, 0.18), (bridge_center_x, cy, floor_z - 0.06), floor_mat, bevel=0.07)
    for edge_y in (cy - 1.56, cy + 1.56):
        add_box(name + f"_BridgeGoldLine_{edge_y:+.2f}", (bridge_length, 0.055, 0.035), (bridge_center_x, edge_y, floor_z + 0.04), gold, bevel=0.01)

    # Readable threshold plaque; the two buildings now have distinct identities.
    plaque_z = floor_z + 3.80
    add_box(name + "_NamePlaque", (0.20, 3.55, 0.48), (inner_x + inward_sign * 0.34, cy, plaque_z), stone_dark, bevel=0.06)
    for accent_sign, accent_y in (("L", -1.58), ("R", 1.58)):
        add_box(
            name + f"_NamePlaqueAccent_{accent_sign}",
            (0.08, 0.20, 0.055),
            (inner_x + inward_sign * 0.46, cy + accent_y, plaque_z),
            gold,
            bevel=0.012,
        )
    gallery_title = "ARCHIVE OF TIDES" if name == "ArchiveOfTides" else "CLIFF GALLERY"
    add_wayfinding_text(
        name + "_Title",
        gallery_title,
        (inner_x + inward_sign * 0.515, cy, plaque_z),
        (inward_sign, 0, 0),
        glow_mat,
        size=0.165,
    )

    if name == "ArchiveOfTides":
        # The archive remains the most complete side pavilion: an intact roof
        # crest, ordered finials and continuous bronze datum reinforce dignity.
        crest_z = wall_base + wall_height + 2.10
        add_box(name + "_RoofCrest", (0.10, 8.25, 0.12), (cx, cy, crest_z), gold, bevel=0.018)
        for finial_index, finial_y in enumerate((cy - 3.2, cy, cy + 3.2)):
            add_box(
                name + f"_RoofFinial_{finial_index:02d}",
                (0.16, 0.16, 0.62),
                (cx, finial_y, crest_z + 0.34),
                gold,
                bevel=0.024,
            )
        add_box(
            name + "_FacadeDatum",
            (0.055, 8.45, 0.075),
            (inner_x + inward_sign * 0.55, cy, floor_z + 1.08),
            gold,
            bevel=0.012,
        )
    else:
        # The cliff gallery is partially swallowed by the rock shelf. Broken
        # terrace slabs and roof rubble create an asymmetrical, eroded profile
        # while all circulation stays on the protected inner side.
        cliff_sign = 1 if cx > 0 else -1
        for rock_index, (x_offset, y_offset, scale, rotation) in enumerate(
            (
                (4.20, -3.75, (1.55, 1.05, 1.25), 0.28),
                (4.55, -0.70, (1.90, 1.35, 1.55), -0.18),
                (4.30, 2.65, (1.45, 1.10, 1.10), 0.52),
                (3.05, 4.70, (1.15, 0.92, 0.82), -0.36),
            )
        ):
            add_rock(
                name + f"_CliffOutcrop_{rock_index:02d}",
                (cx + cliff_sign * x_offset, cy + y_offset, 0.42),
                scale,
                stone_dark if rock_index % 2 else stone,
                rotation,
            )
        for slab_index, (x_offset, y_offset, width, depth, rotation) in enumerate(
            (
                (4.10, -4.10, 2.20, 1.55, 0.12),
                (5.05, -1.70, 1.75, 1.35, -0.24),
                (4.45, 1.25, 2.05, 1.42, 0.20),
            )
        ):
            add_box(
                name + f"_BrokenTerraceSlab_{slab_index:02d}",
                (width, depth, 0.16),
                (cx + cliff_sign * x_offset, cy + y_offset, 0.18 + slab_index * 0.035),
                floor_mat if slab_index != 1 else stone_dark,
                rotation=(0.0, 0.025 * (slab_index - 1), rotation),
                bevel=0.055,
            )
        add_rock(
            name + "_RoofCollapseStone_A",
            (cx + 1.55, cy + 2.85, wall_base + wall_height + 2.22),
            (1.35, 0.82, 0.56),
            stone,
            0.34,
        )
        add_rock(
            name + "_RoofCollapseStone_B",
            (cx + 2.45, cy + 1.85, wall_base + wall_height + 1.90),
            (0.92, 0.66, 0.48),
            stone_dark,
            -0.27,
        )
    return inner_x, floor_z


def add_palace_forecourt_and_wings(stone, stone_dark, floor_mat, gold, glow_mat, guide_glow_mat=None):
    """Tie the two side pavilions into one legible palace museum district."""
    # A broad forecourt announces the transition from processional causeway to
    # the palace, with three shallow terraces instead of an unexplained ramp.
    add_box("PalaceForecourtLower", (19.5, 7.8, 0.24), (0, -44.1, 0.12), stone_dark, bevel=0.14)
    add_box("PalaceForecourtMiddle", (17.5, 6.0, 0.18), (0, -45.0, 0.30), stone, bevel=0.10)
    add_box("PalaceForecourtUpper", (15.6, 4.2, 0.14), (0, -46.1, 0.46), floor_mat, bevel=0.07)
    for x in (-7.35, 7.35):
        add_box(f"PalaceForecourtGoldLine_{x:+.2f}", (0.07, 7.0, 0.025), (x, -44.0, 0.55), gold, bevel=0.01)
    for x in (-3.25, 3.25):
        add_box(
            f"PalaceForecourtLightGuide_{x:+.2f}",
            (0.055, 8.1, 0.022),
            (x, -43.5, 0.57),
            glow_mat,
            bevel=0.008,
        )
    for index, y in enumerate((-41.2, -43.4, -45.6)):
        for side_name, x in (("L", -4.2), ("R", 4.2)):
            bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.17, depth=0.34, location=(x, y, 0.72))
            beacon_base = bpy.context.object
            beacon_base.name = f"ForecourtBeaconBase_{side_name}_{index:02d}"
            beacon_base.data.materials.append(gold)
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.13, location=(x, y, 1.00))
            beacon = bpy.context.object
            beacon.name = f"ForecourtBeacon_{side_name}_{index:02d}"
            beacon.data.materials.append(glow_mat)

    guide_glow = guide_glow_mat or glow_mat
    # Roofed side loggias start at the pavilions and terminate at a pair of
    # domed gatehouses beside the palace entrance.  The previous version only
    # had a row of columns and a low parapet, so an elevated viewport made the
    # two pavilions look unrelated to the palace.  A solid outer wall, inner
    # colonnade and continuous roof now make the circulation unmistakable.
    for side_name, x in (("L", -7.65), ("R", 7.65)):
        side_sign = -1 if x < 0 else 1
        inner_x = x - side_sign * 1.42
        outer_x = x + side_sign * 1.42
        add_box(f"MuseumWingFloor_{side_name}", (3.15, 16.0, 0.16), (x, -38.1, 0.24), floor_mat, bevel=0.06)
        add_box(f"MuseumWingOuterWall_{side_name}", (0.34, 15.85, 3.18), (outer_x, -38.1, 1.84), stone_dark, bevel=0.08)
        add_box(f"MuseumWingOuterCornice_{side_name}", (0.48, 15.75, 0.16), (outer_x, -38.1, 3.50), gold, bevel=0.025)
        add_box(f"MuseumWingRoof_{side_name}", (3.30, 15.85, 0.24), (x, -38.1, 3.58), stone, bevel=0.07)
        add_box(f"MuseumWingRoofGoldRib_{side_name}", (0.09, 15.55, 0.055), (x, -38.1, 3.73), gold, bevel=0.012)
        for index, y in enumerate((-32.2, -35.2, -38.2, -41.2, -44.2)):
            bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.24, depth=3.0, location=(inner_x, y, 1.76))
            col = bpy.context.object
            col.name = f"MuseumWingColumn_{side_name}_{index:02d}"
            col.data.materials.append(stone)
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.30,
                minor_radius=0.045,
                major_segments=20,
                minor_segments=6,
                location=(inner_x, y, 3.24),
            )
            cap = bpy.context.object
            cap.name = f"MuseumWingColumnCap_{side_name}_{index:02d}"
            cap.data.materials.append(gold)
        add_box(f"MuseumWingEntablature_{side_name}", (0.48, 15.4, 0.28), (inner_x, -38.1, 3.32), stone_dark, bevel=0.05)
        add_box(f"MuseumWingEntablatureGold_{side_name}", (0.56, 15.2, 0.07), (inner_x, -38.1, 3.49), gold, bevel=0.015)

        # The connector is circulation, not a painting gallery.  Recessed
        # luminous bays and low relief medallions provide rhythm without
        # creating more floating picture frames along the route.
        for bay_index, y in enumerate((-33.3, -37.9, -42.5)):
            bpy.ops.mesh.primitive_ico_sphere_add(
                subdivisions=2,
                radius=0.12,
                location=(outer_x - side_sign * 0.22, y, 2.44),
            )
            sconce = bpy.context.object
            sconce.name = f"MuseumWingGuideSconce_{side_name}_{bay_index:02d}"
            sconce.data.materials.append(guide_glow)
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.20,
                minor_radius=0.035,
                major_segments=22,
                minor_segments=6,
                location=(outer_x - side_sign * 0.28, y, 2.44),
                rotation=(0, math.pi / 2, 0),
            )
            sconce_rim = bpy.context.object
            sconce_rim.name = f"MuseumWingGuideSconceRim_{side_name}_{bay_index:02d}"
            sconce_rim.data.materials.append(gold)
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.29,
                minor_radius=0.045,
                major_segments=24,
                minor_segments=7,
                location=(outer_x - side_sign * 0.28, y, 1.22),
                rotation=(0, math.pi / 2, 0),
            )
            medallion = bpy.context.object
            medallion.name = f"MuseumWingRelief_{side_name}_{bay_index:02d}"
            medallion.data.materials.append(gold)

        gate_x = x
        gate_y = -46.1
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=1.48, depth=3.6, location=(gate_x, gate_y, 2.16))
        gate = bpy.context.object
        gate.name = f"PalaceGatehouse_{side_name}"
        gate.data.materials.append(stone_dark)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, location=(gate_x, gate_y, 4.08))
        dome = bpy.context.object
        dome.name = f"PalaceGatehouseDome_{side_name}"
        dome.scale = (1.50, 1.50, 0.72)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        dome.data.materials.append(stone)
        bpy.ops.mesh.primitive_torus_add(
            major_radius=1.18,
            minor_radius=0.075,
            major_segments=32,
            minor_segments=8,
            location=(gate_x, gate_y, 4.12),
        )
        dome_rim = bpy.context.object
        dome_rim.name = f"PalaceGatehouseGoldRim_{side_name}"
        dome_rim.data.materials.append(gold)
        add_box(
            f"PalaceGatehousePortalFrame_{side_name}",
            (1.14, 0.32, 1.96),
            (gate_x, gate_y + 1.30, 2.08),
            gold,
            bevel=0.085,
        )
        add_box(
            f"PalaceGatehousePortal_{side_name}",
            (0.78, 0.36, 1.58),
            (gate_x, gate_y + 1.49, 2.08),
            guide_glow,
            bevel=0.065,
        )

    # The title is fixed to the central facade, so the palace reads as the
    # primary museum rather than an unrelated background building.
    add_box("PalaceMuseumTitlePlaque", (6.2, 0.30, 0.72), (0, -46.74, 5.82), stone_dark, bevel=0.08)
    add_box("PalaceMuseumTitleUnderline", (5.35, 0.08, 0.055), (0, -46.54, 5.55), gold, bevel=0.012)
    add_wayfinding_text(
        "PalaceMuseumTitle",
        "THE SUNKEN ARCHIVE",
        (0, -46.525, 5.88),
        (0, 1, 0),
        glow_mat,
        size=0.285,
    )


def add_palace_nave_shell(stone, stone_dark, floor_mat, gold, glow_mat):
    """Enclose the palace collection so its paintings belong to a real hall."""
    floor_z = 0.92
    add_box("PalaceNaveFloor", (9.55, 8.35, 0.14), (0, -52.55, floor_z), floor_mat, bevel=0.055)

    # Side walls sit immediately behind the six interior artworks.  Three
    # shallow bays on each wall make their mounting condition legible even in
    # Blender's free perspective view.
    for side_name, wall_x, inward_sign in (("L", -4.92, 1), ("R", 4.92, -1)):
        add_box(f"PalaceNaveSideWall_{side_name}", (0.36, 8.35, 4.78), (wall_x, -52.55, 3.30), stone, bevel=0.09)
        add_box(f"PalaceNaveSideCornice_{side_name}", (0.48, 8.15, 0.16), (wall_x, -52.55, 5.72), gold, bevel=0.025)
        for bay_index, y in enumerate((-50.5, -52.75, -55.0)):
            add_box(
                f"PalaceNaveArtNiche_{side_name}_{bay_index:02d}",
                (0.16, 1.84, 2.18),
                (wall_x + inward_sign * 0.22, y, 2.72),
                stone_dark,
                bevel=0.07,
            )
            add_box(
                f"PalaceNaveArtLight_{side_name}_{bay_index:02d}",
                (0.08, 1.45, 0.07),
                (wall_x + inward_sign * 0.33, y, 4.02),
                glow_mat,
                bevel=0.015,
            )

    # A complete barrel vault closes the hall from above; previously only
    # decorative ceiling ribs existed, which exposed the paintings from top
    # views and made them look suspended in open water.
    add_barrel_vault("PalaceNaveVault", (0.0, -52.55), 10.25, 8.45, 5.68, 2.10, stone_dark)
    for rib_index, y in enumerate((-55.75, -53.65, -51.55, -49.45)):
        add_barrel_vault(
            f"PalaceNaveVaultRib_{rib_index:02d}",
            (0.0, y),
            10.42,
            0.12,
            5.72,
            2.14,
            gold,
        )

    # The rear sanctum wall carries the focal work; a framed oculus adds a
    # second architectural layer above it instead of another canvas.
    add_box("PalaceNaveRearSanctum", (9.50, 0.38, 5.05), (0, -56.70, 3.43), stone_dark, bevel=0.10)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32,
        radius=0.74,
        depth=0.16,
        location=(0, -56.46, 5.45),
        rotation=(math.pi / 2, 0, 0),
    )
    oculus = bpy.context.object
    oculus.name = "PalaceNaveRearOculus"
    oculus.data.materials.append(glow_mat)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.86,
        minor_radius=0.075,
        major_segments=32,
        minor_segments=8,
        location=(0, -56.36, 5.45),
        rotation=(math.pi / 2, 0, 0),
    )
    bpy.context.object.name = "PalaceNaveRearOculusGoldRim"
    bpy.context.object.data.materials.append(gold)


def add_sculpture_garden(stone, stone_dark, gold):
    """An open-air sculpture reef on the spacious pre-museum seabed."""
    positions = ((-18.0, -12.0, 0.78), (-20.3, -16.0, 0.62), (-17.7, -20.0, 0.68))
    for index, (x, y, scale) in enumerate(positions):
        bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=1.05 * scale, depth=0.34, location=(x, y, 0.30))
        plinth = bpy.context.object
        plinth.name = f"SculptureGarden_Platform_{index:02d}"
        plinth.data.materials.append(stone_dark)
        bevel = plinth.modifiers.new("PlinthBevel", "BEVEL")
        bevel.width = 0.09
        bevel.segments = 2
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.56 * scale,
            minor_radius=0.10 * scale,
            major_segments=28,
            minor_segments=8,
            location=(x, y, 1.18 + index * 0.13),
            rotation=(math.pi * (0.38 + index * 0.12), math.pi * (0.18 + index * 0.09), index * 0.7),
        )
        sculpture = bpy.context.object
        sculpture.name = f"SculptureGarden_Orbital_{index:02d}"
        sculpture.data.materials.append(gold)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.22 * scale, location=(x, y, 1.20 + index * 0.13))
        core = bpy.context.object
        core.name = f"SculptureGarden_Core_{index:02d}"
        core.data.materials.append(stone)


def add_exploration_branch(library, stone, stone_dark, floor_mat, gold, glow_mat):
    """Add a discoverable archaeological spur beyond the Cliff Gallery."""

    def path_segment(name, start, end, width, z):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        angle = math.atan2(dy, dx)
        center = ((start[0] + end[0]) * 0.5, (start[1] + end[1]) * 0.5, z)
        add_box(name, (length, width, 0.16), center, floor_mat, rotation=(0.0, 0.0, angle), bevel=0.07)
        add_box(
            name + "_Guide",
            (length - 0.18, 0.045, 0.025),
            (center[0], center[1], z + 0.095),
            gold,
            rotation=(0.0, 0.0, angle),
            bevel=0.008,
        )
        normal = Vector((-dy / length, dx / length))
        for edge_index, side in enumerate((-1.0, 1.0)):
            edge_center = Vector((center[0], center[1])) + normal * (side * (width * 0.5 - 0.12))
            add_box(
                name + f"_Edge_{edge_index:02d}",
                (length - 0.14, 0.055, 0.028),
                (edge_center.x, edge_center.y, z + 0.098),
                gold,
                rotation=(0.0, 0.0, angle),
                bevel=0.008,
            )

    # The path branches from the Cliff Gallery's real rear doorway, bends
    # behind the building, and keeps its destination hidden from the entrance.
    route = (
        ((11.50, -34.25), (15.20, -37.10), 2.75, 0.42),
        ((15.20, -37.10), (18.75, -41.45), 2.55, 0.48),
        ((18.75, -41.45), (21.40, -46.65), 2.35, 0.54),
        ((21.40, -46.65), (22.55, -50.10), 2.20, 0.60),
    )
    for index, (start, end, width, z) in enumerate(route):
        path_segment(f"SunkenReliquaryPath_{index:02d}", start, end, width, z)

    add_box("SunkenReliquaryTerrace", (6.8, 6.0, 0.22), (22.65, -51.10, 0.52), stone_dark, rotation=(0, 0, -0.18), bevel=0.16)
    add_box("SunkenReliquaryFloor", (5.85, 5.05, 0.11), (22.55, -51.00, 0.685), floor_mat, rotation=(0, 0, -0.18), bevel=0.08)

    # Two unequal pylons and surviving arc fragments form a recognizably
    # ceremonial ruin without adding another complete building.
    direction = Vector((1.15, -3.45)).normalized()
    perpendicular = Vector((-direction.y, direction.x))
    gate_center = Vector((22.0, -48.55))
    for index, (side, height) in enumerate(((-1.0, 3.45), (1.0, 2.35))):
        location_2d = gate_center + perpendicular * (side * 1.42)
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=20,
            radius=0.30,
            depth=height,
            location=(location_2d.x, location_2d.y, 0.70 + height * 0.5),
        )
        pylon = bpy.context.object
        pylon.name = f"SunkenReliquaryBrokenPylon_{index:02d}"
        pylon.rotation_euler = (0.035 * side, -0.025 * side, -0.18)
        pylon.data.materials.append(stone if index == 0 else stone_dark)
        add_box(
            f"SunkenReliquaryPylonBand_{index:02d}",
            (0.66, 0.66, 0.09),
            (location_2d.x, location_2d.y, 0.70 + min(height, 2.05)),
            gold,
            rotation=(0, 0, -0.18),
            bevel=0.02,
        )

    def arch_fragment(name, start_angle, end_angle, steps):
        points = []
        for step in range(steps + 1):
            angle = start_angle + (end_angle - start_angle) * step / steps
            offset = perpendicular * (1.42 * math.cos(angle))
            point_2d = gate_center + offset
            points.append((point_2d.x, point_2d.y, 3.68 + 1.42 * math.sin(angle)))
        add_curve_tube(name, points, 0.22, stone, resolution=1)

    arch_fragment("SunkenReliquaryArchFragment_L", 0.0, 1.22, 7)
    arch_fragment("SunkenReliquaryArchFragment_R", 2.42, math.pi, 4)

    add_box("SunkenReliquaryDais", (2.7, 2.7, 0.28), (22.70, -51.55, 0.86), stone, rotation=(0, 0, -0.18), bevel=0.14)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.72, minor_radius=0.10, major_segments=32, minor_segments=10, location=(22.70, -51.55, 1.66), rotation=(math.pi / 2, 0, -0.18))
    relic_ring = bpy.context.object
    relic_ring.name = "SunkenReliquaryMemoryRing"
    relic_ring.data.materials.append(gold)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.34, location=(22.70, -51.55, 1.66))
    relic_core = bpy.context.object
    relic_core.name = "SunkenReliquaryMemoryCore"
    relic_core.data.materials.append(glow_mat)
    add_box("SunkenReliquaryBrokenWall", (0.45, 4.7, 1.65), (25.25, -51.35, 1.41), stone_dark, rotation=(0.0, 0.12, -0.18), bevel=0.12)
    add_box("SunkenReliquaryPlaque", (1.75, 0.16, 0.38), (22.70, -53.45, 1.20), stone_dark, rotation=(0, 0, -0.18), bevel=0.05)


def add_rear_art_panel(name, path, x, y, z, gold, stone_dark):
    """Mount a large artwork on a wall facing the palace entrance."""
    art_width, art_height = fit_artwork_size(path, 3.02, 2.72)
    add_box(name + "_Backing", (art_width + 0.50, 0.24, art_height + 0.46), (x, y, z), stone_dark, bevel=0.08)
    add_box(name + "_Frame", (art_width + 0.24, 0.18, art_height + 0.24), (x, y + 0.08, z), gold, bevel=0.04)
    half_width, half_height = art_width * 0.5, art_height * 0.5
    verts = [
        (x - half_width, y + 0.181, z - half_height),
        (x + half_width, y + 0.181, z - half_height),
        (x + half_width, y + 0.181, z + half_height),
        (x - half_width, y + 0.181, z + half_height),
    ]
    add_artwork_quad(name + "_Image", path, verts, (3, 2, 1, 0))


def add_palace_mosaic(center, floor_mat, gold, glow_mat):
    """Create a low-profile compass and wave mosaic in the palace nave."""
    x, y, z = center
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=2.05, depth=0.055, location=(x, y, z))
    base = bpy.context.object
    base.name = "PalaceInterior_MosaicBase"
    base.data.materials.append(floor_mat)
    for index, radius in enumerate((0.72, 1.45, 1.92)):
        bpy.ops.mesh.primitive_torus_add(
            major_radius=radius,
            minor_radius=0.035 if index < 2 else 0.055,
            major_segments=40,
            minor_segments=8,
            location=(x, y, z + 0.055),
        )
        ring = bpy.context.object
        ring.name = f"PalaceInterior_MosaicRing_{index:02d}"
        ring.data.materials.append(gold if index != 1 else glow_mat)
    for index in range(12):
        angle = index * math.tau / 12
        length = 1.72 if index % 2 == 0 else 1.24
        add_box(
            f"PalaceInterior_MosaicRay_{index:02d}",
            (0.045, length, 0.032),
            (x + math.sin(angle) * length * 0.46, y + math.cos(angle) * length * 0.46, z + 0.068),
            gold if index % 2 == 0 else glow_mat,
            rotation=(0, 0, -angle),
            bevel=0.008,
        )
    bpy.ops.mesh.primitive_cylinder_add(vertices=36, radius=0.28, depth=0.09, location=(x, y, z + 0.085))
    core = bpy.context.object
    core.name = "PalaceInterior_MosaicCore"
    core.data.materials.append(glow_mat)


def add_palace_artifact(name, location, variant, stone_dark, gold, glass):
    """Create a compact museum plinth and one stylized Atlantean relic."""
    x, y, floor_z = location
    bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.62, depth=0.56, location=(x, y, floor_z + 0.28))
    plinth = bpy.context.object
    plinth.name = name + "_Plinth"
    plinth.data.materials.append(stone_dark)
    bevel = plinth.modifiers.new("PlinthBevel", "BEVEL")
    bevel.width = 0.07
    bevel.segments = 2
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.52,
        minor_radius=0.045,
        major_segments=28,
        minor_segments=8,
        location=(x, y, floor_z + 0.57),
    )
    rim = bpy.context.object
    rim.name = name + "_GoldRim"
    rim.data.materials.append(gold)
    relic_z = floor_z + 1.05
    if variant == "orb":
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=0.34, location=(x, y, relic_z))
        relic = bpy.context.object
        relic.name = name + "_MemoryOrb"
        relic.data.materials.append(glass)
        for ring_index, rotation in enumerate(((0, 0, 0), (math.pi / 2, 0, 0))):
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.46,
                minor_radius=0.035,
                major_segments=24,
                minor_segments=6,
                location=(x, y, relic_z),
                rotation=rotation,
            )
            orbit = bpy.context.object
            orbit.name = name + f"_Orbit_{ring_index:02d}"
            orbit.data.materials.append(gold)
    elif variant == "crown":
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.34,
            minor_radius=0.075,
            major_segments=24,
            minor_segments=7,
            location=(x, y, relic_z - 0.18),
        )
        crown = bpy.context.object
        crown.name = name + "_TidalCrown"
        crown.data.materials.append(gold)
        for spike_index in range(7):
            angle = spike_index * math.tau / 7
            add_box(
                name + f"_CrownRay_{spike_index:02d}",
                (0.055, 0.055, 0.58 + 0.10 * (spike_index % 2)),
                (x + math.cos(angle) * 0.30, y + math.sin(angle) * 0.30, relic_z + 0.08),
                gold,
                rotation=(0.14 * math.sin(angle), 0.14 * math.cos(angle), angle),
                bevel=0.012,
            )
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.16, location=(x, y, relic_z + 0.15))
        gem = bpy.context.object
        gem.name = name + "_CrownGem"
        gem.data.materials.append(glass)
    else:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.38, location=(x, y, relic_z))
        shell = bpy.context.object
        shell.name = name + "_PearlReliquary"
        shell.scale = (1.0, 0.62, 1.18)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        shell.data.materials.append(glass)
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.40,
            minor_radius=0.05,
            major_segments=28,
            minor_segments=7,
            location=(x, y, relic_z),
            rotation=(math.pi / 2, 0, 0),
        )
        clasp = bpy.context.object
        clasp.name = name + "_ReliquaryClasp"
        clasp.data.materials.append(gold)


def add_palace_interior(repo, art_paths, stone, stone_dark, floor_mat, gold, glow_mat, glass_mat):
    """Populate the existing open palace nave with a complete museum program."""
    # The palace instance is rotated 180 degrees at world y=-52; the open portal
    # sits at y=-48 and the rear sanctum wall at y=-56.3.
    side_paths = list(art_paths[:6])
    while side_paths and len(side_paths) < 6:
        side_paths.extend(side_paths)
    for side_index, (x, inward_sign) in enumerate(((-4.70, 1), (4.70, -1))):
        for row, y in enumerate((-50.5, -52.75, -55.0)):
            path = side_paths[side_index * 3 + row]
            add_gallery_art_panel(
                f"PalaceInterior_SideArtwork_{side_index}_{row}",
                path,
                x,
                y,
                2.70,
                inward_sign,
                gold,
                stone_dark,
            )
            add_box(
                f"PalaceInterior_ArtworkPlaque_{side_index}_{row}",
                (0.10, 0.72, 0.12),
                (x + inward_sign * 0.26, y, 1.48),
                glow_mat,
                bevel=0.02,
            )
    focal_path = art_paths[6] if len(art_paths) > 6 else side_paths[0]
    # Mount the focal work on the front of the existing rear sanctum block;
    # placing it on the rear wall would hide it inside that architecture.
    add_rear_art_panel("PalaceInterior_FocalArtwork", focal_path, 0.0, -54.55, 4.05, gold, stone_dark)

    add_palace_mosaic((0.0, -52.65, 0.985), floor_mat, gold, glow_mat)
    artifact_specs = (
        ("PalaceRelic_NW", (-2.35, -50.65, 0.96), "orb"),
        ("PalaceRelic_NE", (2.35, -50.65, 0.96), "reliquary"),
        ("PalaceRelic_SW", (-2.35, -54.55, 0.96), "crown"),
        ("PalaceRelic_SE", (2.35, -54.55, 0.96), "orb"),
    )
    for name, location, variant in artifact_specs:
        add_palace_artifact(name, location, variant, stone_dark, gold, glass_mat)

    # Gold ceiling ribs and restrained luminous pendants give the nave depth.
    for index, y in enumerate((-50.2, -52.55, -54.9)):
        add_box(f"PalaceInterior_CeilingRib_{index:02d}", (8.5, 0.12, 0.12), (0, y, 5.82), gold, bevel=0.025)
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.16, location=(0, y, 4.75))
        pendant = bpy.context.object
        pendant.name = f"PalaceInterior_Pendant_{index:02d}"
        pendant.data.materials.append(glow_mat)
        add_box(f"PalaceInterior_PendantStem_{index:02d}", (0.035, 0.035, 0.95), (0, y, 5.28), gold, bevel=0.008)

    # Level entrance threshold and shallow gold guide lines make the hall walkable.
    add_box("PalaceInterior_Threshold", (4.0, 1.25, 0.13), (0, -48.55, 0.91), floor_mat, bevel=0.05)
    for x in (-1.55, 1.55):
        add_box(f"PalaceInterior_AisleGuide_{x:+.2f}", (0.045, 6.9, 0.025), (x, -52.2, 1.01), gold, bevel=0.008)


def palace_materials():
    """A quieter interior palette: oxidized bronze, deep stone, warm light."""
    bronze = bpy.data.materials.get("PalaceBrushedBronze_mat") or material(
        "PalaceBrushedBronze_mat", (0.34, 0.20, 0.075, 1.0), metallic=0.74, roughness=0.42
    )
    oxidized = bpy.data.materials.get("PalaceOxidizedBronze_mat") or material(
        "PalaceOxidizedBronze_mat", (0.055, 0.22, 0.22, 1.0), metallic=0.48, roughness=0.58
    )
    wall = bpy.data.materials.get("PalaceInteriorWall_mat") or material(
        "PalaceInteriorWall_mat", (0.025, 0.095, 0.115, 1.0), metallic=0.02, roughness=0.88
    )
    floor = bpy.data.materials.get("PalaceInteriorFloor_mat") or material(
        "PalaceInteriorFloor_mat", (0.038, 0.085, 0.095, 1.0), metallic=0.03, roughness=0.78
    )
    warm = bpy.data.materials.get("PalaceWarmLight_mat") or emissive_material(
        "PalaceWarmLight_mat", (0.62, 0.39, 0.17), strength=0.42
    )
    glass = bpy.data.materials.get("PalaceMutedGlass_mat") or emissive_material(
        "PalaceMutedGlass_mat", (0.055, 0.29, 0.34), strength=0.16
    )
    return bronze, oxidized, wall, floor, warm, glass


def apply_window_light_variation() -> None:
    """Replace uniform salmon windows with a lived-in champagne rhythm."""
    bright = emissive_material("WindowChampagneBright_mat", (0.78, 0.49, 0.22), strength=1.65)
    medium = emissive_material("WindowChampagneMedium_mat", (0.46, 0.27, 0.10), strength=0.72)
    dim = emissive_material("WindowChampagneDim_mat", (0.16, 0.11, 0.055), strength=0.16)
    unlit = material("WindowUnlitGlass_mat", (0.012, 0.050, 0.060, 1.0), metallic=0.06, roughness=0.58)
    window_objects = sorted((obj for obj in bpy.data.objects if "WindowGlow" in obj.name), key=lambda obj: obj.name)
    for index, obj in enumerate(window_objects):
        if not hasattr(obj.data, "materials"):
            continue
        if index % 7 == 0:
            chosen = unlit
        elif index % 4 == 0:
            chosen = dim
        elif index % 3 == 0:
            chosen = medium
        else:
            chosen = bright
        obj.data.materials.clear()
        obj.data.materials.append(chosen)


def add_palace_forecourt_and_wings_v2(stone, stone_dark, floor_mat, gold, glow_mat, library, guide_glow_mat=None):
    """Create a continuous museum circuit from both side galleries to the palace."""
    bronze, oxidized, _wall, _interior_floor, warm, _glass = palace_materials()

    # A wider, calmer forecourt gives the enlarged palace enough visual ground.
    add_box("PalaceForecourtLower", (28.0, 8.8, 0.24), (0, -43.0, 0.12), stone_dark, bevel=0.14)
    add_box("PalaceForecourtMiddle", (24.8, 6.9, 0.18), (0, -44.0, 0.30), stone, bevel=0.10)
    add_box("PalaceForecourtUpper", (21.4, 5.0, 0.14), (0, -45.0, 0.46), floor_mat, bevel=0.07)
    for x in (-9.8, 9.8):
        add_box(f"PalaceForecourtBronzeLine_{x:+.2f}", (0.055, 7.6, 0.025), (x, -43.1, 0.55), bronze, bevel=0.008)
    for x in (-3.6, 3.6):
        add_box(f"PalaceForecourtGuide_{x:+.2f}", (0.035, 7.8, 0.020), (x, -43.0, 0.56), oxidized, bevel=0.006)

    # Each cloister begins at the new rear doorway in the side gallery and
    # runs directly to an open palace portico. This is a real circulation path.
    for side_name, x in (("L", -11.5), ("R", 11.5)):
        side_sign = -1 if x < 0 else 1
        inner_x = x - side_sign * 1.55
        outer_x = x + side_sign * 1.55
        add_box(f"MuseumWingFloor_{side_name}", (3.35, 12.2, 0.16), (x, -40.45, 0.39), floor_mat, bevel=0.06)
        add_box(f"MuseumWingThreshold_{side_name}", (3.0, 1.25, 0.13), (x, -34.62, 0.43), floor_mat, bevel=0.05)
        add_box(f"MuseumWingOuterWall_{side_name}", (0.34, 12.0, 3.78), (outer_x, -40.45, 2.28), stone_dark, bevel=0.08)
        add_box(f"MuseumWingOuterDado_{side_name}", (0.42, 11.75, 0.82), (outer_x - side_sign * 0.03, -40.45, 0.91), stone, bevel=0.05)
        add_box(f"MuseumWingRoof_{side_name}", (3.55, 12.05, 0.24), (x, -40.45, 4.24), stone, bevel=0.07)
        add_box(f"MuseumWingRoofBronzeRib_{side_name}", (0.075, 11.75, 0.055), (x, -40.45, 4.39), bronze, bevel=0.010)
        add_box(f"MuseumWingEntablature_{side_name}", (0.46, 11.7, 0.28), (inner_x, -40.45, 3.96), stone_dark, bevel=0.05)
        add_box(f"MuseumWingEntablatureBronze_{side_name}", (0.52, 11.55, 0.06), (inner_x, -40.45, 4.13), bronze, bevel=0.012)

        for index, y in enumerate((-35.4, -38.0, -40.6, -43.2, -45.7)):
            bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.25, depth=3.55, location=(inner_x, y, 2.17))
            column = bpy.context.object
            column.name = f"MuseumWingColumn_{side_name}_{index:02d}"
            column.data.materials.append(stone)
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.31,
                minor_radius=0.042,
                major_segments=20,
                minor_segments=6,
                location=(inner_x, y, 3.93),
            )
            bpy.context.object.name = f"MuseumWingColumnCap_{side_name}_{index:02d}"
            bpy.context.object.data.materials.append(bronze)

        # Warm recessed wall washers replace jewel-like sconces.
        for bay_index, y in enumerate((-36.7, -40.45, -44.2)):
            add_box(
                f"MuseumWingWallWash_{side_name}_{bay_index:02d}",
                (0.055, 0.72, 0.16),
                (outer_x - side_sign * 0.19, y, 2.68),
                warm,
                bevel=0.015,
            )

        # Open portico at the palace end. No glowing solid door.
        instance(
            library["arch"],
            f"PalaceSidePorticoArch_{side_name}",
            (x, -46.28, 0.48),
            scale=(0.88, 0.88, 0.88),
        )
        for portico_x in (x - 1.62, x + 1.62):
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.30, depth=4.05, location=(portico_x, -46.28, 2.49))
            portico_column = bpy.context.object
            portico_column.name = f"PalaceSidePorticoColumn_{side_name}_{portico_x:+.2f}"
            portico_column.data.materials.append(stone)
        add_box(f"PalaceSidePorticoCanopy_{side_name}", (4.05, 2.2, 0.30), (x, -46.28, 4.62), stone_dark, bevel=0.08)
        add_box(f"PalaceSidePorticoBronze_{side_name}", (3.55, 2.28, 0.07), (x, -46.28, 4.82), bronze, bevel=0.012)

        # Short transverse apron visibly joins the portico to the palace base.
        connector_center_x = side_sign * 9.85
        add_box(
            f"PalaceSideConnector_{side_name}",
            (3.65, 2.45, 0.16),
            (connector_center_x, -46.34, 0.47),
            floor_mat,
            bevel=0.06,
        )

    # The title sits higher on the enlarged facade and uses warm, low-output light.
    add_box("PalaceMuseumTitlePlaque", (6.2, 0.30, 0.72), (0, -46.74, 5.82), stone_dark, bevel=0.08)
    add_box("PalaceMuseumTitleUnderline", (5.35, 0.08, 0.055), (0, -46.54, 5.55), bronze, bevel=0.010)
    add_wayfinding_text(
        "PalaceMuseumTitle",
        "THE SUNKEN ARCHIVE",
        (0, -46.525, 5.88),
        (0, 1, 0),
        warm,
        size=0.285,
    )


def add_palace_nave_shell_v2(stone, stone_dark, floor_mat, gold, glow_mat):
    """Build a larger, quieter nave inside the enlarged palace shell."""
    bronze, oxidized, wall, interior_floor, warm, glass = palace_materials()
    floor_z = 0.92
    hall_center_y = -56.15
    hall_width = 14.65
    hall_depth = 17.1
    wall_x = 7.48

    add_box("PalaceNaveFloor", (hall_width, hall_depth, 0.16), (0, hall_center_y, floor_z), interior_floor, bevel=0.055)
    add_box("PalaceNaveFloorBorder", (hall_width - 0.65, hall_depth - 0.55, 0.035), (0, hall_center_y, floor_z + 0.10), oxidized, bevel=0.012)

    for side_name, x, inward_sign in (("L", -wall_x, 1), ("R", wall_x, -1)):
        add_box(f"PalaceNaveSideWall_{side_name}", (0.42, hall_depth, 7.05), (x, hall_center_y, 4.48), wall, bevel=0.10)
        add_box(f"PalaceNaveDado_{side_name}", (0.48, hall_depth - 0.35, 1.15), (x + inward_sign * 0.04, hall_center_y, 1.64), stone_dark, bevel=0.06)
        add_box(f"PalaceNaveSideCornice_{side_name}", (0.54, hall_depth - 0.30, 0.18), (x, hall_center_y, 7.91), bronze, bevel=0.025)
        for bay_index, y in enumerate((-51.35, -56.0, -60.65)):
            add_box(
                f"PalaceNaveArtNiche_{side_name}_{bay_index:02d}",
                (0.17, 3.05, 2.75),
                (x + inward_sign * 0.25, y, 3.55),
                stone_dark,
                bevel=0.07,
            )
        for pier_index, y in enumerate((-49.2, -53.7, -58.35, -62.9)):
            add_box(
                f"PalaceNavePilaster_{side_name}_{pier_index:02d}",
                (0.28, 0.38, 5.95),
                (x + inward_sign * 0.24, y, 4.18),
                stone,
                bevel=0.045,
            )
            add_box(
                f"PalaceNavePilasterBronze_{side_name}_{pier_index:02d}",
                (0.34, 0.46, 0.08),
                (x + inward_sign * 0.29, y, 7.20),
                bronze,
                bevel=0.012,
            )

    add_barrel_vault("PalaceNaveVault", (0.0, hall_center_y), 15.35, hall_depth + 0.20, 7.92, 3.05, wall)
    for rib_index, y in enumerate((-63.7, -60.7, -57.7, -54.7, -51.7, -48.7)):
        add_barrel_vault(
            f"PalaceNaveVaultRib_{rib_index:02d}",
            (0.0, y),
            15.55,
            0.12,
            7.96,
            3.10,
            bronze,
        )

    add_box("PalaceNaveRearSanctum", (hall_width, 0.42, 7.40), (0, -64.72, 4.62), wall, bevel=0.10)
    add_box("PalaceNaveRearRecess", (6.15, 0.18, 4.35), (0, -64.48, 4.14), stone_dark, bevel=0.08)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32,
        radius=0.82,
        depth=0.12,
        location=(0, -64.43, 7.05),
        rotation=(math.pi / 2, 0, 0),
    )
    oculus = bpy.context.object
    oculus.name = "PalaceNaveRearOculus"
    oculus.data.materials.append(glass)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.94,
        minor_radius=0.065,
        major_segments=32,
        minor_segments=8,
        location=(0, -64.30, 7.05),
        rotation=(math.pi / 2, 0, 0),
    )
    bpy.context.object.name = "PalaceNaveRearOculusBronzeRim"
    bpy.context.object.data.materials.append(bronze)

    # A broad, level threshold makes the enlarged hall genuinely enterable.
    add_box("PalaceInterior_Threshold", (6.2, 1.75, 0.13), (0, -47.62, 0.91), interior_floor, bevel=0.05)
    add_box("PalaceInterior_ThresholdBronze", (5.4, 0.06, 0.028), (0, -47.02, 1.00), bronze, bevel=0.008)

    # Monumental inner colonnade gives the nave a readable palace order while
    # leaving the artwork walls visible behind it.
    for side_name, x in (("L", -5.65), ("R", 5.65)):
        for index, y in enumerate((-50.0, -54.1, -58.2, -62.3)):
            bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.34, depth=6.15, location=(x, y, 4.10))
            column = bpy.context.object
            column.name = f"PalaceInnerColumn_{side_name}_{index:02d}"
            column.data.materials.append(stone)
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.43,
                minor_radius=0.055,
                major_segments=24,
                minor_segments=7,
                location=(x, y, 7.18),
            )
            capital = bpy.context.object
            capital.name = f"PalaceInnerCapital_{side_name}_{index:02d}"
            capital.data.materials.append(bronze)

    # Upper side loggias and balustrades introduce the multi-level hierarchy
    # present in stronger Atlantis reconstructions.
    for side_name, x, rail_x in (("L", -6.72, -5.92), ("R", 6.72, 5.92)):
        add_box(f"PalaceUpperGallery_{side_name}", (1.52, 15.4, 0.18), (x, -56.2, 6.22), stone_dark, bevel=0.06)
        add_box(f"PalaceUpperGalleryBronze_{side_name}", (0.08, 15.1, 0.08), (rail_x, -56.2, 6.38), bronze, bevel=0.014)
        for index, y in enumerate((-62.8, -60.2, -57.6, -55.0, -52.4, -49.8)):
            add_box(
                f"PalaceUpperBaluster_{side_name}_{index:02d}",
                (0.075, 0.075, 0.70),
                (rail_x, y, 6.70),
                bronze,
                bevel=0.012,
            )
        add_box(f"PalaceUpperHandrail_{side_name}", (0.10, 15.1, 0.10), (rail_x, -56.2, 7.05), bronze, bevel=0.018)

    # Twin ceremonial stairs make both upper loggias physically reachable.
    # They rise toward the rear sanctum, leaving the central procession axis
    # and the first two artwork bays unobstructed.
    for side_name, x in (("L", -6.55), ("R", 6.55)):
        for step_index in range(11):
            step_height = 0.48 * (step_index + 1)
            step_y = -57.95 - step_index * 0.52
            add_box(
                f"PalaceGalleryStair_{side_name}_{step_index:02d}",
                (1.42, 0.58, step_height),
                (x, step_y, floor_z + step_height * 0.5 + 0.08),
                interior_floor if step_index % 2 else stone_dark,
                bevel=0.035,
            )
            add_box(
                f"PalaceGalleryStairBronze_{side_name}_{step_index:02d}",
                (1.30, 0.035, 0.032),
                (x, step_y - 0.275, floor_z + step_height + 0.105),
                bronze,
                bevel=0.006,
            )
        add_box(
            f"PalaceGalleryStairLanding_{side_name}",
            (1.50, 1.15, 0.18),
            (x, -63.52, 6.16),
            stone_dark,
            bevel=0.05,
        )

    # A three-step archival dais replaces the throne-room cliché and gives the
    # focal work ceremonial presence.
    for step_index, (width, depth, height, y) in enumerate(
        (
            (8.4, 2.30, 0.18, -63.05),
            (7.2, 1.72, 0.18, -63.58),
            (6.0, 1.12, 0.18, -64.05),
        )
    ):
        add_box(
            f"PalaceSanctumDais_{step_index:02d}",
            (width, depth, height),
            (0, y, 1.08 + step_index * 0.16),
            interior_floor if step_index != 1 else stone_dark,
            bevel=0.045,
        )
    add_box("PalaceSanctumDaisBronze", (5.5, 0.055, 0.035), (0, -63.55, 1.46), bronze, bevel=0.008)

    # Three muted ceiling oculi explain the filtered light without turning the
    # ceiling into a sci-fi light panel.
    for index, y in enumerate((-51.3, -56.2, -61.1)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=36, radius=0.66, depth=0.055, location=(0, y, 10.66))
        oculus_glass = bpy.context.object
        oculus_glass.name = f"PalaceCeilingOculus_{index:02d}"
        oculus_glass.data.materials.append(glass)
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.76,
            minor_radius=0.055,
            major_segments=36,
            minor_segments=7,
            location=(0, y, 10.70),
        )
        oculus_rim = bpy.context.object
        oculus_rim.name = f"PalaceCeilingOculusRim_{index:02d}"
        oculus_rim.data.materials.append(bronze)

    # A restrained wave frieze ties the interior to the exterior marine motif.
    for side_name, x, rotation in (("L", -7.20, (0, math.pi / 2, 0)), ("R", 7.20, (0, math.pi / 2, 0))):
        for index, y in enumerate((-52.6, -56.2, -59.8)):
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.33,
                minor_radius=0.034,
                major_segments=24,
                minor_segments=6,
                location=(x, y, 6.65),
                rotation=rotation,
            )
            medallion = bpy.context.object
            medallion.name = f"PalaceWaveFrieze_{side_name}_{index:02d}"
            medallion.scale = (1.0, 1.0, 0.62)
            medallion.data.materials.append(oxidized)


def add_refined_side_art_panel(name, path, x, y, z, inward_sign, bronze, backing):
    add_box(name + "_Backing", (0.20, 2.72, 2.18), (x, y, z), backing, bevel=0.065)
    add_box(name + "_Frame", (0.14, 2.42, 1.88), (x + inward_sign * 0.075, y, z), bronze, bevel=0.025)
    plane_x = x + inward_sign * 0.182
    half_width = 1.08
    half_height = 0.84
    verts = [
        (plane_x, y - half_width, z - half_height),
        (plane_x, y + half_width, z - half_height),
        (plane_x, y + half_width, z + half_height),
        (plane_x, y - half_width, z + half_height),
    ]
    face = (0, 1, 2, 3) if inward_sign > 0 else (3, 2, 1, 0)
    mesh = bpy.data.meshes.new(name + "_Image_mesh")
    mesh.from_pydata(verts, [], [face])
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    uv_values = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    if inward_sign < 0:
        uv_values = tuple(reversed(uv_values))
    for loop, uv in zip(mesh.loops, uv_values):
        uv_layer.data[loop.index].uv = uv
    art = bpy.data.objects.new(name + "_Image", mesh)
    bpy.context.scene.collection.objects.link(art)
    art.name = name + "_Image"
    art.data.materials.append(image_material(path, name + "_mat", emission_strength=0.62))


def add_refined_focal_art(path, bronze, backing):
    x, y, z = 0.0, -64.34, 4.38
    add_box("PalaceInterior_FocalArtwork_Backing", (4.25, 0.18, 3.05), (x, y, z), backing, bevel=0.075)
    add_box("PalaceInterior_FocalArtwork_Frame", (3.70, 0.12, 2.52), (x, y + 0.08, z), bronze, bevel=0.03)
    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(x, y + 0.151, z), rotation=(-math.pi / 2, 0, 0))
    art = bpy.context.object
    art.name = "PalaceInterior_FocalArtwork_Image"
    art.scale = (1.65, 1.09, 1.0)
    art.data.materials.append(image_material(path, "PalaceInterior_FocalArtwork_mat"))


def add_palace_floor_inlay(center, floor, bronze, oxidized):
    """Restrained archaeological inlay replacing the luminous compass."""
    x, y, z = center
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=2.55, depth=0.035, location=(x, y, z))
    base = bpy.context.object
    base.name = "PalaceInterior_InlayBase"
    base.data.materials.append(floor)
    for index, (radius, material_ref) in enumerate(((2.30, bronze), (1.48, oxidized), (0.62, bronze))):
        bpy.ops.mesh.primitive_torus_add(
            major_radius=radius,
            minor_radius=0.028 if index else 0.045,
            major_segments=48,
            minor_segments=6,
            location=(x, y, z + 0.035),
        )
        ring = bpy.context.object
        ring.name = f"PalaceInterior_InlayRing_{index:02d}"
        ring.data.materials.append(material_ref)
    add_box("PalaceInterior_InlayAxis_NS", (0.038, 3.45, 0.024), (x, y, z + 0.048), bronze, bevel=0.006)
    add_box("PalaceInterior_InlayAxis_EW", (3.45, 0.038, 0.024), (x, y, z + 0.048), bronze, bevel=0.006)


def add_palace_interior_v2(repo, art_paths, stone, stone_dark, floor_mat, gold, glow_mat, glass_mat):
    """Curate the enlarged nave with restrained museum furnishings."""
    bronze, oxidized, wall, interior_floor, warm, glass = palace_materials()
    side_paths = list(art_paths[:6])
    while side_paths and len(side_paths) < 6:
        side_paths.extend(side_paths)
    for side_index, (x, inward_sign) in enumerate(((-7.20, 1), (7.20, -1))):
        for row, y in enumerate((-51.35, -56.0, -60.65)):
            path = side_paths[side_index * 3 + row]
            add_refined_side_art_panel(
                f"PalaceInterior_SideArtwork_{side_index}_{row}",
                path,
                x,
                y,
                3.55,
                inward_sign,
                bronze,
                wall,
            )
            add_box(
                f"PalaceInterior_ArtworkPlaque_{side_index}_{row}",
                (0.055, 0.58, 0.08),
                (x + inward_sign * 0.19, y, 2.25),
                oxidized,
                bevel=0.012,
            )

    focal_path = art_paths[6] if len(art_paths) > 6 else side_paths[0]
    add_refined_focal_art(focal_path, bronze, wall)
    add_palace_floor_inlay((0.0, -56.05, 1.025), interior_floor, bronze, oxidized)

    # Two low benches create scale and pause without blocking the center axis.
    for side_name, x in (("L", -2.65), ("R", 2.65)):
        add_box(f"PalaceInterior_BenchSeat_{side_name}", (2.15, 0.58, 0.16), (x, -55.8, 1.42), stone_dark, bevel=0.06)
        for leg_y in (-56.02, -55.58):
            add_box(f"PalaceInterior_BenchLeg_{side_name}_{leg_y:.2f}", (0.18, 0.18, 0.48), (x, leg_y, 1.16), bronze, bevel=0.025)

    # One stone fragment and one bronze ring replace the four fantasy orbs.
    add_box("PalaceRelic_LeftPlinth", (1.25, 1.25, 0.48), (-4.65, -62.55, 1.18), stone_dark, bevel=0.07)
    add_box(
        "PalaceRelic_LeftStele",
        (0.52, 0.40, 2.15),
        (-4.65, -62.55, 2.35),
        stone,
        rotation=(0.08, -0.06, -0.10),
        bevel=0.10,
    )
    add_box("PalaceRelic_RightPlinth", (1.25, 1.25, 0.48), (4.65, -62.55, 1.18), stone_dark, bevel=0.07)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.72,
        minor_radius=0.075,
        major_segments=36,
        minor_segments=8,
        location=(4.65, -62.55, 2.30),
        rotation=(math.pi / 2, 0, 0),
    )
    ring = bpy.context.object
    ring.name = "PalaceRelic_RightBronzeRing"
    ring.data.materials.append(bronze)

    # Recessed warm discs provide illumination without glowing bars.
    for index, y in enumerate((-50.2, -53.2, -56.2, -59.2, -62.2)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.22, depth=0.055, location=(0, y, 7.82))
        fixture = bpy.context.object
        fixture.name = f"PalaceInterior_RecessedLight_{index:02d}"
        fixture.data.materials.append(warm)

    for x in (-2.25, 2.25):
        add_box(f"PalaceInterior_AisleInlay_{x:+.2f}", (0.035, 15.6, 0.022), (x, -56.0, 1.02), bronze, bevel=0.006)


def add_palace_rear_extension_v3(stone, stone_dark, floor_mat, glow_mat):
    """Increase palace scale through depth and height, never through frontage.

    Everything in this extension begins behind y=-58.6.  The side galleries
    and their cloisters occupy the forward museum district and therefore keep
    their original silhouettes and circulation clearance.
    """
    bronze, oxidized, wall, interior_floor, warm, glass = palace_materials()

    add_box("PalaceCoreRearLowerPlinth", (17.2, 9.2, 0.34), (0, -63.30, 0.20), stone_dark, bevel=0.13)
    add_box("PalaceCoreRearUpperPlinth", (15.8, 8.2, 0.28), (0, -63.15, 0.52), stone, bevel=0.09)
    for side_name, x in (("L", -6.55), ("R", 6.55)):
        add_box(f"PalaceCoreRearWing_{side_name}", (3.15, 8.15, 3.72), (x, -62.25, 2.47), stone_dark, bevel=0.11)
        add_box(f"PalaceCoreRearWingCornice_{side_name}", (3.42, 8.32, 0.18), (x, -62.25, 4.38), bronze, bevel=0.028)
        for bay_index, y in enumerate((-59.65, -62.20, -64.75)):
            add_box(
                f"PalaceCoreRearWingWindowFrame_{side_name}_{bay_index:02d}",
                (1.02, 0.18, 1.42),
                (x, y, 2.65),
                bronze,
                bevel=0.055,
            )
            add_box(
                f"PalaceCoreRearWingWindowGlow_{side_name}_{bay_index:02d}",
                (0.72, 0.12, 1.08),
                (x, y + 0.10, 2.64),
                warm,
                bevel=0.04,
            )

        tower_y = -62.55
        bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=1.38, depth=3.85, location=(x, tower_y, 4.60))
        tower = bpy.context.object
        tower.name = f"PalaceCoreRearTower_{side_name}"
        tower.data.materials.append(stone)
        bpy.ops.mesh.primitive_torus_add(
            major_radius=1.30,
            minor_radius=0.085,
            major_segments=28,
            minor_segments=8,
            location=(x, tower_y, 6.48),
        )
        bpy.context.object.name = f"PalaceCoreRearTowerBand_{side_name}"
        bpy.context.object.data.materials.append(bronze)
        bpy.ops.mesh.primitive_cylinder_add(vertices=28, radius=0.96, depth=1.18, location=(x, tower_y, 7.10))
        lantern = bpy.context.object
        lantern.name = f"PalaceCoreRearTowerLantern_{side_name}"
        lantern.data.materials.append(warm)
        for column_index in range(8):
            angle = column_index * math.tau / 8
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=12,
                radius=0.10,
                depth=1.42,
                location=(x + math.cos(angle) * 1.18, tower_y + math.sin(angle) * 1.18, 7.10),
            )
            column = bpy.context.object
            column.name = f"PalaceCoreRearTowerColumn_{side_name}_{column_index:02d}"
            column.data.materials.append(stone)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=28, ring_count=14, location=(x, tower_y, 7.95))
        dome = bpy.context.object
        dome.name = f"PalaceCoreRearTowerDome_{side_name}"
        dome.scale = (1.42, 1.42, 0.82)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        dome.data.materials.append(stone_dark)
        add_box(f"PalaceCoreRearTowerFinial_{side_name}", (0.16, 0.16, 0.72), (x, tower_y, 9.02), bronze, bevel=0.025)

    # A second, rear rotunda creates depth in the skyline while staying behind
    # the original front palace. Its footprint remains inside x=+-3.5 m.
    rotunda_y = -63.25
    bpy.ops.mesh.primitive_cylinder_add(vertices=36, radius=3.25, depth=0.58, location=(0, rotunda_y, 9.62))
    drum = bpy.context.object
    drum.name = "PalaceCoreRearRotundaDrum"
    drum.data.materials.append(stone)
    bpy.ops.mesh.primitive_cylinder_add(vertices=36, radius=2.32, depth=1.35, location=(0, rotunda_y, 10.35))
    rotunda_glow = bpy.context.object
    rotunda_glow.name = "PalaceCoreRearRotundaGlow"
    rotunda_glow.data.materials.append(glass)
    for index in range(12):
        angle = index * math.tau / 12
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=14,
            radius=0.13,
            depth=1.65,
            location=(math.cos(angle) * 2.86, rotunda_y + math.sin(angle) * 2.54, 10.35),
        )
        column = bpy.context.object
        column.name = f"PalaceCoreRearRotundaColumn_{index:02d}"
        column.data.materials.append(stone)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=3.05,
        minor_radius=0.11,
        major_segments=40,
        minor_segments=8,
        location=(0, rotunda_y, 11.20),
    )
    bpy.context.object.name = "PalaceCoreRearRotundaBronzeBand"
    bpy.context.object.data.materials.append(bronze)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=36, ring_count=18, location=(0, rotunda_y, 11.60))
    rear_dome = bpy.context.object
    rear_dome.name = "PalaceCoreRearRotundaDome"
    rear_dome.scale = (3.28, 2.96, 1.72)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    rear_dome.data.materials.append(stone_dark)
    add_box("PalaceCoreRearRotundaFinial", (0.18, 0.18, 0.95), (0, rotunda_y, 13.78), bronze, bevel=0.028)


def add_palace_nave_shell_v3(stone, stone_dark, floor_mat, glow_mat):
    """Build a deep, two-level palace hall inside the fixed frontage."""
    bronze, oxidized, wall, interior_floor, warm, glass = palace_materials()
    floor_z = 0.92
    hall_center_y = -57.35
    hall_depth = 18.1
    hall_width = 9.62
    wall_x = 4.92

    add_box("PalaceCoreNaveFloor", (hall_width, hall_depth, 0.16), (0, hall_center_y, floor_z), interior_floor, bevel=0.055)
    add_box("PalaceCoreNaveFloorBorder", (hall_width - 0.55, hall_depth - 0.55, 0.032), (0, hall_center_y, floor_z + 0.10), oxidized, bevel=0.010)
    add_box("PalaceCoreThreshold", (5.25, 1.20, 0.13), (0, -48.02, 0.92), interior_floor, bevel=0.045)

    for side_name, x, inward_sign in (("L", -wall_x, 1), ("R", wall_x, -1)):
        add_box(f"PalaceCoreSideWall_{side_name}", (0.38, hall_depth, 5.90), (x, hall_center_y, 3.95), wall, bevel=0.09)
        add_box(f"PalaceCoreDado_{side_name}", (0.44, hall_depth - 0.35, 1.02), (x, hall_center_y, 1.52), stone_dark, bevel=0.05)
        add_box(f"PalaceCoreCornice_{side_name}", (0.48, hall_depth - 0.25, 0.16), (x, hall_center_y, 6.92), bronze, bevel=0.022)
        for pier_index, y in enumerate((-49.4, -53.0, -56.7, -60.4, -64.1)):
            add_box(
                f"PalaceCorePilaster_{side_name}_{pier_index:02d}",
                (0.26, 0.34, 5.05),
                (x + inward_sign * 0.22, y, 3.82),
                stone,
                bevel=0.04,
            )

    add_barrel_vault("PalaceCoreNaveVault", (0.0, hall_center_y), 10.15, hall_depth + 0.12, 6.86, 2.42, wall)
    for rib_index, y in enumerate((-65.7, -62.8, -59.9, -57.0, -54.1, -51.2, -48.5)):
        add_barrel_vault(
            f"PalaceCoreVaultRib_{rib_index:02d}",
            (0.0, y),
            10.32,
            0.10,
            6.90,
            2.46,
            bronze,
        )

    add_box("PalaceCoreRearSanctum", (hall_width, 0.40, 6.30), (0, -66.46, 4.12), wall, bevel=0.09)
    add_box("PalaceCoreRearRecess", (5.20, 0.18, 3.80), (0, -66.22, 3.95), stone_dark, bevel=0.07)

    # A glazed fanlight closes the barrel-vault end while preserving a view of
    # filtered seawater. Bronze radial ribs make the opening read as palace
    # ornament rather than an unfinished hole in the rear wall.
    fanlight_y = -66.18
    fanlight_base_z = 6.86
    fanlight_radius = 5.02
    fanlight_rise = 2.38
    segments = 24
    fanlight_verts = [(0.0, fanlight_y, fanlight_base_z)]
    fanlight_arc = []
    for index in range(segments + 1):
        angle = math.pi * index / segments
        point = (
            fanlight_radius * math.cos(angle),
            fanlight_y,
            fanlight_base_z + fanlight_rise * math.sin(angle),
        )
        fanlight_verts.append(point)
        fanlight_arc.append(point)
    fanlight_faces = [(0, index + 2, index + 1) for index in range(segments)]
    fanlight_mesh = bpy.data.meshes.new("PalaceCoreRearFanlightGlass_mesh")
    fanlight_mesh.from_pydata(fanlight_verts, [], fanlight_faces)
    fanlight_mesh.update()
    fanlight = bpy.data.objects.new("PalaceCoreRearFanlightGlass", fanlight_mesh)
    bpy.context.scene.collection.objects.link(fanlight)
    fanlight.data.materials.append(glass)
    add_curve_tube("PalaceCoreRearFanlightArch", fanlight_arc, 0.07, bronze, resolution=1)
    add_box(
        "PalaceCoreRearFanlightSill",
        (fanlight_radius * 2.0, 0.11, 0.11),
        (0, fanlight_y + 0.04, fanlight_base_z),
        bronze,
        bevel=0.018,
    )
    for spoke_index in range(1, 8):
        angle = math.pi * spoke_index / 8
        endpoint = (
            fanlight_radius * math.cos(angle),
            fanlight_y + 0.04,
            fanlight_base_z + fanlight_rise * math.sin(angle),
        )
        add_curve_tube(
            f"PalaceCoreRearFanlightSpoke_{spoke_index:02d}",
            [(0.0, fanlight_y + 0.04, fanlight_base_z), endpoint],
            0.035,
            bronze,
            resolution=1,
        )

    # Colonnade and upper galleries create a palace hierarchy without widening
    # beyond the original 10 m building envelope.
    for side_name, x in (("L", -3.58), ("R", 3.58)):
        for index, y in enumerate((-50.2, -53.8, -57.4, -61.0, -64.2)):
            bpy.ops.mesh.primitive_cylinder_add(vertices=22, radius=0.28, depth=4.95, location=(x, y, 3.53))
            column = bpy.context.object
            column.name = f"PalaceCoreInnerColumn_{side_name}_{index:02d}"
            column.data.materials.append(stone)
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.36,
                minor_radius=0.046,
                major_segments=22,
                minor_segments=7,
                location=(x, y, 6.02),
            )
            bpy.context.object.name = f"PalaceCoreInnerCapital_{side_name}_{index:02d}"
            bpy.context.object.data.materials.append(bronze)

    for side_name, x, rail_x in (("L", -4.35, -3.72), ("R", 4.35, 3.72)):
        add_box(f"PalaceCoreUpperGallery_{side_name}", (1.10, 16.55, 0.17), (x, -57.20, 5.30), stone_dark, bevel=0.05)
        for index, y in enumerate((-64.6, -62.3, -60.0, -57.7, -55.4, -53.1, -50.8, -49.0)):
            add_box(
                f"PalaceCoreUpperBaluster_{side_name}_{index:02d}",
                (0.07, 0.07, 0.62),
                (rail_x, y, 5.66),
                bronze,
                bevel=0.010,
            )
        add_box(f"PalaceCoreUpperHandrail_{side_name}", (0.09, 16.25, 0.09), (rail_x, -57.20, 6.00), bronze, bevel=0.015)

        for step_index in range(10):
            step_height = 0.43 * (step_index + 1)
            step_y = -60.00 - step_index * 0.48
            add_box(
                f"PalaceCoreGalleryStair_{side_name}_{step_index:02d}",
                (1.05, 0.54, step_height),
                (x, step_y, floor_z + step_height * 0.5 + 0.05),
                interior_floor if step_index % 2 else stone_dark,
                bevel=0.03,
            )
            add_box(
                f"PalaceCoreGalleryStairBronze_{side_name}_{step_index:02d}",
                (0.94, 0.032, 0.028),
                (x, step_y - 0.255, floor_z + step_height + 0.07),
                bronze,
                bevel=0.005,
            )
        add_box(f"PalaceCoreGalleryLanding_{side_name}", (1.12, 0.95, 0.17), (x, -64.75, 5.28), stone_dark, bevel=0.045)

    for step_index, (width, depth, y) in enumerate(((6.8, 1.65, -65.10), (5.8, 1.18, -65.65), (4.8, 0.72, -66.02))):
        add_box(
            f"PalaceCoreSanctumDais_{step_index:02d}",
            (width, depth, 0.17),
            (0, y, 1.07 + step_index * 0.15),
            interior_floor if step_index != 1 else stone_dark,
            bevel=0.04,
        )

    for index, y in enumerate((-52.0, -57.0, -62.0)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.54, depth=0.05, location=(0, y, 9.18))
        oculus = bpy.context.object
        oculus.name = f"PalaceCoreCeilingOculus_{index:02d}"
        oculus.data.materials.append(glass)
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.63,
            minor_radius=0.048,
            major_segments=32,
            minor_segments=7,
            location=(0, y, 9.21),
        )
        bpy.context.object.name = f"PalaceCoreCeilingOculusRim_{index:02d}"
        bpy.context.object.data.materials.append(bronze)

    # A continuous bronze spine and three low pendants give the vault a clear
    # ceremonial rhythm. The fixtures stay above sight lines and away from art.
    add_box(
        "PalaceCoreVaultSpine",
        (0.09, 17.25, 0.09),
        (0, -57.30, 9.34),
        bronze,
        bevel=0.016,
    )
    for pendant_index, y in enumerate((-52.0, -57.0, -62.0)):
        add_box(
            f"PalaceCorePendantStem_{pendant_index:02d}",
            (0.035, 0.035, 0.90),
            (0, y, 8.68),
            bronze,
            bevel=0.006,
        )
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, radius=0.18, location=(0, y, 8.15))
        lantern = bpy.context.object
        lantern.name = f"PalaceCorePendantLantern_{pendant_index:02d}"
        lantern.scale = (1.0, 1.0, 1.35)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        lantern.data.materials.append(warm)
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.23,
            minor_radius=0.028,
            major_segments=20,
            minor_segments=6,
            location=(0, y, 8.15),
        )
        bpy.context.object.name = f"PalaceCorePendantCage_{pendant_index:02d}"
        bpy.context.object.data.materials.append(bronze)

    # Oxidized wave medallions break up the long upper walls without competing
    # with the framed works below.
    for side_name, x in (("L", -4.70), ("R", 4.70)):
        for medallion_index, y in enumerate((-52.9, -56.9, -60.9)):
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.28,
                minor_radius=0.032,
                major_segments=22,
                minor_segments=6,
                location=(x, y, 6.30),
                rotation=(0, math.pi / 2, 0),
            )
            medallion = bpy.context.object
            medallion.name = f"PalaceCoreWaveMedallion_{side_name}_{medallion_index:02d}"
            medallion.scale = (1.0, 1.0, 0.62)
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
            medallion.data.materials.append(oxidized)

    # Inner handrails make the twin ceremonial stairs visibly usable.
    for side_name, rail_x in (("L", -3.78), ("R", 3.78)):
        rail_points = [
            (rail_x, -59.72, 1.52),
            (rail_x, -61.15, 2.80),
            (rail_x, -62.60, 4.10),
            (rail_x, -64.50, 5.62),
        ]
        add_curve_tube(f"PalaceCoreStairHandrail_{side_name}", rail_points, 0.045, bronze, resolution=1)
        for post_index, (y, z) in enumerate(((-60.0, 1.64), (-61.45, 2.95), (-62.90, 4.22), (-64.35, 5.38))):
            add_box(
                f"PalaceCoreStairRailPost_{side_name}_{post_index:02d}",
                (0.055, 0.055, 0.62),
                (rail_x, y, z),
                bronze,
                bevel=0.010,
            )


def add_palace_upper_circulation_v1(stone, stone_dark, floor_mat):
    """Close the missing circulation loop above the palace nave.

    The v3 nave already contains two stair flights and narrow side loggias.
    This pass adds the architectural pieces that make those stairs meaningful:
    a rear bridge, visible bridge edge, undercroft supports and explicit
    landing thresholds.  The central nave remains open so the focal artwork
    and ceiling volume are not buried under a second-floor slab.
    """
    bronze, oxidized, wall, interior_floor, warm, glass = palace_materials()
    upper_z = 5.30

    # Give each stair a readable lower threshold and a level upper threshold.
    # These overlap the existing stair footprint by design, hiding the abrupt
    # first/last step transitions without changing the nave envelope.
    for side_name, x in (("L", -4.35), ("R", 4.35)):
        add_box(
            f"PalaceCoreStairBaseThreshold_{side_name}",
            (1.18, 0.82, 0.16),
            (x, -59.55, 1.00),
            interior_floor,
            bevel=0.035,
        )
        add_box(
            f"PalaceCoreStairUpperThreshold_{side_name}",
            (1.18, 0.92, 0.17),
            (x, -64.56, upper_z),
            interior_floor,
            bevel=0.040,
        )
        add_box(
            f"PalaceCoreStairUpperThresholdBronze_{side_name}",
            (1.02, 0.045, 0.035),
            (x, -64.12, upper_z + 0.105),
            bronze,
            bevel=0.006,
        )

    # A narrow rear bridge joins both upper galleries while leaving the nave
    # and focal wall visually open below it.
    add_box(
        "PalaceCoreUpperRearBridge",
        (8.20, 1.22, 0.18),
        (0.0, -64.78, upper_z),
        stone_dark,
        bevel=0.055,
    )
    add_box(
        "PalaceCoreUpperRearBridgeFrontEdge",
        (8.00, 0.075, 0.08),
        (0.0, -64.16, upper_z + 0.13),
        bronze,
        bevel=0.012,
    )
    add_box(
        "PalaceCoreUpperRearBridgeBackEdge",
        (8.00, 0.075, 0.08),
        (0.0, -65.38, upper_z + 0.13),
        oxidized,
        bevel=0.012,
    )

    # The bridge railing makes the second level legible from the lower nave.
    for rail_name, y in (("Front", -64.12), ("Back", -65.38)):
        add_box(
            f"PalaceCoreUpperBridgeHandrail_{rail_name}",
            (7.95, 0.09, 0.09),
            (0.0, y, 6.08),
            bronze,
            bevel=0.014,
        )
        for post_index, x in enumerate((-3.55, -2.35, -1.15, 0.0, 1.15, 2.35, 3.55)):
            add_box(
                f"PalaceCoreUpperBridgeBaluster_{rail_name}_{post_index:02d}",
                (0.07, 0.07, 0.70),
                (x, y, 5.70),
                bronze,
                bevel=0.010,
            )

    # Two quiet supports explain the bridge load and align with the lower
    # colonnade instead of introducing arbitrary freestanding pillars.
    for side_name, x in (("L", -3.58), ("R", 3.58)):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=20,
            radius=0.22,
            depth=4.15,
            location=(x, -64.78, 3.20),
        )
        support = bpy.context.object
        support.name = f"PalaceCoreUpperBridgeSupport_{side_name}"
        support.data.materials.append(stone)
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.29,
            minor_radius=0.035,
            major_segments=20,
            minor_segments=6,
            location=(x, -64.78, 5.22),
        )
        cap = bpy.context.object
        cap.name = f"PalaceCoreUpperBridgeSupportCap_{side_name}"
        cap.data.materials.append(bronze)

    scene = bpy.context.scene
    scene["palace_upper_circulation_version"] = "v1"
    scene["palace_upper_level_z"] = upper_z
    scene["palace_upper_route"] = "left_stair-left_loggia-rear_bridge-right_loggia-right_stair"


def add_compact_side_art_panel_v3(name, path, x, y, z, inward_sign, bronze, backing):
    art_width, art_height = fit_artwork_size(path, 1.48, 1.42)
    add_box(name + "_Backing", (0.18, art_width + 0.38, art_height + 0.34), (x, y, z), backing, bevel=0.055)
    add_box(name + "_Frame", (0.13, art_width + 0.20, art_height + 0.20), (x + inward_sign * 0.07, y, z), bronze, bevel=0.022)
    plane_x = x + inward_sign * 0.155
    half_width, half_height = art_width * 0.5, art_height * 0.5
    if inward_sign > 0:
        verts = [
            (plane_x, y - half_width, z - half_height),
            (plane_x, y + half_width, z - half_height),
            (plane_x, y + half_width, z + half_height),
            (plane_x, y - half_width, z + half_height),
        ]
    else:
        verts = [
            (plane_x, y + half_width, z - half_height),
            (plane_x, y - half_width, z - half_height),
            (plane_x, y - half_width, z + half_height),
            (plane_x, y + half_width, z + half_height),
        ]
    add_artwork_quad(name + "_Image", path, verts, (0, 1, 2, 3), emission_strength=0.48)


def add_palace_interior_v3(repo, art_paths, stone, stone_dark, floor_mat, glow_mat, glass_mat):
    """Curate the safe-depth palace with quieter ceremonial museum furniture."""
    bronze, oxidized, wall, interior_floor, warm, glass = palace_materials()
    side_paths = list(art_paths[:6])
    while side_paths and len(side_paths) < 6:
        side_paths.extend(side_paths)
    for side_index, (x, inward_sign) in enumerate(((-4.70, 1), (4.70, -1))):
        for row, y in enumerate((-51.35, -55.35, -58.55)):
            add_compact_side_art_panel_v3(
                f"PalaceInterior_SideArtwork_{side_index}_{row}",
                side_paths[side_index * 3 + row],
                x,
                y,
                3.20,
                inward_sign,
                bronze,
                wall,
            )
            add_box(
                f"PalaceInterior_ArtworkPlaque_{side_index}_{row}",
                (0.05, 0.52, 0.07),
                (x + inward_sign * 0.19, y, 2.16),
                oxidized,
                bevel=0.010,
            )

    focal_path = art_paths[6] if len(art_paths) > 6 else side_paths[0]
    focal_width, focal_height = fit_artwork_size(focal_path, 3.02, 2.82)
    add_box("PalaceInterior_FocalArtwork_Backing", (focal_width + 0.50, 0.18, focal_height + 0.46), (0, -66.14, 3.85), wall, bevel=0.07)
    add_box("PalaceInterior_FocalArtwork_Frame", (focal_width + 0.24, 0.12, focal_height + 0.24), (0, -66.02, 3.85), bronze, bevel=0.028)
    half_width, half_height = focal_width * 0.5, focal_height * 0.5
    focal_verts = [
        (-half_width, -65.94, 3.85 - half_height),
        (half_width, -65.94, 3.85 - half_height),
        (half_width, -65.94, 3.85 + half_height),
        (-half_width, -65.94, 3.85 + half_height),
    ]
    focal = add_artwork_quad(
        "PalaceInterior_FocalArtwork_Image",
        focal_path,
        focal_verts,
        (3, 2, 1, 0),
        emission_strength=0.34,
    )

    add_palace_floor_inlay((0.0, -55.40, 1.025), interior_floor, bronze, oxidized)
    for side_name, x in (("L", -1.75), ("R", 1.75)):
        add_box(f"PalaceInterior_BenchSeat_{side_name}", (1.55, 0.52, 0.15), (x, -56.05, 1.38), stone_dark, bevel=0.05)
        for leg_y in (-56.23, -55.87):
            add_box(f"PalaceInterior_BenchLeg_{side_name}_{leg_y:.2f}", (0.16, 0.16, 0.42), (x, leg_y, 1.15), bronze, bevel=0.022)

    add_box("PalaceInterior_LeftStelePlinth", (1.02, 1.02, 0.42), (-2.65, -63.25, 1.16), stone_dark, bevel=0.06)
    add_box("PalaceInterior_LeftStele", (0.42, 0.34, 1.88), (-2.65, -63.25, 2.18), stone, rotation=(0.06, -0.04, -0.08), bevel=0.085)
    add_box("PalaceInterior_RightRelicPlinth", (1.02, 1.02, 0.42), (2.65, -63.25, 1.16), stone_dark, bevel=0.06)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.61,
        minor_radius=0.065,
        major_segments=32,
        minor_segments=8,
        location=(2.65, -63.25, 2.18),
        rotation=(math.pi / 2, 0, 0),
    )
    bpy.context.object.name = "PalaceInterior_RightBronzeRelic"
    bpy.context.object.data.materials.append(bronze)

    for x in (-1.65, 1.65):
        add_box(f"PalaceInterior_AisleInlay_{x:+.2f}", (0.032, 16.6, 0.020), (x, -57.1, 1.02), bronze, bevel=0.005)

    # Small recessed wall lanterns add palace warmth while preserving the art
    # as the brightest visual content on each side.
    for side_name, x, inward_sign in (("L", -4.70, 1), ("R", 4.70, -1)):
        face_x = x + inward_sign * 0.10
        for fixture_index, y in enumerate((-53.35, -57.00, -60.65)):
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=24,
                radius=0.20,
                depth=0.06,
                location=(face_x, y, 4.92),
                rotation=(0, math.pi / 2, 0),
            )
            glow_disc = bpy.context.object
            glow_disc.name = f"PalaceInterior_WallLantern_{side_name}_{fixture_index:02d}"
            glow_disc.data.materials.append(warm)
            bpy.ops.mesh.primitive_torus_add(
                major_radius=0.25,
                minor_radius=0.032,
                major_segments=24,
                minor_segments=6,
                location=(face_x + inward_sign * 0.045, y, 4.92),
                rotation=(0, math.pi / 2, 0),
            )
            bpy.context.object.name = f"PalaceInterior_WallLanternRim_{side_name}_{fixture_index:02d}"
            bpy.context.object.data.materials.append(bronze)

    # A quiet archive crest fills the band between the focal work and fanlight.
    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.58,
        minor_radius=0.050,
        major_segments=32,
        minor_segments=7,
        location=(0, -65.91, 5.66),
        rotation=(math.pi / 2, 0, 0),
    )
    crest = bpy.context.object
    crest.name = "PalaceInterior_ArchiveCrest"
    crest.scale = (1.0, 0.68, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    crest.data.materials.append(oxidized)
    for spoke_index, angle in enumerate((0.0, math.pi / 3, 2 * math.pi / 3)):
        dx = 0.46 * math.cos(angle)
        dz = 0.46 * math.sin(angle)
        add_curve_tube(
            f"PalaceInterior_ArchiveCrestSpoke_{spoke_index:02d}",
            [(-dx, -65.86, 5.66 - dz), (dx, -65.86, 5.66 + dz)],
            0.025,
            bronze,
            resolution=1,
        )


def validate_palace_core_envelope() -> None:
    """Fail the build if a rear extension can touch the forward district."""
    core_objects = [obj for obj in bpy.context.scene.objects if obj.name.startswith("PalaceCore")]
    if not core_objects:
        raise RuntimeError("PalaceCore envelope audit found no objects")
    points = [obj.matrix_world @ Vector(corner) for obj in core_objects for corner in obj.bound_box]
    bounds_min = tuple(min(point[index] for point in points) for index in range(3))
    bounds_max = tuple(max(point[index] for point in points) for index in range(3))
    safe = (
        bounds_min[0] >= -8.85
        and bounds_max[0] <= 8.85
        and bounds_min[1] >= -68.25
        and bounds_max[1] <= -47.35
        and bounds_min[2] >= -0.05
        and bounds_max[2] <= 14.50
    )
    if not safe:
        raise RuntimeError(f"PalaceCore crossed reserved envelope: min={bounds_min}, max={bounds_max}")
    scene = bpy.context.scene
    scene["palace_core_bounds_min"] = tuple(round(value, 3) for value in bounds_min)
    scene["palace_core_bounds_max"] = tuple(round(value, 3) for value in bounds_max)
    scene["palace_frontage_locked"] = True


def add_seabed(stone):
    width, depth = 70.0, 105.0
    x_segments, y_segments = 34, 52
    verts, faces = [], []
    for yi in range(y_segments + 1):
        y = 24.0 - depth * yi / y_segments
        for xi in range(x_segments + 1):
            x = -width / 2 + width * xi / x_segments
            edge = max(0.0, abs(x) - 5.0) * 0.035
            z = -0.18 + 0.12 * math.sin(x * 0.44) + 0.09 * math.cos(y * 0.31) + edge
            verts.append((x, y, z))
    stride = x_segments + 1
    for yi in range(y_segments):
        for xi in range(x_segments):
            a = yi * stride + xi
            faces.append((a, a + 1, a + 1 + stride, a + stride))
    mesh = bpy.data.meshes.new("Seabed_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Seabed", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(stone)


def set_blended(mat: bpy.types.Material) -> None:
    mat.use_backface_culling = False
    try:
        mat.surface_render_method = "DITHERED"
    except (AttributeError, TypeError):
        pass


def retune_material_family(prefix: str, base_color, roughness: float, metallic: float = 0.0) -> None:
    """Keep every appended collection copy in one underwater palette."""
    for mat in bpy.data.materials:
        if not mat.name.startswith(prefix) or not mat.use_nodes:
            continue
        bsdf = next((node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
        if not bsdf:
            continue
        base_input = bsdf.inputs["Base Color"]
        base_input.default_value = (*base_color, 1.0)
        if base_input.is_linked:
            source_socket = base_input.links[0].from_socket
            mat.node_tree.links.remove(base_input.links[0])
            tint = mat.node_tree.nodes.new("ShaderNodeMixRGB")
            tint.name = prefix + "_underwater_tint"
            tint.blend_type = "MULTIPLY"
            tint.inputs[0].default_value = 1.0
            tint.inputs[2].default_value = (*base_color, 1.0)
            mat.node_tree.links.new(source_socket, tint.inputs[1])
            mat.node_tree.links.new(tint.outputs[0], base_input)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic


def make_water_surface_material(repo: Path) -> bpy.types.Material:
    mat = bpy.data.materials.new("WaterSurface_mat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.015, 0.30, 0.48, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.22
    bsdf.inputs["IOR"].default_value = 1.333
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.0
    bsdf.inputs["Alpha"].default_value = 1.0
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (0.025, 0.34, 0.58, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 0.55
    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (3.4, 5.8, 1.0)
    mapping.inputs["Rotation"].default_value[2] = 0.22
    # Slow shader drift lets the surface read as living water in the Blender
    # review timeline while keeping the mesh itself lightweight.
    mapping.inputs["Location"].default_value = (0.0, 0.0, 0.0)
    mapping.inputs["Location"].keyframe_insert(data_path="default_value", frame=1)
    mapping.inputs["Location"].default_value = (0.42, -0.18, 0.0)
    mapping.inputs["Location"].keyframe_insert(data_path="default_value", frame=80)
    mapping.inputs["Location"].default_value = (0.84, -0.36, 0.0)
    mapping.inputs["Location"].keyframe_insert(data_path="default_value", frame=160)
    water_noise = nodes.new("ShaderNodeTexNoise")
    water_noise.inputs["Scale"].default_value = 1.65
    water_noise.inputs["Detail"].default_value = 4.2
    water_noise.inputs["Roughness"].default_value = 0.58
    water_noise.inputs["Distortion"].default_value = 0.28
    water_wave = nodes.new("ShaderNodeTexWave")
    water_wave.wave_type = "BANDS"
    water_wave.bands_direction = "X"
    water_wave.inputs["Scale"].default_value = 2.4
    water_wave.inputs["Distortion"].default_value = 7.0
    water_wave.inputs["Detail"].default_value = 4.0
    water_wave.inputs["Detail Scale"].default_value = 1.3
    wave_mix = nodes.new("ShaderNodeMixRGB")
    wave_mix.blend_type = "MULTIPLY"
    wave_mix.inputs[0].default_value = 0.62
    water_color = nodes.new("ShaderNodeValToRGB")
    water_color.color_ramp.elements[0].position = 0.20
    water_color.color_ramp.elements[0].color = (0.004, 0.105, 0.20, 1.0)
    water_color.color_ramp.elements[1].position = 0.76
    water_color.color_ramp.elements[1].color = (0.12, 0.66, 0.90, 1.0)
    middle = water_color.color_ramp.elements.new(0.48)
    middle.color = (0.018, 0.34, 0.54, 1.0)
    water_bump = nodes.new("ShaderNodeBump")
    water_bump.inputs["Strength"].default_value = 0.24
    water_bump.inputs["Distance"].default_value = 0.28
    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], water_noise.inputs["Vector"])
    links.new(mapping.outputs["Vector"], water_wave.inputs["Vector"])
    links.new(water_noise.outputs["Fac"], wave_mix.inputs[1])
    links.new(water_wave.outputs["Fac"], wave_mix.inputs[2])
    links.new(wave_mix.outputs["Color"], water_color.inputs["Fac"])
    links.new(water_color.outputs["Color"], bsdf.inputs["Base Color"])
    if "Emission Color" in bsdf.inputs:
        links.new(water_color.outputs["Color"], bsdf.inputs["Emission Color"])
    links.new(wave_mix.outputs["Color"], water_bump.inputs["Height"])
    links.new(water_bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def add_water_surface(mat: bpy.types.Material) -> bpy.types.Object:
    width, depth = 90.0, 132.0
    x_segments, y_segments = 24, 36
    verts, faces = [], []
    for yi in range(y_segments + 1):
        y = 25.0 - depth * yi / y_segments
        for xi in range(x_segments + 1):
            x = -width / 2 + width * xi / x_segments
            z = 16.4 + 0.20 * math.sin(x * 0.43 + y * 0.09) + 0.10 * math.sin(x * 0.15 - y * 0.32)
            verts.append((x, y, z))
    stride = x_segments + 1
    for yi in range(y_segments):
        for xi in range(x_segments):
            a = yi * stride + xi
            faces.append((a, a + stride, a + 1 + stride, a + 1))
    mesh = bpy.data.meshes.new("WaterSurface_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj = bpy.data.objects.new("WaterSurface", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    obj.visible_shadow = False
    return obj


def make_caustic_material() -> bpy.types.Material:
    mat = bpy.data.materials.new("CausticProjection_mat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (0.08, 0.56, 0.70, 1.0)
    emission.inputs["Strength"].default_value = 0.18
    mix_shader = nodes.new("ShaderNodeMixShader")

    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.2, 1.7, 1.0)
    mapping.inputs["Rotation"].default_value[2] = 0.16
    mapping.inputs["Location"].default_value = (0.0, 0.0, 0.0)
    mapping.inputs["Location"].keyframe_insert(data_path="default_value", frame=1)
    mapping.inputs["Location"].default_value = (-0.18, 0.28, 0.0)
    mapping.inputs["Location"].keyframe_insert(data_path="default_value", frame=80)
    mapping.inputs["Location"].default_value = (-0.36, 0.56, 0.0)
    mapping.inputs["Location"].keyframe_insert(data_path="default_value", frame=160)
    voronoi = nodes.new("ShaderNodeTexVoronoi")
    voronoi.feature = "DISTANCE_TO_EDGE"
    voronoi.distance = "EUCLIDEAN"
    # Finer cells read as projected water caustics instead of a giant cracked
    # floor mosaic when seen from the district and visitor-route cameras.
    voronoi.inputs["Scale"].default_value = 12.0
    edge_ramp = nodes.new("ShaderNodeValToRGB")
    edge_ramp.color_ramp.elements[0].position = 0.018
    edge_ramp.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
    edge_ramp.color_ramp.elements[1].position = 0.050
    edge_ramp.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)

    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.6
    noise.inputs["Detail"].default_value = 3.2
    noise.inputs["Roughness"].default_value = 0.68
    noise_scale = nodes.new("ShaderNodeMath")
    noise_scale.operation = "MULTIPLY"
    noise_scale.inputs[1].default_value = 0.58
    noise_bias = nodes.new("ShaderNodeMath")
    noise_bias.operation = "ADD"
    noise_bias.inputs[1].default_value = 0.30
    mask = nodes.new("ShaderNodeMath")
    mask.operation = "MULTIPLY"
    opacity = nodes.new("ShaderNodeMath")
    opacity.operation = "MULTIPLY"
    opacity.inputs[1].default_value = 0.34

    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], voronoi.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(voronoi.outputs["Distance"], edge_ramp.inputs["Fac"])
    links.new(noise.outputs["Fac"], noise_scale.inputs[0])
    links.new(noise_scale.outputs[0], noise_bias.inputs[0])
    links.new(edge_ramp.outputs["Color"], mask.inputs[0])
    links.new(noise_bias.outputs[0], mask.inputs[1])
    links.new(mask.outputs[0], opacity.inputs[0])
    links.new(transparent.outputs[0], mix_shader.inputs[1])
    links.new(emission.outputs[0], mix_shader.inputs[2])
    links.new(opacity.outputs[0], mix_shader.inputs[0])
    links.new(mix_shader.outputs[0], output.inputs["Surface"])
    set_blended(mat)
    return mat


def add_caustic_planes(mat: bpy.types.Material) -> None:
    specs = [
        ("CausticProjection_Approach", (0, -25.0, 0.15), (14.0, 32.0), -0.04),
        ("CausticProjection_Palace", (0, -51.0, 0.96), (21.0, 15.0), 0.03),
        ("CausticProjection_LeftGarden", (-13.0, -15.0, 0.14), (14.0, 26.0), 0.18),
        ("CausticProjection_RightGarden", (13.0, -33.0, 0.14), (14.0, 26.0), -0.16),
    ]
    for name, location, size, rotation in specs:
        width, depth = size
        bpy.ops.mesh.primitive_plane_add(size=2.0, location=location, rotation=(0, 0, rotation))
        obj = bpy.context.object
        obj.name = name
        obj.scale = (width * 0.5, depth * 0.5, 1.0)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(mat)
        obj.visible_shadow = False


def make_god_ray_material(
    name: str = "GodRayVolume_mat",
    density_strength: float = 0.032,
    emission_strength: float = 0.040,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    texcoord = nodes.new("ShaderNodeTexCoord")
    separate = nodes.new("ShaderNodeSeparateXYZ")
    links.new(texcoord.outputs["Generated"], separate.inputs[0])

    x_center = nodes.new("ShaderNodeMath")
    x_center.operation = "SUBTRACT"
    x_center.inputs[1].default_value = 0.5
    y_center = nodes.new("ShaderNodeMath")
    y_center.operation = "SUBTRACT"
    y_center.inputs[1].default_value = 0.5
    links.new(separate.outputs["X"], x_center.inputs[0])
    links.new(separate.outputs["Y"], y_center.inputs[0])

    x_square = nodes.new("ShaderNodeMath")
    x_square.operation = "MULTIPLY"
    y_square = nodes.new("ShaderNodeMath")
    y_square.operation = "MULTIPLY"
    links.new(x_center.outputs[0], x_square.inputs[0])
    links.new(x_center.outputs[0], x_square.inputs[1])
    links.new(y_center.outputs[0], y_square.inputs[0])
    links.new(y_center.outputs[0], y_square.inputs[1])

    radial_sum = nodes.new("ShaderNodeMath")
    radial_sum.operation = "ADD"
    radial_distance = nodes.new("ShaderNodeMath")
    radial_distance.operation = "SQRT"
    radial_scale = nodes.new("ShaderNodeMath")
    radial_scale.operation = "MULTIPLY"
    # Fade to zero well before the helper box boundary.  The previous value
    # reached zero exactly on the mesh face, which exposed a rectangular
    # volume seam from oblique cameras.
    radial_scale.inputs[1].default_value = 3.0
    radial_inverse = nodes.new("ShaderNodeMath")
    radial_inverse.operation = "SUBTRACT"
    radial_inverse.inputs[0].default_value = 1.0
    radial_clamp = nodes.new("ShaderNodeMath")
    radial_clamp.operation = "MAXIMUM"
    radial_clamp.inputs[1].default_value = 0.0
    radial_falloff = nodes.new("ShaderNodeMath")
    radial_falloff.operation = "POWER"
    radial_falloff.inputs[1].default_value = 2.2
    links.new(x_square.outputs[0], radial_sum.inputs[0])
    links.new(y_square.outputs[0], radial_sum.inputs[1])
    links.new(radial_sum.outputs[0], radial_distance.inputs[0])
    links.new(radial_distance.outputs[0], radial_scale.inputs[0])
    links.new(radial_scale.outputs[0], radial_inverse.inputs[1])
    links.new(radial_inverse.outputs[0], radial_clamp.inputs[0])
    links.new(radial_clamp.outputs[0], radial_falloff.inputs[0])

    z_up = nodes.new("ShaderNodeMath")
    z_up.operation = "MULTIPLY"
    z_up.inputs[1].default_value = 6.0
    z_up_clamp = nodes.new("ShaderNodeMath")
    z_up_clamp.operation = "MINIMUM"
    z_up_clamp.inputs[1].default_value = 1.0
    z_inverse = nodes.new("ShaderNodeMath")
    z_inverse.operation = "SUBTRACT"
    z_inverse.inputs[0].default_value = 1.0
    z_down = nodes.new("ShaderNodeMath")
    z_down.operation = "MULTIPLY"
    z_down.inputs[1].default_value = 6.0
    z_down_clamp = nodes.new("ShaderNodeMath")
    z_down_clamp.operation = "MINIMUM"
    z_down_clamp.inputs[1].default_value = 1.0
    vertical_fade = nodes.new("ShaderNodeMath")
    vertical_fade.operation = "MULTIPLY"
    links.new(separate.outputs["Z"], z_up.inputs[0])
    links.new(z_up.outputs[0], z_up_clamp.inputs[0])
    links.new(separate.outputs["Z"], z_inverse.inputs[1])
    links.new(z_inverse.outputs[0], z_down.inputs[0])
    links.new(z_down.outputs[0], z_down_clamp.inputs[0])
    links.new(z_up_clamp.outputs[0], vertical_fade.inputs[0])
    links.new(z_down_clamp.outputs[0], vertical_fade.inputs[1])

    density_profile = nodes.new("ShaderNodeMath")
    density_profile.operation = "MULTIPLY"
    density_noise = nodes.new("ShaderNodeTexNoise")
    density_noise.inputs["Scale"].default_value = 1.35
    density_noise.inputs["Detail"].default_value = 2.2
    density_noise.inputs["Roughness"].default_value = 0.62
    links.new(texcoord.outputs["Generated"], density_noise.inputs["Vector"])
    noise_scale = nodes.new("ShaderNodeMath")
    noise_scale.operation = "MULTIPLY"
    noise_scale.inputs[1].default_value = 0.52
    noise_bias = nodes.new("ShaderNodeMath")
    noise_bias.operation = "ADD"
    noise_bias.inputs[1].default_value = 0.48
    links.new(density_noise.outputs["Fac"], noise_scale.inputs[0])
    links.new(noise_scale.outputs[0], noise_bias.inputs[0])

    density_modulated = nodes.new("ShaderNodeMath")
    density_modulated.operation = "MULTIPLY"
    density_scale = nodes.new("ShaderNodeMath")
    density_scale.operation = "MULTIPLY"
    density_scale.inputs[1].default_value = density_strength
    links.new(radial_falloff.outputs[0], density_profile.inputs[0])
    links.new(vertical_fade.outputs[0], density_profile.inputs[1])
    links.new(density_profile.outputs[0], density_modulated.inputs[0])
    links.new(noise_bias.outputs[0], density_modulated.inputs[1])
    links.new(density_modulated.outputs[0], density_scale.inputs[0])

    volume = nodes.new("ShaderNodeVolumePrincipled")
    volume.inputs["Color"].default_value = (0.30, 0.66, 0.78, 1.0)
    volume.inputs["Anisotropy"].default_value = 0.58
    if "Emission Color" in volume.inputs:
        volume.inputs["Emission Color"].default_value = (0.035, 0.24, 0.34, 1.0)
        volume.inputs["Emission Strength"].default_value = emission_strength
    links.new(density_scale.outputs[0], volume.inputs["Density"])
    links.new(volume.outputs["Volume"], output.inputs["Volume"])
    return mat


def add_god_rays(
    side_mat: bpy.types.Material,
    palace_mat: bpy.types.Material | None = None,
) -> None:
    # Tapered volumes read as shafts while staying off the processional route.
    # Their analytic density still fades before the mesh boundary, avoiding a
    # hard cone silhouette in final Cycles renders.
    beams = (
        ("LeftCoral", -17.2, -16.0, 8.0, 2.85, 0.46, 16.0),
        ("Reliquary", 22.7, -51.6, 8.0, 2.75, 0.42, 16.0),
        ("PalaceDome", 0.0, -56.2, 12.0, 3.35, 0.56, 8.2),
    )
    for index, (label, x, y, z, bottom_radius, top_radius, depth) in enumerate(beams):
        bpy.ops.mesh.primitive_cone_add(
            vertices=40,
            radius1=bottom_radius,
            radius2=top_radius,
            depth=depth,
            location=(x, y, z),
        )
        ray = bpy.context.object
        ray.name = f"GodRayVolume_{index:02d}_{label}"
        ray.data.materials.append(palace_mat if index == 2 and palace_mat else side_mat)
        ray.visible_shadow = False


def make_soft_shaft_material() -> bpy.types.Material:
    """A camera-stable light curtain with feathered sides and vertical ends."""
    mat = bpy.data.materials.new("SoftUnderwaterShaft_mat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (0.14, 0.60, 0.78, 1.0)
    emission.inputs["Strength"].default_value = 0.85
    texcoord = nodes.new("ShaderNodeTexCoord")
    separate = nodes.new("ShaderNodeSeparateXYZ")
    links.new(texcoord.outputs["Generated"], separate.inputs[0])

    x_center = nodes.new("ShaderNodeMath")
    x_center.operation = "SUBTRACT"
    x_center.inputs[1].default_value = 0.5
    x_abs = nodes.new("ShaderNodeMath")
    x_abs.operation = "ABSOLUTE"
    x_scale = nodes.new("ShaderNodeMath")
    x_scale.operation = "MULTIPLY"
    x_scale.inputs[1].default_value = 2.0
    x_inverse = nodes.new("ShaderNodeMath")
    x_inverse.operation = "SUBTRACT"
    x_inverse.inputs[0].default_value = 1.0
    x_power = nodes.new("ShaderNodeMath")
    x_power.operation = "POWER"
    x_power.inputs[1].default_value = 2.4
    links.new(separate.outputs["X"], x_center.inputs[0])
    links.new(x_center.outputs[0], x_abs.inputs[0])
    links.new(x_abs.outputs[0], x_scale.inputs[0])
    links.new(x_scale.outputs[0], x_inverse.inputs[1])
    links.new(x_inverse.outputs[0], x_power.inputs[0])

    z_bottom = nodes.new("ShaderNodeMath")
    z_bottom.operation = "MULTIPLY"
    z_bottom.inputs[1].default_value = 5.0
    z_bottom_clamp = nodes.new("ShaderNodeMath")
    z_bottom_clamp.operation = "MINIMUM"
    z_bottom_clamp.inputs[1].default_value = 1.0
    z_inverse = nodes.new("ShaderNodeMath")
    z_inverse.operation = "SUBTRACT"
    z_inverse.inputs[0].default_value = 1.0
    z_top = nodes.new("ShaderNodeMath")
    z_top.operation = "MULTIPLY"
    z_top.inputs[1].default_value = 5.0
    z_top_clamp = nodes.new("ShaderNodeMath")
    z_top_clamp.operation = "MINIMUM"
    z_top_clamp.inputs[1].default_value = 1.0
    z_fade = nodes.new("ShaderNodeMath")
    z_fade.operation = "MULTIPLY"
    links.new(separate.outputs["Z"], z_bottom.inputs[0])
    links.new(z_bottom.outputs[0], z_bottom_clamp.inputs[0])
    links.new(separate.outputs["Z"], z_inverse.inputs[1])
    links.new(z_inverse.outputs[0], z_top.inputs[0])
    links.new(z_top.outputs[0], z_top_clamp.inputs[0])
    links.new(z_bottom_clamp.outputs[0], z_fade.inputs[0])
    links.new(z_top_clamp.outputs[0], z_fade.inputs[1])

    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.2
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.55
    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    profile = nodes.new("ShaderNodeMath")
    profile.operation = "MULTIPLY"
    profile_noise = nodes.new("ShaderNodeMath")
    profile_noise.operation = "MULTIPLY"
    gain = nodes.new("ShaderNodeMath")
    gain.operation = "MULTIPLY"
    gain.inputs[1].default_value = 0.050
    links.new(x_power.outputs[0], profile.inputs[0])
    links.new(z_fade.outputs[0], profile.inputs[1])
    links.new(profile.outputs[0], profile_noise.inputs[0])
    links.new(noise.outputs["Fac"], profile_noise.inputs[1])
    links.new(profile_noise.outputs[0], gain.inputs[0])
    mix = nodes.new("ShaderNodeMixShader")
    links.new(gain.outputs[0], mix.inputs[0])
    links.new(transparent.outputs[0], mix.inputs[1])
    links.new(emission.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs["Surface"])
    set_blended(mat)
    return mat


def add_soft_light_shaft(name, center, bottom_z, top_z, bottom_width, top_width, mat):
    """Cross three feathered trapezoids so a shaft reads from any approach."""
    for plane_index, angle in enumerate((0.0, math.pi / 3.0, 2.0 * math.pi / 3.0)):
        direction = (math.cos(angle), math.sin(angle))
        verts = []
        for z, half_width in ((bottom_z, bottom_width), (top_z, top_width)):
            verts.append((center[0] - direction[0] * half_width, center[1] - direction[1] * half_width, z))
            verts.append((center[0] + direction[0] * half_width, center[1] + direction[1] * half_width, z))
        mesh = bpy.data.meshes.new(f"{name}_{plane_index:02d}_mesh")
        mesh.from_pydata(verts, [], [(0, 1, 3, 2)])
        mesh.update()
        plane = bpy.data.objects.new(f"{name}_{plane_index:02d}", mesh)
        bpy.context.scene.collection.objects.link(plane)
        plane.data.materials.append(mat)
        plane.visible_shadow = False


def add_surface_light_shafts(mat: bpy.types.Material) -> None:
    add_soft_light_shaft("SoftShaft_LeftCoral", (-17.2, -16.0), 0.35, 15.35, 3.10, 0.42, mat)
    add_soft_light_shaft("SoftShaft_Reliquary", (22.7, -51.6), 0.72, 15.35, 2.85, 0.42, mat)
    add_soft_light_shaft("SoftShaft_PalaceDome", (0.0, -56.2), 6.10, 15.35, 3.25, 0.48, mat)


def make_underwater_atmosphere_material() -> bpy.types.Material:
    """Create one continuous low-density water volume without local box seams."""
    mat = bpy.data.materials.new("UnderwaterAtmosphere_mat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    volume = nodes.new("ShaderNodeVolumePrincipled")
    volume.inputs["Density"].default_value = 0.0018
    volume.inputs["Color"].default_value = (0.10, 0.38, 0.48, 1.0)
    volume.inputs["Anisotropy"].default_value = 0.46
    links.new(volume.outputs["Volume"], output.inputs["Volume"])
    return mat


def add_underwater_atmosphere(mat: bpy.types.Material) -> None:
    """Enclose every review camera in the same volume to avoid visible edges."""
    bpy.ops.mesh.primitive_cube_add(location=(0.0, -27.0, 8.0))
    atmosphere = bpy.context.object
    atmosphere.name = "UnderwaterAtmosphere"
    atmosphere.dimensions = (82.0, 124.0, 31.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    atmosphere.data.materials.append(mat)
    atmosphere.visible_shadow = False
    atmosphere.hide_select = True


def make_particle_material() -> bpy.types.Material:
    mat = bpy.data.materials.new("SuspendedParticles_mat")
    mat.use_nodes = True
    bsdf = next(node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.34, 0.78, 0.90, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.45
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (0.18, 0.62, 0.82, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 2.2
    return mat


def add_suspended_particles(mat: bpy.types.Material) -> None:
    rng = random.Random(137)
    verts, faces = [], []
    camera_safe_zones = (
        ((0.0, -9.5, 3.3), 8.0),
        ((0.0, 16.0, 2.6), 6.0),
        ((18.0, -29.0, 11.8), 7.0),
    )
    particle_count = 0
    while particle_count < 140:
        x = rng.uniform(-34.0, 34.0)
        y = rng.uniform(-79.0, 21.0)
        z = rng.uniform(0.5, 15.7)
        if any(
            (x - location[0]) ** 2 + (y - location[1]) ** 2 + (z - location[2]) ** 2 < radius**2
            for location, radius in camera_safe_zones
        ):
            continue
        size = rng.uniform(0.012, 0.045)
        start = len(verts)
        verts.extend(((x, y, z + size), (x - size, y - size, z - size), (x + size, y - size, z - size), (x, y + size, z - size)))
        faces.extend(((start, start + 1, start + 2), (start, start + 2, start + 3), (start, start + 3, start + 1), (start + 1, start + 3, start + 2)))
        particle_count += 1
    mesh = bpy.data.meshes.new("SuspendedParticles_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("SuspendedParticles", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat)
    obj.visible_shadow = False


def add_rock(name, location, scale, mat, rotation=0.0):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.rotation_euler.z = rotation
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    return obj


def add_kelp(name, location, height, lean, mat):
    curve = bpy.data.curves.new(name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.045
    curve.bevel_resolution = 2
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(3)
    for index, point in enumerate(spline.bezier_points):
        t = index / 3
        point.co = (lean * t + math.sin(index * 1.9) * 0.12, 0.08 * math.cos(index), height * t)
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    obj.location = location
    obj.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(obj)


def add_low_rock(name, location, scale, mat, rotation=0.0):
    """Low-poly boulder used for distant ridges and natural scene boundaries."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    obj.rotation_euler = (0.08 * math.sin(rotation), 0.06 * math.cos(rotation), rotation)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    return obj


def make_branch_coral_prototype(name, mat):
    curve = bpy.data.curves.new(name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = 0.065
    curve.bevel_resolution = 1
    for branch_index in range(9):
        angle = branch_index * math.tau / 9
        height = 1.0 + 0.42 * (branch_index % 3)
        reach = 0.48 + 0.15 * (branch_index % 2)
        spline = curve.splines.new("POLY")
        spline.points.add(3)
        for point_index, point in enumerate(spline.points):
            t = point_index / 3
            bend = reach * t * (0.45 + 0.55 * t)
            point.co = (
                math.cos(angle) * bend,
                math.sin(angle) * bend * 0.55,
                height * t,
                1.0,
            )
    obj = bpy.data.objects.new(name, curve)
    obj.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def make_sea_fan_prototype(name, mat):
    curve = bpy.data.curves.new(name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 1
    curve.bevel_depth = 0.026
    curve.bevel_resolution = 1
    for branch_index in range(11):
        normalized = (branch_index - 5) / 5
        spline = curve.splines.new("POLY")
        spline.points.add(3)
        for point_index, point in enumerate(spline.points):
            t = point_index / 3
            point.co = (
                normalized * (0.32 + 0.75 * t),
                0.05 * math.sin(branch_index + point_index),
                t * (1.18 - 0.20 * abs(normalized)) + 0.10 * math.sin(t * math.pi),
                1.0,
            )
    for band_index, height in enumerate((0.38, 0.70, 0.96)):
        spline = curve.splines.new("POLY")
        spline.points.add(8)
        for point_index, point in enumerate(spline.points):
            normalized = (point_index - 4) / 4
            point.co = (
                normalized * (0.55 + height * 0.48),
                0.03 * math.cos(point_index + band_index),
                height - 0.12 * normalized * normalized,
                1.0,
            )
    obj = bpy.data.objects.new(name, curve)
    obj.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def place_linked_instances(prototype, specs, prefix):
    for index, (location, scale, rotation) in enumerate(specs):
        obj = prototype if index == 0 else prototype.copy()
        if index > 0:
            obj.data = prototype.data
            bpy.context.scene.collection.objects.link(obj)
        obj.name = f"{prefix}_{index:02d}"
        obj.location = location
        obj.scale = scale
        obj.rotation_euler.z = rotation


def add_sponge_cluster(name, location, scale, coral_mat, dark_mat):
    x, y, z = location
    specs = ((-0.34, 0.02, 0.28, 0.82), (0.05, -0.08, 0.38, 1.20), (0.38, 0.10, 0.24, 0.68))
    for index, (dx, dy, radius, height) in enumerate(specs):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=12,
            radius=radius * scale,
            depth=height * scale,
            location=(x + dx * scale, y + dy * scale, z + height * scale * 0.5),
        )
        sponge = bpy.context.object
        sponge.name = f"{name}_Tube_{index:02d}"
        sponge.data.materials.append(coral_mat)
        bpy.ops.mesh.primitive_torus_add(
            major_radius=radius * scale * 0.68,
            minor_radius=max(0.018, radius * scale * 0.10),
            major_segments=12,
            minor_segments=5,
            location=(x + dx * scale, y + dy * scale, z + height * scale),
        )
        rim = bpy.context.object
        rim.name = f"{name}_Rim_{index:02d}"
        rim.data.materials.append(dark_mat)


def add_ecological_dressing(library, stone, stone_dark, ridge_mat, kelp_mat, coral_warm, coral_cool, sponge_mat):
    """Add layered marine life, debris, ridge silhouettes, and distant ruins."""
    warm_coral = make_branch_coral_prototype("WarmCoralPrototype", coral_warm)
    warm_specs = (
        ((-8.6, 7.5, 0.18), (1.05, 1.05, 1.05), 0.15),
        ((8.7, 4.0, 0.18), (0.85, 0.85, 1.12), -0.45),
        ((-16.8, -8.0, 0.35), (1.20, 1.05, 1.35), 0.52),
        ((17.0, -18.0, 0.34), (1.10, 1.00, 1.20), -0.35),
        ((-17.2, -30.0, 0.38), (1.30, 1.10, 1.42), 0.70),
        ((-20.8, -13.8, 0.30), (0.62, 0.66, 0.82), -0.24),
        ((-16.8, -18.2, 0.30), (0.58, 0.62, 0.76), 0.44),
        ((17.4, -41.5, 0.38), (1.05, 1.00, 1.25), -0.72),
        ((-12.7, -49.0, 0.30), (1.12, 1.05, 1.30), 0.35),
        ((12.8, -57.0, 0.32), (1.18, 1.00, 1.38), -0.20),
    )
    place_linked_instances(warm_coral, warm_specs, "WarmCoralCluster")

    cool_coral = make_branch_coral_prototype("CoolCoralPrototype", coral_cool)
    cool_specs = (
        ((-10.5, 1.0, 0.15), (0.78, 0.82, 0.95), -0.22),
        ((11.8, -7.0, 0.22), (0.96, 0.90, 1.15), 0.48),
        ((-18.6, -20.5, 0.38), (1.10, 1.00, 1.28), -0.55),
        ((18.5, -31.8, 0.40), (1.22, 1.10, 1.36), 0.18),
        ((-15.0, -42.0, 0.32), (0.92, 0.90, 1.12), 0.63),
        ((-20.8, -18.6, 0.30), (0.82, 0.86, 1.08), -0.36),
        ((15.3, -51.2, 0.34), (1.15, 1.00, 1.30), -0.44),
    )
    place_linked_instances(cool_coral, cool_specs, "CoolCoralCluster")

    sea_fan = make_sea_fan_prototype("SeaFanPrototype", coral_cool)
    fan_specs = (
        ((-9.4, -3.0, 0.12), (0.90, 0.90, 1.15), 0.28),
        ((10.1, -11.5, 0.18), (0.78, 0.78, 0.96), -0.48),
        ((-18.0, -16.0, 0.35), (1.20, 1.10, 1.38), 0.72),
        ((18.0, -27.0, 0.38), (1.05, 1.00, 1.22), -0.62),
        ((-16.5, -14.8, 0.30), (0.82, 0.84, 1.06), -0.30),
        ((-14.0, -52.0, 0.30), (0.95, 0.90, 1.16), 0.34),
        ((14.2, -59.0, 0.30), (1.10, 1.00, 1.30), -0.24),
    )
    place_linked_instances(sea_fan, fan_specs, "SeaFanCluster")

    for index, (location, scale) in enumerate(
        (
            ((-11.2, 10.0, 0.05), 0.72),
            ((12.2, 7.0, 0.05), 0.62),
            ((-17.8, -12.0, 0.30), 0.88),
            ((17.8, -22.0, 0.32), 0.78),
            ((-18.0, -38.0, 0.32), 0.92),
            ((17.0, -54.0, 0.30), 0.84),
        )
    ):
        add_sponge_cluster(f"SpongeCluster_{index:02d}", location, scale, sponge_mat, stone_dark)

    # Sparse outer kelp banks frame the route without invading walkable spaces.
    for index in range(24):
        side = -1 if index % 2 == 0 else 1
        x = side * (19.0 + (index % 4) * 1.8)
        y = 14.0 - index * 3.45
        add_kelp(
            f"OuterKelp_{index:02d}",
            (x, y, 0.20),
            1.8 + (index % 5) * 0.48,
            -side * (0.20 + (index % 3) * 0.08),
            kelp_mat,
        )

    # Side and rear rock ridges hide the rectangular seabed edge as silhouettes.
    ridge_index = 0
    for side in (-1, 1):
        for row, y in enumerate(range(18, -75, -8)):
            x = side * (28.0 + 1.8 * math.sin(row * 1.7))
            scale = (4.2 + row % 3, 5.0 + (row + 1) % 3, 2.2 + (row % 4) * 0.55)
            add_low_rock(f"BoundaryRidge_{ridge_index:02d}", (x, y, 0.9), scale, ridge_mat, side * row * 0.23)
            ridge_index += 1
    for column, x in enumerate(range(-30, 31, 6)):
        add_low_rock(
            f"RearRidge_{column:02d}",
            (float(x), -77.5 + 1.2 * math.sin(column), 1.0),
            (4.6 + column % 3, 3.4 + (column + 1) % 2, 2.5 + (column % 4) * 0.45),
            ridge_mat,
            column * 0.31,
        )

    # A second, fainter ruin band creates depth behind the existing midground.
    for index, y in enumerate((-8, -27, -48, -67)):
        scale = 0.92 - index * 0.10
        instance(library["arch"], f"FarRuinArch_L_{index}", (-22.5, y, 0.45), rotation=(0, 0, math.pi / 2 + 0.06), scale=(scale, scale, scale))
        if index != 2:
            # Reserve this coordinates band for the hand-built reliquary arch.
            instance(library["arch"], f"FarRuinArch_R_{index}", (22.5, y - 3, 0.45), rotation=(0, 0, -math.pi / 2 - 0.05), scale=(scale, scale, scale))
        if index != 1:
            instance(library["column"], f"FarBrokenColumn_L_{index}", (-20.0, y - 6, 0.25), rotation=(0.18, 0.05, 0.20), scale=(0.66, 0.66, 0.52 + index * 0.05))
        instance(library["column"], f"FarBrokenColumn_R_{index}", (20.0, y - 9, 0.25), rotation=(-0.14, 0.04, -0.18), scale=(0.62, 0.62, 0.48 + index * 0.05))

    rng = random.Random(409)
    debris_count = 0
    while debris_count < 24:
        x = rng.choice((-1, 1)) * rng.uniform(8.0, 24.0)
        y = rng.uniform(-68.0, 14.0)
        if x < 0 and -23.0 < y < -9.0 and abs(x) < 17.0:
            continue
        if x > 0 and -36.0 < y < -22.0 and abs(x) < 17.0:
            continue
        add_box(
            f"SeabedFragment_{debris_count:02d}",
            (rng.uniform(0.45, 1.55), rng.uniform(0.28, 0.85), rng.uniform(0.16, 0.42)),
            (x, y, rng.uniform(0.05, 0.22)),
            stone if debris_count % 3 else stone_dark,
            rotation=(rng.uniform(-0.16, 0.16), rng.uniform(-0.10, 0.10), rng.uniform(0, math.tau)),
            bevel=0.08,
        )
        debris_count += 1


def add_fish_schools(fish_mat):
    """Add two lightweight linked schools as distant underwater silhouettes."""
    verts = (
        (0.72, 0.0, 0.0),
        (-0.56, 0.0, 0.0),
        (0.0, 0.0, 0.24),
        (0.0, 0.0, -0.24),
        (0.0, 0.18, 0.0),
        (0.0, -0.18, 0.0),
        (-0.58, 0.0, 0.0),
        (-1.02, 0.0, 0.34),
        (-1.02, 0.0, -0.34),
        (-0.08, 0.0, 0.20),
        (-0.34, 0.0, 0.42),
        (-0.46, 0.0, 0.16),
    )
    faces = (
        (0, 2, 4),
        (0, 4, 3),
        (0, 3, 5),
        (0, 5, 2),
        (1, 4, 2),
        (1, 3, 4),
        (1, 5, 3),
        (1, 2, 5),
        (6, 7, 8),
        (9, 10, 11),
    )
    mesh = bpy.data.meshes.new("DistantFish_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    prototype = bpy.data.objects.new("DistantFishPrototype", mesh)
    bpy.context.scene.collection.objects.link(prototype)
    prototype.data.materials.append(fish_mat)

    rng = random.Random(827)
    schools = (
        ((-15.5, -42.0, 11.2), 12, 0.18),
        ((14.5, -18.0, 10.8), 10, math.pi + 0.08),
        ((5.0, -66.0, 12.5), 7, math.pi - 0.12),
    )
    fish_index = 0
    for origin, count, heading in schools:
        for local_index in range(count):
            fish = prototype if fish_index == 0 else prototype.copy()
            if fish_index > 0:
                fish.data = prototype.data
                bpy.context.scene.collection.objects.link(fish)
            fish.name = f"DistantFish_{fish_index:02d}"
            fish.location = (
                origin[0] + rng.uniform(-4.6, 4.6),
                origin[1] + rng.uniform(-5.5, 5.5),
                origin[2] + rng.uniform(-1.9, 2.0),
            )
            scale = rng.uniform(0.22, 0.46) * (0.90 if local_index % 4 else 1.04)
            fish.scale = (scale, scale, scale)
            fish.rotation_euler = (
                rng.uniform(-0.10, 0.10),
                rng.uniform(-0.12, 0.12),
                heading + rng.uniform(-0.22, 0.22),
            )
            fish_index += 1


def image_material(path: Path, name: str, emission_strength: float = 0.18):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(path), check_existing=True)
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.42
    if "Emission Color" in bsdf.inputs:
        links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def tag_gallery_artwork(obj: bpy.types.Object, path: Path) -> None:
    """Persist the catalog thumbnail path as glTF extras for web picking."""
    normalized = Path(path).as_posix()
    marker = "/static/"
    public_path = "/" + normalized.split(marker, 1)[1] if marker in normalized else normalized
    obj["gallery_interactive"] = True
    obj["gallery_artwork_thumb"] = public_path


def add_artwork_wall(repo: Path, gold, stone_dark):
    candidates = sorted((repo / "static" / "assets" / "gallery" / "thumbs").glob("**/*.jpg"))[:8]
    # Bridges occupy y=-16 and y=-29, so the route art is deliberately offset.
    positions = [(-6.2, y) for y in (2, -7, -22, -39)]
    positions += [(6.2, y) for y in (2, -7, -22, -39)]
    for index, ((x, y), path) in enumerate(zip(positions, candidates)):
        add_box(f"ArtworkFrame_{index:02d}", (0.18, 2.15, 1.65), (x, y, 2.2), gold, bevel=0.035)
        bpy.ops.mesh.primitive_plane_add(size=2.0, location=(x + (-0.101 if x > 0 else 0.101), y, 2.2), rotation=(0, math.pi / 2 if x < 0 else -math.pi / 2, 0))
        art = bpy.context.object
        art.name = f"Artwork_{index:02d}_{path.stem}"
        art.scale = (0.75, 0.96, 1.0)
        art.data.materials.append(image_material(path, f"Artwork_{index:02d}_mat"))
        tag_gallery_artwork(art, path)
        add_box(f"ArtworkBacking_{index:02d}", (0.24, 2.5, 2.05), (x + (0.08 if x > 0 else -0.08), y, 2.2), stone_dark, bevel=0.09)


def point_at(obj: bpy.types.Object, target: tuple[float, float, float]):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def bind_review_timeline(scene: bpy.types.Scene, camera_specs) -> None:
    """Bind the spatial-review cameras to timeline markers for fast inspection."""
    for marker in list(scene.timeline_markers):
        scene.timeline_markers.remove(marker)
    collection = bpy.data.collections.get("07_REVIEW_CAMERAS") or bpy.data.collections.new("07_REVIEW_CAMERAS")
    if collection.name not in scene.collection.children:
        scene.collection.children.link(collection)
    for frame, label, camera in camera_specs:
        marker = scene.timeline_markers.new(label, frame=frame)
        marker.camera = camera
        if camera.name not in collection.objects:
            collection.objects.link(camera)
    collection.color_tag = "COLOR_05"
    scene.frame_start = 1
    scene.frame_end = camera_specs[-1][0]
    scene.frame_set(1)
    scene.camera = camera_specs[0][2]
    scene["review_controls"] = "Use Up/Down Arrow to jump markers; Numpad 0 toggles camera view"


def organize_scene_for_review(scene: bpy.types.Scene) -> None:
    """Keep the generated master understandable for a first-time Blender user."""
    specs = (
        ("00_ENVIRONMENT", "COLOR_04"),
        ("01_PROCESSIONAL_ROUTE", "COLOR_03"),
        ("02_ARCHIVE_OF_TIDES", "COLOR_02"),
        ("03_CLIFF_GALLERY", "COLOR_06"),
        ("04_PALACE_COMPLEX", "COLOR_01"),
        ("05_ECOLOGY_AND_RUINS", "COLOR_07"),
        ("06_LIGHTING_RIG", "COLOR_08"),
        ("07_REVIEW_CAMERAS", "COLOR_05"),
    )
    managed = {}
    for collection_name, color_tag in specs:
        collection = bpy.data.collections.get(collection_name) or bpy.data.collections.new(collection_name)
        if scene.collection.children.get(collection_name) is None:
            scene.collection.children.link(collection)
        collection.color_tag = color_tag
        managed[collection_name] = collection

    route_prefixes = (
        "EntryCompass",
        "Processional",
        "PrecinctEntryArch",
        "Causeway",
        "RouteMedallion",
        "Column_",
    )
    palace_prefixes = (
        "Palace",
        "SunkenPalace",
        "MuseumWing",
        "Forecourt",
    )
    ecology_prefixes = (
        "Rock_",
        "Kelp_",
        "Coral",
        "SeaFan",
        "Sponge",
        "Fish",
        "DistantFish",
        "DistantArch",
        "DistantColumn",
        "FarRuin",
        "FarBroken",
        "Boundary",
        "SculptureGarden",
    )

    for obj in list(scene.objects):
        name = obj.name
        if obj.type == "LIGHT":
            target_name = "06_LIGHTING_RIG"
            obj.hide_select = True
        elif obj.type == "CAMERA":
            target_name = "07_REVIEW_CAMERAS"
            obj.hide_select = True
        elif name.startswith("ArchiveOfTides"):
            target_name = "02_ARCHIVE_OF_TIDES"
        elif name.startswith("CliffGallery"):
            target_name = "03_CLIFF_GALLERY"
        elif name.startswith(palace_prefixes):
            target_name = "04_PALACE_COMPLEX"
        elif name.startswith(route_prefixes):
            target_name = "01_PROCESSIONAL_ROUTE"
        elif name.startswith(ecology_prefixes):
            target_name = "05_ECOLOGY_AND_RUINS"
        else:
            target_name = "00_ENVIRONMENT"

        target = managed[target_name]
        if target.objects.get(name) is None:
            target.objects.link(obj)
        for current_collection in list(obj.users_collection):
            if current_collection == target:
                continue
            if (
                current_collection == scene.collection
                or current_collection.name == "Collection"
                or current_collection.name in managed
            ):
                current_collection.objects.unlink(obj)

    default_collection = bpy.data.collections.get("Collection")
    if default_collection and not default_collection.objects and not default_collection.children:
        bpy.data.collections.remove(default_collection)


def configure_review_viewports(scene: bpy.types.Scene) -> None:
    """Persist a clean camera view instead of the default grid and helper wires."""
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.overlay.show_overlays = False
            space.shading.type = "MATERIAL"
            try:
                space.region_3d.view_perspective = "CAMERA"
            except AttributeError:
                pass


def configure_depth_compositor(scene: bpy.types.Scene, world: bpy.types.World) -> None:
    scene.view_layers[0].use_pass_mist = True
    world.mist_settings.start = 13.0
    world.mist_settings.depth = 74.0
    world.mist_settings.falloff = "QUADRATIC"
    scene.use_nodes = True
    tree = scene.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()
    render = nodes.new("CompositorNodeRLayers")
    fog_color = nodes.new("CompositorNodeRGB")
    fog_color.outputs[0].default_value = (0.006, 0.105, 0.155, 1.0)
    mix = nodes.new("CompositorNodeMixRGB")
    mix.blend_type = "MIX"
    composite = nodes.new("CompositorNodeComposite")
    links.new(render.outputs["Mist"], mix.inputs[0])
    links.new(render.outputs["Image"], mix.inputs[1])
    links.new(fog_color.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], composite.inputs[0])


def add_light(name, light_type, location, color, energy, target=None, size=5.0, angle=0.5, cast_shadow=False):
    data = bpy.data.lights.new(name + "_data", light_type)
    data.color = color
    data.energy = energy * (0.22 if light_type == "SUN" else 0.08)
    data.use_shadow = True if bpy.context.scene.render.engine == "CYCLES" else cast_shadow
    if light_type == "AREA":
        data.shape = "DISK"
        data.size = size
    if light_type == "SPOT":
        data.spot_size = angle
        data.spot_blend = 0.55
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    if target:
        point_at(obj, target)
    return obj


def build(repo: Path):
    clear_scene()
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    # Eevee Next on the target Mac currently stalls in Metal's shadow buffer
    # even when light shadows are disabled. Cycles CPU is slower but produces a
    # stable review render with predictable memory use.
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 2
    scene.cycles.transparent_max_bounces = 4
    if hasattr(scene.cycles, "use_caustics"):
        scene.cycles.use_caustics = False
    if hasattr(scene.cycles, "caustics_reflective"):
        scene.cycles.caustics_reflective = False
        scene.cycles.caustics_refractive = False
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 55
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.92

    library = append_asset_library(repo / "assets" / "gallery" / "blender" / "components")
    # Asset libraries contain legacy review lights. They would stack with the
    # master rig and wash every material to white, so only the master rig below
    # is allowed to emit light.
    for obj in bpy.data.objects:
        if obj.type == "LIGHT":
            obj.data.energy = 0.0
    retune_material_family("AtlantisStone_mat", (0.045, 0.205, 0.205), 0.82)
    retune_material_family("AtlantisStoneDark_mat", (0.011, 0.066, 0.082), 0.90)
    retune_material_family("AtlantisFloor_mat", (0.028, 0.125, 0.135), 0.78, 0.08)
    retune_material_family("AtlantisGold_mat", (0.58, 0.29, 0.055), 0.34, 0.72)
    retune_material_family("Material", (0.025, 0.105, 0.125), 0.72)
    stone = bpy.data.materials.get("AtlantisStone_mat") or material("MasterStone", (0.09, 0.24, 0.25, 1), roughness=0.84)
    stone_dark = bpy.data.materials.get("AtlantisStoneDark_mat") or material("MasterStoneDark", (0.025, 0.10, 0.13, 1), roughness=0.9)
    floor_mat = bpy.data.materials.get("AtlantisFloor_mat") or stone_dark
    gold = bpy.data.materials.get("AtlantisGold_mat") or material("MasterGold", (0.72, 0.48, 0.16, 1), metallic=0.72, roughness=0.34)
    kelp_mat = material("Kelp_mat", (0.025, 0.28, 0.21, 1), roughness=0.76)
    sand_mat = material("Seabed_mat", (0.055, 0.19, 0.22, 1), roughness=0.95)
    sand_nodes = sand_mat.node_tree.nodes
    sand_links = sand_mat.node_tree.links
    sand_bsdf = next(node for node in sand_nodes if node.type == "BSDF_PRINCIPLED")
    sand_coord = sand_nodes.new("ShaderNodeTexCoord")
    sand_noise = sand_nodes.new("ShaderNodeTexNoise")
    sand_noise.inputs["Scale"].default_value = 8.0
    sand_noise.inputs["Detail"].default_value = 3.0
    sand_noise.inputs["Roughness"].default_value = 0.62
    sand_bump = sand_nodes.new("ShaderNodeBump")
    sand_bump.inputs["Strength"].default_value = 0.20
    sand_bump.inputs["Distance"].default_value = 0.18
    sand_links.new(sand_coord.outputs["Generated"], sand_noise.inputs["Vector"])
    sand_links.new(sand_noise.outputs["Fac"], sand_bump.inputs["Height"])
    sand_links.new(sand_bump.outputs["Normal"], sand_bsdf.inputs["Normal"])
    ridge_mat = material("BoundaryRidge_mat", (0.012, 0.075, 0.095, 1), roughness=0.96)
    coral_warm = material("CoralWarm_mat", (0.52, 0.12, 0.065, 1), roughness=0.78)
    coral_cool = material("CoralCool_mat", (0.035, 0.32, 0.36, 1), roughness=0.72)
    sponge_mat = material("SpongeOchre_mat", (0.48, 0.26, 0.06, 1), roughness=0.82)
    fish_mat = material("DistantFish_mat", (0.006, 0.047, 0.062, 1), roughness=0.76)
    # A restrained self-illumination keeps reef colors readable through blue
    # water attenuation while preserving a physically shaded surface.
    for reef_mat, glow_color, strength in (
        (coral_warm, (0.34, 0.045, 0.012, 1.0), 0.46),
        (coral_cool, (0.010, 0.18, 0.22, 1.0), 0.32),
        (sponge_mat, (0.25, 0.085, 0.008, 1.0), 0.28),
    ):
        reef_bsdf = next(node for node in reef_mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
        if "Emission Color" in reef_bsdf.inputs:
            reef_bsdf.inputs["Emission Color"].default_value = glow_color
            reef_bsdf.inputs["Emission Strength"].default_value = strength
    interior_glow = emissive_material("GalleryInteriorGlow_mat", (0.24, 0.76, 0.90), strength=1.9)
    palace_glow = emissive_material("PalaceInteriorGlow_mat", (0.08, 0.42, 0.62), strength=0.46)
    memory_glass = emissive_material("AtlantisMemoryGlass_mat", (0.025, 0.22, 0.42), strength=0.24)
    pavilion_warm = emissive_material("PavilionWindowWarm_mat", (0.74, 0.45, 0.19), strength=1.55)
    connector_glow = emissive_material("ConnectorGuideGlow_mat", (0.028, 0.22, 0.31), strength=0.50)

    add_seabed(sand_mat)
    add_water_surface(make_water_surface_material(repo))
    add_caustic_planes(make_caustic_material())
    add_suspended_particles(make_particle_material())
    instance(library["platform"], "EntryCompass", (0, 10, 0.05), scale=(1.35, 1.35, 1.35))

    # A single 4 m processional causeway leaves open seabed on both sides. A
    # small number of tile medallions punctuate the route without turning the
    # foreground into a repeated roof-like grid.
    add_box("ProcessionalCauseway", (4.2, 59.0, 0.14), (0, -19.5, 0.02), floor_mat, bevel=0.06)
    for side_x in (-2.02, 2.02):
        add_box(f"CausewayGoldInlay_{side_x:+.2f}", (0.07, 57.5, 0.025), (side_x, -19.5, 0.105), gold, bevel=0.01)
    for index, y in enumerate(range(7, -48, -6)):
        instance(library["tile"], f"RouteMedallion_{index:02d}", (0, float(y), 0.10), scale=(1.18, 1.18, 0.72))
    # One gateway belongs at the beginning of the processional axis.  The old
    # second arch at y=-35 stood between the side museums and the palace with
    # no enclosing wall, so it read as an unexplained freestanding prop.
    instance(library["arch"], "PrecinctEntryArch", (0, 6, 0.08))
    for row, y in enumerate((4, -4, -12, -23, -34, -43)):
        for side, x in (("L", -3.55), ("R", 3.55)):
            instance(library["column"], f"Column_{row:02d}_{side}", (x, y, 0.06), scale=(1.05, 1.05, 1.05))
    # Keep the processional route free of freestanding art panels. Earlier
    # relief monuments read as floating black rectangles from oblique views;
    # all framed artwork now belongs inside the three museum buildings.
    # Two complete side museums replace the former floating vault canopies.
    all_art_paths = sorted((repo / "static" / "assets" / "gallery" / "thumbs").glob("**/*.jpg"))
    add_side_gallery_shell(
        "ArchiveOfTides",
        (-11.5, -29.0),
        library,
        all_art_paths[8:11],
        stone,
        stone_dark,
        floor_mat,
        gold,
        interior_glow,
        relic_glow_mat=memory_glass,
        window_glow_mat=pavilion_warm,
    )
    add_side_gallery_shell(
        "CliffGallery",
        (11.5, -29.0),
        library,
        all_art_paths[11:14],
        stone,
        stone_dark,
        floor_mat,
        gold,
        interior_glow,
        relic_glow_mat=memory_glass,
        window_glow_mat=pavilion_warm,
        stepped_foundation=False,
    )
    add_sculpture_garden(stone, stone_dark, gold)
    add_exploration_branch(library, stone, stone_dark, floor_mat, gold, memory_glass)
    add_palace_forecourt_and_wings_v2(
        stone,
        stone_dark,
        floor_mat,
        gold,
        interior_glow,
        library,
        guide_glow_mat=connector_glow,
    )
    # Keep the palace inside its original reserved footprint. Future scale
    # studies must move the palace rearward and may not move or overlap the
    # side galleries, their cloisters, or the processional causeway.
    palace_exterior = filtered_asset_collection(
        library["palace"],
        "LIB_PALACE_EXTERIOR_ONLY",
        (
            "PalaceNave",
            "PalaceSanctum",
            "PalaceRearSanctum",
        ),
    )
    instance(
        palace_exterior,
        "SunkenPalace",
        (0, -52.0, 0.0),
        rotation=(0, 0, math.pi),
        scale=(1.0, 1.0, 1.0),
    )
    add_palace_rear_extension_v3(stone, stone_dark, floor_mat, palace_glow)
    add_palace_nave_shell_v3(stone, stone_dark, floor_mat, palace_glow)
    add_palace_upper_circulation_v1(stone, stone_dark, floor_mat)
    palace_art_paths = all_art_paths[14:21]
    if len(palace_art_paths) < 7:
        palace_art_paths = (all_art_paths * 2)[:7]
    add_palace_interior_v3(
        repo,
        palace_art_paths,
        stone,
        stone_dark,
        floor_mat,
        palace_glow,
        memory_glass,
    )
    validate_palace_core_envelope()

    for index in range(34):
        side = -1 if index % 2 == 0 else 1
        x = side * (7.8 + (index % 5) * 1.55)
        y = 12 - index * 1.75
        # Reserve clean footprints for each building and its level bridge.
        if side < 0 and abs(y + 29.0) < 8.5:
            x -= 8.0
        if side > 0 and abs(y + 29.0) < 8.5:
            x += 8.0
        add_rock(f"Rock_{index:02d}", (x, y, 0.0), (0.8 + index % 3 * 0.28, 0.65 + index % 4 * 0.2, 0.45 + index % 3 * 0.18), stone_dark, index * 0.37)
        add_kelp(f"Kelp_{index:02d}", (x + side * 0.5, y + 0.4, 0.15), 1.2 + (index % 5) * 0.35, side * (0.18 + (index % 3) * 0.08), kelp_mat)

    # Distant ruins turn the former boundary into layered silhouettes.
    for index, y in enumerate((0, -14, -29, -44, -58)):
        scale = 1.15 - index * 0.08
        instance(library["arch"], f"DistantArch_L_{index}", (-22.0, y, 0.0), rotation=(0, 0, math.pi / 2), scale=(scale, scale, scale))
        if index != 3:
            instance(library["arch"], f"DistantArch_R_{index}", (22.0, y - 4, 0.0), rotation=(0, 0, -math.pi / 2), scale=(scale, scale, scale))
        instance(library["column"], f"DistantColumn_L_{index}", (-18.5, y - 5, 0.0), scale=(0.85, 0.85, 0.85 + index * 0.04))
        instance(library["column"], f"DistantColumn_R_{index}", (18.5, y - 9, 0.0), scale=(0.8, 0.8, 0.72 + index * 0.05))

    # A restrained final skyline layer suggests the rest of Atlantis without
    # competing with the three museum buildings in the foreground.
    for tower_index, (x, y, radius, height) in enumerate(
        (
            (-24.0, -70.0, 1.65, 4.2),
            (-16.5, -75.0, 1.25, 3.5),
            (-9.8, -72.5, 1.45, 4.0),
            (10.5, -73.0, 1.35, 3.8),
            (17.5, -76.0, 1.20, 3.4),
            (24.5, -70.5, 1.70, 4.4),
        )
    ):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=20,
            radius=radius,
            depth=height,
            location=(x, y, height * 0.5),
        )
        tower = bpy.context.object
        tower.name = f"DistantCityTower_{tower_index:02d}"
        tower.data.materials.append(ridge_mat)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, location=(x, y, height + 0.18))
        dome = bpy.context.object
        dome.name = f"DistantCityDome_{tower_index:02d}"
        dome.scale = (radius * 1.06, radius * 1.06, radius * 0.48)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        dome.data.materials.append(ridge_mat)

    add_ecological_dressing(
        library,
        stone,
        stone_dark,
        ridge_mat,
        kelp_mat,
        coral_warm,
        coral_cool,
        sponge_mat,
    )
    add_fish_schools(fish_mat)
    apply_window_light_variation()

    world = bpy.data.worlds.new("AtlantisWorld") if not bpy.data.worlds else bpy.data.worlds[0]
    scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    background = next(node for node in nodes if node.type == "BACKGROUND")
    background.inputs["Color"].default_value = (0.006, 0.085, 0.135, 1.0)
    background.inputs["Strength"].default_value = 0.40
    configure_depth_compositor(scene, world)
    # A single continuous water volume lets the existing spotlights create
    # soft shafts without the hard rectangular edges of local volume boxes.
    add_underwater_atmosphere(make_underwater_atmosphere_material())
    # Three low-opacity feathered curtains make the water columns legible in
    # both interactive Eevee previews and final Cycles renders. They land only
    # on coral/relic zones and the palace dome, never the central route.
    add_surface_light_shafts(make_soft_shaft_material())

    add_light("OceanSun", "SUN", (4, 14, 18), (0.48, 0.86, 1.0), 3.8, target=(0, -16, 0), angle=0.3, cast_shadow=True)
    add_light("SurfaceGlow", "AREA", (0, -24, 15.8), (0.30, 0.86, 1.0), 4200, target=(0, -26, 0), size=22.0, cast_shadow=False)
    add_light("CausticKey", "SPOT", (-11, -4, 15.0), (0.32, 0.92, 1.0), 2800, target=(0, -31, 0.2), angle=0.82)
    add_light("EntryPool", "AREA", (0, 10, 10), (0.34, 0.88, 1.0), 1800, target=(0, 10, 0), size=6.0, cast_shadow=False)
    add_light("MidPool", "AREA", (0, -9, 11), (0.26, 0.72, 0.95), 2600, target=(0, -9, 0), size=7.0, cast_shadow=False)
    add_light("DeepPool", "AREA", (0, -29, 12), (0.18, 0.58, 0.82), 2200, target=(0, -29, 0), size=8.0, cast_shadow=False)
    add_light("LeftEcologyShaft", "SPOT", (-15.0, -16.5, 15.4), (0.34, 0.82, 1.0), 36000, target=(-15.0, -16.5, 0.2), angle=0.38)
    add_light("RightReliquaryShaft", "SPOT", (22.7, -51.6, 15.4), (0.30, 0.74, 0.96), 36000, target=(22.7, -51.6, 0.3), angle=0.38)
    add_light("PalaceDomeShaft", "SPOT", (0.0, -56.2, 16.4), (0.28, 0.70, 0.94), 38000, target=(0.0, -56.2, 7.0), angle=0.40)
    add_light("EntryReefWarmFill", "AREA", (-8.0, 8.0, 4.8), (1.0, 0.34, 0.14), 520, target=(-8.6, 7.5, 0.8), size=3.2, cast_shadow=False)
    add_light("EntryReefCoolFill", "AREA", (8.0, 5.0, 4.6), (0.18, 0.78, 0.86), 640, target=(8.7, 4.0, 0.8), size=3.0, cast_shadow=False)
    add_light("WarmCoralAccent", "AREA", (-19.0, -37.2, 4.5), (1.0, 0.36, 0.16), 900, target=(-19.5, -38.0, 0.8), size=2.8, cast_shadow=False)
    add_light("CoolCoralAccent", "AREA", (16.8, -42.0, 4.8), (0.18, 0.76, 0.86), 1050, target=(17.4, -41.5, 0.8), size=3.0, cast_shadow=False)
    add_light("CompassFocus", "SPOT", (-4.5, 15, 9), (0.92, 0.76, 0.43), 1000, target=(0, 10, 0.2), angle=0.65)
    add_light("MuseumWingLeftFill", "AREA", (-11.5, -40.4, 3.75), (0.30, 0.74, 0.82), 3000, target=(-11.5, -44.0, 1.4), size=4.4, cast_shadow=False)
    add_light("MuseumWingRightFill", "AREA", (11.5, -40.4, 3.75), (0.30, 0.74, 0.82), 3000, target=(11.5, -44.0, 1.4), size=4.4, cast_shadow=False)
    add_light("ArchiveInteriorCool", "AREA", (-10.2, -29.0, 4.15), (0.25, 0.82, 1.0), 3000, target=(-15.0, -29.0, 2.0), size=3.8, cast_shadow=False)
    add_light("ArchiveArtworkWarmth", "POINT", (-13.4, -29.0, 2.8), (1.0, 0.55, 0.24), 1200, cast_shadow=False)
    add_light("ArchiveThresholdGold", "SPOT", (-5.8, -26.2, 5.7), (1.0, 0.68, 0.30), 1050, target=(-7.7, -29.0, 2.3), angle=0.80)
    add_light("ArchivePortalFill", "AREA", (-5.6, -29.0, 4.9), (0.24, 0.70, 0.82), 3600, target=(-8.2, -29.0, 2.35), size=3.6, cast_shadow=False)
    add_light("ArchiveFacadeWarm", "AREA", (-11.5, -19.5, 5.5), (1.0, 0.42, 0.16), 1850, target=(-11.5, -23.5, 3.2), size=4.0, cast_shadow=False)
    add_light("CliffInteriorCool", "AREA", (10.2, -29.0, 4.4), (0.28, 0.78, 1.0), 3200, target=(15.0, -29.0, 2.2), size=4.0, cast_shadow=False)
    add_light("CliffArtworkWarmth", "POINT", (13.4, -29.0, 3.0), (1.0, 0.52, 0.22), 1350, cast_shadow=False)
    add_light("CliffThresholdGold", "SPOT", (5.8, -26.1, 6.1), (1.0, 0.64, 0.27), 1150, target=(7.7, -29.0, 2.5), angle=0.78)
    add_light("CliffPortalFill", "AREA", (5.6, -29.0, 4.9), (0.24, 0.70, 0.82), 3800, target=(8.2, -29.0, 2.35), size=3.6, cast_shadow=False)
    add_light("CliffFacadeWarm", "AREA", (11.5, -19.5, 5.5), (1.0, 0.42, 0.16), 1850, target=(11.5, -23.5, 3.2), size=4.0, cast_shadow=False)
    add_light("ForecourtBeaconFill", "AREA", (0, -38.0, 8.0), (0.22, 0.78, 1.0), 1900, target=(0, -44.0, 0.8), size=7.0, cast_shadow=False)
    add_light("PalaceFacadeKey", "AREA", (-9.0, -38.0, 12.5), (0.34, 0.82, 0.94), 4600, target=(0, -55.0, 5.8), size=9.5, cast_shadow=False)
    add_light("PalaceOceanFill", "AREA", (0, -29.0, 16.0), (0.25, 0.72, 0.88), 4700, target=(0, -56.0, 5.6), size=17.0, cast_shadow=False)
    add_light("PalaceGoldRim", "SPOT", (10.0, -39.0, 12.5), (1.0, 0.59, 0.24), 2600, target=(0, -59.0, 7.0), angle=0.76)
    add_light("PalaceInteriorGlow", "AREA", (0, -48.6, 6.4), (0.25, 0.72, 0.84), 3200, target=(0, -57.0, 2.8), size=5.8, cast_shadow=False)
    add_light("PalaceNaveCoolFill", "AREA", (0, -57.0, 8.45), (0.20, 0.54, 0.64), 3900, target=(0, -57.0, 1.4), size=7.2, cast_shadow=False)
    add_light("PalaceNaveWarmFillFront", "AREA", (0, -52.0, 6.2), (1.0, 0.58, 0.28), 2800, target=(0, -53.0, 2.0), size=3.6, cast_shadow=False)
    add_light("PalaceNaveWarmFillRear", "AREA", (0, -61.8, 6.1), (1.0, 0.50, 0.22), 3200, target=(0, -63.0, 2.0), size=3.8, cast_shadow=False)
    add_light("ReliquaryColdPool", "AREA", (22.7, -50.8, 6.8), (0.23, 0.72, 0.90), 1750, target=(22.7, -51.5, 0.7), size=4.6, cast_shadow=False)
    add_light("ReliquaryWarmCore", "POINT", (22.7, -51.55, 1.35), (0.88, 0.58, 0.26), 420, cast_shadow=False)
    add_light("PalaceFocalArtworkWarm", "SPOT", (0, -59.2, 7.6), (1.0, 0.47, 0.18), 2800, target=(0, -65.94, 3.85), angle=0.58)
    add_light("PalaceLeftArtWash", "AREA", (-3.45, -55.3, 4.8), (0.34, 0.72, 0.82), 2800, target=(-4.70, -55.3, 3.20), size=3.5, cast_shadow=False)
    add_light("PalaceRightArtWash", "AREA", (3.45, -55.3, 4.8), (0.34, 0.72, 0.82), 2800, target=(4.70, -55.3, 3.20), size=3.5, cast_shadow=False)
    add_light("PalaceDaisWarmPool", "POINT", (0, -63.2, 4.5), (1.0, 0.46, 0.18), 1500, cast_shadow=False)
    add_light("PalaceRearWallFill", "AREA", (0, -61.0, 5.6), (0.20, 0.58, 0.68), 2800, target=(0, -65.9, 3.8), size=4.4, cast_shadow=False)
    for oculus_index, oculus_y in enumerate((-52.0, -57.0, -62.0)):
        add_light(
            f"PalaceOculusShaft_{oculus_index:02d}",
            "SPOT",
            (0, oculus_y, 8.78),
            (0.36, 0.75, 0.86),
            1200,
            target=(0, oculus_y, 1.2),
            angle=0.38,
        )

    bpy.ops.object.camera_add(location=(22.0, 30.0, 18.5))
    camera = bpy.context.object
    camera.name = "GalleryOverviewCamera"
    camera.data.lens = 36
    camera.data.sensor_width = 36
    point_at(camera, (0, -27, 2.4))
    scene.camera = camera

    bpy.ops.object.camera_add(location=(0.0, 16.0, 2.6))
    walk_camera = bpy.context.object
    walk_camera.name = "GalleryWalkthroughCamera"
    walk_camera.data.lens = 30
    point_at(walk_camera, (0, -28, 2.1))

    bpy.ops.object.camera_add(location=(20.0, -13.0, 11.8))
    palace_camera = bpy.context.object
    palace_camera.name = "PalaceReviewCamera"
    palace_camera.data.lens = 36
    palace_camera.data.sensor_width = 36
    point_at(palace_camera, (0, -57.0, 6.2))

    bpy.ops.object.camera_add(location=(0.0, -46.55, 2.62))
    palace_entrance_camera = bpy.context.object
    palace_entrance_camera.name = "PalaceInteriorEntranceCamera"
    palace_entrance_camera.data.lens = 29
    palace_entrance_camera.data.sensor_width = 36
    point_at(palace_entrance_camera, (0, -60.0, 3.45))

    bpy.ops.object.camera_add(location=(0.0, -28.0, 8.0))
    palace_facade_camera = bpy.context.object
    palace_facade_camera.name = "PalaceFacadeReviewCamera"
    palace_facade_camera.data.lens = 34
    palace_facade_camera.data.sensor_width = 36
    point_at(palace_facade_camera, (0, -56.0, 6.4))

    bpy.ops.object.camera_add(location=(0.0, -48.9, 4.25))
    palace_inside_camera = bpy.context.object
    palace_inside_camera.name = "PalaceInteriorGalleryCamera"
    palace_inside_camera.data.lens = 24
    palace_inside_camera.data.sensor_width = 36
    point_at(palace_inside_camera, (0.0, -59.0, 3.45))

    bpy.ops.object.camera_add(location=(0.0, -48.15, 2.65))
    palace_walk_camera = bpy.context.object
    palace_walk_camera.name = "PalaceInteriorWalkReviewCamera"
    palace_walk_camera.data.lens = 23
    palace_walk_camera.data.sensor_width = 36
    point_at(palace_walk_camera, (0, -63.10, 3.70))

    bpy.ops.object.camera_add(location=(-4.10, -58.10, 2.85))
    palace_upper_stair_camera = bpy.context.object
    palace_upper_stair_camera.name = "PalaceUpperStairReviewCamera"
    palace_upper_stair_camera.data.lens = 28
    palace_upper_stair_camera.data.sensor_width = 36
    point_at(palace_upper_stair_camera, (-4.35, -64.55, 4.75))

    bpy.ops.object.camera_add(location=(-3.60, -59.10, 5.55))
    palace_upper_bridge_camera = bpy.context.object
    palace_upper_bridge_camera.name = "PalaceUpperBridgeReviewCamera"
    palace_upper_bridge_camera.data.lens = 32
    palace_upper_bridge_camera.data.sensor_width = 36
    point_at(palace_upper_bridge_camera, (0.0, -64.78, 5.35))

    bpy.ops.object.camera_add(location=(0.0, -48.20, 4.80))
    palace_upper_overview_camera = bpy.context.object
    palace_upper_overview_camera.name = "PalaceUpperOverviewReviewCamera"
    palace_upper_overview_camera.data.lens = 26
    palace_upper_overview_camera.data.sensor_width = 36
    point_at(palace_upper_overview_camera, (0.0, -63.40, 5.05))

    bpy.ops.object.camera_add(location=(-2.25, -55.35, 3.10))
    palace_sidewall_camera = bpy.context.object
    palace_sidewall_camera.name = "PalaceSideWallReviewCamera"
    palace_sidewall_camera.data.lens = 42
    palace_sidewall_camera.data.sensor_width = 36
    point_at(palace_sidewall_camera, (-4.66, -55.35, 3.20))

    bpy.ops.object.camera_add(location=(0.0, -9.5, 3.3))
    environment_camera = bpy.context.object
    environment_camera.name = "UnderwaterEstablishingCamera"
    environment_camera.data.lens = 36
    environment_camera.data.sensor_width = 36
    point_at(environment_camera, (0, -56.0, 5.8))

    # Stand on the gallery bridge and look squarely through the named arch.
    # This makes the architectural sequence and the fact that the paintings
    # belong to an enclosed room immediately readable in review renders.
    bpy.ops.object.camera_add(location=(-3.6, -29.0, 3.05))
    archive_camera = bpy.context.object
    archive_camera.name = "ArchiveOfTidesReviewCamera"
    archive_camera.data.lens = 23
    archive_camera.data.sensor_width = 36
    point_at(archive_camera, (-11.5, -29.0, 2.95))

    bpy.ops.object.camera_add(location=(3.6, -29.0, 3.05))
    cliff_camera = bpy.context.object
    cliff_camera.name = "CliffGalleryReviewCamera"
    cliff_camera.data.lens = 23
    cliff_camera.data.sensor_width = 36
    point_at(cliff_camera, (11.5, -29.0, 2.95))

    bpy.ops.object.camera_add(location=(0.0, 5.5, 14.2))
    district_camera = bpy.context.object
    district_camera.name = "SideDistrictWideReviewCamera"
    district_camera.data.lens = 31
    district_camera.data.sensor_width = 36
    point_at(district_camera, (0, -38.0, 3.10))

    # Elevated oblique plan view for checking the architectural relationship:
    # two side galleries -> roofed loggias -> gatehouses -> central palace.
    bpy.ops.object.camera_add(location=(19.0, -8.0, 13.4))
    architecture_camera = bpy.context.object
    architecture_camera.name = "ArchitectureLogicReviewCamera"
    architecture_camera.data.lens = 38
    architecture_camera.data.sensor_width = 36
    point_at(architecture_camera, (0, -41.0, 2.8))

    # Eye-level view through the newly opened rear door and continuous
    # cloister, used to verify that the side gallery and palace are connected.
    bpy.ops.object.camera_add(location=(-11.50, -32.05, 2.48))
    connection_camera = bpy.context.object
    connection_camera.name = "PalaceConnectionReviewCamera"
    connection_camera.data.lens = 26
    connection_camera.data.sensor_width = 36
    point_at(connection_camera, (-11.50, -45.8, 2.20))

    bpy.ops.object.camera_add(location=(18.0, 10.0, 8.8))
    ecology_camera = bpy.context.object
    ecology_camera.name = "UnderwaterEcologyReviewCamera"
    ecology_camera.data.lens = 34
    ecology_camera.data.sensor_width = 36
    point_at(ecology_camera, (0, -35.0, 2.85))

    bpy.ops.object.camera_add(location=(0.0, 13.0, 2.72))
    visitor_camera = bpy.context.object
    visitor_camera.name = "VisitorRouteReviewCamera"
    visitor_camera.data.lens = 31
    visitor_camera.data.sensor_width = 36
    point_at(visitor_camera, (0, -56.0, 5.10))

    bpy.ops.object.camera_add(location=(0.0, 17.0, 6.2))
    final_hero_camera = bpy.context.object
    final_hero_camera.name = "FinalHeroReviewCamera"
    final_hero_camera.data.lens = 32
    final_hero_camera.data.sensor_width = 36
    point_at(final_hero_camera, (0, -47.5, 5.10))

    bpy.ops.object.camera_add(location=(0.0, -36.5, 5.2))
    god_ray_camera = bpy.context.object
    god_ray_camera.name = "GodRayReviewCamera"
    god_ray_camera.data.lens = 34
    god_ray_camera.data.sensor_width = 36
    point_at(god_ray_camera, (0.0, -48.0, 6.8))

    bpy.ops.object.camera_add(location=(-20.8, -4.5, 2.90))
    reef_camera = bpy.context.object
    reef_camera.name = "CoralGardenReviewCamera"
    reef_camera.data.lens = 48
    reef_camera.data.sensor_width = 36
    point_at(reef_camera, (-18.7, -15.5, 1.05))

    # Eye-level proof that the optional route turns away from the museum loop
    # and resolves at a separate archaeological destination.
    bpy.ops.object.camera_add(location=(14.8, -33.0, 6.8))
    branch_camera = bpy.context.object
    branch_camera.name = "SunkenReliquaryRouteReviewCamera"
    branch_camera.data.lens = 31
    branch_camera.data.sensor_width = 36
    point_at(branch_camera, (20.4, -45.5, 0.8))

    # An oblique view across the left coral garden makes the water column and
    # localized shaft readable; the main path remains outside the light pool.
    bpy.ops.object.camera_add(location=(-10.5, -7.0, 4.2))
    shaft_camera = bpy.context.object
    shaft_camera.name = "CoralShaftReviewCamera"
    shaft_camera.data.lens = 32
    shaft_camera.data.sensor_width = 36
    point_at(shaft_camera, (-17.2, -16.0, 5.0))
    bind_review_timeline(
        scene,
        (
            (1, "01_FINAL_HERO", final_hero_camera),
            (20, "02_VISITOR_ROUTE", visitor_camera),
            (40, "03_MUSEUM_DISTRICT", district_camera),
            (50, "03B_ARCHITECTURE_LOGIC", architecture_camera),
            (55, "03C_CONNECTION_CLOISTER", connection_camera),
            (60, "04_ARCHIVE_OF_TIDES", archive_camera),
            (80, "05_CLIFF_GALLERY", cliff_camera),
            (100, "06_PALACE_FACADE", palace_facade_camera),
            (110, "07_PALACE_ENTRY", palace_entrance_camera),
            (120, "08_PALACE_INTERIOR", palace_walk_camera),
            (122, "08A_PALACE_UPPER_STAIR", palace_upper_stair_camera),
            (124, "08B_PALACE_UPPER_BRIDGE", palace_upper_bridge_camera),
            (126, "08C_PALACE_UPPER_OVERVIEW", palace_upper_overview_camera),
            (130, "08B_PALACE_SIDE_WALL", palace_sidewall_camera),
            (140, "09_UNDERWATER_ECOLOGY", ecology_camera),
            (150, "09B_SUNKEN_RELIQUARY_ROUTE", branch_camera),
            (155, "09C_CORAL_LIGHT_SHAFT", shaft_camera),
            (160, "10_CORAL_GARDEN", reef_camera),
        ),
    )
    # Open on the architectural-logic checkpoint for this review round.  The
    # palace facade remains available at frame 100.
    scene.frame_set(50)
    scene.camera = architecture_camera

    master = bpy.data.objects.new("ATLANTIS_GALLERY_MASTER", None)
    master["purpose"] = "Spatial review and lighting master"
    master["web_runtime"] = "Six modular GLBs loaded by Three.js"
    master["units"] = "meters"
    master["textures"] = "packed into master blend"
    master["review_frames"] = "1, 20, 40, 50, 55, 60, 80, 100, 110, 120, 130, 140, 150, 155, 160"
    bpy.context.scene.collection.objects.link(master)
    organize_scene_for_review(scene)
    configure_review_viewports(scene)

    output_dir = repo / "assets" / "gallery" / "blender"
    preview_dir = repo / "output" / "gallery"
    output_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    blend_path = output_dir / "atlantis-gallery-master-v1.blend"
    # Keep the review master portable. The modular source assets already pack
    # their PBR maps; this also embeds the gallery artwork thumbnails added by
    # the assembly script so opening the .blend never depends on absolute paths.
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
    if args().skip_renders:
        scene.frame_set(50)
        scene.camera = architecture_camera
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
        print(f"MASTER_BLEND={blend_path}")
        return

    # Camera-bound timeline markers are useful in the interactive review file,
    # but Blender reapplies the marker camera at frame 50 during a render.  Keep
    # a copy, clear them for the batch preview pass, then restore them before the
    # final save so every output really uses the camera named in preview_specs.
    marker_specs = tuple(
        (marker.name, marker.frame, marker.camera)
        for marker in scene.timeline_markers
    )
    for marker in list(scene.timeline_markers):
        scene.timeline_markers.remove(marker)

    preview_specs = (
        (architecture_camera, preview_dir / "atlantis-architecture-logic-review.png"),
        (district_camera, preview_dir / "atlantis-museum-district-review.png"),
        (ecology_camera, preview_dir / "atlantis-ecology-boundary-review.png"),
        (visitor_camera, preview_dir / "atlantis-visitor-route-review.png"),
        (reef_camera, preview_dir / "atlantis-coral-garden-review.png"),
        (god_ray_camera, preview_dir / "atlantis-god-ray-review.png"),
        (branch_camera, preview_dir / "atlantis-sunken-reliquary-route-review.png"),
        (shaft_camera, preview_dir / "atlantis-coral-shaft-review.png"),
        (palace_walk_camera, preview_dir / "atlantis-final-palace-interior-review.png"),
    )
    for review_camera, preview_path in preview_specs:
        scene.camera = review_camera
        scene.render.filepath = str(preview_path)
        bpy.ops.render.render(write_still=True)
        print(f"MASTER_PREVIEW={preview_path}")
    scene.cycles.samples = 48
    scene.render.resolution_percentage = 72
    scene.camera = final_hero_camera
    hero_path = preview_dir / "atlantis-final-hero-review.png"
    scene.render.filepath = str(hero_path)
    bpy.ops.render.render(write_still=True)
    print(f"MASTER_PREVIEW={hero_path}")
    for marker_name, marker_frame, marker_camera in marker_specs:
        marker = scene.timeline_markers.new(marker_name, frame=marker_frame)
        marker.camera = marker_camera
    scene.camera = final_hero_camera
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
    print(f"MASTER_BLEND={blend_path}")


if __name__ == "__main__":
    build(Path(args().repo).expanduser().resolve())
