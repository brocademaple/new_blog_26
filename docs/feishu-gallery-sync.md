# Feishu Gallery data sync

The Gallery uses static JSON at runtime. Feishu is read only during the local build step.

## Source

- Base: `01_Midjourney素材数据库`
- Groups: `00_生成组`
- Images: `01_图片资产`
- Comparisons: `10_反向偏好实验`
- Personal CLI profile: `cli_aada483257381cd2` (override with `LARK_PROFILE`)

## Run

Validate the complete mapping without writing files:

```bash
python3 scripts/sync_feishu_gallery_data.py --check
```

Write the static artifacts:

```bash
python3 scripts/sync_feishu_gallery_data.py
```

Generated artifacts:

- `static/assets/gallery/gallery-data.json`: current 288 public assets, enriched with exact prompt, translation, params, canonical Feishu IDs and pairing verification.
- `static/assets/gallery/gallery-manifest.json`: all `asset_role=main` assets. Entries without a copied static image stay `assetAvailable=false` and `published=false`.
- `static/assets/gallery/gallery-comparisons.json`: the ten A/B preference experiments, each with exact before/after groups and four images per group.
- `data/gallery-source-audit.json`: non-sensitive count and validation summary.

## Safety contract

- Existing public image paths, legacy IDs, featured works, highlights and hidden states are preserved.
- `imageId`, `groupId` and `pairingHash` are the stable source keys.
- Every existing public asset must match exactly one Feishu image by `theme + row_slug + image_index`.
- Every Feishu image must be `verified_by_job_map + verified`.
- Every generation group must contain exactly four images.
- The command stops before writing when any invariant fails.
- The website never requests Feishu or Yuque at runtime.

The sync currently enriches the 288 static images already present in the repository. The manifest also contains the remaining verified main images as unpublished drafts; adding their compressed static files is a separate publishing step.
