# Rebuild everything from NASA's data

This guide takes you from nothing to the same photos, the same 1.9 million spots, the same tracks and the same website data we used. Every photo comes straight from NASA, and every known-object position from NASA JPL.

Each step says what to run, how long it takes, and what you should see when it worked.

## What you need

| | |
|---|---|
| **Disk** | About **160 GB** free (raw photos 99.2 GB, then about 33 GB of intermediate files and 14 GB of packages) |
| **Python** | 3.11 or newer (the detector was tested on 3.12) |
| **Node.js** | 20 or newer (only for the website) |
| **Internet** | NASA's Amazon mirror of the SPHEREx archive, NASA/IPAC IRSA, and NASA JPL's APIs |

```bash
git clone https://github.com/MuathLoss/Specula-NASA
cd Specula-NASA
pip install -r pipeline/requirements.txt -r detector/requirements.txt
```

Commands below use `python`. On some systems it is `python3`. Unless a step says otherwise, run it **inside `pipeline/`**:

```bash
cd pipeline
```

---

## Step 1. Download the 1,401 photos

The full list is already in `manifest_all.csv`: one row per photo, with its NASA download link.

```bash
python download_spherex.py check                  # can we reach NASA? how fast? is there enough disk?
python download_spherex.py test --mode full       # downloads 1 photo per patch and shows what is inside
python download_spherex.py all --mode full        # downloads all 1,401 full photos (99.2 GB)
```

- Photos come from **NASA's Amazon mirror** by default. Add `--source irsa` to download from IRSA instead.
- You can stop it at any time and run the same command again: finished files are skipped.
- Output: `data/raw/full/<patch>/<photo>_<detector>.fits`

> We download the **full** photos and cut our squares ourselves in step 3, because IRSA's cutout service was not available when we built this. The pixels are the same.

## Step 2. Check every file

```bash
python verify_spherex.py
```

**You should see 1,401 / 1,401 ok.** Each file is checked to be complete (its size matches its layers) and to be the right photo (photo ID, detector, start time and sky-position quality match the list). Details go to `verify_report.csv`.

## Step 3. Crop, clean and align

```bash
python crop_spherex.py      # cut our square out of each photo        -> data/cut/      (15 GB)
python clean_spherex.py     # remove the dust glow, mark bad pixels  -> data/clean/    (18 GB)
python align_spherex.py     # north up, shared sky grid, time order  -> data/aligned/  (11 GB)
```

**You should see 1,401 files at each stage** and 0 failed (see `crop_log.csv` and `clean_log.csv`). Each script skips files it already made; add `--redo` to rebuild them.

After this step you can delete `data/cut/` and `data/clean/` (33 GB) if you need the space. Nothing later reads them.

## Step 4. Difference images and star shapes

```bash
python diff_spherex.py      # fixed patches only: photo minus "empty sky" -> data/diff/  (2.8 GB)
python psf_info_spherex.py  # star-shape model of every photo            -> data/psf_info.csv
```

**You should see** difference images for `ecliptic-virgo` (341 photos), `ecliptic-ra90` (218) and `nep-cats-eye` (306), plus `static_sky_D1.fits` … `static_sky_D6.fits` in each.

## Step 5. Known-object labels (NASA JPL)

```bash
python labels_spherex.py --offline    # fixed patches
python labels_moving.py --offline     # Ceres and 3I/ATLAS patches (3I/ATLAS itself is never labelled)
python labels_confirm.py              # always last: adds the "seen in 2+ photos" column
```

`--offline` reuses the JPL answers already saved in `data/labels/<patch>/jpl_cache/`, so you get exactly our labels with no internet. Leave `--offline` out to ask JPL again.

**You should see** `data/labels/labels_all.csv` with **15,996 labels**.

## Step 6. Package the photos for the detector

`package_handoff.py` looks for its docs in `handoff_docs/`, so copy them there first:

```bash
mkdir handoff_docs
cp ../docs/handoffs/detector_package/README.md ../docs/handoffs/detector_package/CLAUDE.md \
   ../docs/handoffs/detector_package/verify_and_unzip.py ../docs/DATA_DICTIONARY.md handoff_docs/
python package_handoff.py --dry    # show the plan
python package_handoff.py          # build it
```

On Windows, use `copy` instead of `cp`, one file at a time.

**You should see** `handoff/Specula_handoff_v0.5/` with 5 `images_aligned/aligned_<patch>.zip`, 3 `images_difference/diff_<patch>.zip` and 22 tables in `tables/`. The script stops by itself if anything about the 3I/ATLAS answer key would enter the package.

## Step 7. Run the detector

From the **repository root** (`cd ..`):

