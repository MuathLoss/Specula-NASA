# Specula: UI ideas (what the data lets you show)

**From:** Muath (data) · **For:** Zuhair (data integration) and Reham (UI design)

> These are **ideas, not decisions**. They come from your answer sheets and from what is in the Drive.
> The design is yours: change anything, and tell Muath if you need a file in a different shape.

## 1. What's in the Drive folder "frontend data"
| File | What it is | Who needs it |
|---|---|---|
| `frontend_data_v0.1.zip` | **The pictures** (153 MB, 3,530 files). Unzip into the site's `public/data/` | Zuhair |
| `frontend_update_v0.2.zip` | **The 3D files** (0.9 MB). Unzip over v0.1 | Zuhair |
| `specula_orbit.js` | Tested orbit maths for the 3D scene | Zuhair |
| `Specula_UI_ideas.md` | This file: what the UI could show | Both, read first |
| `README.md` | Start in 3 steps | Zuhair |
| `Specula_frontend_data_contract.md` | Exact format of every file | Zuhair (Reham: sections 5, 7, 8) |
| `Specula_project_story.md` | The whole project story, for you and your AI assistant | Both |
| `CLAUDE.md` | Guide for your AI assistant | Zuhair |
| `checksums.sha256` | Fingerprints to check the download | Zuhair |

**Inside the v0.1 zip**, one folder per patch (`ecliptic-virgo`, `ecliptic-ra90`, `nep-cats-eye`, `ceres`, `3i-atlas`):

| What | Count | Use it for |
|---|---|---|
| Full photos (`full/`) | 1,401 | The main picture |
| Thumbnails (`thumb/`, 128 px) | 1,401 | Timeline strip |
| Colour composites (`composite/` + thumbnails) | 357, one per burst | Overview / gallery |
| `timeline.json` | 1 per patch | The slider: every photo and burst, in time order |
| `markers.json` | 14,335 rows | Circles on known asteroids (460 bright enough to see) |
| `manifest.json`, `history.json` | 1 each | Entry point; NEW badge |
| `detections_mock.json` | 5 fake tracks | Build the detection UI now (ids start with `MOCK-`) |
| `addons/3i-atlas_markers.json` | 259 rows | 3I/ATLAS position in each of its photos |

## 2. What each screen could show
### A. Sky viewer (main screen)
- **Picture:** `full/<frame_id>.webp` on a dark background (photos are transparent where there is no data).
  The 293 / 351 px patches look good at 2× with pixelated scaling.
- **Time slider:** all photos of the patch, tick marks for bursts, a play button to animate.
- **Info per step:** date and time (UTC), patch, detector + wavelength (e.g. "D4 · 2.77 µm"), and
  "latest published" (never "live").
- **Known asteroids:** a circle at each `markers.json` x, y. Idea: solid circle when `likely_visible` is true,
  dim dashed circle when false; name and brightness on hover.
- **Toggle idea: "Show faint (predicted)"**, off by default. 13,875 of the 14,335 markers are too faint to see;
  showing them all covers the picture in circles around nothing visible.
- **Candidates (later):** orange diamonds from the detections file, always labelled "candidate".
- **Showcase objects:** Ceres = the bright dot in the centre of every ceres photo (easy first check).
  3I/ATLAS = a special marker from the addon file (likely visible in 207 of 259 photos), off-centre on purpose.

### B. Overview / gallery
- One colour composite per burst (357). Click one → open that burst in the viewer.
- Composites are **false colour**: shorter infrared wavelength → blue, longer → red. Suggest a small label
  "false colour (infrared)". 15 bursts are greyscale (only one detector).

### C. 3D solar system (data delivered in v0.2)
- Sun, the 8 planets, and the 48 `show_in_3d` objects with their orbits (Ceres, 3I/ATLAS, and every asteroid
  ≥ 10 km we photographed). 3I/ATLAS's path is a hyperbola: it passes once and leaves the solar system.
- Where SPHEREx looked (`pointings.json`), as lines or cones from Earth.
- Background: 8,404 real stars (coloured by temperature), a drawn Milky Way band, 18 named bright stars (`cosmos.json`).
- A layer toggle for each of these.
- Candidates: a segment along the line of sight from Earth, labelled "approximate distance". Candidates
  without a distance (seen for only a few minutes): sky viewer only, labelled "distance unknown".

### D. NEW badge
- A photo is NEW for 7 days after the dataset's latest update (rule D1 in the contract).
- **Note:** v0.1 is all baseline data, so **no NEW badge shows yet**. To design and test it, fake an update
  locally (change one frame's `update_id`, add a matching entry to `history.json`), then remove it.

## 3. Rules that shape the UI
1. Candidates are **"candidate"**, never "discovery".
2. Sizes and distances are **ranges**, labelled "estimated" / "approximate".
3. Say **"latest published"**, not "live" (NASA publishes photos about 6 weeks after they are taken).
4. **Never share** this folder, or `addons/`, `orbits.json` and `reference_positions.json` (they hold 3I/ATLAS's positions and orbit), with the detector teammate before his
   results are scored.
5. Don't edit the data files; ask Muath for changes, so every copy stays identical.

## 4. What's next
v0.2 (3D files) ✅ → v0.3: real detections + scoring → v1.0: one frozen zip for
offline use at the event.
