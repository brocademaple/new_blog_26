# Atlantis Gallery Master V2 implementation plan

## Direction

Master V2 uses the asymmetric crescent campus as its spatial structure:

- `atlantis-gallery-crescent-campus-v4-hero.png` defines the three-quarter arrival composition.
- `atlantis-gallery-crescent-campus-v4-plan.png` defines the open oval garden and continuous visitor loop.
- `atlantis-gallery-coral-garden-v3-c.png` is the atmosphere reference for flowing paths, reef integration, sunlight, and distributed pavilions.
- `atlantis-archive-interior-v4.md` defines the archive pavilion interior.

The current axial palace campus remains Master V1 and stays deployable during V2 development. V2 work must not overwrite `atlantis-gallery-master-v1.blend` or the `master-v1` GLBs.

## Spatial program

1. Lower-left arrival terrace reveals the sculpture garden first.
2. A 3.2 m visitor loop follows the crescent terrain instead of a straight ceremonial axis.
3. The long glass-vault gallery occupies the left reef edge.
4. Three different terraced pavilions climb the right reef edge.
5. The archive pavilion sits rear-left and remains visually secondary from arrival.
6. Two branch paths lead to overlooks and small installations before rejoining the loop.
7. Stairs and 1:12 ramps connect the three terrain bands at Z=0, Z=3.2 m, and Z=6.4 m.

## Theme allocation

- Long glass gallery: Color and Lighting.
- Lower right pavilion: Recomposition.
- Middle right pavilion: Material.
- Upper right pavilion: Mood and Object.
- Archive pavilion: curated highlights, prompt records, and the three-level archive experience.
- Central garden: sculpture, relic, and non-image installations only.

This allocation is a planning baseline. The user's next round of requirements can change it before graybox approval.

## Build sequence

### Phase 0: Freeze V1

- Keep the current V1 Blender master, six GLBs, Hugo runtime, and Aliyun release as the rollback baseline.
- Retain `scripts/audit_gallery_artwork_binding.py` as a mandatory export gate.

### Phase 1: Terrain and circulation graybox

- Create `assets/gallery/blender/working/atlantis-gallery-master-v2-graybox.blend`.
- Build only terrain bands, the oval garden, the complete loop, branches, stairs, ramps, and building envelopes.
- Add arrival, aerial-plan, loop, and accessibility review cameras.
- Stop for visual approval before adding detailed architecture.

### Phase 2: Gallery shells

- Build the glass-vault bay, curved retaining wall, terraced pavilion bay, and curved balustrade as reusable modules.
- Give every exhibition room a floor, enclosed art wall, doorway, and visible return route.
- Test the full route in Blender and a temporary web GLB before detail work.

### Phase 3: Archive pavilion

- Implement the vestibule, rotunda, four radial rooms, upper ring, bridge, lower archive, and service route from the archive-interior contract.
- Verify that every stair visibly lands on usable floors.

### Phase 4: Artwork binding

- Assign each mounted work a stable Gallery record identifier plus thumbnail path in glTF extras.
- Generate frames from source aspect ratios; never stretch or rotate source images.
- Require byte-for-byte texture binding audit and real browser click verification before release.

### Phase 5: Web handoff

- Export V2 as spatial modules sharing one world origin.
- Load modules progressively by visitor distance while keeping the entrance usable during download.
- Preserve the V1 URL until V2 passes desktop, mobile, navigation, interaction, and performance gates.

### Phase 6: Material and atmosphere

- Add pale limestone, oxidized bronze, glass vaults, warm protected interiors, reef ecology, sunlight shafts, and restrained particulate motion.
- Use the coral-garden image for flow and environmental density; avoid copying its excessive ornamental detail into the first production pass.

## Rejection gates

Reject a V2 blockout when any of these are true:

- It reads as a central palace with mirrored wings.
- The visitor route becomes one straight processional avenue.
- Buildings float as detached objects on empty seabed.
- A room has no floor, no doorway, or no clear route back to the loop.
- Stairs terminate in walls or decorative platforms.
- A mounted image is rotated, stretched, or opens a different Gallery record.
- V2 work modifies the V1 Blender master or `master-v1` runtime files before approval.

## Approval checkpoints

1. Graybox aerial plan and arrival view.
2. Walkable loop and accessible height changes.
3. Gallery shell program and artwork capacity.
4. Archive cutaway and circulation.
5. Web graybox performance and click mapping.
6. Final materials, lighting, and Aliyun release candidate.

Implementation starts only after the user's remaining structural notes are added to this plan.
