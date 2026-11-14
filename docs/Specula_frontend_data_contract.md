# Specula: frontend data contract (v1.3)

**From:** Muath (data) · **For:** Zuhair (data integration), Reham (UI design)
Built from your two answer sheets. It answers Zuhair's open questions and fixes the exact format of every file.
Decisions are final (section 5). **Pack v0.1 (the pictures) and v0.2 (the 3D files) are delivered**; section 6 says
what is in each and what comes next. v1.1 = v1.0 + the real v0.2 formats (section 4) and orbit-maths help (section 4b). v1.2 = + the real detection and
scoring formats (section 4c). v1.3 = v0.3 delivered (real detections, end of 4c) + distances defined exactly.

> **Published pack:** the bookkeeping timestamps (`generated_utc`, `latest_ingest_utc`, `ingested_utc`, `added_utc`) are left out of the files in `site/public/data/`. The site treats them as optional, so nothing is marked NEW.

---

## 1. Folder layout (unzip straight into `public/data/`)
```
public/data/
├── manifest.json              entry point: version, dates, NEW-badge rule, patches, file list      [v0.1 ✅]
├── history.json               data updates (drives the NEW badge)                                  [v0.1 ✅]
├── detections_mock.json       FAKE detector results in the final format, to build against now      [v0.1 ✅]
├── addons/3i-atlas_markers.json   3I/ATLAS true position in every 3i-atlas frame                   [v0.1 ✅]
├── objects.csv                every object (known + candidates)                                    [v0.2 ✅]
├── orbits.json                orbit elements: objects (incl. Ceres, 3I/ATLAS) + planets             [v0.2 ✅]
├── reference_positions.json   test answers for your Kepler solver (JPL Horizons)                    [v0.2 ✅]
├── pointings.json             where SPHEREx looked, per burst                                       [v0.2 ✅]
├── cosmos.json                3D background: stars, galactic band, labels                           [v0.2 ✅]
├── detections.json            real detector results                                                 [after the detector]
├── scoring.json               how well the detector did                                             [after the detector]
└── <patch_id>/                ecliptic-virgo, ecliptic-ra90, nep-cats-eye, ceres, 3i-atlas           [v0.1 ✅]
    ├── timeline.json
    ├── markers.json
    ├── full/<frame_id>.webp
    ├── thumb/<frame_id>.webp
    ├── composite/<burst_id>.webp
    └── composite_thumb/<burst_id>.webp
```
Same layout on every update; a new `version` in manifest.json each time. v0.1 = 3,530 files, 153 MB (JSON 3.1 MB).
v0.2 = an **update zip** (6 files, 0.9 MB): the 5 new files + a new `manifest.json`. Unzip it over v0.1 (replace
manifest.json) → 3,535 files.

