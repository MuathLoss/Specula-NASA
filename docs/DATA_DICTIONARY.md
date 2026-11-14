# Specula data dictionary (package v0.5)

Reference for every folder, file, layer and column. Start with `README.md`; come here when you need detail.

## 1. Folder layout
As downloaded (Google Drive folder "detector data"):
```
README.md, CLAUDE.md, DATA_DICTIONARY.md, verify_and_unzip.py, checksums.sha256
images_aligned/aligned_<patch>.zip       x5, one per patch
images_difference/diff_<patch>.zip       x3, fixed patches only
tables/*.csv                             22 small tables (section 6)
```
After `python verify_and_unzip.py`:
```
data/aligned/<patch>/NNNN_<obs_id>_<detector>.fits   one file per photo, NNNN = time order (0001 = oldest)
data/aligned/<patch>/frames.csv                     list of those photos in time order
data/diff/<patch>/NNNN_<obs_id>_<detector>.fits      difference image of the same photo (fixed patches only)
data/diff/<patch>/static_sky_D1.fits ... D6.fits     the "empty sky" that was subtracted, one per detector
data/diff/<patch>/diff_frames.csv                   frames.csv + leftovers count
tables/                                             small CSVs (section 6)
```
A file in `data/diff/` has the **same name** as its photo in `data/aligned/`.

## 2. The sky grid
| Item | Value |
|---|---|
| Orientation | North up, east left (FITS `CDELT1` is negative: x to the right = RA decreasing) |
| Pixel size | 6.15 arcsec (0.0017083 deg) |
| Projection | TAN (gnomonic), ICRS. Read it with `astropy.wcs.WCS(header)` |
| Pixel numbering in our CSVs | **0-based**: `x` = column, `y` = row, so `data[round(y), round(x)]`. astropy's `world_to_pixel` gives the same 0-based numbers |
| Fixed patches | One grid per patch: ecliptic-virgo and ecliptic-ra90 585 x 585 px (1.0 deg), nep-cats-eye 293 x 293 px (0.5 deg). Any two photos of a patch line up pixel for pixel (stars scatter 0.06-0.07 px) |
| Moving patches | One grid per burst (`grid_id`): ceres 293 px (50 grids), 3i-atlas 351 px (46 grids). Same `grid_id` = same pixels |

