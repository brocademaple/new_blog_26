# Atlantis Gallery asset pipeline

The Art Gallery architecture uses one canonical Blender master, seven reusable
component `.blend` files, six web GLB modules, and three deterministic PBR
material families. The source files and generated web files are separated so
the Blender folder stays understandable and the site publishes only what the
browser loads.

The canonical source layout is:

- `assets/gallery/blender/atlantis-gallery-master-v1.blend`: approved master;
- `assets/gallery/blender/components/`: reusable rebuild inputs;
- `static/assets/gallery/models/master-v1/`: six current web modules;
- `output/gallery/component-glb-v1/`: generated component QA exports, when needed.

## Visual reference

The shared style board lives at:

`assets/gallery/concepts/atlantis-modeling-reference-board.png`

It fixes the common language for all six assets: weathered teal stone,
oxidized bronze, restrained warm-gold inlay, geometric Art Deco structure,
baroque carving, chipped underwater edges, and a silhouette that remains
readable at web scale. The original Midjourney-ready prompts remain in
`.claude/midjourney-prompts.md`. The checked-in board was generated with the
available image-generation runtime so modeling could proceed in this run.

## Rebuild

Blender 4.5 LTS or newer is recommended.

```bash
python3 scripts/generate_atlantis_textures.py --output-root "$PWD"

ATLANTIS_BLENDER=/path/to/Blender.app/Contents/MacOS/Blender
"$ATLANTIS_BLENDER" \
  --background \
  --python scripts/generate_atlantis_assets.py \
  -- \
  --output-root "$PWD"
```

To rebuild one model while iterating:

```bash
"$ATLANTIS_BLENDER" \
  --background \
  --python scripts/generate_atlantis_assets.py \
  -- \
  --output-root "$PWD" \
  --only room-archway
```

The texture generator produces a 1K weathered-stone set, a 1K oxidized-bronze
set, a 2K silt-mosaic floor set, and a 1K ruin decal atlas. The browser keeps
the full-resolution floor maps; Blender embeds a 512px floor copy so the small
tile GLB remains below the 5 MB guide limit.

The Blender generator enforces metric units, applies transforms and
modifiers, creates UV coordinates, triangulates export meshes, packs the PBR
maps into each GLB, exports glTF Binary with +Y up, and leaves Draco disabled.

## Material pass

The canonical browser assets live under
`static/assets/gallery/textures/atlantis/`:

- weathered stone: base color, normal, roughness, and AO;
- oxidized bronze: base color, normal, roughness, and metalness;
- silt mosaic floor: base color, normal, roughness, and AO;
- ruin decal atlas: cracks, algae, barnacles, and silt quadrants.

`static/assets/gallery/textures/atlantis/material-manifest.json` records the
resolution and channel contract. `scripts/generate_atlantis_textures.py` is
deterministic, so generated maps can be reviewed or rebuilt without relying
on a cloud image-generation session.

## Verified budgets

| Asset | Three.js dimensions (m) | Triangles | Limit | GLB size |
| --- | ---: | ---: | ---: | ---: |
| lobby-platform | 3.000 x 0.220 x 3.000 | 3,732 | 5,000 | 4.49 MB |
| room-archway | 4.301 x 5.030 x 0.600 | 1,548 | 8,000 | 4.24 MB |
| corridor-column | 0.620 x 5.010 x 0.600 | 2,496 | 3,000 | 4.36 MB |
| wall-relief-panel | 3.000 x 2.000 x 0.243 | 2,364 | 4,000 | 4.34 MB |
| ceiling-vault | 8.029 x 0.985 x 6.000 | 2,780 | 10,000 | 4.30 MB |
| floor-tile-unit | 1.000 x 0.072 x 1.000 | 128 | 500 | 2.84 MB |

Component QA exports and their budget report are regenerated under
`output/gallery/component-glb-v1/` when needed; they are not published by
Hugo. The browser uses only the six modules under
`static/assets/gallery/models/master-v1/`.

## Runtime contract

- `layouts/gallery/list.html` preloads the six `master-v1` modules with `GLTFLoader`.
- GLB materials keep their embedded normal and roughness maps. Runtime code
  normalizes stone and gold base PBR values to the existing sea-blue and gold
  palette.
- The lobby platform anchors the Arrival Court at the beginning of the route.
- Archways and columns are instanced along the promenade and at room entries.
- Each room receives one relief, one vaulted ceiling, and six floor-tile units.
- Large walls, the 124-meter seabed, rooms, and procedural ruins use the same
  PBR source maps as the GLBs, avoiding a visible material break.
- The Arrival Court and first promenade segment include six debris fields,
  seaweed, barnacles, silt/crack decals, a fallen relief, and a broken tile.
- The six rooms occupy staggered branches along a roughly 100-meter route. Two
  route bends, ruin walls, fog, and a terminal beacon keep the full museum from
  being visible in one camera view.
- Existing Three.js primitives remain as graceful fallback if the loader or an
  individual GLB is unavailable.
- Mobile screens at 720px and below continue to use the catalog fallback.

## Verification

The Gallery is built through Hugo. The checked-in Stack v3.33.0 theme is
vendored at `themes/hugo-theme-stack`, while gallery data, images, thumbnails,
and GLBs live under `static/assets/gallery`.

```bash
/Users/eee/Desktop/works/tools/bin/hugo --minify
python3 -m http.server 8790 --directory public
```

`layouts/gallery/list.html` consumes `content/gallery/_index.md` frontmatter
for the HTML title and exhibition copy, which confirms that `public/gallery/`
is rendered output rather than a copied source file.

Open `http://127.0.0.1:8790/gallery/` and verify the following runtime markers
after the scene loads:

- `#experience[data-model-state="ready"][data-model-count="6"]`
- `#experience[data-material-state="ready"][data-material-pack="3"]`
- one `#threeCanvas` on a desktop viewport wider than 720px
- six working room-jump controls and 288 catalog cards before filtering
- the artwork detail dialog opens and closes with correct `aria-hidden` state
- a 390 x 844 viewport has no Three.js canvas, shows `.scene-fallback`, keeps
  all 288 catalog cards, and has no horizontal document overflow
- `prefers-reduced-motion: reduce` keeps the full catalog and disables the
  continuous glint and caustic animation loops
- browser console has zero errors and zero warnings after a full desktop load

The 2026-08-09 material browser pass verified all of the checks above. At a
1920 x 1080 desktop viewport, the real-browser requestAnimationFrame sample
measured 60 fps after the static-shadow and light-batching pass. The console
reported zero errors and zero warnings. A 390 x 844 reload retained all 288
catalog buttons, showed no scene canvas, displayed the 2D fallback, and had no
horizontal overflow.

Material-pass evidence is retained at:

- `output/playwright/atlantis-material-hero-arrival-final.png`;
- `output/playwright/atlantis-material-hero-room.png`;
- `output/playwright/atlantis-material-mobile-fallback.png`.

## Key assumptions

- The long-axis room coordinates and collision planes in
  `layouts/gallery/list.html` are authoritative for navigation.
- Texture detail is deterministic and shared between Blender and Three.js. A
  later art pass can replace maps without changing filenames or the runtime
  interface.
- The wall relief is the only asset whose origin is at the back-face center.
  Freestanding assets use a bottom-center origin.