## 2. Conventions (answers to Zuhair's open questions)
| Topic | Rule |
|---|---|
| **Preview vs aligned grid** | 1:1, same size (585 / 293 / 351 px), no crop, no rescale. Flipped vertically once when written, so image row 0 = north edge. North up, east left |
| **Pixel convention** | Every x, y we send (markers, detections) is in **image** convention: 0-based, origin top-left, y down, (0,0) = centre of the top-left pixel. Verified: bright known asteroids sit on bright pixels at the marker; the vertically flipped position does not |
| **Sky ↔ pixel** | Every grid is a north-up TAN projection, 6.15″/px, centred on (ra_center, dec_center) at pixel ((size−1)/2, (size−1)/2). With ξ, η = gnomonic offsets in degrees (east, north): x = (size−1)/2 − ξ/0.0017083, y = (size−1)/2 − η/0.0017083 |
| **Moving patches** | Each **burst** has its own grid (centre in `bursts[]` and in every frame). Frames inside one burst share pixels; across bursts the stars drift. Ceres sits at the centre; 3I/ATLAS is deliberately off-centre |
| **object_id** | One id everywhere: numbered → the number (`"1"` = Ceres, `"370"`); unnumbered → provisional designation (`"2010 JB20"`); 3I/ATLAS → `"3I"`; candidates → `"cand-<patch>-<nnn>"` |
| **Sizes** | Two numbers: `size_min_km`, `size_max_km`. Measured diameter (JPL) when available, else estimated from brightness (H) with albedo 0.05-0.25 |
| **Distances (candidates)** | `distance_min_au`, `distance_max_au`: an **approximate** range of the candidate's distance **from SPHEREx (= from Earth, to 0.00005 AU) along its line of sight**, from its sky motion, assuming a typical (circular, low-tilt) asteroid orbit. Draw it from Earth's position, not from the Sun. Always labelled "approximate" |
| **Time** | UTC everywhere, ISO 8601 (`2025-06-24T09:26:51Z`) + MJD where useful. Orbit epochs: JD **TDB** (JPL standard). For orbit maths use t = JD TDB = JD UTC + 69.2 s (`jdTdbFromDate` in `specula_orbit.js`). `pointings.json` `jd` is UTC |
| **Units** | AU, degrees, km for sizes. 3D frame: heliocentric ecliptic J2000 (x toward the March equinox, z = ecliptic north). Three.js is y-up: map (x, y, z) → (x, z, −y) to lay the ecliptic flat |
| **Sky directions** | `cosmos.json` and `pointings.json` give RA/Dec J2000 (equatorial). Convert to the 3D frame with `radecToEcliptic` (`specula_orbit.js`), obliquity 23.4392911° |

## 3. Per-patch files (delivered)
### `<patch_id>/timeline.json`
```json
{
  "patch": {"patch_id": "ceres", "name": "Ceres", "kind": "moving", "followed_object": "1",
            "size_px": 293, "pixel_scale_arcsec": 6.15, "north_up": true, "projection": "TAN",
            "date_start": "2025-06-24T09:26:51Z", "date_end": "2026-01-01T14:53:18Z",
            "n_frames": 277, "n_bursts": 50},
  "frames": [
    {"frame_id": "0001_2025W26_1A_0306_1_D4", "burst_id": "2025W26_1A_0306",
     "time_utc": "2025-06-24T09:26:51Z", "mjd": 60850.393657, "detector": "D4", "wavelength_um": 2.7747,
     "image": "full/0001_2025W26_1A_0306_1_D4.webp", "thumb": "thumb/0001_2025W26_1A_0306_1_D4.webp",
     "ra_center": 13.773746, "dec_center": -5.771419, "coverage": 0.9303, "quality": "ok",
     "update_id": "u000"}
  ],
  "bursts": [
    {"burst_id": "2025W26_1A_0306", "time_utc": "2025-06-24T09:30:05Z",
     "frame_ids": ["0001_2025W26_1A_0306_1_D4", "0002_2025W26_1A_0306_2_D1", "…"], "detectors": ["D1", "D4"],
     "ra_center": 13.773746, "dec_center": -5.771419,
     "composite": "composite/2025W26_1A_0306.webp", "composite_thumb": "composite_thumb/2025W26_1A_0306.webp",
     "representative": "composite/2025W26_1A_0306.webp"}
  ]
}
```
`frame_id` = the aligned file name without `.fits`, unique across the dataset. Frames are in time order.
`quality` is `ok` or `warn_transients` (7 photos with > 5% pixels hit by cosmic rays/satellites).

### `<patch_id>/markers.json` (known objects, from NASA JPL)
`[{"frame_id", "object_id", "name", "x", "y", "v_mag", "likely_visible"}]`, one row per object per frame where the
object falls on real data (14,335 rows). `likely_visible`: fixed patches = seen in the difference image in 2+
photos of the same burst; moving patches = V < 17 (estimate: no difference images there). nep-cats-eye has none.

### Images (WebP, RGBA)
| | Size | Notes |
|---|---|---|
| `full` | native (585 / 293 / 351 px) | Lossy q90. Tested: faint known asteroids (V 17.6-19.0) keep 94-100% of their contrast vs lossless |
| `thumb` | 128 px wide | |
| `composite` + `composite_thumb` | same | **2-colour false colour**: each burst is shot through 2 detectors (pairs D1+D4, D2+D5, D3+D6); shorter wavelength → blue, longer → red. 15 of 357 bursts have one detector → greyscale |

