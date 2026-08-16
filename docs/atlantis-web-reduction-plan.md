# Atlantis Gallery web reduction plan

Status: master-v1 is integrated in the local Hugo preview. The approved Blender
master, including the v1 upper-circulation loop, is exported as six modules that
share Blender's world origin. The old procedural district is disabled whenever
all master modules load, so the browser no longer composes a different palace
and route from hand-authored Three.js primitives.

## Authoritative inputs

- Blender master: `assets/gallery/blender/atlantis-gallery-master-v1.blend`
- Master audit: `output/gallery/blender-master-audit.json`
- Render-instance profile: `output/gallery/web-zone-profile.json`
- Visual audit: `output/gallery/audit-latest/`

The packed Blender master currently renders approximately **289,692 triangles** across all dependency-graph instances. The proposed desktop LOD0 budget is approximately **142,000 triangles**.

## Zone budgets

| Zone | Current rendered triangles | Desktop LOD0 target | Primary treatment |
| --- | ---: | ---: | --- |
| Arrival and route | 78,824 | 22,000 | Reuse one arch/column mesh, collapse hidden trim, simplify compass spokes |
| Archive of Tides | 31,330 | 18,000 | Preserve entrance, title, three artworks and relic silhouettes |
| Cliff Gallery | 28,514 | 18,000 | Preserve entrance, title, three artworks and relic silhouettes |
| Central palace | 59,764 | 42,000 | Preserve three domes, twin towers, facade rhythm, sign and interior focal wall |
| Water and boundary | 9,158 | 12,000 | Keep water surface, four caustic planes and three volume shafts; budget includes export-safe replacements |
| Ecology and ruins | 82,102 | 22,000 | Instance coral/kelp prototypes, reduce far ruins and rock segmentation |
| Shared contingency | 0 | 8,000 | Collision proxies, export pivots and integration helpers |

## Preserve at highest fidelity

1. Palace silhouette, three domes and twin side towers.
2. `THE SUNKEN ARCHIVE`, `ARCHIVE OF TIDES` and `CLIFF GALLERY` signage.
3. Open thresholds and walkable interiors for all three museum buildings.
4. Artwork aspect ratios, frames, focal portrait and palace mosaic.
5. Sea-surface silhouette, procedural caustic rhythm and volume-light landing points.
6. Warm-window versus cyan-water color contrast.

## Reduce first

1. Far ruin arches and broken columns outside the playable corridor.
2. Repeated high-segment torus caps, coral branches and sculpture rings.
3. Hidden wall backs, buried foundations and unseen dome undersides.
4. Suspended-particle geometry; replace with Three.js instancing or shader particles.
5. Boundary rocks outside hero-camera silhouettes.
6. Repeated route columns; share geometry and materials instead of baking unique copies.

## Implemented web modules (`static/assets/gallery/models/master-v1/`)

1. `atlantis-environment.glb`
2. `atlantis-route.glb`
3. `atlantis-archive.glb`
4. `atlantis-cliff-gallery.glb`
5. `atlantis-palace-complex.glb` (facade, interior, twin stairs, upper loggias and rear bridge)
6. `atlantis-ecology.glb`
7. Water surface, fog, caustics and key lights are recreated in Three.js because Blender volume/procedural transparency nodes do not translate faithfully to glTF.

The current manifest is about 50.4 MB across the six modules. Loading is
sequential to reduce peak memory. The next optimization pass should create
desktop/mobile LODs without changing the shared world-space layout.

## Export gates after approval

- Metric units, applied transforms, bottom-center origins and +Y Up.
- No cameras or Blender lights in GLB exports.
- UVs, normals, tangents and required modifiers applied.
- No Ngons; verify triangle counts from exported GLBs, not only source meshes.
- Pack/bake base color, normal, roughness and metalness maps as applicable.
- Each module below 5 MB where practical; preserve the existing mobile 2D fallback.
- Load all modules through `GLTFLoader`, verify runtime camera movement, collisions and zero console errors.

## Current evidence

- The pre-v1 Blender and web rollback snapshots were retired after master-v1 acceptance on 2026-08-14.
- Master export script: `scripts/export_atlantis_web_master.py`
- Master manifest: `static/assets/gallery/models/master-v1/manifest.json`
- Blender review renders: `output/gallery/atlantis-palace-upper-stair-review.png` and `output/gallery/atlantis-palace-upper-bridge-review.png`
- Hugo preview exposes `?review=palace` and `?review=palace-upper` for direct facade and upper-loggia checks.
- `document.body.dataset.blenderMaster=ready` and `blenderModules=6` are set only after all six master modules have loaded.

## Approval boundary

Continue with collision, lighting and decoration iterations only after each
review render and the corresponding local web screenshot are checked. Keep the
rollback copy until the five-stage goal is accepted.
