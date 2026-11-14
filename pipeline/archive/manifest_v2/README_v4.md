# Specula: SPHEREx Data (v4)

**Project:** Specula, NASA Space Apps 2026, challenge "Planet X and SPHEREx"
**Source:** NASA SPHEREx via NASA/IPAC IRSA (QR2 + QR3) · **Owner:** Muath (data)

A manifest is a **shopping list**: one row per SPHEREx photo. All 1,401 photos are **downloaded, verified, cropped, cleaned and aligned**.

**Start here:** `data/aligned/<patch>/` holds one file per photo, numbered from oldest (`0001_...`) to newest, all north-up on a shared sky grid. `frames.csv` in the same folder lists them in time order.

## Files

| File | What it is |
|---|---|
| `manifest_all.csv` | **Main file.** All 1,401 photos, all 5 patches |
| `manifest_<patch>.csv` | The same rows, split per patch |
| `answer_key_3i_atlas.csv` | Where comet 3I/ATLAS really is in each photo. ⚠️ **Detector team: don't use this while building. It's only for scoring** |
| `patches.csv` | The watchlist: each sky patch, where it is, and its job |
| `nep_candidates.csv` | Audit trail for the NEP patch: all 3,453 candidate photos, their centrality score, and why each was or wasn't chosen |
| `data/raw/full/<patch>/<obs_id>_<detector>.fits` | Full SPHEREx photos as downloaded (93 GiB) |
| `data/cut/<patch>/...` | Our square cut from each photo, 1.42x bigger to survive rotation (15 GiB) |
| `data/clean/<patch>/...` | Cleaned: SCI, ERR, SNR, MASK, FLAGS, ZODI (18 GiB) |
| `data/aligned/<patch>/NNNN_<obs_id>_<detector>.fits` | **The final images**: north-up, shared grid, time-ordered: SCI, ERR, SNR, MASK, WAVE, PSF (11 GiB) |
| `data/aligned/<patch>/frames.csv` | One row per frame in time order: frame, UTC time, burst, window, detector, wavelength, grid, coverage, star-alignment check, file |
| `download_log.csv` | One row per download attempt |
| `verify_report.csv` | One row per photo: verification status, size, layers |
| `download_spherex.py` | Downloads the photos (`check`, `test`, `all`) |
| `build_nep_manifest.py` | Builds the NEP daily sample and adds it to `manifest_all.csv` |
| `verify_spherex.py` | Checks every downloaded photo against the manifest |
| `crop_spherex.py`, `clean_spherex.py`, `align_spherex.py` | The processing chain (run in this order; `--redo` rebuilds) |
| `crop_log.csv`, `clean_log.csv` | One row per photo per stage |
| `_backup_v1/`, `_backup_v2/` | Earlier manifest versions. Safe to ignore |

## What's inside

| Patch | What it is | Photos | Dates | Bursts |
|---|---|---|---|---|
| ecliptic-virgo | Fixed 1° window on the ecliptic (asteroid hunting) | 341 | May–Jun 2025, Dec 2025, May–Jun 2026 | 64 |
| ceres | 0.5° square following dwarf planet Ceres | 277 | Jun 24–Jul 19 2025, Dec 13 2025–Jan 1 2026 | 50 |
| 3i-atlas | 0.6° square following interstellar comet 3I/ATLAS (randomly off-centre) | 259 | Aug 1–15 2025, Dec 8–14 2025 | 46 |
| ecliptic-ra90 | Fixed 1° window on the ecliptic, near the Milky Way | 218 | Sep 2025, Mar 2026 | 38 |
| nep-cats-eye | Fixed 0.5° window at the North Ecliptic Pole, Cat's Eye Nebula inside | 306 | Every day, Jul 1–Aug 30 2026 | – |
| **Total** | | **1,401** | | |

## Columns

| Column | Meaning | Example |
|---|---|---|
| `patch` | Which patch the row belongs to | `ecliptic-virgo` |
| `patch_type` | `fixed` = same sky square every time · `moving` = square follows an object | `fixed` |
| `release` | Archive release: `qr2` (up to Jul 19 2026) or `qr3` (from Jul 20 2026) | `qr2` |
| `obs_id` | Photo ID: year, week, plan, large slew, small slew | `2025W20_2D_0234_1` |
| `detector` | D1–D6, which sets the colour (wavelength) range | `D3` |
| `burst_id` | Photos taken back-to-back, ~2.15 min apart (obs_id minus the last digit) | `2025W20_2D_0234` |
| `window_id` | Visit season: a new window starts after a 30+ day gap. Always `1` for the NEP (photographed daily) | `1` |
| `t_start_utc` | Exposure start (UTC; Saudi time = +3h) | `2025-05-16T21:44:24Z` |
| `t_start_mjd`, `t_mid_mjd` | Start and middle of exposure as MJD (astronomy day count) | `60811.905839` |
| `exp_s` | Exposure length (seconds) | `113.58` |
| `wl_min_um`, `wl_max_um` | Wavelength range of the detector (microns) | `1.6301`, `2.4346` |
| `photo_ra`, `photo_dec` | Centre of the **full** photo (degrees) | |
| `cutout_ra`, `cutout_dec` | Centre of **our square** (degrees) | |
| `cutout_size_deg` | Side of our square (degrees) | `1` |
| `file_url` | Full photo (what we downloaded) | |
| `cutout_url` | IRSA's cropping link for our square (service unavailable, so not used) | |
| `pipeline_version` | NASA software version that processed the photo | `6.4+psffix1`, `7.0.5` |
| `finast` | NASA's sky-position quality flag: **0 = good** | `0` |
| `transient_pct` | % of pixels hit by cosmic rays or satellites (median ≈ 0.5–0.8%) | `0.55` |
| `full_file_mb` | Size of the full photo (71.6 for QR2, ~66.0 for QR3) | `71.6` |
| `quality` | Our verdict: `ok`, or `warn_transients` (> 5% pixels hit) | `ok` |