```bash
python detector/export_all.py --root pipeline/handoff/Specula_handoff_v0.5 \
  --out detector/runs/rebuild --bundle detector/exports/rebuild \
  --max-sources-per-frame 100000 --audit-ceres
```

Both output folders must be new.

**You should see** `"complete": true` in `detector/exports/rebuild/batch_summary.json` and **1,911,543 spots** in total:

| Patch | Spots |
|---|---|
| ecliptic-ra90 | 1,151,444 |
| ecliptic-virgo | 355,406 |
| 3i-atlas | 218,055 |
| nep-cats-eye | 136,811 |
| ceres | 49,827 |

Compare it with our run in `detector/exports/all_sources/`.

## Step 8. Link spots into tracks

Run **inside `linking/`** (`cd linking`). `EXP` is the detector output from step 7, and `DATA` is the website data folder (linking reads each patch's `timeline.json`).

```bash
EXP=../detector/exports/rebuild
DATA=../site/public/data
P="ecliptic-virgo ecliptic-ra90 nep-cats-eye ceres 3i-atlas"

# the real run, with the locked code
python assoc_frozen_v2.py --exp $EXP --data $DATA --out runs/final2 --patches $P

# noise trials on scrambled data (seeds 1-5)
for s in 1 2 3 4 5; do
  python assoc_frozen_v2.py --exp $EXP --data $DATA --out runs/rot$s --patches ceres ecliptic-ra90 ecliptic-virgo \
    --set SCRAMBLE=true SEED=$s T_STATIC_MOVING_D=0.25
done
for s in 1 2 3; do
  python assoc_frozen_v2.py --exp $EXP --data $DATA --out runs/v2rot$s --patches 3i-atlas ceres --set SCRAMBLE=true SEED=$s
done
for s in 4 5; do
  python assoc_frozen_v2.py --exp $EXP --data $DATA --out runs/v2rot$s \
    --patches ceres ecliptic-ra90 ecliptic-virgo nep-cats-eye --set SCRAMBLE=true SEED=$s
done

# the evidence bar per patch, chosen from the noise trials only
python calibrate.py
```

On Windows, run each command on one line, typing out the patch names and seed numbers.

These commands write over our saved runs in `runs/`, so `git diff --stat runs/` shows any difference from our result. The `*_tracks.csv` and `*_bursts.csv` files should not change. Each `*_assoc.json` also records how many seconds its run took, so those files always change a little.

We checked this: with our detector output (`EXP=../detector/exports/all_sources`), these exact commands rebuild every track file byte for byte, and `calibrate.py` rebuilds `runs/release/detections.csv` byte for byte. The real run takes about 5 minutes, most of it on the 3I/ATLAS patch.

**You should see** 8 tracks in `runs/release/detections.csv`: Ceres (4 tracks), 3I/ATLAS, 20 Massalia, 232 Russia and 207 Hedda.

## Step 9. Website data and the website

```bash
cd ../pipeline
python fetch_v02.py        # JPL orbits and positions (skips what is already saved in data/v02/)
python fetch_comets.py     # JPL's current comet list (always downloads; skip it to keep ours in data/v02/comets.json)
python build_previews.py   # photo previews, colour composites, timeline.json, markers.json -> handoff/frontend_data/
python build_v02.py        # 3D files: objects, orbits, pointings, cosmos                    -> handoff/frontend_data/
python merge_detections.py --input ../linking/runs/release/detections.csv   # detections.json + scoring.json
```

`merge_detections.py` saves its progress and stops after about 150 seconds. If it prints "NOT DONE", run the same command again until it prints the summary.

**You should see** `detections.json` with 8 tracks, all known, and in `scoring.json` 3I/ATLAS found in 50 photos with 0 false points.

Optional: score the 3I/ATLAS patch against the answer key, from inside `linking/`:

```bash
cd ../linking
python score_3i.py runs/final2 .. ../pipeline
cd ../pipeline
```

(It reads our saved detector output in `detector/exports/all_sources/`.)

To view it, copy `handoff/frontend_data/` into `site/public/data/` and start the site:

```bash
cd ../site
npm ci
npm run dev        # http://localhost:3000
```

> The copy in `site/public/data/` leaves out the bookkeeping timestamps (when files were built). The website treats them as optional. Everything else is the same.

---

## Shortcuts

- **Only the website:** skip to step 9's last block. `site/public/data/` already holds our data.
- **Only the linking and scores:** our detector output is in `detector/exports/all_sources/`, so run step 8 with `EXP=../detector/exports/all_sources`. No photos needed.
- **Only the labels:** step 5 with `--offline` needs the aligned photos (steps 1–3), but no internet.
