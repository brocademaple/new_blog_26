#!/usr/bin/env python3
"""Generate deterministic PBR texture sets for the Atlantis Gallery.

The output is shared by Blender (embedded in GLB assets) and Three.js
(large architectural surfaces and environmental dressing).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True, help="Root of the Hugo repository")
    return parser.parse_args()


def smooth_noise(size: int, rng: np.random.Generator, cells: int) -> np.ndarray:
    grid = rng.random((cells, cells), dtype=np.float32)
    image = Image.fromarray(np.uint8(grid * 255))
    image = image.resize((size, size), Image.Resampling.BICUBIC)
    return np.asarray(image, dtype=np.float32) / 255.0


def fbm(size: int, rng: np.random.Generator) -> np.ndarray:
    layers = [(8, 0.52), (20, 0.26), (52, 0.14), (128, 0.08)]
    result = np.zeros((size, size), dtype=np.float32)
    for cells, weight in layers:
        result += smooth_noise(size, rng, cells) * weight
    lo, hi = float(result.min()), float(result.max())
    return (result - lo) / max(1e-6, hi - lo)


def crack_mask(size: int, rng: np.random.Generator, count: int) -> np.ndarray:
    image = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(image)
    for _ in range(count):
        x = int(rng.integers(0, size))
        y = int(rng.integers(0, size))
        points = [(x, y)]
        angle = float(rng.random() * math.tau)
        for _ in range(int(rng.integers(4, 9))):
            angle += float(rng.normal(0, 0.55))
            distance = int(rng.integers(size // 38, size // 13))
            x = int(np.clip(x + math.cos(angle) * distance, 0, size - 1))
            y = int(np.clip(y + math.sin(angle) * distance, 0, size - 1))
            points.append((x, y))
        draw.line(points, fill=int(rng.integers(165, 245)), width=max(1, size // 420))
        if len(points) > 3 and rng.random() > 0.45:
            px, py = points[int(rng.integers(1, len(points) - 1))]
            branch = [(px, py), (px + int(rng.normal(0, size / 34)), py + int(rng.normal(0, size / 34)))]
            draw.line(branch, fill=150, width=max(1, size // 700))
    image = image.filter(ImageFilter.GaussianBlur(max(0.4, size / 1400)))
    return np.asarray(image, dtype=np.float32) / 255.0


def height_to_normal(height: np.ndarray, strength: float) -> np.ndarray:
    gy, gx = np.gradient(height)
    nx = -gx * strength
    ny = gy * strength
    nz = np.ones_like(height)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack((nx / length, ny / length, nz / length), axis=-1)
    return np.uint8(np.clip(normal * 0.5 + 0.5, 0, 1) * 255)


def save_rgb(path: Path, pixels: np.ndarray, quality: int = 90) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.fromarray(np.uint8(np.clip(pixels, 0, 255)))
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        image.save(path, quality=quality, optimize=True, progressive=True)
    else:
        image.save(path, optimize=True)


def save_gray(path: Path, values: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.uint8(np.clip(values, 0, 1) * 255)).save(path, optimize=True)


def build_stone(root: Path, size: int = 1024) -> dict:
    rng = np.random.default_rng(1407)
    noise = fbm(size, rng)
    fine = smooth_noise(size, rng, 180)
    cracks = crack_mask(size, rng, 24)
    mineral = np.clip((smooth_noise(size, rng, 38) - 0.54) * 4.2, 0, 1)
    height = np.clip(0.34 + noise * 0.52 + fine * 0.08 - cracks * 0.28, 0, 1)

    low = np.array([19, 54, 57], dtype=np.float32)
    high = np.array([71, 104, 101], dtype=np.float32)
    base = low + (high - low) * noise[..., None]
    base = base * (1.0 - cracks[..., None] * 0.56)
    base = base * (1.0 - mineral[..., None] * 0.12) + np.array([28, 88, 78]) * mineral[..., None] * 0.24
    roughness = np.clip(0.72 + fine * 0.18 + mineral * 0.08 - cracks * 0.07, 0.52, 0.98)
    ao = np.clip(0.92 - cracks * 0.42 - (1.0 - noise) * 0.10, 0.42, 1.0)

    folder = root / "stone"
    save_rgb(folder / "stone_basecolor.jpg", base)
    save_rgb(folder / "stone_normal.png", height_to_normal(height, 13.0))
    save_gray(folder / "stone_roughness.png", roughness)
    save_gray(folder / "stone_ao.png", ao)
    return {"id": "weathered-stone", "size": size, "channels": ["baseColor", "normal", "roughness", "ao"]}


def build_bronze(root: Path, size: int = 1024) -> dict:
    rng = np.random.default_rng(2718)
    noise = fbm(size, rng)
    patina_field = smooth_noise(size, rng, 34)
    patina = np.clip((patina_field - 0.43) * 3.7, 0, 1)
    pits = np.clip((smooth_noise(size, rng, 125) - 0.58) * 5.0, 0, 1)
    scratches = crack_mask(size, rng, 36) * 0.48
    exposed = np.clip(1.0 - patina * 0.82, 0, 1)

    metal = np.array([139, 101, 43], dtype=np.float32)
    metal_hi = np.array([194, 147, 67], dtype=np.float32)
    verdigris = np.array([22, 85, 78], dtype=np.float32)
    base = metal + (metal_hi - metal) * noise[..., None]
    base = base * (1.0 - patina[..., None]) + verdigris * patina[..., None]
    base *= 1.0 - pits[..., None] * 0.23
    height = np.clip(0.45 + noise * 0.24 - pits * 0.20 - scratches * 0.14, 0, 1)
    roughness = np.clip(0.31 + patina * 0.45 + pits * 0.18 + scratches * 0.1, 0.25, 0.94)
    metalness = np.clip(0.82 * exposed + 0.18 * patina, 0.16, 0.88)

    folder = root / "bronze"
    save_rgb(folder / "bronze_basecolor.jpg", base)
    save_rgb(folder / "bronze_normal.png", height_to_normal(height, 9.0))
    save_gray(folder / "bronze_roughness.png", roughness)
    save_gray(folder / "bronze_metalness.png", metalness)
    return {"id": "oxidized-bronze", "size": size, "channels": ["baseColor", "normal", "roughness", "metalness"]}


def build_floor(root: Path, size: int = 2048) -> dict:
    rng = np.random.default_rng(31415)
    noise = fbm(size, rng)
    fine = smooth_noise(size, rng, 190)
    cracks = crack_mask(size, rng, 32)
    silt = np.clip((smooth_noise(size, rng, 22) - 0.44) * 3.0, 0, 1)

    line_image = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(line_image)
    unit = size // 4
    line_w = max(5, size // 260)
    for value in range(0, size + 1, unit):
        draw.line((value, 0, value, size), fill=255, width=line_w)
        draw.line((0, value, size, value), fill=255, width=line_w)
    for row in range(4):
        for col in range(4):
            x0, y0 = col * unit, row * unit
            draw.line((x0, y0, x0 + unit, y0 + unit), fill=210, width=line_w // 2)
            draw.line((x0 + unit, y0, x0, y0 + unit), fill=210, width=line_w // 2)
            margin = int(unit * 0.21)
            draw.ellipse((x0 + margin, y0 + margin, x0 + unit - margin, y0 + unit - margin), outline=235, width=line_w)
    inlay = np.asarray(line_image.filter(ImageFilter.GaussianBlur(size / 1800)), dtype=np.float32) / 255.0

    stone_low = np.array([18, 57, 63], dtype=np.float32)
    stone_high = np.array([56, 93, 94], dtype=np.float32)
    base = stone_low + (stone_high - stone_low) * noise[..., None]
    gold = np.array([157, 116, 52], dtype=np.float32)
    base = base * (1.0 - inlay[..., None]) + gold * inlay[..., None]
    sand = np.array([92, 91, 71], dtype=np.float32)
    silt_mix = silt * (1.0 - inlay * 0.72)
    base = base * (1.0 - silt_mix[..., None] * 0.46) + sand * silt_mix[..., None] * 0.46
    base *= 1.0 - cracks[..., None] * 0.46

    height = np.clip(0.37 + noise * 0.34 + inlay * 0.18 - cracks * 0.24 + fine * 0.05, 0, 1)
    roughness = np.clip(0.78 + silt_mix * 0.16 + fine * 0.08 - inlay * 0.43, 0.28, 0.98)
    ao = np.clip(0.93 - cracks * 0.48 - silt_mix * 0.08, 0.38, 1.0)

    folder = root / "floor"
    normal_pixels = height_to_normal(height, 15.0)
    save_rgb(folder / "floor_basecolor.jpg", base)
    save_rgb(folder / "floor_normal.png", normal_pixels)
    save_gray(folder / "floor_roughness.png", roughness)
    save_gray(folder / "floor_ao.png", ao)

    # The browser uses the full 2K set. Blender embeds this compact copy so the
    # floor tile stays within the guide's 5 MB-per-GLB budget.
    embedded = folder / "embedded-512"
    embedded.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.uint8(np.clip(base, 0, 255))).resize(
        (512, 512), Image.Resampling.LANCZOS
    ).save(embedded / "floor_basecolor.jpg", quality=88, optimize=True, progressive=True)
    Image.fromarray(normal_pixels).resize((512, 512), Image.Resampling.LANCZOS).save(
        embedded / "floor_normal.png", optimize=True
    )
    Image.fromarray(np.uint8(np.clip(roughness, 0, 1) * 255)).resize(
        (512, 512), Image.Resampling.LANCZOS
    ).save(embedded / "floor_roughness.png", optimize=True)
    return {"id": "silt-mosaic-floor", "size": size, "channels": ["baseColor", "normal", "roughness", "ao"]}


def build_decal_atlas(root: Path, size: int = 1024) -> dict:
    rng = np.random.default_rng(16180)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    half = size // 2

    # Upper-left: branching cracks.
    for _ in range(9):
        x, y = int(rng.integers(70, half - 70)), int(rng.integers(70, half - 70))
        points = [(x, y)]
        for _ in range(5):
            x += int(rng.normal(0, 42))
            y += int(rng.normal(34, 34))
            points.append((int(np.clip(x, 12, half - 12)), int(np.clip(y, 12, half - 12))))
        draw.line(points, fill=(5, 19, 18, 210), width=4)

    # Upper-right: algae and water stains.
    for _ in range(70):
        x = int(rng.integers(half + 18, size - 18))
        y = int(rng.integers(18, half - 18))
        rx, ry = int(rng.integers(9, 42)), int(rng.integers(16, 64))
        draw.ellipse((x - rx, y - ry, x + rx, y + ry), fill=(20, 83, 67, int(rng.integers(20, 92))))

    # Lower-left: barnacle cluster.
    for _ in range(62):
        angle = float(rng.random() * math.tau)
        radius = float(abs(rng.normal(0, half * 0.22)))
        x = half // 2 + math.cos(angle) * radius
        y = half + half // 2 + math.sin(angle) * radius
        r = int(rng.integers(5, 18))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(103, 121, 103, 190), outline=(30, 66, 65, 225), width=3)

    # Lower-right: soft silt deposit.
    silt = Image.new("RGBA", (half, half), (0, 0, 0, 0))
    silt_draw = ImageDraw.Draw(silt, "RGBA")
    for _ in range(120):
        x, y = int(rng.integers(0, half)), int(rng.integers(0, half))
        r = int(rng.integers(18, 75))
        silt_draw.ellipse((x - r, y - r // 2, x + r, y + r // 2), fill=(89, 91, 72, int(rng.integers(8, 32))))
    silt = silt.filter(ImageFilter.GaussianBlur(10))
    image.alpha_composite(silt, (half, half))

    folder = root / "decals"
    folder.mkdir(parents=True, exist_ok=True)
    image.save(folder / "ruin_decal_atlas.png", optimize=True)
    return {"id": "ruin-decal-atlas", "size": size, "quadrants": ["cracks", "algae", "barnacles", "silt"]}


def main() -> None:
    args = parse_args()
    output_root = Path(args.output_root).expanduser().resolve()
    texture_root = output_root / "static" / "assets" / "gallery" / "textures" / "atlantis"
    texture_root.mkdir(parents=True, exist_ok=True)
    materials = [build_stone(texture_root), build_bronze(texture_root), build_floor(texture_root)]
    decals = build_decal_atlas(texture_root)
    manifest = {
        "version": 1,
        "generator": "scripts/generate_atlantis_textures.py",
        "materials": materials,
        "decals": decals,
    }
    (texture_root / "material-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
