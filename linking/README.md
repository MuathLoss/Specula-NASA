# Linking: from spots to moving objects

The detector ([`../detector`](../detector)) lists every bright spot in every photo: 1.9 million of them. Almost all are stars. This step finds the few spots that move in a straight line across several visits, and proves those lines are not chance.

Think of a car park filmed once an hour. Parked cars sit in the same place in every frame, so we remove them first. A person walking through shows up at a new place each time, and the places line up along their path. That line is a track.

No answer key is read here: no labels, no markers, no orbits, no target positions.

## Steps

| # | Step | How |
|---|---|---|
| 1 | Remove stars | A spot is a star if another spot sits within 9″ of it in at least min(4, 10% of covering bursts) other bursts taken well apart in time (more than 2 days for fixed patches, more than 0.08 days for patches that follow a target) |
| 2 | Group each burst | A burst is a few photos taken minutes apart. Spots that agree within 15″ in at least 2 photos of one burst become one burst detection |
| 3 | Link bursts | Pairs of burst detections 0.5–50 h apart define a straight-line motion (1–300″ per hour). Other bursts that fall on that line join it. A track needs at least 4 bursts and a scatter (RMS) of at most 4″ |
| 4 | Remove ghosts | Tracks right next to a very bright moving object (S/N ≥ 150, within 0.5°) are its reflections and are dropped |
| 5 | Noise test | The same steps run on scrambled data: each burst is rotated by a random angle, so real motion can't survive. Any track found there is a chance alignment |
| 6 | Evidence bar | `calibrate.py` picks, per patch, the strictest bar the scrambled runs need: at most 1 chance track across all noise trials together. It uses scrambled runs only, never the answer key |

## A fair test

- The settings were **locked before any 3I/ATLAS run**. `FROZEN_assoc_sha256_v2.txt` holds the fingerprint (sha256) of the locked code, saved as `assoc_frozen_v2.py`. Anyone can check it: `sha256sum assoc_frozen_v2.py`.
- One fix was made between the first lock (`FROZEN_assoc_sha256.txt`) and the second, still before any 3I/ATLAS scoring: a timing limit (0.25 → 0.08 days), checked on Ceres, and faster linking with identical results.
- **Added after the lock:** the per-patch evidence bar (`calibrate.py`). We added it because the locked settings alone left chance tracks in the 3I/ATLAS patch (41 tracks, 2 of them the comet). The bar comes from scrambled data only. For 3I/ATLAS it is at least 6 bursts and RMS at most 3″, and it leaves one track: the comet, 50 out of 50 points on target. `3i_blind_score.json` (before the bar) and `3i_release_score.json` (after) show both.

## Files

| File | What it is |
|---|---|
| `assoc_frozen_v2.py` | The locked linking code used for the results |
| `assoc.py` | The same code plus two experimental filters we tried after the lock (`INTRA_CHECK`, `REQUIRE_TESTED`). Both are off by default and were not used for the results |
| `calibrate.py` | Chooses each patch's evidence bar from the noise trials, writes `release/detections.csv` |
| `evaluate.py` | Scores tracks against known asteroids (NASA JPL positions), on the tuning patches |
| `score_3i.py` | Scores the 3I/ATLAS patch against the answer key. Run only after the locked run |
| `calibration_report.json` | Per patch: noise trials, chance tracks, the chosen bar, tracks kept |
| `3i_blind_score.json`, `3i_release_score.json` | 3I/ATLAS before and after the evidence bar |
| `FROZEN_assoc_sha256*.txt` | Fingerprints of the locked code |

## Run

```bash
# real run (EXP = the detector's exports/all_sources folder, DATA = ../pipeline/data)
python assoc_frozen_v2.py --exp EXP --data DATA --out final2 \
  --patches ecliptic-virgo ecliptic-ra90 nep-cats-eye ceres 3i-atlas

# noise trials: same command, scrambled, one folder per seed (calibrate.py lists the folder names)
python assoc_frozen_v2.py --exp EXP --data DATA --out v2rot1 --patches 3i-atlas --set SCRAMBLE=true SEED=1

# evidence bar per patch, then merge for the website
python calibrate.py
cd ../pipeline && python merge_detections.py --input ../linking/release/detections.csv
```

`calibrate.py` reads its run folders from this folder (`final2`, `rot1`…`rot5`, `v2rot1`…`v2rot5`). Those run outputs are not stored in the repo.
