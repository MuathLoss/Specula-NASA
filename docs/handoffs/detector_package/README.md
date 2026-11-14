# Specula: detector data package v0.5

**From:** Muath (data) · **For:** the detector teammate
**Project:** NASA Space Apps 2026, challenge "Planet X and SPHEREx"

## What this is
Real NASA SPHEREx infrared photos of **5 small patches of sky** (1,401 photos), already cleaned and
lined up so every star sits on the same pixel in every photo of a patch. Your job: **find things that move**
(asteroids, comets).

> **Analogy:** a security camera over a car park. Parked cars = stars (never move). People walking
> through = asteroids. We already removed most parked cars for you (the difference images).

## The folder ("detector data" on Google Drive)
```
detector data/
├── README.md               ← you are here
├── CLAUDE.md               ← give this to your AI assistant first
├── DATA_DICTIONARY.md      ← every layer, column and unit
├── verify_and_unzip.py     ← step 2 below
├── checksums.sha256        ← fingerprint of every file
├── images_aligned/         ← 5 zips: the photos, one zip per patch (11.5 GB)
├── images_difference/      ← 3 zips: the same photos with the stars removed (2.9 GB)
└── tables/                 ← 22 CSVs: photo lists, known-asteroid labels, PSF info (9 MB)
```

**Using Claude?** Give it `CLAUDE.md` first. It explains everything step by step. (Claude Code reads
`CLAUDE.md` automatically when you open this folder.)

## Start in 3 steps
1. **Download the whole `detector data` folder** to your PC (~14.4 GB). Keep the file names. If Google
   Drive gives you several zip parts, unzip them all into the same folder.
2. **Check and unzip** in the top folder (where this README is; needs ~15 GB more free disk):
   ```
   python verify_and_unzip.py
   ```
   It fingerprints every file, stops if anything is damaged, then unzips. After "Done" you may delete the `.zip` files.
3. **Open your first frame:** `data/diff/ecliptic-virgo/` (stars removed, movers left) together with
   `tables/labels_ecliptic-virgo.csv` (where known asteroids really are = your practice answer sheet).

## What's in the box
| Item | What it is | Size |
|---|---|---|
| `images_aligned/` (5 zips) | The photos, all 5 patches: brightness, noise, confidence, mask, wavelength, star shape | 11.5 GB |
| `images_difference/` (3 zips) | Difference images (photo minus "empty sky") for the 3 fixed patches | 2.9 GB |
| `tables/` | Small CSV tables: photo lists, known-asteroid labels, PSF info | 9 MB |
| `DATA_DICTIONARY.md` | Every layer, column, unit and pitfall (reference) | |
| `CLAUDE.md` | Guide for your AI assistant | |
| `verify_and_unzip.py` | Step 2 above | |
| `checksums.sha256` | Fingerprint of every file | |

## The 5 patches
| Patch | Type | Photos | Dates | Why it's here |
|---|---|---|---|---|
| ecliptic-virgo | fixed, 1.0° | 341 | May-Jun 2025, Dec 2025, May-Jun 2026 | Main asteroid hunt (302 known asteroids labelled) |
| ecliptic-ra90 | fixed, 1.0° | 218 | Sep 2025, Mar 2026 | Second hunt, inside the Milky Way (crowded) |
| nep-cats-eye | fixed, 0.5° | 306 | Daily, Jul 1-Aug 30 2026 | 0 known asteroids: anything found is new or a false alarm |
| ceres | moving, 0.5° | 277 | Jun-Jul 2025, Dec 2025-Jan 2026 | Dwarf planet Ceres: easy, bright target |
| 3i-atlas | moving, 0.6° | 259 | Aug 2025, Dec 2025 | Interstellar comet 3I/ATLAS: **scored blind** |

**Fixed** = the camera stays on one piece of sky. **Moving** = the camera follows the target, re-pointing
for each burst of photos, so those have no difference images.

**Known-asteroid labels** exist for all 5 patches. In the fixed patches they also say whether each asteroid
is visible (`seen`, `confirmed`). In ceres and 3i-atlas they give **positions only**: stars are still in those
photos, so "visible" can't be measured reliably. Ceres itself is labelled; 3I/ATLAS is not (scored blind).

## 7 things to know before you start
1. **Pixels:** 0-based, `data[y, x]` (row, column). North is up, east is left. 1 pixel = 6.15 arcsec.
2. **Asteroids are slow:** typically 0.08-0.11 pixels per minute. About 0.5-1 px within one burst (photos
   ~2 min apart), many pixels between days.
3. **Depth:** one photo shows known asteroids down to about magnitude **V 18-19**. Fainter needs several photos.
4. **Use `confirmed`, not a lone `seen`,** in the labels. A single faint "seen" is often luck.
5. **Don't throw away MASK 2 or 4 pixels.** Moving objects get flagged there.
6. **Same `grid_id` = same pixels.** In ceres/3i-atlas, compare photos inside one burst.
7. **Each photo sees a different colour** (wavelength 0.75-5.0 micron), so brightness changes between
   photos. Compare **positions**, not raw brightness.

## Not included (on purpose)
- **3I/ATLAS true positions.** Muath keeps them to score your detector blind. Don't ask for them before scoring.
- Raw, cropped and cleaned intermediate stages (not needed for detection).

## What we need back (draft, agree with Muath)
One CSV, `detections.csv`, one row per detection per photo:
`patch, frame, file, x, y, snr, track_id, is_target`
(`track_id` links detections of the same object; `is_target` = 1 if you think it's Ceres or 3I/ATLAS.)
Muath matches it against the known-asteroid list (known vs new candidate) and scores 3I/ATLAS.

**Questions:** ask Muath.
