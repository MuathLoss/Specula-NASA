# CLAUDE.md: guide for the AI assistant helping with this data

You are helping the **detector teammate** of team Specula (NASA Space Apps 2026, challenge "Planet X and
SPHEREx"). This folder is the data package Muath (data owner) prepared. Your user
will build a **moving-object detector**: find asteroids and comets in these photos.

Read this file fully, then `README.md` (short overview) and `DATA_DICTIONARY.md` (full reference) before
answering questions. Every number here was measured on this data.

## How to help
- Explain step by step in plain language, with an analogy when something is technical.
- Before giving results, check them with numbers (counts, medians, a quick plot). Say what you checked.
- If something is unclear or missing, say so. Don't guess; ask the user to check with Muath.

## Rules (please keep them)
1. **3I/ATLAS is scored blind.** Its true positions are deliberately not in this package. Don't try to
   reconstruct them from metadata and don't ask for them before scoring. The photo centre is **not**
   the comet's position (it was shifted at random; the comet sits 20-146 px from the centre).
2. **Never edit the original files.** Write outputs to a new folder (e.g. `work/`).
3. **nep-cats-eye is the false-alarm test.** No known asteroid crossed it, so treat every detection there
   as "new or false alarm" and report how many you get.

## First session: do these in order
1. Run `python verify_and_unzip.py` in the top folder of the download (where README.md is; the data sits in
   `images_aligned/`, `images_difference/` and `tables/`). Expect "all ... files OK" and 1,401 aligned FITS
   (virgo 341, ra90 218, nep 306, 3i-atlas 259, ceres 277) and 865 difference images (virgo 341, ra90 218,
   nep 306), each fixed patch also with 6 static-sky files.
2. Install: `pip install astropy numpy pandas matplotlib`.
3. Show the user one known asteroid on screen (code below). Seeing a label sit on a blob builds trust in the data.
4. Walk the user through the 5 patches and the 7 points in README.md.
5. Agree the output format (end of this file) before writing detection code.

## The data in one minute
- 5 sky patches. **Fixed** (camera stays put): ecliptic-virgo, ecliptic-ra90 (585 x 585 px), nep-cats-eye
  (293 px). **Moving** (camera follows the target, new grid each burst): ceres (293 px), 3i-atlas (351 px).
- Every photo is north-up, 6.15 arcsec per pixel, 0-based pixels `data[y, x]`. In a fixed patch all photos
  share one grid (stars agree to 0.06-0.07 px). In a moving patch, photos with the same `grid_id` share a grid.
- Photos come in **bursts**: ~4-8 photos about 2.15 min apart, each exposure 113.58 s. Bursts are hours
  to months apart.
- Each shot uses **two detectors at once** on the same sky: D1+D4, D2+D5, D3+D6. Different colours
  (0.75-5.0 micron). Brightness changes with colour; positions don't.
- **Difference images** (`data/diff/`, fixed patches only): photo minus the median "empty sky" of that
  detector. Stars cancel 79-89%; movers remain. Leftover spots with S/N >= 5 per photo, median:
  virgo 47, ra90 127 (Milky Way, crowded), nep 17. Most leftovers are single pixels and cosmic rays.
- A star is about **1 pixel wide** (FWHM median 0.99 px). A real object is usually a small blob of a few pixels.
- **Asteroid motion:** median 0.08 px/min (virgo) and 0.11 px/min (ra90), max ~0.3 px/min. So ~0.5-1 px
  within a burst and many pixels between days.
- **Depth of one photo:** known asteroids are seen 100% at V < 17, 27-51% at V 17-18, ~7% at V 18-19,
  ~1% at V 19-21 (mostly chance). Depth improves by combining photos.
- **Labels** (`tables/labels_<patch>.csv`): known asteroids from NASA JPL with the predicted pixel in every
  photo. Fixed patches: virgo 302 objects, ra90 156, nep 0; use `confirmed == 1` as "really visible in that
  photo". Moving patches (ceres 25 objects, 3i-atlas 185): **positions only** (`seen`/`confirmed` blank, because
  stars are still in those photos). Ceres itself is labelled; 3I/ATLAS is not. Use the labels to sort your detections
  into "known" (within ~2 px of a label at that time) and "new candidate".

## Code you can start from
```python
from astropy.io import fits
from astropy.wcs import WCS
import numpy as np, pandas as pd

patch = "ecliptic-virgo"
lab = pd.read_csv("tables/labels_%s.csv" % patch)
r = lab[lab.confirmed == 1].sort_values("v_mag").iloc[0]          # brightest confirmed known asteroid

with fits.open("data/diff/%s/%s" % (patch, r.file)) as h:
    dsnr = h["DIFF_SNR"].data
    mask = h["MASK"].data
with fits.open("data/aligned/%s/%s" % (patch, r.file)) as h:
    sci = h["SCI"].data
    wcs = WCS(h["SCI"].header)

iy, ix = int(round(r.y)), int(round(r.x))
print(r.object, "V", r.v_mag, "peak S/N", dsnr[iy-2:iy+3, ix-2:ix+3].max())
x, y = wcs.world_to_pixel_values(r.ra_deg, r.dec_deg)                # same 0-based x, y as the table
```
Useful masks: `good = ~np.isnan(dsnr) & ((mask & (1 | 8)) == 0)`; star residue: `(mask & 32) != 0`.
Do **not** exclude bits 2 and 4: moving objects are often flagged there.

Photos of one burst: `frames = pd.read_csv("data/aligned/%s/frames.csv" % patch)`, then
`frames.groupby("burst_id")`. Same `grid_id` = same pixels.

## Pitfalls we already found
- A strong peak next to a predicted position can be a **star residue** that stays on the same pixel while
  the asteroid moves. Real movers shift by `motion_px_per_min` x minutes between photos.
- Faint single detections are often chance hits (~0.4-0.9% per position). Require the same object in
  2+ photos of a burst, or in both detectors of a pair.
- **Moving patches have no difference images.** Within one burst an asteroid moves only ~0.5-1 px, so a
  median of that burst would partly erase it. Prefer detecting sources in `SNR` and linking ones that
  shift consistently, or compare different bursts after reprojecting with the WCS.
- Ceres saturates (MASK 16): position is fine, brightness is a lower limit.
- The PSF layer has two formats (QR2 cube `PSF`, QR3 table `EPSF`); see `tables/psf_info.csv` and the dictionary.
- Virgo frame 101 (D4) contains a diagonal streak (satellite or artefact).

## What to send back to Muath (draft, confirm with him)
`detections.csv`, one row per detection per photo:
| Column | Meaning |
|---|---|
| `patch`, `frame`, `file` | Which photo |
| `x`, `y` | Pixel (0-based, float) |
| `snr` | Detection strength |
| `track_id` | Same number for detections you believe are the same object |
| `is_target` | 1 if you think it is Ceres or 3I/ATLAS, else 0 |

Plus a short note on the method and thresholds. Muath then marks each track as known (matches JPL) or a
new candidate, and scores 3I/ATLAS against the withheld positions (258 photos where the comet is on real
data; it is above S/N 5 in about 203 of them, so ~79% is the realistic ceiling).