## Verification

| Check | Result |
|---|---|
| Re-queried IRSA: same photos? | ✅ Identical lists for both fixed patches (341/341, 218/218); 3I/ATLAS table still 259 |
| Headers of all manifest photos read before download | ✅ Detector and ID match 100% · times within ~1 s |
| Sky-position quality (`finast`) | ✅ **All 1,401 good** |
| Cosmic-ray / satellite damage | ✅ 1,394 ok · ⚠️ **7 warn** (5–10% of pixels hit; all in the original 1,095). Kept, but flagged |
| Ceres positions vs JPL Horizons at all 141 exact times | ✅ Worst difference **0.09″** (1/70 of a pixel) |
| NEP selection, computed twice independently (builder script + separate browser check) | ✅ Same 306 photos (fingerprint `58cde76afe562187`) |
| **Download** | ✅ **1,401 / 1,401**, 0 failed, 99.2 GB |
| **Every file checked (`verify_spherex.py`)** | ✅ **1,401 / 1,401 ok**: complete FITS (file size exactly matches its layers), photo ID, detector, start time and FINAST all match the manifest · 0 extra files |

## Inside every aligned frame

| Layer | What it holds | Unit |
|---|---|---|
| SCI | Cleaned brightness: dust glow (ZODI) removed, untrustworthy pixels = NaN | MJy/sr |
| ERR | 1-sigma noise of each pixel | MJy/sr |
| SNR | Significance above the sky: (SCI - BKG_MED) / ERR. Above 5 = real | - |
| MASK | 1 bad (NaN) · 2 suspect (cosmic ray or a mover, kept) · 4 star/galaxy · 8 no data · 16 saturated (kept, brightness is a lower limit). Values add up, e.g. 6 = star + suspect | - |
| WAVE | Wavelength each pixel saw | micron |
| PSF / EPSF | Star shape, in detector orientation (not rotated) | - |

Grids: Virgo, RA90 and NEP use **one grid per patch** (any two frames compare pixel to pixel). Ceres and 3I/ATLAS use **one grid per burst** (photos minutes apart); 3I/ATLAS grids never use the comet's true position.

## Processing verification (all 1,401 frames)

| Check | Result |
|---|---|
| Files at every stage (cut, clean, aligned) | 1,401 / 1,401, 0 missing, 0 extra, 0 failed |
| Crop centre on target / wavelength map | error 0.000 px / 0 |
| Clean reversible (SCI + ZODI = IMAGE) | enforced on every file |
| Stars on the same pixel across frames (Virgo, RA90, NEP, visits up to 13 months apart) | median scatter 0.06-0.07 px, visit-to-visit offset <= 0.06 px |
| Ceres vs JPL Horizons (277 frames) | median 0.18 px, worst 0.72 px; centre missing in 4 frames |
| 3I/ATLAS vs IRSA answer key (259 frames) | visible (S/N > 5) in 203 of 258; Aug 2025 faint in D5-D6, Dec 2025 bright in all detectors |
| Wavelength layer inside each detector's band | 536 / 536 checked frames |

## How the patches were selected

- **Fixed patches** (`ecliptic-virgo`, `ecliptic-ra90`): every QR2 + QR3 photo whose footprint contains the patch centre (QR3 has none yet; their next visits aren't published).
- **ceres**: for every photo taken during Ceres's two visits, we computed Ceres's position at that photo's exact mid-time (JPL Horizons) and kept the photo only if Ceres falls inside its footprint. The square is centred on Ceres.
- **3i-atlas**: IRSA's official list of every SPHEREx photo of the comet. The square's centre is **shifted by up to 0.2° at random** (seeded, so it can be repeated), so the comet isn't always dead-centre. That keeps the detector test fair. The comet always stays inside the 0.6° square.
- **nep-cats-eye** (option C, daily sample): SPHEREx photographs our NEP square ~57 times a day (26,523 photos exist). For each day from Jul 1 to Aug 30 2026 and each detector, we kept **one** photo: the one where our square sits most centrally, provided FINAST = 0 and ≤ 5% transient pixels (else the next most central, up to 3 tries). Day/detector slots where our square would be cut off by the photo edge are skipped (16 of 322). Result: 306 photos, all 61 days covered, all 6 detectors on 33 days. Each shot hits 2 detectors at once (D1+D4, D2+D5, D3+D6).

## Known issues / next steps

1. ⚠️ **IRSA's SPHEREx cutout service was down (HTTP 503)**, while full files work. We downloaded **full photos** instead and cropped our squares locally (same pixels).
2. **Two file formats.** 1,189 QR2 photos have `PSF`. The 212 QR3 photos (NEP, Jul 20 onward, pipeline 7.0.5) have **`EPSF`** and a compressed `FLAGS` layer. The scripts handle both.
3. Squares at the edge of a photo may come out smaller than requested (not the case for the NEP).
4. Ceres positions are geocentric. SPHEREx orbits ~700 km up, which shifts Ceres by ~5″ (~1 pixel). That's negligible.
5. Ceres and bright stars saturate the detector. Their cores are kept and marked MASK 16: right position, brightness is a lower limit.
6. Each frame sees a different wavelength (SPHEREx's filter), so a star's brightness changes from frame to frame. Compare positions, or frames from the same detector.
7. Next: difference images + known-asteroid labels (detector), previews + timeline (frontend).
