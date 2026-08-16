#!/usr/bin/env python3
"""Sync verified Midjourney metadata from personal Feishu Base into the static Gallery.

The public site never talks to Feishu at runtime. This command reads Base through the
user's lark-cli profile, enriches the existing published assets, and writes static JSON.
It deliberately preserves the current curation and image files.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


BASE_TOKEN = "W90nb0w5raux1gsVnu0cwiYDnhg"
TABLES = {
    "groups": "tblmyGNDzyRkAgeH",
    "images": "tblirTTQKRM6AuEK",
    "experiments": "tblpqGBjTzanvQl9",
}
DEFAULT_PROFILE = "cli_aada483257381cd2"

THEMES = {
    "01_color_palette": {"room": "color", "roomTitle": "Color Room", "label": "色彩"},
    "02_composition": {"room": "composition", "roomTitle": "Composition Hall", "label": "构图"},
    "03_lighting": {"room": "lighting", "roomTitle": "Light Room", "label": "光线"},
    "04_texture_material": {"room": "material", "roomTitle": "Material Room", "label": "材质"},
    "05_character_mood": {"room": "mood", "roomTitle": "Mood Room", "label": "人物情绪"},
    "06_product_scene": {"room": "scene", "roomTitle": "Object Room", "label": "场景"},
    "07_layout_editorial": {"room": "editorial", "roomTitle": "Editorial Room", "label": "排版"},
    "08_world_atmosphere": {"room": "atmosphere", "roomTitle": "Atmosphere Room", "label": "世界氛围"},
    "09_reference_style": {"room": "reference", "roomTitle": "Reference Room", "label": "风格母题"},
    "10_reject_notes": {"room": "comparison", "roomTitle": "Comparison Lab", "label": "反向偏好"},
}

GROUP_FIELDS = [
    "group_id",
    "theme",
    "row_slug",
    "prompt_exact",
    "prompt_zh",
    "params_exact",
    "asset_role",
    "experiment_id",
    "variant",
    "metadata_json",
]
IMAGE_FIELDS = [
    "image_id",
    "group_id",
    "theme",
    "row_slug",
    "image_index",
    "prompt_snapshot",
    "params_snapshot",
    "image_sha256",
    "pairing_hash",
    "pairing_state",
    "asset_role",
    "gallery_status",
    "feishu_sync_state",
    "width",
    "height",
    "bytes",
    "filename",
]
EXPERIMENT_FIELDS = [
    "experiment_id",
    "实验主题",
    "原因分类",
    "不喜欢点",
    "修正方向",
    "原提示词",
    "修改后提示词",
    "避免词",
    "是否改善",
    "结论",
    "原版group_ids",
    "修改版group_ids",
    "额外重试group_ids",
    "sync_state",
]


class SyncError(RuntimeError):
    pass


def run_json(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SyncError(f"command failed ({result.returncode}): {' '.join(command[:4])}\n{detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SyncError(f"lark-cli returned invalid JSON: {exc}") from exc
    if not payload.get("ok"):
        raise SyncError(json.dumps(payload.get("error", payload), ensure_ascii=False))
    return payload


def fetch_records(profile: str, table_id: str, fields: Iterable[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    fields = list(fields)
    while True:
        command = [
            "lark-cli",
            "base",
            "+record-list",
            "--base-token",
            BASE_TOKEN,
            "--table-id",
            table_id,
            "--limit",
            "200",
            "--offset",
            str(offset),
            "--as",
            "user",
            "--profile",
            profile,
            "--format",
            "json",
        ]
        for field in fields:
            command.extend(["--field-id", field])
        payload = run_json(command)["data"]
        names = payload.get("fields", [])
        rows = payload.get("data", [])
        record_ids = payload.get("record_id_list", [])
        if len(rows) != len(record_ids):
            raise SyncError(f"table {table_id}: row/record id count mismatch")
        for record_id, row in zip(record_ids, rows):
            if len(row) != len(names):
                raise SyncError(f"table {table_id}: field/value count mismatch")
            record = dict(zip(names, row))
            record["_record_id"] = record_id
            records.append(record)
        if not payload.get("has_more"):
            break
        if not rows:
            raise SyncError(f"table {table_id}: has_more without rows")
        offset += len(rows)
    return records


def scalar(value: Any, default: Any = "") -> Any:
    if value is None:
        return default
    if isinstance(value, list):
        if not value:
            return default
        if len(value) == 1 and not isinstance(value[0], (dict, list)):
            return value[0]
    return value


def text(value: Any) -> str:
    result = scalar(value, "")
    return result if isinstance(result, str) else str(result)


def number(value: Any, default: int = 0) -> int:
    result = scalar(value, default)
    try:
        return int(result)
    except (TypeError, ValueError):
        return default


def metadata(record: dict[str, Any]) -> dict[str, Any]:
    raw = text(record.get("metadata_json"))
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def prompt_zh(record: dict[str, Any]) -> str:
    direct = text(record.get("prompt_zh"))
    if direct:
        return direct
    meta = metadata(record)
    for key in ("中文理解", "中文翻译", "说明", "修改说明"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def legacy_key(item: dict[str, Any]) -> tuple[str, str, int]:
    source_folder = text(item.get("sourceFolder"))
    parts = source_folder.split("/", 1)
    if len(parts) != 2:
        raise SyncError(f"legacy record lacks theme/slug sourceFolder: {item.get('id')}")
    return parts[0], parts[1], number(item.get("variant"), 0)


def image_key(item: dict[str, Any]) -> tuple[str, str, int]:
    return text(item.get("theme")), text(item.get("row_slug")), number(item.get("image_index"), 0)


def public_manifest_record(
    image: dict[str, Any],
    group: dict[str, Any],
    legacy: dict[str, Any] | None,
) -> dict[str, Any]:
    theme = text(image.get("theme"))
    theme_info = THEMES.get(theme, {"room": theme, "roomTitle": theme, "label": theme})
    width = number(image.get("width"))
    height = number(image.get("height"))
    available = legacy is not None
    return {
        "id": text(image.get("image_id")),
        "legacyId": legacy.get("id") if legacy else None,
        "groupId": text(image.get("group_id")),
        "theme": theme,
        "themeLabel": theme_info["label"],
        "room": legacy.get("room", theme_info["room"]) if legacy else theme_info["room"],
        "roomTitle": legacy.get("roomTitle", theme_info["roomTitle"]) if legacy else theme_info["roomTitle"],
        "title": legacy.get("title") if legacy else text(image.get("row_slug")).replace("_", " ").title(),
        "index": number(image.get("image_index")),
        "prompt": text(image.get("prompt_snapshot")),
        "translation": prompt_zh(group),
        "params": text(image.get("params_snapshot")),
        "src": legacy.get("src") if legacy else None,
        "thumb": legacy.get("thumb") if legacy else None,
        "assetAvailable": available,
        "published": bool(legacy and legacy.get("published") is not False),
        "featured": bool(legacy and legacy.get("featured")),
        "highlight": bool(legacy and legacy.get("highlight")),
        "status": legacy.get("status", "archive") if legacy else "archive",
        "sourceGalleryStatus": text(image.get("gallery_status")) or "archive",
        "pairingHash": text(image.get("pairing_hash")),
        "imageSha256": text(image.get("image_sha256")),
        "pairingState": text(image.get("pairing_state")),
        "syncState": text(image.get("feishu_sync_state")),
        "width": width,
        "height": height,
        "aspect": round(width / height, 4) if height else None,
        "bytes": number(image.get("bytes")),
    }


def enrich_legacy_record(
    legacy: dict[str, Any], image: dict[str, Any], group: dict[str, Any]
) -> dict[str, Any]:
    result = dict(legacy)
    previous_group_id = result.get("groupId")
    result.update(
        {
            "imageId": text(image.get("image_id")),
            "legacyGroupId": previous_group_id,
            "groupId": text(image.get("group_id")),
            "prompt": text(image.get("prompt_snapshot")),
            "translation": prompt_zh(group),
            "params": text(image.get("params_snapshot")),
            "pairingHash": text(image.get("pairing_hash")),
            "imageSha256": text(image.get("image_sha256")),
            "pairingState": text(image.get("pairing_state")),
            "syncState": text(image.get("feishu_sync_state")),
            "sourceGalleryStatus": text(image.get("gallery_status")) or "archive",
            "dataSource": "feishu-base",
            "dataVerified": (
                text(image.get("pairing_state")) == "verified_by_job_map"
                and text(image.get("feishu_sync_state")) == "verified"
            ),
        }
    )
    return result


def comparison_records(
    experiments: list[dict[str, Any]],
    groups_by_id: dict[str, dict[str, Any]],
    images_by_group: dict[str, list[dict[str, Any]]],
    public_by_image_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    def group_ids(value: Any) -> list[str]:
        return [item.strip() for item in text(value).split(",") if item.strip()]

    def side(group_id: str, prompt_fallback: str) -> dict[str, Any]:
        group = groups_by_id.get(group_id)
        if not group:
            raise SyncError(f"comparison references missing group: {group_id}")
        images = sorted(images_by_group.get(group_id, []), key=lambda item: number(item.get("image_index")))
        if len(images) != 4:
            raise SyncError(f"comparison group {group_id} has {len(images)} images, expected 4")
        return {
            "groupId": group_id,
            "prompt": text(group.get("prompt_exact")) or prompt_fallback,
            "translation": prompt_zh(group),
            "params": text(group.get("params_exact")),
            "images": [
                {
                    "id": text(image.get("image_id")),
                    "src": public_by_image_id.get(text(image.get("image_id")), {}).get("src"),
                    "available": bool(public_by_image_id.get(text(image.get("image_id")), {}).get("assetAvailable")),
                }
                for image in images
            ],
        }

    def experiment_side(
        candidate_ids: list[str], expected_variant: str, prompt_fallback: str
    ) -> dict[str, Any]:
        if not candidate_ids:
            raise SyncError(f"comparison has no {expected_variant} group")
        exact = [
            group_id
            for group_id in candidate_ids
            if text(groups_by_id.get(group_id, {}).get("variant")) == expected_variant
        ]
        primary_id = exact[0] if exact else candidate_ids[0]
        value = side(primary_id, prompt_fallback)
        value["alternates"] = [
            side(group_id, prompt_fallback)
            for group_id in candidate_ids
            if group_id != primary_id
        ]
        return value

    result: list[dict[str, Any]] = []
    for experiment in sorted(experiments, key=lambda item: text(item.get("experiment_id"))):
        before_group_ids = group_ids(experiment.get("原版group_ids"))
        after_group_ids = group_ids(experiment.get("修改版group_ids"))
        result.append(
            {
                "type": "comparison",
                "experimentId": text(experiment.get("experiment_id")),
                "title": text(experiment.get("实验主题")),
                "reasonCategory": text(experiment.get("原因分类")),
                "dislike": text(experiment.get("不喜欢点")),
                "correction": text(experiment.get("修正方向")),
                "avoid": text(experiment.get("避免词")),
                "before": experiment_side(before_group_ids, "original", text(experiment.get("原提示词"))),
                "after": experiment_side(after_group_ids, "revised", text(experiment.get("修改后提示词"))),
                "improved": text(experiment.get("是否改善")),
                "conclusion": text(experiment.get("结论")),
                "retryGroupIds": group_ids(experiment.get("额外重试group_ids")),
                "syncState": text(experiment.get("sync_state")),
            }
        )
    return result


def sync(repo: Path, profile: str, check_only: bool) -> dict[str, Any]:
    gallery_path = repo / "static/assets/gallery/gallery-data.json"
    if not gallery_path.is_file():
        raise SyncError(f"missing current gallery data: {gallery_path}")
    legacy_records = json.loads(gallery_path.read_text(encoding="utf-8"))
    if not isinstance(legacy_records, list):
        raise SyncError("gallery-data.json must be an array")

    groups = fetch_records(profile, TABLES["groups"], GROUP_FIELDS)
    images = fetch_records(profile, TABLES["images"], IMAGE_FIELDS)
    experiments = fetch_records(profile, TABLES["experiments"], EXPERIMENT_FIELDS)
    groups_by_id = {text(item.get("group_id")): item for item in groups}
    images_by_id = {text(item.get("image_id")): item for item in images}
    if len(groups_by_id) != len(groups):
        raise SyncError("group_id values are not unique")
    if len(images_by_id) != len(images):
        raise SyncError("image_id values are not unique")

    images_by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    images_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for image in images:
        key = image_key(image)
        if key in images_by_key:
            raise SyncError(f"duplicate theme/slug/index image key: {key}")
        images_by_key[key] = image
        images_by_group[text(image.get("group_id"))].append(image)

    legacy_by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    for item in legacy_records:
        key = legacy_key(item)
        if key in legacy_by_key:
            raise SyncError(f"duplicate legacy source key: {key}")
        legacy_by_key[key] = item

    missing = sorted(set(legacy_by_key) - set(images_by_key))
    if missing:
        raise SyncError(f"{len(missing)} published assets do not match Feishu records; first={missing[0]}")

    enriched: list[dict[str, Any]] = []
    for legacy in legacy_records:
        image = images_by_key[legacy_key(legacy)]
        group_id = text(image.get("group_id"))
        group = groups_by_id.get(group_id)
        if not group:
            raise SyncError(f"image references missing group: {group_id}")
        enriched.append(enrich_legacy_record(legacy, image, group))

    main_images = [item for item in images if text(item.get("asset_role")) == "main"]
    audit_images = [item for item in images if text(item.get("asset_role")) == "audit_retry"]
    public_manifest: list[dict[str, Any]] = []
    legacy_match_by_key = {legacy_key(item): item for item in enriched}
    for image in sorted(
        main_images,
        key=lambda item: (text(item.get("theme")), text(item.get("row_slug")), number(item.get("image_index"))),
    ):
        group_id = text(image.get("group_id"))
        group = groups_by_id.get(group_id)
        if not group:
            raise SyncError(f"main image references missing group: {group_id}")
        public_manifest.append(public_manifest_record(image, group, legacy_match_by_key.get(image_key(image))))

    public_by_image_id = {item["id"]: item for item in public_manifest}
    comparisons = comparison_records(experiments, groups_by_id, images_by_group, public_by_image_id)

    group_sizes = Counter(text(item.get("group_id")) for item in images)
    bad_groups = sorted(group_id for group_id, count in group_sizes.items() if count != 4)
    if bad_groups:
        raise SyncError(f"groups without exactly four images: {bad_groups[:5]}")
    unverified = [
        text(item.get("image_id"))
        for item in images
        if text(item.get("pairing_state")) != "verified_by_job_map"
        or text(item.get("feishu_sync_state")) != "verified"
    ]
    if unverified:
        raise SyncError(f"unverified image mappings: {unverified[:5]}")
    if any(not item.get("prompt") or not item.get("params") for item in enriched):
        raise SyncError("at least one public asset still lacks prompt or params")

    audit = {
        "source": "personal-feishu-base",
        "baseToken": BASE_TOKEN,
        "profile": profile,
        "groups": len(groups),
        "images": len(images),
        "mainImages": len(main_images),
        "auditRetryImages": len(audit_images),
        "publishedAssetsEnriched": len(enriched),
        "manifestAssets": len(public_manifest),
        "manifestAssetsAvailable": sum(bool(item["assetAvailable"]) for item in public_manifest),
        "comparisons": len(comparisons),
        "validation": "passed",
    }
    if not check_only:
        atomic_json(gallery_path, enriched)
        atomic_json(repo / "static/assets/gallery/gallery-manifest.json", {
            "schemaVersion": 1,
            "source": {"provider": "feishu-base", "baseToken": BASE_TOKEN, "tables": TABLES},
            "themes": [{"key": key, **value} for key, value in THEMES.items()],
            "assets": public_manifest,
        })
        atomic_json(repo / "static/assets/gallery/gallery-comparisons.json", comparisons)
        atomic_json(repo / "data/gallery-source-audit.json", audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--profile", default=os.environ.get("LARK_PROFILE", DEFAULT_PROFILE))
    parser.add_argument("--check", action="store_true", help="validate without writing files")
    args = parser.parse_args()
    try:
        audit = sync(args.repo.resolve(), args.profile, args.check)
    except SyncError as exc:
        print(f"GALLERY_SYNC_ERROR {exc}", file=sys.stderr)
        return 1
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
