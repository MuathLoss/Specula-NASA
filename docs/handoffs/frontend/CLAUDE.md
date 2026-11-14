# CLAUDE.md: guide for the AI assistant helping the Specula frontend

You are helping **Zuhair (data integration: React + Vite, Three.js via @react-three/fiber)** or **Reham (UI
design)** of team Specula (NASA Space Apps 2026, challenge "Planet X and SPHEREx"). Muath (data) built
this pack. Read this file, then `Specula_frontend_data_contract.md` (exact formats) and
`Specula_project_story.md` (the whole project). Every number here was measured on the real data.

## How to help
- Explain step by step in plain language, with an analogy when something is technical.
- Check results with numbers or a quick render before claiming they work.
- If a format question isn't answered in the contract, say so and suggest asking Muath. Don't guess formats.

## Rules
1. **`addons/`, `orbits.json` and `reference_positions.json` (they hold 3I/ATLAS's positions and orbit) must never reach the detector
   teammate** before his results are scored. Keep them out of any repo, folder, chat or deployed site he can see.
2. Candidates are "candidates", never "discoveries". Sizes and candidate distances are ranges, labelled
   "estimated" / "approximate".
3. Don't edit files in `public/data/`; ask Muath for changes (the same files go to everyone).
4. Say "latest published", not "live": NASA publishes ~6 weeks after the photos are taken.

## The pack in one minute
- `manifest.json` is the entry point. Patches: `ecliptic-virgo` (341 frames, 64 bursts, 585 px),
  `ecliptic-ra90` (218, 38, 585 px), `nep-cats-eye` (306, 159, 293 px), `ceres` (277, 50, 293 px),
  `3i-atlas` (259, 46, 351 px). 1,401 frames, 357 bursts.
- Per patch: `timeline.json` = `patch` header + `frames[]` (time order) + `bursts[]` (with `representative` =
  the burst's colour composite). `markers.json` = known asteroids per frame.
- **Pixel convention:** every x, y is image pixels, 0-based, origin top-left, y down, (0,0) = centre of the
  top-left pixel. Images are north up, east left, 6.15 arcsec per pixel, 1:1 with the science grid.
- **Images are RGBA WebP.** Transparent = no data (the photo didn't cover that part). Design on a dark background.
  Fully covered frames may decode without an alpha channel (that's normal).
- Small patches (293 / 351 px) shown ~500-650 px wide: use `image-rendering: pixelated` (Zuhair's plan).
- **Composites are 2-colour false colour** (each burst is shot through 2 detectors: blue = shorter wavelength,
  red = longer). 15 bursts have one detector: greyscale.
- Each frame sees a different infrared colour (`wavelength_um`, 0.75-5.0 micron), so stars change brightness
  between frames. That's real, not a bug.
- `likely_visible` in markers: fixed patches = confirmed in 2+ photos of the burst; ceres / 3i-atlas = V < 17.
  Use it to decide which markers are shown by default.
- **NEW badge rule** (from manifest.json): a frame is NEW if its `update_id` belongs to a non-baseline update in
  `history.json` whose `ingested_utc ≥ latest_ingest_utc − 7 days`. In v0.1 everything is baseline (`u000`), so
  nothing is NEW yet: that's correct.
- `detections_mock.json` is FAKE (ids start with `MOCK-`), in the final format: build the known (circle) and
  candidate (orange diamond) paths now; the real `detections.json` replaces it later.
- **v0.2 (3D)** comes as an update zip: unzip over v0.1, replace `manifest.json`. Files: `objects.csv` (652 objects,
  48 `show_in_3d`), `orbits.json` (`objects[]` + `planets[]`), `reference_positions.json`, `pointings.json` (357 bursts),
  `cosmos.json` (8,404 stars, Milky Way band, lines, 26 labels). 3D frame: heliocentric ecliptic J2000, AU, z = ecliptic
  north (Three.js is y-up: use (x, z, −y)). Sky positions are RA/Dec J2000: convert with `radecToEcliptic`.
- **Use `specula_orbit.js`** (tested) for orbit maths: `orbitPosition(entry, jdTdb)`, `radecToEcliptic(ra, dec)`,
  `jdTdbFromDate(date)`. Elliptic and hyperbolic (3I/ATLAS) orbits are handled. Don't write your own unless it
  matches `reference_positions.json` `two_body_*` to ~1e-6 AU.
- **v0.3 (delivered):** `detections.json` replaces the mock (same fields plus extras, contract 4c): 8 tracks,
  all `status: "known"` (Ceres x4, 3I/ATLAS, 20, 232, 207), **0 candidates**. Use `object_id` to find each orbit in
  `orbits.json`. Keep the candidate code path (test it with the mock) but never show `MOCK-` data in the demo.
  `scoring.json`: 3I/ATLAS found in 50 of 207 visible photos (`score_vs_visible_frames` 0.242, 0 false points).
  Wording: "recovered", not "discovered" or "blind" (see `Specula_v0.3_update.md`).

## First session, in order
1. Unzip `frontend_data_v0.1.zip` into `public/data/` (3,530 files: 3,516 WebP + 14 JSON), then
   `frontend_update_v0.2.zip` over it, replacing `manifest.json`. Expect 3,535 files.
2. Fetch `manifest.json`, list the 5 patches with frame and burst counts.
3. Render one ceres frame with its markers. Check: Ceres (object_id "1") sits on the bright object at the centre.
4. Render one ecliptic-virgo frame with `likely_visible` markers: each circle should sit on a small dot.
5. Render the burst overview (composites) for one patch, then the per-frame timeline.
6. 3D: for each `reference_positions.json` position, `orbitPosition` must match `two_body_*` (~1e-6 AU).
7. Draw the Sun, the 8 `planets[]` and the 48 `show_in_3d` objects at a chosen date; sizes from `objects.csv`.
8. Draw each burst of `pointings.json` as a line from `earth_au` along `dir_ecl`; for ceres bursts, Ceres
   (`orbitPosition` at `jdTdbFromDate(new Date(time_utc))`) must sit on that line (within 0.008°).
9. Put `cosmos.json` stars on a large sphere (`radecToEcliptic`), size by `vmag`, colour by `bv`.

Starter (plain JS; adapt to React):
```js
const base = "/data/";
const manifest = await fetch(base + "manifest.json").then(r => r.json());
const tl = await fetch(base + "ceres/timeline.json").then(r => r.json());
const markers = await fetch(base + "ceres/markers.json").then(r => r.json());
const f = tl.frames[0];
const img = new Image(); img.src = base + "ceres/" + f.image;
await img.decode();
const scale = 600 / tl.patch.size_px;                 // display width / native width
const canvas = document.querySelector("canvas");
canvas.width = canvas.height = 600;
const ctx = canvas.getContext("2d");
ctx.imageSmoothingEnabled = false;                     // keep pixels crisp
ctx.drawImage(img, 0, 0, 600, 600);
for (const m of markers.filter(m => m.frame_id === f.frame_id && m.likely_visible)) {
  ctx.beginPath();
  ctx.arc((m.x + 0.5) * scale, (m.y + 0.5) * scale, 10, 0, 2 * Math.PI);   // +0.5: pixel centre
  ctx.strokeStyle = "cyan"; ctx.stroke();
}
```

## Known quirks
- A few frames show a faint stripe along the photo's real edge (SPHEREx detector edge glow, subtracted but not
  perfectly). Real data, not a rendering bug.
- 2 of 460 visible-marker positions fall in the 3 px transparent rim along a photo edge.
- Some frames contain satellite trails or a detector column defect (e.g. a vertical line in some 3i-atlas frames).