Display processing (pictures only, never the science data): one fixed brightness stretch per patch **and
detector** (no flicker when flipping same-detector frames); a smooth background removed; bad pixels and saturated
star cores filled from their neighbours; **transparent** where there is no data, plus a thin rim along the photo's
real edge (SPHEREx detector edges glow, up to ~45 px, measured per frame). Design for a dark background.

## 4. Global files
| File | Content |
|---|---|
| `manifest.json` ✅ | `version, generated_utc, data_through_utc, latest_ingest_utc, new_badge_days, new_badge_rule, patches[]` (`patch_id, name, kind, n_frames, n_bursts, date_start, date_end, folder`), `files[]` (`path, bytes`) |
| `history.json` ✅ | `[{update_id, ingested_utc, baseline, data_through_utc, n_frames, frames_added, note}]`. `u000` = the baseline (all 1,401 photos) and is never NEW |
| `detections_mock.json` ✅ | **Fake** results in exactly the final format: 3 real known asteroids in ecliptic-virgo (real positions, made-up scores) + 2 invented candidates (`MOCK-cand-001` virgo, `MOCK-cand-002` nep) with approximate distance and size. Track ids start with `MOCK-`. Format: `[{track_id, patch, status, object_id, match_sep_arcsec, motion_arcsec_per_hr, direction_deg (0 = north, 90 = east), score, first_seen_utc, size_min_km, size_max_km, distance_min_au, distance_max_au, points: [{frame_id, x, y, ra, dec, mag}]}]` |
| `addons/3i-atlas_markers.json` ✅ | `[{frame_id, object_id: "3I", name, x, y, in_data, snr_peak, likely_visible}]` for all 259 frames: on data in 258, likely visible (S/N ≥ 5 within 2 px) in 207. **Frontend only** (section 7) |
| `objects.csv` ✅ | `object_id, name, kind` (asteroid / dwarf_planet / interstellar / candidate), `status` (known / candidate), `H_mag, size_min_km, size_max_km, size_source, distance_min_au, distance_max_au, show_in_3d, patches` (`;`-separated), `n_frames` (photos where it falls on real data), `first_utc, last_utc`. **652 rows** = every known object in our photos (651) + 3I/ATLAS; real candidates are added in v0.3. Sizes: measured diameter ± its uncertainty (JPL, 303 objects) or estimated from H with albedo 0.05-0.25 (348); 3I/ATLAS has no size (its nucleus is hidden by its coma). `show_in_3d` = size_max ≥ 10 km, plus Ceres, 3I/ATLAS and every candidate: **48 objects** now |
| `orbits.json` ✅ | `{frame, how_to, source, objects[], planets[]}`, heliocentric ecliptic J2000, AU, degrees. Elliptic (from JPL SBDB): `object_id, name, orbit_type: "elliptic", a_au, e, i_deg, node_deg, peri_deg, M_deg, n_deg_day, epoch_jd_tdb`. Hyperbolic (3I/ATLAS, from JPL Horizons, elements at 2025-10-15 = the middle of our 3I photos): `orbit_type: "hyperbolic", q_au, a_au (< 0), e, i_deg, node_deg, peri_deg, tp_jd_tdb, n_deg_day`. `planets[]`: Mercury-Neptune system barycentres in the elliptic format, `object_id` `planet-<name>`, elements at 2026-01-01 TDB (Earth = Earth-Moon barycentre, < 0.0001 AU from Earth itself). All 652 objects have an orbit. Use `n_deg_day` as given. Candidates: no orbit (see D2) |
| `reference_positions.json` ✅ | Ceres, 370 Modestia, 3I/ATLAS at 5 dates (2025-05-15 → 2026-08-30, JD TDB): JPL's true `x_au, y_au, z_au` + `two_body_x/y/z_au` (what correct two-body maths from orbits.json gives) + `two_body_error_au`. **Test: your solver must match `two_body_*` to ~1e-6 AU.** Two-body vs truth: ≤ 0.0005 AU (Ceres), ≤ 0.002 AU (Modestia), ≤ 0.0001 AU for 3I/ATLAS during our photos (0.007 AU by Aug 2026): invisible in 3D |
| `pointings.json` ✅ | 357 bursts in time order: `burst_id, patch_id, time_utc, jd` (UTC), `ra_deg, dec_deg, fov_deg` (0.999 / 0.5 / 0.6), `dir_ecl` (unit vector, 3D frame), `earth_au` (Earth's centre, x y z). SPHEREx ≈ Earth at this scale (< 0.00005 AU apart). Checked: Ceres sits inside every ceres pointing within 0.008° |
| `cosmos.json` ✅ | `stars`: `[ra_deg, dec_deg, vmag, bv]` for **8,404 stars to V 6.5**, brightest first (Yale Bright Star Catalogue 5th ed.; `bv` = colour, null if unknown). `galactic_band`: `{half_width_deg: 10, points: [ra, dec, l]}` every 2° of galactic longitude (l = 0 = Galactic Centre). `lines`: `ecliptic`, `galactic_equator` as `[ra, dec]`. `labels` (26): 18 named stars (Sirius … Polaris), our 5 patches (`moving: true` for ceres / 3i-atlas, placed at their middle burst), both ecliptic poles, Galactic Centre. All positions RA/Dec J2000 |

### 4b. Orbit maths (`specula_orbit.js`, delivered with v0.2)
`orbitPosition(entry, jdTdb)` → [x, y, z] AU for any `orbits.json` entry (objects or planets); `radecToEcliptic(ra, dec)`
→ unit vector in the 3D frame; `jdTdbFromDate(date)`. Tested: matches our Python solver to 1e-9 AU on all reference
dates; Earth from `planets[]` lands within 0.0001 AU of `earth_au` at all 357 bursts; Ceres falls inside every ceres
pointing (0.008° max). The same steps are in `orbits.json` → `how_to`.

### 4c. Real detections (`detections.json`, `scoring.json`, from v0.3)
`detections.json` has every field of `detections_mock.json`, plus:

| Field | Meaning |
|---|---|
| `is_target_claimed`, `points[].is_target` | The detector marked this track / point as Ceres or 3I/ATLAS |
| `n_points` | Detections in the track |
| `linked_tracks`, `arc_hours` (candidates) | Detector tracks joined across bursts (1-48 h apart) and the time they span |
| `v_mag_est`, `H_range`, `position_error_px` (candidates) | Estimated brightness (from our difference images, about ±0.7 mag), absolute-magnitude range, position error used |
| `comet_check` (candidates) | Result of the check against every known comet (NASA JPL) |
| `note` (candidates) | Why distance / size are null, in plain words (e.g. "only 6 min of motion") |

Rules: a candidate's `object_id` is `cand-<patch>-<nnn>`; known tracks have `distance_*` null (use their orbit) and sizes
from `objects.csv`; 3I/ATLAS comes as `status: "known"`, `object_id: "3I"`; x, y are image pixels (as in markers.json).
**Candidates with null distance**: show them in the sky viewer only (no 3D segment), labelled "distance unknown".
`scoring.json`: `3I_ATLAS_blind_test` (`frames_on_data, frames_likely_visible, frames_found, score_vs_all_frames,
score_vs_visible_frames` = the fair score, `false_target_points, median_position_error_arcsec`), `ceres_check` (same
fields), `known_asteroids_recovered` per brightness bin, `tracks` (counts by patch and status), `rules` (method).
`objects.csv` gets one row per candidate (`kind` and `status` "candidate"); `show_in_3d` is true only if it has a distance.
How distances were tested: 34 real asteroids run through the method as if unknown: the true distance was inside the
range every time. One burst (~6 min of motion) is usually too short (null); seen in 2+ bursts → ranges ~1.5-3.5x wide.

**What v0.3 actually contains.** `detections.json` is a list of **8 tracks, all `status: "known"`**: Ceres
(`"1"`, 4 tracks), 3I/ATLAS (`"3I"`), 20 Massalia, 232 Russia, 207 Hedda. **0 candidates**, so the candidate-only fields
are absent. `is_target_claimed` / `points[].is_target` are false everywhere: the pipeline makes no target claims; known
objects (3I/ATLAS too) are recognised afterwards by position. `scoring.json` targets carry `mode` = "position only":
every reported point in the patch counts, and points away from the target count as false. How the tracks were made:
the detector's per-photo spot list (1,911,543 spots), then star removal, burst grouping, straight-line linking over
4+ bursts and a noise test on scrambled data (`Specula_v0.3_update.md`).

## 5. Decisions (final)
- **D1 · NEW badge:** a frame is NEW if its `update_id` is not a baseline update and that update's `ingested_utc ≥ latest_ingest_utc − 7 days` (the dataset's clock from manifest.json, not the visitor's). Can't expire before the event.
- **D2 · Candidates in 3D:** placed on their sight-line from Earth at an **approximate distance range** (`distance_min_au`-`distance_max_au`), shown as a segment or a marker with an uncertainty bar, labelled "approximate". No orbit. Never "confirmed discovery".
  Ranges come from statistical ranging (near-circular, low-inclination orbit, SPHEREx's real position, 95% region);
  when the motion is too short to pin the distance down, both values are null (section 4c).
- **D3 · 3I/ATLAS:** delivered to the frontend **now** (`addons/3i-atlas_markers.json`; its orbit comes in `orbits.json`). See the rule in section 7.
- **D4 · Not built:** `positions.json` (you compute positions from orbits) and a Milky Way photo (a drawn band instead).

## 6. Delivery
| Pack | Content | Status |
|---|---|---|
| **v0.1** | All 1,401 frames: full + thumb + 357 composites, `timeline.json` + `markers.json` per patch, `manifest.json`, `history.json`, `detections_mock.json`, 3I markers | ✅ delivered (Google Drive "frontend data") |
| **v0.2** | `objects.csv`, `orbits.json` (+ planets, Ceres, 3I), `reference_positions.json`, `pointings.json`, `cosmos.json`, new `manifest.json` (update zip over v0.1) + `specula_orbit.js` | ✅ delivered (same Drive folder) |
| **v0.3** | real `detections.json` + `scoring.json`, new `manifest.json` (update zip over v0.2) | ✅ delivered |

## 7. Rules
1. **3I/ATLAS positions never reach the detector teammate** before his results are scored: keep `addons/`, `orbits.json` and `reference_positions.json` (they hold 3I/ATLAS's positions and orbit) out of any repo, folder, chat or deployed site he can see.
2. Candidates are always "candidate", never "discovery". Distances and sizes are always ranges, labelled "approximate" / "estimated".
3. Don't edit delivered files; ask Muath, so every copy stays identical.
4. Say "latest published", not "live" (NASA publishes ~6 weeks after capture).

## 8. Reham's answers, as built
| Request | How the data supports it |
|---|---|
| All 1,401 photos in the timeline, one representative per burst in the overview | `frames` (all) + `bursts[].representative` (the composite). **Burst count confirmed: 357** (virgo 64, ra90 38, nep 159, ceres 50, 3i-atlas 46). The "~220" was an earlier mistake |
| ~500-650 px display | 585 px fits; 293/351 px patches show ~2× with pixelated scaling (the pixels become visible, by design) |
| Per step: time, patch, image, detections, wavelength/detector | All in `frames[]`; detections via `markers.json` / `detections.json` by `frame_id` |
| 3D: Sun, planets, orbits, SPHEREx pointings, layer toggles | `orbits.json` (+ planets), `pointings.json`, `cosmos.json` as separate layers; `show_in_3d` keeps it to 48 objects |
| Sizes as ranges | `size_min_km` / `size_max_km` |
| Circles = known, orange diamonds = candidates | `markers.json` (known) and `detections.json` `status` |
| NEW badge 7 days from ingestion | `update_id` + `added_utc` per frame, `history.json`, rule D1 |
