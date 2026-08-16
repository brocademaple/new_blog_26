#!/usr/bin/env python3
"""Generate the six Atlantis Gallery assets with Blender.

Run with:
  blender --background --python generate_atlantis_assets.py -- --output-root /path/to/repo

The script intentionally uses only Blender's bundled Python API so the asset
pipeline stays reproducible on a clean machine.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import bpy
from mathutils import Vector


ASSETS = {
    "lobby-platform": {"tri_limit": 5000, "builder": "build_lobby_platform"},
    "room-archway": {"tri_limit": 8000, "builder": "build_room_archway"},
    "corridor-column": {"tri_limit": 3000, "builder": "build_corridor_column"},
    "wall-relief-panel": {"tri_limit": 4000, "builder": "build_wall_relief_panel"},
    "ceiling-vault": {"tri_limit": 10000, "builder": "build_ceiling_vault"},
    "floor-tile-unit": {"tri_limit": 500, "builder": "build_floor_tile_unit"},
    "sunken-palace": {"tri_limit": 20000, "builder": "build_sunken_palace"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True, help="Root of the Hugo repository")
    parser.add_argument("--only", choices=sorted(ASSETS), help="Generate one asset")
    parser.add_argument("--blend-only", action="store_true", help="Save editable Blender source without exporting GLB")
    argv = os.sys.argv
    return parser.parse_args(argv[argv.index("--") + 1 :] if "--" in argv else [])


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.images):
        for block in list(collection):
            collection.remove(block)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.world.color = (0.004, 0.02, 0.028)


def load_texture(path: Path, non_color: bool = False, max_size: int | None = None) -> bpy.types.Image:
    if not path.exists():
        raise FileNotFoundError(
            f"Missing Atlantis PBR texture: {path}. Run scripts/generate_atlantis_textures.py first."
        )
    image = bpy.data.images.load(str(path), check_existing=True)
    if max_size and max(image.size) > max_size:
        image.scale(max_size, max_size)
    if non_color:
        image.colorspace_settings.name = "Non-Color"
    image.pack()
    return image


def make_materials(output_root: Path, max_size: int | None = None) -> dict[str, bpy.types.Material]:
    pbr_root = output_root / "static" / "assets" / "gallery" / "textures" / "atlantis"
    texture_sets = {
        "stone": {
            "base": load_texture(pbr_root / "stone" / "stone_basecolor.jpg", max_size=max_size),
            "normal": load_texture(pbr_root / "stone" / "stone_normal.png", True, max_size),
            "roughness": load_texture(pbr_root / "stone" / "stone_roughness.png", True, max_size),
        },
        "bronze": {
            "base": load_texture(pbr_root / "bronze" / "bronze_basecolor.jpg", max_size=max_size),
            "normal": load_texture(pbr_root / "bronze" / "bronze_normal.png", True, max_size),
            "roughness": load_texture(pbr_root / "bronze" / "bronze_roughness.png", True, max_size),
            "metalness": load_texture(pbr_root / "bronze" / "bronze_metalness.png", True, max_size),
        },
        "floor": {
            # The 2K floor set remains available to Three.js for the 124 m scene.
            # A 512 px packed copy keeps the small tile GLB below the 5 MB guide limit.
            "base": load_texture(pbr_root / "floor" / "embedded-512" / "floor_basecolor.jpg"),
            "normal": load_texture(pbr_root / "floor" / "embedded-512" / "floor_normal.png", True),
            "roughness": load_texture(pbr_root / "floor" / "embedded-512" / "floor_roughness.png", True),
        },
    }

    def material(
        name: str,
        color: tuple[float, float, float, float],
        metallic: float,
        rough: float,
        texture_set: dict[str, bpy.types.Image],
        normal_strength: float,
    ):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        bsdf = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            bsdf = nodes.new("ShaderNodeBsdfPrincipled")
            output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
            if output is None:
                output = nodes.new("ShaderNodeOutputMaterial")
            links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Metallic"].default_value = metallic
        bsdf.inputs["Roughness"].default_value = rough

        base_tex = nodes.new("ShaderNodeTexImage")
        base_tex.name = f"{name}_basecolor"
        base_tex.image = texture_set["base"]
        links.new(base_tex.outputs["Color"], bsdf.inputs["Base Color"])

        normal_tex = nodes.new("ShaderNodeTexImage")
        normal_tex.name = f"{name}_normal"
        normal_tex.image = texture_set["normal"]
        normal_tex.image.colorspace_settings.name = "Non-Color"
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.inputs["Strength"].default_value = normal_strength
        links.new(normal_tex.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])

        rough_tex = nodes.new("ShaderNodeTexImage")
        rough_tex.name = f"{name}_roughness"
        rough_tex.image = texture_set["roughness"]
        rough_tex.image.colorspace_settings.name = "Non-Color"
        links.new(rough_tex.outputs["Color"], bsdf.inputs["Roughness"])

        if texture_set.get("metalness"):
            metal_tex = nodes.new("ShaderNodeTexImage")
            metal_tex.name = f"{name}_metalness"
            metal_tex.image = texture_set["metalness"]
            metal_tex.image.colorspace_settings.name = "Non-Color"
            links.new(metal_tex.outputs["Color"], bsdf.inputs["Metallic"])
        return mat

    return {
        "stone": material("AtlantisStone_mat", (0.72, 0.82, 0.78, 1.0), 0.03, 0.84, texture_sets["stone"], 0.62),
        "stone_dark": material("AtlantisStoneDark_mat", (0.42, 0.56, 0.55, 1.0), 0.02, 0.9, texture_sets["stone"], 0.72),
        "gold": material("AtlantisGold_mat", (0.92, 0.80, 0.58, 1.0), 0.76, 0.34, texture_sets["bronze"], 0.34),
        "floor": material("AtlantisFloor_mat", (0.72, 0.80, 0.76, 1.0), 0.08, 0.78, texture_sets["floor"], 0.66),
    }


def assign_material(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    if obj.type in {"MESH", "CURVE"}:
        obj.data.materials.append(mat)


def make_emissive_material(
    name: str,
    color: tuple[float, float, float, float],
    strength: float = 4.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(node for node in mat.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.28
    emission_input = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
    if emission_input:
        emission_input.default_value = color
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def add_box(
    name: str,
    size: tuple[float, float, float],
    location: tuple[float, float, float],
    mat: bpy.types.Material,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    bevel: float = 0.02,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        modifier = obj.modifiers.new("EdgeWeathering", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    assign_material(obj, mat)
    return obj


def add_cylinder(
    name: str,
    radius: float,
    depth: float,
    z: float,
    mat: bpy.types.Material,
    vertices: int = 24,
    bevel: float = 0.025,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=(0, 0, z))
    obj = bpy.context.object
    obj.name = name
    assign_material(obj, mat)
    if bevel:
        modifier = obj.modifiers.new("EdgeWeathering", "BEVEL")
        modifier.width = min(bevel, depth * 0.12)
        modifier.segments = 2
    return obj


def add_torus(
    name: str,
    major: float,
    minor: float,
    location: tuple[float, float, float],
    mat: bpy.types.Material,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
    major_segments: int = 32,
    minor_segments: int = 6,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=major_segments,
        minor_segments=minor_segments,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    assign_material(obj, mat)
    return obj


def add_curve_tube(
    name: str,
    points: list[tuple[float, float, float]],
    radius: float,
    mat: bpy.types.Material,
    resolution: int = 2,
) -> bpy.types.Object:
    curve = bpy.data.curves.new(name + "_curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = resolution
    curve.bevel_depth = radius
    curve.bevel_resolution = 1
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (*co, 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    assign_material(obj, mat)
    return obj


def radial_spoke(name: str, angle: float, length: float, width: float, z: float, mat: bpy.types.Material):
    x = math.cos(angle) * length * 0.53
    y = math.sin(angle) * length * 0.53
    return add_box(name, (length, width, 0.018), (x, y, z), mat, rotation=(0, 0, angle), bevel=0.008)


def build_lobby_platform(mats: dict[str, bpy.types.Material]) -> None:
    add_cylinder("LobbyPlatform_mesh", 1.5, 0.13, 0.065, mats["stone_dark"], 48)
    add_cylinder("LobbyPlatformDeck_mesh", 1.42, 0.07, 0.165, mats["stone"], 48)
    add_torus("LobbyPlatformOuterInlay_mesh", 1.39, 0.025, (0, 0, 0.198), mats["gold"], major_segments=48)
    add_torus("LobbyPlatformInnerInlay_mesh", 0.62, 0.018, (0, 0, 0.202), mats["gold"], major_segments=36)
    add_cylinder("LobbyPlatformMedallion_mesh", 0.19, 0.025, 0.205, mats["gold"], 24)
    for index in range(12):
        radial_spoke(f"LobbyPlatformSpoke_{index:02d}_mesh", index * math.tau / 12, 0.67, 0.025, 0.204, mats["gold"])


def build_room_archway(mats: dict[str, bpy.types.Material]) -> None:
    # Blender Z becomes Three.js Y; Blender -Y becomes the model's forward +Z.
    add_box("ArchLeftPier_mesh", (0.55, 0.48, 3.12), (-1.72, 0, 1.56), mats["stone"], bevel=0.05)
    add_box("ArchRightPier_mesh", (0.55, 0.48, 3.12), (1.72, 0, 1.56), mats["stone"], bevel=0.05)
    add_box("ArchLeftFoot_mesh", (0.78, 0.58, 0.34), (-1.72, 0, 0.17), mats["stone_dark"], bevel=0.04)
    add_box("ArchRightFoot_mesh", (0.78, 0.58, 0.34), (1.72, 0, 0.17), mats["stone_dark"], bevel=0.04)
    add_box("ArchLeftCapital_mesh", (0.82, 0.58, 0.26), (-1.72, 0, 3.05), mats["gold"], bevel=0.025)
    add_box("ArchRightCapital_mesh", (0.82, 0.58, 0.26), (1.72, 0, 3.05), mats["gold"], bevel=0.025)

    outer_points = []
    inner_points = []
    for index in range(25):
        theta = index * math.pi / 24
        outer_points.append((1.72 * math.cos(theta), 0, 3.05 + 1.72 * math.sin(theta)))
        inner_points.append((1.49 * math.cos(theta), -0.255, 3.05 + 1.49 * math.sin(theta)))
    add_curve_tube("ArchStoneArc_mesh", outer_points, 0.30, mats["stone"], resolution=1)
    add_curve_tube("ArchGoldInlay_mesh", inner_points, 0.045, mats["gold"], resolution=1)
    # Broken silhouette blocks echo the concept board without exceeding the web budget.
    fragments = [(-1.93, 3.68, 0.34, -0.08), (1.9, 3.55, 0.42, 0.09), (-1.55, 4.42, 0.28, 0.05)]
    for index, (x, z, height, tilt) in enumerate(fragments):
        add_box(
            f"ArchFragment_{index:02d}_mesh",
            (0.42, 0.44, height),
            (x, 0, z),
            mats["stone_dark"],
            rotation=(0, tilt, tilt),
            bevel=0.045,
        )


def build_corridor_column(mats: dict[str, bpy.types.Material]) -> None:
    add_cylinder("ColumnBaseLower_mesh", 0.30, 0.24, 0.12, mats["stone_dark"], 20)
    add_cylinder("ColumnBaseGold_mesh", 0.27, 0.08, 0.29, mats["gold"], 20)
    add_cylinder("ColumnBaseUpper_mesh", 0.25, 0.24, 0.45, mats["stone"], 20)
    add_cylinder("ColumnShaft_mesh", 0.205, 3.92, 2.53, mats["stone"], 20)
    for index in range(8):
        angle = index * math.tau / 8
        radius = 0.218
        add_box(
            f"ColumnFlute_{index:02d}_mesh",
            (0.025, 0.035, 3.48),
            (math.cos(angle) * radius, math.sin(angle) * radius, 2.54),
            mats["gold"] if index % 2 == 0 else mats["stone_dark"],
            rotation=(0, 0, angle),
            bevel=0.005,
        )
    add_cylinder("ColumnNeckGold_mesh", 0.24, 0.09, 4.56, mats["gold"], 20)
    add_cylinder("ColumnCapitalRound_mesh", 0.29, 0.18, 4.69, mats["stone"], 20)
    add_box("ColumnCapital_mesh", (0.62, 0.56, 0.22), (0, 0, 4.86), mats["stone_dark"], bevel=0.035)
    add_box("ColumnCapitalGold_mesh", (0.56, 0.50, 0.08), (0, 0, 4.97), mats["gold"], bevel=0.018)


def panel_box(
    name: str,
    size_x: float,
    size_z: float,
    center_x: float,
    center_z: float,
    depth: float,
    mat: bpy.types.Material,
    rotation_y: float = 0.0,
) -> bpy.types.Object:
    # The panel's front is Blender -Y, exported as Three.js +Z.
    return add_box(
        name,
        (size_x, depth, size_z),
        (center_x, -0.10 - depth / 2, center_z),
        mat,
        rotation=(0, rotation_y, 0),
        bevel=0.012,
    )


def build_wall_relief_panel(mats: dict[str, bpy.types.Material]) -> None:
    add_box("WallReliefBase_mesh", (3.0, 0.10, 2.0), (0, -0.05, 1.0), mats["stone_dark"], bevel=0.04)
    panel_box("WallReliefTop_mesh", 2.72, 0.08, 0, 1.86, 0.045, mats["gold"])
    panel_box("WallReliefBottom_mesh", 2.72, 0.08, 0, 0.14, 0.045, mats["gold"])
    panel_box("WallReliefLeft_mesh", 0.08, 1.72, -1.36, 1.0, 0.045, mats["gold"])
    panel_box("WallReliefRight_mesh", 0.08, 1.72, 1.36, 1.0, 0.045, mats["gold"])
    add_torus(
        "WallReliefMedallion_mesh",
        0.43,
        0.055,
        (0, -0.16, 1.0),
        mats["gold"],
        rotation=(math.pi / 2, 0, 0),
        major_segments=32,
        minor_segments=6,
    )
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=10, radius=0.19, location=(0, -0.19, 1.0))
    center = bpy.context.object
    center.name = "WallReliefCenter_mesh"
    center.scale.y = 0.28
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(center, mats["stone"])
    for index in range(8):
        angle = index * math.tau / 8
        x = math.cos(angle) * 0.76
        z = 1.0 + math.sin(angle) * 0.60
        panel_box(
            f"WallReliefRay_{index:02d}_mesh",
            0.50,
            0.035,
            x,
            z,
            0.035,
            mats["gold"],
            rotation_y=-angle,
        )
    for index, x in enumerate((-1.05, 1.05)):
        panel_box(f"WallReliefPilaster_{index}_mesh", 0.14, 1.48, x, 1.0, 0.05, mats["stone"])
    # This asset is the documented exception: origin at the back-face center,
    # rather than at the bottom center used by freestanding architecture.
    for obj in bpy.context.scene.objects:
        obj.location.z -= 1.0


def build_ceiling_vault(mats: dict[str, bpy.types.Material]) -> None:
    width = 8.0
    depth = 6.0
    x_segments = 24
    y_segments = 8
    vertices = []
    faces = []
    uvs = []
    for yi in range(y_segments + 1):
        y = -depth / 2 + depth * yi / y_segments
        for xi in range(x_segments + 1):
            x = -width / 2 + width * xi / x_segments
            profile = max(0.0, 1.0 - (x / (width / 2)) ** 2)
            z = 0.02 + 0.82 * profile
            vertices.append((x, y, z))
            uvs.append((xi / x_segments, yi / y_segments))
    stride = x_segments + 1
    for yi in range(y_segments):
        for xi in range(x_segments):
            a = yi * stride + xi
            faces.append((a, a + 1, a + 1 + stride, a + stride))
    mesh = bpy.data.meshes.new("CeilingVault_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for polygon in mesh.polygons:
        for loop_index in polygon.loop_indices:
            uv_layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]
    shell = bpy.data.objects.new("CeilingVault_mesh", mesh)
    bpy.context.collection.objects.link(shell)
    assign_material(shell, mats["stone"])
    solidify = shell.modifiers.new("VaultThickness", "SOLIDIFY")
    solidify.thickness = 0.055

    for index, y in enumerate((-2.55, -1.25, 0.0, 1.25, 2.55)):
        points = []
        for step in range(25):
            x = -width / 2 + width * step / 24
            profile = max(0.0, 1.0 - (x / (width / 2)) ** 2)
            points.append((x, y, 0.08 + 0.82 * profile))
        add_curve_tube(f"CeilingVaultRib_{index:02d}_mesh", points, 0.045, mats["gold"], resolution=1)
    add_box("CeilingVaultSpine_mesh", (0.10, 5.62, 0.08), (0, 0, 0.87), mats["gold"], bevel=0.018)
    add_torus("CeilingVaultMedallion_mesh", 0.48, 0.05, (0, 0, 0.91), mats["gold"], major_segments=28)


def build_floor_tile_unit(mats: dict[str, bpy.types.Material]) -> None:
    add_box("FloorTileBase_mesh", (1.0, 1.0, 0.045), (0, 0, 0.0225), mats["floor"], bevel=0)
    border_specs = [
        ((0.84, 0.035, 0.018), (0, -0.40, 0.054)),
        ((0.84, 0.035, 0.018), (0, 0.40, 0.054)),
        ((0.035, 0.84, 0.018), (-0.40, 0, 0.054)),
        ((0.035, 0.84, 0.018), (0.40, 0, 0.054)),
    ]
    for index, (size, location) in enumerate(border_specs):
        add_box(f"FloorTileBorder_{index:02d}_mesh", size, location, mats["gold"], bevel=0)
    for index, angle in enumerate((math.pi / 4, -math.pi / 4)):
        add_box(
            f"FloorTileDiamond_{index:02d}_mesh",
            (0.62, 0.035, 0.018),
            (0, 0, 0.056),
            mats["gold"],
            rotation=(0, 0, angle),
            bevel=0,
        )
    add_cylinder("FloorTileMedallion_mesh", 0.12, 0.022, 0.061, mats["gold"], 12, bevel=0)


def build_sunken_palace(mats: dict[str, bpy.types.Material]) -> None:
    """Build the terminal palace as one readable architectural silhouette."""
    warm_glass = make_emissive_material("PalaceWarmGalleryGlass_mat", (1.0, 0.20, 0.025, 1.0), 2.35)
    # Terraced base and broad ceremonial stair.
    add_box("PalaceLowerPlinth_mesh", (20.0, 13.5, 0.42), (0, 0.5, 0.21), mats["stone_dark"], bevel=0.10)
    add_box("PalaceUpperPlinth_mesh", (18.4, 11.8, 0.36), (0, 0.25, 0.60), mats["stone"], bevel=0.08)
    for index in range(7):
        width = 10.8 - index * 0.58
        add_box(
            f"PalaceStair_{index:02d}_mesh",
            (width, 0.78, 0.16),
            (0, -7.1 + index * 0.62, 0.16 + index * 0.13),
            mats["stone"] if index % 2 else mats["stone_dark"],
            bevel=0.035,
        )

    # The standalone component now contains the palace exterior only.  The
    # authoritative nave, rear archive and upper circulation are generated in
    # build_atlantis_gallery_master.py.  Keeping a second interior here caused
    # legacy walls to reappear at the collection-instance origin during glTF
    # export and block the public entrance.
    add_box("PalaceFacadeLeftShoulder_mesh", (3.15, 0.78, 5.35), (-3.72, -3.48, 3.27), mats["stone"], bevel=0.09)
    add_box("PalaceFacadeRightShoulder_mesh", (3.15, 0.78, 5.35), (3.72, -3.48, 3.27), mats["stone"], bevel=0.09)
    add_box("PalaceFacadeCrown_mesh", (10.6, 0.78, 0.86), (0, -3.48, 5.86), mats["stone_dark"], bevel=0.08)
    add_box("PalaceLeftWing_mesh", (4.2, 9.6, 3.3), (-7.1, 0.65, 2.15), mats["stone_dark"], bevel=0.11)
    add_box("PalaceRightWing_mesh", (4.2, 9.6, 3.3), (7.1, 0.65, 2.15), mats["stone_dark"], bevel=0.11)

    # Horizontal bronze bands keep the palace legible through underwater fog.
    add_box("PalaceMainCornice_mesh", (11.25, 8.55, 0.22), (0, 0.55, 6.42), mats["gold"], bevel=0.045)
    add_box("PalaceLeftCornice_mesh", (4.55, 9.85, 0.18), (-7.1, 0.65, 3.86), mats["gold"], bevel=0.035)
    add_box("PalaceRightCornice_mesh", (4.55, 9.85, 0.18), (7.1, 0.65, 3.86), mats["gold"], bevel=0.035)

    # Central ceremonial portal. The asset front is Blender -Y, exported as Three.js +Z.
    for side in (-1, 1):
        add_box(f"PalacePortalPier_{side:+d}_mesh", (0.62, 0.68, 3.75), (side * 1.82, -3.92, 2.50), mats["stone"], bevel=0.06)
        add_box(f"PalacePortalGold_{side:+d}_mesh", (0.13, 0.73, 3.15), (side * 1.47, -4.01, 2.64), mats["gold"], bevel=0.018)
    portal_outer = []
    portal_inner = []
    for index in range(29):
        theta = index * math.pi / 28
        portal_outer.append((2.12 * math.cos(theta), -4.0, 4.12 + 2.12 * math.sin(theta)))
        portal_inner.append((1.58 * math.cos(theta), -4.08, 4.02 + 1.58 * math.sin(theta)))
    add_curve_tube("PalacePortalArch_mesh", portal_outer, 0.38, mats["stone"], resolution=1)
    add_curve_tube("PalacePortalInlay_mesh", portal_inner, 0.07, mats["gold"], resolution=1)

    # Facade colonnade creates architectural depth rather than a flat box.
    for index, x in enumerate((-4.4, -3.25, 3.25, 4.4)):
        add_cylinder(f"PalaceFacadeColumn_{index:02d}_mesh", 0.24, 3.8, 2.55, mats["stone"], 18, bevel=0.035)
        column = bpy.context.object
        column.location.x = x
        column.location.y = -4.0
        add_cylinder(f"PalaceFacadeCapital_{index:02d}_mesh", 0.34, 0.20, 4.50, mats["gold"], 18, bevel=0.02)
        capital = bpy.context.object
        capital.location.x = x
        capital.location.y = -4.0

    # Balcony, balustrade, and second-level facade windows.
    add_box("PalaceBalconySlab_mesh", (9.2, 1.35, 0.22), (0, -4.12, 4.78), mats["gold"], bevel=0.045)
    for index, x in enumerate((-4.15, -3.45, -2.75, -2.05, 2.05, 2.75, 3.45, 4.15)):
        add_cylinder(f"PalaceBaluster_{index:02d}_mesh", 0.075, 0.72, 5.18, mats["stone"], 12, bevel=0.012)
        baluster = bpy.context.object
        baluster.location.x = x
        baluster.location.y = -4.62
    add_box("PalaceBalconyRail_mesh", (9.0, 0.16, 0.16), (0, -4.62, 5.58), mats["gold"], bevel=0.025)
    for index, x in enumerate((-3.75, -2.55, 2.55, 3.75)):
        add_box(f"PalaceUpperWindowFrame_{index:02d}_mesh", (0.86, 0.20, 1.35), (x, -3.92, 5.38), mats["gold"], bevel=0.07)
        add_box(f"PalaceUpperWindowGlow_{index:02d}_mesh", (0.58, 0.12, 1.02), (x, -4.04, 5.34), warm_glass, bevel=0.06)

    # Warm exhibition windows make the building read as a functioning gallery.
    for side in (-1, 1):
        for bay, x in enumerate((side * 5.85, side * 7.12, side * 8.38)):
            add_box(f"PalaceWingWindowFrame_{side:+d}_{bay:02d}_mesh", (0.86, 0.18, 1.52), (x, -4.18, 2.28), mats["gold"], bevel=0.065)
            add_box(f"PalaceWingWindowGlow_{side:+d}_{bay:02d}_mesh", (0.60, 0.11, 1.18), (x, -4.28, 2.26), warm_glass, bevel=0.05)

    # Open side towers echo the concept art and avoid the earlier solid silo silhouette.
    for side in (-1, 1):
        x = side * 7.05
        add_cylinder(f"PalaceTowerBase_{side:+d}_mesh", 1.72, 2.15, 4.82, mats["stone"], 24, bevel=0.055)
        tower_base = bpy.context.object
        tower_base.location.x = x
        tower_base.location.y = 0.15
        add_torus(f"PalaceTowerLowerBand_{side:+d}_mesh", 1.60, 0.10, (x, 0.15, 5.72), mats["gold"], major_segments=32)
        add_cylinder(f"PalaceTowerLanternGlow_{side:+d}_mesh", 1.15, 1.62, 6.42, warm_glass, 24, bevel=0.02)
        tower_glow = bpy.context.object
        tower_glow.location.x = x
        tower_glow.location.y = 0.15
        for column_index in range(8):
            angle = column_index * math.tau / 8
            add_cylinder(f"PalaceTowerColumn_{side:+d}_{column_index:02d}_mesh", 0.13, 1.92, 6.40, mats["stone"], 12, bevel=0.018)
            tower_column = bpy.context.object
            tower_column.location.x = x + math.cos(angle) * 1.42
            tower_column.location.y = 0.15 + math.sin(angle) * 1.42
        add_torus(f"PalaceTowerUpperBand_{side:+d}_mesh", 1.60, 0.11, (x, 0.15, 7.33), mats["gold"], major_segments=32)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=28, ring_count=14, radius=1.0, location=(x, 0.15, 7.58))
        dome = bpy.context.object
        dome.name = f"PalaceTowerDome_{side:+d}_mesh"
        dome.scale = (1.72, 1.72, 1.02)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        assign_material(dome, mats["stone_dark"])
        add_cylinder(f"PalaceTowerFinial_{side:+d}_mesh", 0.14, 0.78, 8.83, mats["gold"], 14, bevel=0.015)
        finial = bpy.context.object
        finial.location.x = x
        finial.location.y = 0.15

    # Central rotunda: an illuminated open colonnade under the main dome.
    add_cylinder("PalaceCentralDrumBase_mesh", 3.18, 0.72, 6.86, mats["stone"], 32, bevel=0.06)
    central_drum = bpy.context.object
    central_drum.location.y = 0.8
    add_cylinder("PalaceRotundaGlow_mesh", 2.35, 1.65, 7.76, warm_glass, 36, bevel=0.02)
    rotunda_glow = bpy.context.object
    rotunda_glow.location.y = 0.8
    for index in range(12):
        angle = index * math.tau / 12
        add_cylinder(f"PalaceRotundaColumn_{index:02d}_mesh", 0.16, 1.94, 7.72, mats["stone"], 14, bevel=0.02)
        rotunda_column = bpy.context.object
        rotunda_column.location.x = math.cos(angle) * 2.82
        rotunda_column.location.y = 0.8 + math.sin(angle) * 2.82
    add_torus("PalaceCentralDrumBand_mesh", 3.03, 0.13, (0, 0.8, 8.64), mats["gold"], major_segments=40)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=36, ring_count=18, radius=1.0, location=(0, 0.8, 9.08))
    central_dome = bpy.context.object
    central_dome.name = "PalaceCentralDome_mesh"
    central_dome.scale = (3.22, 2.88, 1.86)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(central_dome, mats["stone_dark"])
    for index in range(8):
        angle = index * math.tau / 8
        points = []
        for step in range(10):
            t = step / 9
            radius = 2.72 * (1.0 - t)
            points.append((math.cos(angle) * radius, 0.8 + math.sin(angle) * radius * 0.87, 8.70 + math.sin(t * math.pi / 2) * 1.78))
        add_curve_tube(f"PalaceDomeRib_{index:02d}_mesh", points, 0.055, mats["gold"], resolution=1)
    add_cylinder("PalaceCentralFinial_mesh", 0.18, 1.05, 11.28, mats["gold"], 16, bevel=0.018)

    # Wing arcades and buttresses give both side elevations a palace scale.
    for side in (-1, 1):
        wing_x = side * 7.1
        for bay, y in enumerate((-3.3, -0.8, 1.7, 4.0)):
            add_cylinder(f"PalaceWingColumn_{side:+d}_{bay:02d}_mesh", 0.18, 2.65, 2.08, mats["stone"], 14, bevel=0.025)
            wing_column = bpy.context.object
            wing_column.location.x = wing_x - side * 2.18
            wing_column.location.y = y
            add_box(f"PalaceWingLintel_{side:+d}_{bay:02d}_mesh", (0.42, 1.70, 0.22), (wing_x - side * 2.18, y, 3.46), mats["gold"], bevel=0.028)
        for buttress_index, y in enumerate((-3.7, 4.65)):
            add_box(f"PalaceButtress_{side:+d}_{buttress_index}_mesh", (0.72, 1.05, 4.15), (side * 9.0, y, 2.68), mats["stone_dark"], rotation=(0, 0, side * 0.035), bevel=0.08)

    # Recessed side portals and broken roof fragments add age without obscuring the main facade.
    for side in (-1, 1):
        for level, y in enumerate((-3.95, -1.55)):
            add_box(f"PalaceSidePortal_{side:+d}_{level}_mesh", (1.25, 0.24, 1.75), (side * 7.08, y, 1.9), mats["stone"], bevel=0.10)
            add_box(f"PalaceSidePortalVoid_{side:+d}_{level}_mesh", (0.78, 0.12, 1.26), (side * 7.08, y - 0.16, 1.86), mats["stone_dark"], bevel=0.08)
    fragments = [(-8.85, 2.4, 4.28, -0.14), (8.72, 3.25, 4.18, 0.11), (-4.9, 4.0, 5.74, 0.08)]
    for index, (x, y, z, tilt) in enumerate(fragments):
        add_box(f"PalaceFragment_{index:02d}_mesh", (1.35, 0.75, 0.42), (x, y, z), mats["stone_dark"], rotation=(tilt, 0, tilt), bevel=0.07)


def convert_apply_uv_triangulate() -> None:
    # Curves are resolved to ordinary meshes before export.
    for obj in list(bpy.context.scene.objects):
        if obj.type == "CURVE":
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.convert(target="MESH")
            obj.select_set(False)

    for obj in [item for item in bpy.context.scene.objects if item.type == "MESH"]:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        for modifier in list(obj.modifiers):
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        if not obj.data.uv_layers:
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(angle_limit=1.15192, island_margin=0.02)
            bpy.ops.object.mode_set(mode="OBJECT")
        for polygon in obj.data.polygons:
            polygon.use_smooth = False
        tri = obj.modifiers.new("ExportTriangulation", "TRIANGULATE")
        bpy.ops.object.modifier_apply(modifier=tri.name)
        obj.select_set(False)


def scene_stats(asset_id: str, tri_limit: int) -> dict:
    depsgraph = bpy.context.evaluated_depsgraph_get()
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    triangles = 0
    points: list[Vector] = []
    for obj in meshes:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        mesh.calc_loop_triangles()
        triangles += len(mesh.loop_triangles)
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
        evaluated.to_mesh_clear()
    mins = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maxs = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    blender_dims = maxs - mins
    # glTF exporter maps Blender XYZ to Three.js X, Z, -Y.
    three_dims = (blender_dims.x, blender_dims.z, blender_dims.y)
    return {
        "asset": asset_id,
        "triangles": triangles,
        "triangle_limit": tri_limit,
        "within_triangle_budget": triangles <= tri_limit,
        "dimensions_m_threejs_xyz": [round(value, 4) for value in three_dims],
        "mesh_count": len(meshes),
        "units": "meters",
        "front_axis": "+Z",
        "up_axis": "+Y",
    }


def export_asset(asset_id: str, spec: dict, output_root: Path, blend_only: bool = False) -> dict:
    reset_scene()
    blend_dir = output_root / "assets" / "gallery" / "blender" / "components"
    model_dir = output_root / "output" / "gallery" / "component-glb-v1"
    blend_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    # The palace uses the same PBR families across a much larger mesh. A 768 px
    # packed copy keeps the standalone GLB below the 5 MB browser budget while
    # Three.js still applies the canonical 1K material maps at runtime.
    mats = make_materials(output_root, 768 if asset_id == "sunken-palace" else None)
    if asset_id == "sunken-palace":
        # Keep base color and normal detail in the palace GLB. The runtime sets
        # roughness and metalness numerically, so embedding those extra maps
        # would add transfer cost without changing the browser result.
        for mat in mats.values():
            if not mat.use_nodes:
                continue
            for node in list(mat.node_tree.nodes):
                if node.type == "TEX_IMAGE" and any(key in node.name.lower() for key in ("roughness", "metalness")):
                    mat.node_tree.nodes.remove(node)
    globals()[spec["builder"]](mats)
    convert_apply_uv_triangulate()

    root = bpy.data.objects.new(asset_id.replace("-", "_").title(), None)
    root["asset_id"] = asset_id
    root["units"] = "meter"
    root["threejs_up_axis"] = "+Y"
    root["threejs_front_axis"] = "+Z"
    root["triangle_limit"] = spec["tri_limit"]
    root["origin"] = "back_center" if asset_id == "wall-relief-panel" else "bottom_center"
    bpy.context.collection.objects.link(root)
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            obj.parent = root

    stats = scene_stats(asset_id, spec["tri_limit"])
    stats["origin"] = root["origin"]
    bpy.ops.file.pack_all()
    blend_path = blend_dir / f"{asset_id}.blend"
    glb_path = model_dir / f"{asset_id}.glb"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)

    stats["blend_path"] = str(blend_path.relative_to(output_root))
    if blend_only:
        stats["review_only"] = True
        return stats

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
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
    stats["glb_path"] = str(glb_path.relative_to(output_root))
    stats["glb_bytes"] = glb_path.stat().st_size
    stats["under_5mb"] = glb_path.stat().st_size < 5 * 1024 * 1024
    if not stats["within_triangle_budget"]:
        raise RuntimeError(f"{asset_id} exceeds triangle budget: {stats['triangles']} > {spec['tri_limit']}")
    if not stats["under_5mb"]:
        raise RuntimeError(f"{asset_id} GLB exceeds 5 MB")
    return stats


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root).expanduser().resolve()
    selected = [args.only] if args.only else list(ASSETS)
    report = [export_asset(asset_id, ASSETS[asset_id], output_root, args.blend_only) for asset_id in selected]
    if not args.blend_only:
        report_path = output_root / "output" / "gallery" / "component-glb-v1" / "asset-report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
