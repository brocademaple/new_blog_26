# Atlantis Archive Interior v4

## Interior contract

The archive pavilion is a complete three-level museum interior. It must not collapse into one nave or one frontal display wall.

- Outer building diameter: approximately `24 m`.
- Central rotunda clear diameter: approximately `11 m`.
- Dome apex: approximately `18 m` above ground-floor finish.
- Visitor floors: lower archive at `Z=-4.2 m`, ground galleries at `Z=0`, upper ring gallery at `Z=4.8 m`.
- Sealed vertical light chamber: approximately `2.8 m` diameter, continuous through all levels.

## Ground level

- Entrance vestibule: approximately `5 m x 6 m`; use it as a visual compression zone before the rotunda reveal.
- Central orientation rotunda with one sculpture focal point and clear circulation around it.
- Four radial exhibition chambers, each approximately `5.5 m x 6.5 m`, with three protected wall works per room.
- Rear sanctum gallery: approximately `6 m x 8 m`, holding one focal work and two supporting pieces.
- Visitor ring corridor: minimum clear width `2.4 m`.
- Two stairs rise to the upper ring and two stairs descend to the archive. Every stair must visibly land on a usable floor.

## Upper level

- Continuous ring gallery: minimum clear width `3 m`.
- Two balcony overlooks into the rotunda.
- One `2.2 m` wide bridge crosses the light void and provides a second loop choice.
- Two cabinet rooms, each approximately `4 m x 5 m`, for smaller works and material studies.
- Preserve view lines to the dome, the light chamber, and at least two ground-floor doorways.

## Lower archive

- Circular public archive around the base of the light chamber.
- Three radial storage vaults, one conservation room, and one staff-only service corridor.
- Keep archive shelves and worktables outside the main visitor turning radius.
- Use brighter floor-level guidance and warm shelf lighting so this level remains readable underwater.

## Art and circulation capacity

- Ground level: approximately 15 mounted works across the four side rooms and rear sanctum.
- Upper level: approximately 8 works across the ring and two cabinet rooms.
- Lower level: archival objects and conservation displays; avoid filling it with framed paintings.
- Primary loop should return visitors to the rotunda without backtracking; branch rooms may be short dead ends only when their entrance remains visible.

## Blender module list

1. Rotunda wall wedge, `30°` segment.
2. Upper ring floor and railing wedge, `30°` segment.
3. Radial gallery chamber shell.
4. Curved stair pair connecting one level.
5. Bridge segment over the light chamber.
6. Lower archive shelf and workbench kit.
7. Sealed light-chamber glass cylinder and dome oculus.

Instance repeated wedges and trim. Keep doors, stairs, artworks, and room-specific furniture as separate objects so layout and web-export LOD can be adjusted independently.

## Review cameras and acceptance gates

- `ArchiveInteriorArrivalCamera`: vestibule reveal showing four destinations, upper ring, and lower stair.
- `ArchiveInteriorCutawayCamera`: three-quarter section showing all three floors.
- `ArchiveInteriorUpperRingCamera`: view across the bridge toward two side chambers.
- `ArchiveInteriorLowerVaultCamera`: archive level with the light chamber and conservation room entrance visible.
- Reject the build if any review view reads as a single hall, if stairs terminate into walls, if upper rooms lack floors, or if artworks appear in open water.

## Concept references

- `assets/gallery/concepts/atlantis-archive-interior-v4-cutaway.png`
- `assets/gallery/concepts/atlantis-archive-interior-v4-rotunda.png`

Build this only in a working copy under `assets/gallery/blender/working/`. Do not overwrite `atlantis-gallery-master-v1.blend`; the approved structural rebuild becomes `atlantis-gallery-master-v2.blend`.
