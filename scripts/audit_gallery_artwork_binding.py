#!/usr/bin/env python3
"""Verify every clickable GLB artwork maps to the exact embedded texture."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


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
    catalog = json.loads(data_path.read_text(encoding="utf-8"))
    catalog_by_thumb = {item["thumb"]: item for item in catalog}
    failures: list[str] = []
    verified = 0

    for glb_path in sorted(models_dir.glob("*.glb")):
        document, binary = read_glb(glb_path)
        for node in document.get("nodes", []):
            extras = node.get("extras") or {}
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
            embedded = embedded_base_color(document, binary, node)
            source = source_path.read_bytes()
            if embedded != source:
                failures.append(
                    f"{label}: texture mismatch "
                    f"embedded={hashlib.sha256(embedded).hexdigest()} "
                    f"source={hashlib.sha256(source).hexdigest()}"
                )
                continue
            verified += 1

    if failures:
        print("ARTWORK BINDING AUDIT FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"ARTWORK BINDING AUDIT PASSED: {verified} clickable GLB artworks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
