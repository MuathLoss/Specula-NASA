# Pipeline: from NASA's archive to the website's data

These scripts take real SPHEREx photos from NASA/IPAC IRSA, prepare them so stars line up pixel for pixel, label every known object with NASA JPL's positions, and build the data files the website reads.

Run every script from this folder. Outputs go to `data/` (photos and tables) and `handoff/` (packages), created next to the scripts. A full run downloads **99.2 GB** of photos.

```bash
pip install -r requirements.txt
```

## The steps, in order

| # | Step | Script | What it does |
|---|---|---|---|
| 1 | Choose photos | `build_nep_manifest.py` | Builds the North Ecliptic Pole daily sample and adds it to `manifest_all.csv` (the other patches are already listed) |
| 2 | Download | `download_spherex.py` | Downloads every photo in `manifest_all.csv` (`check`, `test`, `all`) |
| 3 | Verify | `verify_spherex.py` | Checks each file against the list: complete FITS, photo ID, detector, start time, quality flag |
| 4 | Crop | `crop_spherex.py` | Cuts our square out of each full photo (1.42x bigger, so it survives rotation) |
| 5 | Clean | `clean_spherex.py` | Removes the zodiacal dust glow, marks bad pixels, adds a signal-to-noise layer |
| 6 | Align | `align_spherex.py` | Rotates every photo north-up onto a shared sky grid, in time order |
| 7 | Difference | `diff_spherex.py` | Fixed patches only: photo minus the "empty sky" of its detector, so stars cancel and movers remain |
| 8 | Known objects | `labels_spherex.py` → `labels_moving.py` → `labels_confirm.py` | NASA JPL's predicted position of every known asteroid in every photo. Run `labels_confirm.py` last |
| 9 | Star shapes | `psf_info_spherex.py` | Which star-shape (PSF) model each photo has |
| 10 | Package for the detector | `package_handoff.py` | Zips the aligned photos and tables for the detector. Stops if anything about the 3I/ATLAS answer key would enter the package |
| 11 | Reference data | `fetch_v02.py`, `fetch_comets.py` | Orbits (JPL Small-Body Database), true positions (JPL Horizons), the comet list, the Yale Bright Star Catalogue |
| 12 | Website pictures | `build_previews.py` | Photo previews, thumbnails, colour composites, `timeline.json`, `markers.json` per patch |
| 13 | Website 3D files | `build_v02.py` | `objects.csv`, `orbits.json`, `reference_positions.json`, `pointings.json`, `cosmos.json` |
| 14 | Merge tracks | `merge_detections.py` | Takes the tracks from [`../linking`](../linking), matches them to known objects, writes `detections.json` and `scoring.json` |
| 15 | Website pack | `package_frontend.py` | Zips the data pack with checksums |

The detector ([`../detector`](../detector)) runs between steps 10 and 14. The linking step ([`../linking`](../linking)) turns its spots into tracks.

## The five patches

| Patch | What it is | Photos | Observed | Bursts |
|---|---|---|---|---|
| `ecliptic-virgo` | Fixed 1° window on the ecliptic, where asteroids travel | 341 | May–Jun 2025, Dec 2025, May–Jun 2026 | 64 |
| `ecliptic-ra90` | Fixed 1° window on the ecliptic, inside the Milky Way | 218 | Sep 2025, Mar 2026 | 38 |
| `nep-cats-eye` | Fixed 0.5° window at the North Ecliptic Pole. No known object crosses it: the false-alarm test | 306 | daily, Jul 1–Aug 30 2026 | 159 |
| `ceres` | 0.5° square that follows dwarf planet Ceres | 277 | Jun–Jul 2025, Dec 2025–Jan 2026 | 50 |
| `3i-atlas` | 0.6° square that follows interstellar comet 3I/ATLAS, shifted off-centre at random (seeded) so the comet is not always in the middle | 259 | Aug 2025, Dec 2025 | 46 |
| **Total** | | **1,401** | | |

How they were chosen:
- **Fixed patches:** every QR2 + QR3 photo whose footprint contains the patch centre.
- **Ceres:** for every photo taken during Ceres's two visits, Ceres's position at that photo's exact mid-time (JPL Horizons); the photo is kept only if Ceres falls inside it.
- **3I/ATLAS:** IRSA's official list of every SPHEREx photo of the comet.
- **North Ecliptic Pole:** SPHEREx photographs this spot about 57 times a day. For each day and detector we kept the one photo where our square sits most centrally (quality flag 0, at most 5% damaged pixels). `build_nep_manifest.py` makes this choice; a second, independent check picked the same 306 photos.

## Files in this folder

| File | What it is |
|---|---|
| `manifest_all.csv` | One row per photo (1,401): patch, photo ID, detector, time, wavelength range, centre, IRSA download link, quality |
| `patches.csv` | The five patches: where each is and its job |
| `requirements.txt` | Python packages |

## Checks

| Check | Result |
|---|---|
| Downloads | **1,401 / 1,401**, 0 failed |
| Every file verified | **1,401 / 1,401** complete; photo ID, detector, start time and quality flag match the list |
| Sky-position quality flag | all 1,401 good |
| Damaged pixels (cosmic rays, satellites) | 1,394 ok, 7 flagged (5–10% of pixels), kept |
| Ceres positions vs JPL Horizons at 141 exact times | worst difference **0.09″** |
| Stars on the same pixel across frames, visits up to 13 months apart | median scatter **0.06–0.07 px** |
| Ceres vs JPL Horizons on the aligned grid (277 frames) | median 0.18 px |

## Inside every aligned photo

| Layer | What it holds | Unit |
|---|---|---|
| SCI | Cleaned brightness, dust glow removed, untrustworthy pixels = NaN | MJy/sr |
| ERR | Noise of each pixel (1 sigma) | MJy/sr |
| SNR | Significance above the sky. Above 5 = real | – |
| MASK | 1 bad · 2 suspect · 4 star/galaxy · 8 no data · 16 saturated. Values add up | – |
| WAVE | Wavelength each pixel saw | micron |
| PSF / EPSF | Star-shape model | – |

Grids: Virgo, RA 90 and the North Ecliptic Pole use one grid per patch, so any two photos compare pixel to pixel. Ceres and 3I/ATLAS use one grid per burst (photos minutes apart). The 3I/ATLAS grids never use the comet's true position.

## Good to know

1. IRSA's SPHEREx cutout service was not available, so we downloaded full photos and cropped them ourselves (same pixels).
2. Two file formats: QR2 photos have `PSF`, QR3 photos have `EPSF` and a compressed `FLAGS` layer. The scripts handle both.
3. Ceres and bright stars saturate the detector. Their cores are kept and marked MASK 16: right position, brightness is a lower limit.
4. Each detector sees a different wavelength, so a star's brightness changes from frame to frame. Compare positions, or frames from the same detector.
5. JPL's identification service returned no comets for our fields, even 3I/ATLAS, so `merge_detections.py` also checks every track against JPL's full comet list.
