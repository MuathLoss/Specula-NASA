# Specula: frontend data pack v0.3 (pictures + 3D files + real detections)

**From:** Muath (data) · **For:** Zuhair (data integration) and Reham (UI design)
**Project:** NASA Space Apps 2026, challenge "Planet X and SPHEREx"

## What's in this folder
| File | What it is |
|---|---|
| `frontend_data_v0.1.zip` | **The pictures (v0.1).** Unzip its contents straight into the site's `public/data/` (153 MB, 3,530 files) |
| `frontend_update_v0.2.zip` | **The 3D files (v0.2).** Unzip it into the same `public/data/` *after* v0.1 and replace `manifest.json` (0.9 MB, 6 files) |
| `frontend_update_v0.3.zip` | **The real detections (v0.3).** Unzip it into the same `public/data/` *after* v0.2 and replace `manifest.json` (3 files) |
| `Specula_v0.3_update.md` | **Read first for v0.3:** how the detections were made, the results, honest wording |
| `specula_orbit.js` | Tested orbit maths for the 3D scene (ES module): positions from `orbits.json`, RA/Dec → 3D |
| `Specula_UI_ideas.md` | **Read first (both of you).** Ideas for what the UI could show |
| `Specula_frontend_data_contract.md` | The exact format of every file (v1.3, built from your answer sheets) |
| `Specula_project_story.md` | The whole project story: idea, data, what we did, decisions |
| `CLAUDE.md` | Guide for your AI assistant: give it this file first |
| `checksums.sha256` | Fingerprint of every file in this folder |

## Start in 3 steps
1. Download the folder, unzip `frontend_data_v0.1.zip` into `public/data/` (keep the folder names), then unzip
   `frontend_update_v0.2.zip` into the same place (say yes to replacing `manifest.json`).
2. Open `public/data/manifest.json`: the entry point (patches, dates, file list, NEW-badge rule).
3. Load `ceres/timeline.json`, show `ceres/full/<frame_id>.webp`, draw `ceres/markers.json` on top.
   Ceres is the bright object in the centre of every ceres frame: your first check that markers line up.

## What v0.1 contains
- **All 1,401 SPHEREx photos** of the 5 sky patches as WebP: full size (585 / 293 / 351 px), 128 px thumbnails,
  and **357 burst colour composites** (+ thumbnails).
- Per patch: `timeline.json` (every frame and burst, in time order) and `markers.json` (14,335 known-asteroid
  positions from NASA JPL, already in image pixels).
- `manifest.json`, `history.json` (baseline update; NEW badge rule), `detections_mock.json` (FAKE detector
  results in the final format, track ids start with `MOCK-`).
- `addons/3i-atlas_markers.json`: 3I/ATLAS true position in each 3i-atlas frame. **Frontend only**: never share
  it with the detector teammate before his results are scored (same for `orbits.json` and `reference_positions.json`
  from v0.2, which hold 3I/ATLAS's orbit).

## What v0.2 adds (the 3D files)
- `objects.csv`: 652 objects (every known object in our photos + 3I/ATLAS), sizes as ranges, 48 marked `show_in_3d`.
- `orbits.json`: orbits of all 652 + the 8 planets. `reference_positions.json`: JPL answers to test the orbit maths.
- `pointings.json`: where SPHEREx looked for each of the 357 bursts + Earth's position.
- `cosmos.json`: 8,404 stars, the Milky Way band, ecliptic + galactic lines, 26 labels.
- First 3D check: with `specula_orbit.js`, Ceres must land inside every ceres pointing.

## What v0.3 adds (the real detections)
- `detections.json`: 8 tracks, all known objects (Ceres, 3I/ATLAS, 20 Massalia, 232 Russia, 207 Hedda), 0 candidates.
- `scoring.json`: 3I/ATLAS found in 50 of its 207 visible photos with 0 false points; Ceres in 134 of 273.

## Coming next
v1.0: one frozen zip for offline use at the event.

**Questions:** ask Muath.
