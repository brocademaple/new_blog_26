#!/usr/bin/env python3
"""Verify every clickable GLB artwork maps to the exact embedded texture."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import struct
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


def read_glb(path: Path) -> tuple[dict, bytes]:
    payload = path.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", payload, 0)
    if magic != b"glTF" or version != 2 or length != len(payload):
        raise ValueError(f"Invalid GLB header: {path}")
    offset = 12
    chunks: dict[int, bytes] = {}
    while offset < length:
        chunk_length, chunk_type = struct.unpack_from("<II", payload, offset)
        offset += 8
        chunks[chunk_type] = payload[offset : offset + chunk_length]
        offset += chunk_length
    document = json.loads(chunks[JSON_CHUNK].decode("utf-8").rstrip("\x00 "))
    return document, chunks[BIN_CHUNK]


def embedded_base_color(document: dict, binary: bytes, node: dict) -> bytes:
    mesh = document["meshes"][node["mesh"]]
    primitive = mesh["primitives"][0]
    material = document["materials"][primitive["material"]]
    texture_info = material["pbrMetallicRoughness"]["baseColorTexture"]
    texture = document["textures"][texture_info["index"]]
    image = document["images"][texture["source"]]
    view = document["bufferViews"][image["bufferView"]]
    start = view.get("byteOffset", 0)
    return binary[start : start + view["byteLength"]]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    repo = args.repo.resolve()
    data_path = repo / "static/assets/gallery/gallery-data.json"
    models_dir = repo / "static/assets/gallery/models/master-v1"
    gallery_template = repo / "layouts/gallery/list.html"
    catalog = json.loads(data_path.read_text(encoding="utf-8"))
    catalog_by_thumb = {item["thumb"]: item for item in catalog}
    failures: list[str] = []
    verified = 0
    verified_thumbs: list[str] = []
    verified_rooms: Counter[str] = Counter()
    verified_modules: Counter[str] = Counter()
    thumbnail_source_mae: list[float] = []
    navigation: dict[str, str] = {}
    navigation_targets: dict[str, str] = {}

    for glb_path in sorted(models_dir.glob("*.glb")):
        document, binary = read_glb(glb_path)
        for node in document.get("nodes", []):
            extras = node.get("extras") or {}
            nav_id = extras.get("gallery_nav_id")
            if nav_id:
                label = f"{glb_path.name}:{node.get('name', '<unnamed>')}"
                if nav_id in navigation:
                    failures.append(f"{label}: duplicate navigation id {nav_id}")
                else:
                    navigation[nav_id] = label
            target_for = extras.get("gallery_nav_target_for")
            if target_for:
                label = f"{glb_path.name}:{node.get('name', '<unnamed>')}"
                if target_for in navigation_targets:
                    failures.append(f"{label}: duplicate navigation target {target_for}")
                else:
                    navigation_targets[target_for] = label
            if not extras.get("gallery_interactive"):
                continue
            thumb = extras.get("gallery_artwork_thumb")
            label = f"{glb_path.name}:{node.get('name', '<unnamed>')}"
            if thumb not in catalog_by_thumb:
                failures.append(f"{label}: catalog record missing for {thumb}")
                continue
            source_path = repo / "static" / thumb.lstrip("/")
            if not source_path.is_file():
                failures.append(f"{label}: thumbnail file missing: {source_path}")
                continue
            item = catalog_by_thumb[thumb]
            full_path = repo / "static" / item["src"].lstrip("/")
            if not full_path.is_file():
                failures.append(f"{label}: full-size image missing: {full_path}")
                continue
            if source_path.name != full_path.name:
                failures.append(
                    f"{label}: thumbnail/full-size filenames differ "
                    f"thumb={source_path.name} src={full_path.name}"
                )
                continue
            embedded = embedded_base_color(document, binary, node)
            source = source_path.read_bytes()
            if embedded != source:
                failures.append(
                    f"{label}: texture mismatch "
                    f"embedded={hashlib.sha256(embedded).hexdigest()} "
                    f"source={hashlib.sha256(source).hexdigest()}"
                )
                continue
            # A GLB displays the thumbnail while the detail viewer displays the
            # full-size file.  Matching paths alone cannot detect a stale or
            # accidentally overwritten thumbnail, so compare their actual
            # pixels at a small common resolution.
            with Image.open(source_path) as thumb_image, Image.open(full_path) as full_image:
                thumb_sample = thumb_image.convert("RGB").resize((64, 64))
                full_sample = full_image.convert("RGB").resize((64, 64))
                mae = sum(ImageStat.Stat(ImageChops.difference(thumb_sample, full_sample)).mean) / 3
            if mae > 3.0:
                failures.append(f"{label}: thumbnail/full-size visual mismatch mae={mae:.2f}")
                continue
            verified += 1
            verified_thumbs.append(thumb)
            verified_rooms[item["room"]] += 1
            verified_modules[glb_path.name] += 1
            thumbnail_source_mae.append(mae)

    if verified != 13:
        failures.append(f"expected 13 clickable artworks, found {verified}")
    duplicate_thumbs = sorted(thumb for thumb, count in Counter(verified_thumbs).items() if count > 1)
    if duplicate_thumbs:
        failures.append("duplicate clickable artwork thumbnails: " + ", ".join(duplicate_thumbs))
    expected_rooms = {"color", "composition", "lighting", "material", "mood", "scene"}
    missing_rooms = sorted(expected_rooms - set(verified_rooms))
    if missing_rooms:
        failures.append("Gallery themes missing from the 3D exhibition: " + ", ".join(missing_rooms))
    thin_rooms = sorted(room for room in expected_rooms if verified_rooms[room] < 2)
    if thin_rooms:
        failures.append("Gallery themes need at least two 3D works: " + ", ".join(thin_rooms))
    expected_modules = {
        "atlantis-archive.glb": 3,
        "atlantis-cliff-gallery.glb": 3,
        "atlantis-palace-complex.glb": 7,
    }
    actual_modules = {name: count for name, count in verified_modules.items() if count}
    if actual_modules != expected_modules:
        failures.append(
            "spatial artwork distribution mismatch "
            f"expected={expected_modules} actual={actual_modules}"
        )
    expected_navigation = {"archive-of-tides", "cliff-gallery", "sunken-palace"}
    if set(navigation) != expected_navigation:
        failures.append(
            "navigation ids mismatch "
            f"expected={sorted(expected_navigation)} actual={sorted(navigation)}"
        )
    if set(navigation_targets) != expected_navigation:
        failures.append(
            "navigation target ids mismatch "
            f"expected={sorted(expected_navigation)} actual={sorted(navigation_targets)}"
        )

    template_source = gallery_template.read_text(encoding="utf-8")
    required_runtime_contract = {
        "model navigation position": "gallery_nav_id",
        "model navigation look target": "gallery_nav_target_for",
        "artwork identity lookup": "gallery_artwork_thumb",
        "separate spatial navigation": "state.spatialDestinations",
        "all-artwork review hook": "window.focusGalleryArtworkReview",
    }
    for requirement, needle in required_runtime_contract.items():
        if needle not in template_source:
            failures.append(f"runtime contract missing {requirement}: {needle}")
    if "const masterTargets" in template_source:
        failures.append("legacy hard-coded masterTargets navigation is still present")

    if failures:
        print("ARTWORK BINDING AUDIT FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    room_summary = ", ".join(f"{room}={verified_rooms[room]}" for room in sorted(verified_rooms))
    max_mae = max(thumbnail_source_mae, default=0.0)
    print(
        f"ARTWORK BINDING AUDIT PASSED: {verified} unique clickable GLB artworks; "
        f"themes {room_summary}; thumbnail/full-size max MAE={max_mae:.2f}; "
        f"navigation {', '.join(sorted(navigation))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