## 3. Aligned photos: `data/aligned/<patch>/*.fits`
| Layer (EXTNAME) | Type | What it holds | Unit |
|---|---|---|---|
| `SCI` | float32 2-D | Cleaned brightness: zodiacal dust glow removed. Untrustworthy pixels = NaN | MJy/sr (header `BUNIT` reads "MJy") |
| `ERR` | float32 2-D | 1-sigma noise of each pixel | same as SCI |
| `SNR` | float32 2-D | Significance above the sky: (SCI - BKG_MED) / ERR. Above 5 = probably real | none |
| `MASK` | uint8 2-D | Bit flags, values add up (6 = 4 + 2). See section 4 | none |
| `WAVE` | float32 2-D | Wavelength each pixel saw (SPHEREx's filter changes colour across the detector) | micron |
| `PSF` or `EPSF` | see right | The shape a point of light makes. **Two formats**, see below | |

**PSF formats.** Photos up to 2026-07-19 (QR2, 1,189 photos) have `PSF`: an image cube of 121 models
(11 x 11 zones of the original detector), each 101 x 101 px, oversampled 10x (0.615 arcsec per PSF pixel).
Photos from 2026-07-20 (QR3, the last 212 NEP photos) have `EPSF`: a binary table of 441 rows
(21 x 21 zones), column `EPSF` holds a 33 x 33 model oversampled 5x. Both are in the **detector's
orientation, not north-up**. `tables/psf_info.csv` tells you which format each photo has, which model is
nearest our square (`psf_zone`), and the PSF width. In practice a star is about **1 pixel wide**
(FWHM 0.84-1.47 px, median 0.99 px).

**Useful header keys** (in every layer): `FRAME` (time-order number), `PATCH`, `OBSID`, `DETECTOR`,
`DATE-BEG`/`DATE-END` (UTC), `MJD-BEG`/`MJD-END`, `WL_UM` (wavelength at the grid centre), `GRID_ID`,
`COVERAGE` (share of the grid with data), `BKG_MED` (median sky level), `ERR_MED` (median noise).

## 4. MASK bits
| Bit | Meaning | What to do |
|---|---|---|
| 1 | Bad pixel (SCI is NaN) | Ignore |
| 2 | Suspect: cosmic ray **or a moving object** (kept) | **Keep.** Asteroids can carry this flag |
| 4 | Source: star, galaxy, **or asteroid** | **Keep.** Most labelled asteroids sit on bit 4 |
| 8 | No data (outside the photo's footprint) | Ignore |
| 16 | Saturated: too bright, position fine, brightness is a lower limit (e.g. Ceres's core) | Keep for position |
| 32 | `STAR_RESIDUE`, difference images only: a bright static star sits here, so leftovers are expected | Treat a detection here with suspicion |

Test a bit with `(mask & 2) != 0`.

## 5. Difference images: `data/diff/<patch>/*.fits` (fixed patches only)
| Layer | What it holds |
|---|---|
| `DIFF` | (SCI - BKG_MED) - static sky of this detector. Stars mostly cancel (79-89%); movers remain |
| `DIFF_ERR` | Noise of DIFF |
| `DIFF_SNR` | DIFF / DIFF_ERR. A mover shows as a positive blob, typically S/N >= 5 |
| `MASK` | Aligned MASK plus bit 32 (star residue) |

Header extras: `CONTENT` (the formula), `STATICSK` (which static sky was used), `NLEFT5` (leftover spots
with S/N >= 5 in this frame). Leftovers per frame, median: virgo 47, ra90 127, nep 17. Most are single
pixels and cosmic rays. Known artefact: virgo frame 101 (D4) has a diagonal streak.

`static_sky_D<n>.fits`: layers `STATIC` (median of all frames of that detector), `STATIC_ERR`, `NFRAMES`.

## 6. Tables
### `frames_<patch>.csv` (also inside each aligned zip as `frames.csv`)
| Column | Meaning |
|---|---|
| `frame` | Time-order number (1 = oldest), same as the file prefix |
| `patch` | Patch name |
| `t_mid_utc`, `t_mid_mjd` | Middle of the exposure (UTC; Saudi time = +3 h) and as MJD |
| `window_id` | Visit season (new window after a 30+ day gap) |
| `burst_id` | Photos taken back-to-back (~2.15 min apart) |
| `obs_id` | SPHEREx photo ID |
| `detector` | D1-D6 (see section 7) |
| `wl_um` | Wavelength at the grid centre (micron) |
| `grid_id`, `grid_ra`, `grid_dec`, `grid_px` | Which grid, its centre (deg) and size (px) |
| `coverage` | Share of the grid with data (0-1) |
| `shift_px` | Alignment check: star shift vs the grid's first good frame (should be ~0.0; blank if coverage too low) |
| `quality` | `ok` or `warn_transients` (more than 5% pixels hit by cosmic rays/satellites; 7 photos) |
| `file` | File name |

### `diff_frames_<patch>.csv`
Same columns plus `leftovers_snr5` (= header `NLEFT5`).

### `labels_<patch>.csv` and `labels_all.csv`: known asteroids (one row per object per photo)
Built from NASA JPL's catalogue (Horizons for SPHEREx's own position, sb_ident for objects down to V 21).
Fixed patches: one JPL query per 15-minute group. Moving patches (ceres, 3i-atlas): one query per burst,
**positions only**: `diff_snr_peak`, `peak_dx`, `peak_dy`, `seen`, `seen_n_group`, `confirmed` are blank
(= not measured, because stars are still in those photos), and `mask` is the aligned MASK (no bit 32).
Ceres is labelled (`1 Ceres (A801 AA)`); 3I/ATLAS is never labelled (it is scored blind).
| Column | Meaning |
|---|---|
| `frame`, `patch`, `obs_id`, `detector`, `t_mid_utc`, `t_mid_mjd`, `file` | Which photo |
| `object`, `kind` | Name (e.g. `370 Modestia (A893 NB)`) and `asteroid`/`comet` |
| `ra_deg`, `dec_deg` | Predicted sky position at this photo's time |
| `x`, `y` | Predicted pixel (0-based, float). Accuracy < 0.1 px for main-belt asteroids |
| `in_data` | 1 = that pixel has data |
| `mask` | MASK value at that pixel (diff MASK, includes 32) |
| `v_mag` | Brightness (V magnitude: bigger = fainter) |
| `ra_rate_arcsec_h`, `dec_rate_arcsec_h` | Motion on the sky (arcsec/hour) |
| `motion_px_per_min` | Total motion in pixels per minute |
| `diff_snr_peak`, `peak_dx`, `peak_dy` | Highest DIFF_SNR within +-2 px, and where (peak minus predicted, px) |
| `seen` | 1 = peak >= 5, within 1.5 px, on real data, not star residue |
| `group` | 15-minute group of photos (one JPL query) |
| `seen_n_group` | How many photos in the same group see this object |
| `confirmed` | 1 = seen and `seen_n_group` >= 2. **Use this one** (blank = not measured) |

Counts: virgo 302 objects, 8,586 rows, 214 seen, 152 confirmed. ra90 156 objects, 4,319 rows, 58 seen,
21 confirmed. NEP 0 objects (empty files with headers). ceres 25 objects, 973 rows (Ceres itself in all
277 photos; its label sits 0.10 px, median, from Ceres's measured centre). 3i-atlas 185 objects, 2,118 rows.
All labels are asteroids: JPL's identification service returned no comets for any of our fields. Single-photo detection rate by brightness:
V < 17 100%; V 17-18 51% (virgo) / 27% (ra90); V 18-19 ~7%; V 19-21 about 1%, of which most is luck
(measured chance rate 0.4-0.9%).

### `known_objects_<patch>.csv`: one row per known object
`object, kind, frames_on_grid, frames_in_data, frames_seen, v_brightest, first_utc, last_utc,
motion_px_per_min, frames_confirmed` (`frames_seen` and `frames_confirmed` blank in the moving patches).

### `psf_info.csv`: one row per photo
`patch, frame, file, detector, release (qr2/qr3), psf_layer (PSF/EPSF), psf_zone (0-based model index:
cube plane or table row), psf_fwhm_arcsec, psf_fwhm_px, crop_x0, crop_y0, det_x, det_y` (the last four:
where our square sits on the original detector, pixels).

### `manifest_all.csv`: the original photo list (one row per photo, 1,401)
Key columns: `patch, patch_type, release, obs_id, detector, burst_id, window_id, t_start_utc, t_mid_mjd,
exp_s (113.58 s), wl_min_um, wl_max_um, photo_ra, photo_dec, cutout_ra, cutout_dec, finast (0 = good),
transient_pct, quality`.

### `patches.csv`
The 5 patches: centre, size, role.

## 7. Detectors and wavelengths
Each shot uses two detectors at the same moment on the same sky: **D1+D4, D2+D5, D3+D6**. A real object
appears in both at the same time and place (if bright enough in both colours); a cosmic ray does not.
| Detector | D1 | D2 | D3 | D4 | D5 | D6 |
|---|---|---|---|---|---|---|
| Wavelength (micron) | 0.75-1.12 | 1.10-1.65 | 1.63-2.43 | 2.40-3.85 | 3.81-4.43 | 4.41-5.01 |

## 8. Patch notes
- **ecliptic-virgo** (RA 180, Dec 0): far from the Milky Way, clean sky, most asteroids.
- **ecliptic-ra90** (RA 90, Dec +23.44): exactly on the Milky Way plane. Crowded: more star leftovers, lower detection rates.
- **nep-cats-eye** (RA 270, Dec +66.56): no known asteroids brighter than V 21 crossed it (Jul-Aug 2026), so it measures your false-alarm rate. The Cat's Eye Nebula (bright, static) sits 0.16 deg from the centre.
- **ceres**: centred on Ceres per burst. Ceres is bright and saturates (MASK 16); its centre is missing in 4 frames.
- **3i-atlas**: the comet is deliberately **off-centre** (20-146 px from the centre). It is faint in Aug 2025 (especially D5-D6) and bright in Dec 2025. Scored on the 258 photos where it lands on real data.
