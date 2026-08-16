#!/usr/bin/env python3
"""Generate lightweight baked water-surface textures for the Atlantis review scene."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--size", type=int, default=1024)
    args = parser.parse_args()

    size = args.size
    axis = np.linspace(0.0, np.pi * 12.0, size, endpoint=False, dtype=np.float32)
    x, y = np.meshgrid(axis, axis)
    height = (
        0.50 * np.sin(x * 0.72 + np.sin(y * 0.31) * 1.7)
        + 0.32 * np.sin(y * 0.91 - x * 0.19)
        + 0.18 * np.sin((x + y) * 1.43)
    )
    height = (height - height.min()) / (height.max() - height.min())

    shimmer = np.clip((height - 0.56) * 3.2, 0.0, 1.0)
    base = np.empty((size, size, 3), dtype=np.float32)
    base[..., 0] = 0.015 + shimmer * 0.14
    base[..., 1] = 0.28 + height * 0.24 + shimmer * 0.20
    base[..., 2] = 0.46 + height * 0.30 + shimmer * 0.18
    base = np.clip(base, 0.0, 1.0)

    grad_y, grad_x = np.gradient(height)
    strength = 5.5
    nx = -grad_x * strength
    ny = -grad_y * strength
    nz = np.ones_like(height)
    norm = np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.stack((nx / norm, ny / norm, nz / norm), axis=-1)
    normal = normal * 0.5 + 0.5

    out = Path(args.output_root) / "static" / "assets" / "gallery" / "textures" / "atlantis" / "water"
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray((base * 255).astype(np.uint8), "RGB").save(out / "water_surface_basecolor.jpg", quality=90)
    Image.fromarray((normal * 255).astype(np.uint8), "RGB").save(out / "water_surface_normal.png", optimize=True)
    print(out / "water_surface_basecolor.jpg")
    print(out / "water_surface_normal.png")


if __name__ == "__main__":
    main()
