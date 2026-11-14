> Detector code by Omar Teskyeh. The full source exports it produced (about 600 MB of CSV) are not stored in this repo;
> `export_all.py` rebuilds them from the aligned SPHEREx frames (see `BATCH_EXPORT.md`).

# Reverse MOST detector  repository-ready research pipeline

Select three real observations together, subtract the endpoint images, and check
eligible motion hypotheses against an independent middle epoch. No mock observations,
labels, target positions or ephemerides enter the scientific pipeline. Unit tests use
controlled fixtures only to test numerical and program logic.

This is a tested software handoff, not a confirmed-object catalog or a calibrated
survey. Read `VALIDATION.md` for results and remaining scientific limits.

## Ceres: independent-frame export and recovery audit

For the Ceres dataset, start here instead of joint triplet selection. The supplied
reference table flags Ceres as saturated in 242 of 277 frames; 31 other positions are
in-data and not saturated, while four are outside/bad. These are reference-table
properties, not detection results. Its 50 grids move across the sky, so a common-sky
triplet is not required for this audit.

After the usual Python 3.12 environment setup below, run:

```bat
.venv\Scripts\python.exe audit_recovery.py --root "C:\path\to\ceres_test" --out "runs\ceres_recovery" --patch ceres --max-sources-per-frame 5000
```

The root needs `aligned_ceres.zip` (or extracted original aligned images),
`tables/frames_ceres.csv`, and `tables/labels_ceres.csv`. No new observations or PSF
metadata are required by this command. All frames in the frame table are attempted;
progress and errors are reported for each. Keep the ZIP's original filename.

`audit_recovery.py` writes all source catalogs **before opening the label table**.
It then compares those fixed measurements to reference positions using a 2-pixel
radius, checking file/frame/detector/time and WCS consistency. Multiple matches and
shared-source associations remain ambiguous. No forced measurement at a reference
position is performed. The target defaults to the exact table name
`1 Ceres (A801 AA)`; `--object-name` selects a different reference object for evaluation,
never for source detection.

Outputs:
- **`measured_sources.csv`**: teammate integration catalog: run-specific source IDs, RA/Dec,
  pixel coordinates, times, significance, centroid uncertainty, wavelength, mask and
  quality flags. Every row is an unidentified measured source, not a moving track.
- `catalogs/`: full per-frame measurements and WCS metadata, independent of labels.
- `frame_report.json`: per-frame status, errors, source counts and input SHA-256.
- **`recovery_summary.json`**: frame/source counts and reference-match categories.
- `recovery_matches.csv` / `.json`: separate positional reference audit with offsets,
  ambiguity, quality and saturation categories. `confirmed` remains false.

A saturated positional match can support review, but its centroid is approximate and
its photometry is unreliable. An unsaturated positional match also does not establish
an orbit, independent identity, motion track, or calibrated recovery probability.
Missing/failed frames and invalid reference rows are not counted as ordinary misses.
If the label table is missing, the source export is retained and the audit failure is
reported. Supply a new output directory on reruns; existing results are not overwritten.

Commit `audit_recovery.py` and `tests/test_recovery.py` along with the other source
files. Share the bounded CSV parts under `exports/all_sources/` with the next teammate. This supports
source display/crossmatching/review; it does not yet provide confirmed motion tracks.

## Install and run (Windows CMD, Python 3.12)

Extract the package into a **fresh** `reverse_most_ready` folder. Do not merge old
project files into it. Inside that folder run:

```bat
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe tests\run_tests.py
.venv\Scripts\python.exe run_real.py --root "C:\path\to\full_dataset" --out "runs\ra90_triplets" --patches ecliptic-ra90
```

No activation or PATH change is needed. Use a new output name for another run.
This one command selects and packages real triplets, extracts them, runs the endpoint
comparisons and third-epoch checks, and writes `handoff.json`. Do not use the old
four-frame `ra90_inputs_better` as the full dataset: it contains no eligible triplet.

The full root must contain:
- `tables/frames_ecliptic-ra90.csv` listing the full available observations.
- `tables/psf_info.csv` with one metadata row per available image.
- `data/aligned/ecliptic-ra90/<filename>.fits`, or aligned ZIP archives accessible
  under the root, its `images_aligned` directory, or the root's parent.

The selector copies original image bytes, including PSF layers; it does not edit
observations. Archives must have unambiguous FITS basenames. Keep input data outside
the code folder. The default search evaluates at most 2,000 time-compatible triplets,
ranks qualifying triplets by full-resolution shared coverage, and selects up to three
disjoint triplets per patch. Progress is printed every 50 triplets. The audit records
budget limits, missing data, every evaluated combination, and partial selections.
A bounded search is not an exhaustive statement that no other triplet exists.

Optional arguments:

```bat
.venv\Scripts\python.exe run_real.py --root "C:\path\to\full_dataset" --out "runs\multi_patch" --patches ecliptic-ra90 nep-cats-eye --max-triplets 5000 --triplets-per-patch 3 --max-sources-per-frame 5000
```

Increase the search budget only when the selection report says the budget was
exhausted. Do not lower source-quality or wavelength gates just to obtain a result.
The source cap is a fail-safe: exceeding it rejects that measurement rather than
silently truncating its source list.

## What changed

- Three observations are selected jointly by detector, timing, clear 7x7 pixel
  neighborhoods, and local wavelength agreement across all three images.
- Shared coverage is confirmed at full resolution. The default requires at least
  10% of the first frame's grid and a connected region of at least 25 pixels.
  This selection threshold is separate from the unchanged 20% pair-processing
  usable-area gate. Shared sky coverage is a proxy; moving candidates can still
  leave that region, so their actual predicted positions are checked separately.
- Symmetric smoothing tails are bounded to at most 0.1% removed kernel mass.
  Images and covariance propagation use the same retained, normalized operator.
  All retained support must be valid; bad/saturated pixels are never filled in.
- Third-epoch matching preserves conflicts, quality flags and missing-coverage
  reasons. Multiple matches are not greedily reduced to a single winner.
- `partial_verification_no_support` distinguishes mixed tested/unavailable
  hypotheses from a comparison where all eligible hypotheses were tested.
- One command and a compact machine-readable handoff replace manual packaging steps.

## Third-epoch model and limits

The short-arc constant-angular-speed model interpolates only: a baseline no longer
than 14 days, middle time between 15% and 85% of that baseline, and at least one hour
between adjacent selected observations. Prediction must be more than 10 arcsec from
both endpoints. A third source must be within 5 arcsec of the prediction, pass native
quality gates, and agree with both endpoint wavelengths within 1%. Reference-star
counterparts are excluded. Registration uses real reference stars; complete valid
7x7 neighborhoods are required on the approximately 6.15 arcsec/pixel images.
These conservative settings are explicit MVP limits, not an orbital fit or measured
survey completeness. A missing third-epoch match does not rule out a real object.

The source PSF matching and calibration errors remain approximate. Upstream aligned
image covariance is unavailable. Scores are not probabilities. No external object
identity, orbit, recovery rate or calibrated chance-association rate is produced.

## Outputs and team contract

Start with `runs/<run>/handoff.json`. It contains schema version, input mode, exact
runtime dependency versions, settings, completion/error counts, candidate counts,
and report paths. `confirmation_performed` is always false: do not present the
software as confirming an object. `selection_complete` means all requested triplet
counts were met; `every_patch_has_a_triplet` is the weaker coverage condition.

- `selection.json`: complete joint-selection audit, including any search limit.
- `selected_inputs.zip`, `inputs/`: the exact selected original observations and tables.
- `results/summary.json`: every selected endpoint comparison, including failures.
- Per-comparison `run_report.json`: SHA-256 input hashes, registration, PSF assumptions,
  mask fractions, noise treatment, selection provenance and verification outcome.
- `verification_report.json`: extra frames considered, original candidate flags,
  match offsets, exclusions, missing data, and supporting-frame hashes.
- `candidates.json` / `.csv`: every proposed endpoint association and its flags.
- `two_epoch_candidates.json`: candidates passing only two-epoch gates; unconfirmed.
- `third_epoch_supported_review.json`: uniquely supported among the tested hypotheses;
  review evidence, not confirmed objects. Untested competitors prevent this status.
- `detections.csv`: compatibility export of two-epoch endpoints, with `is_target=0`;
  downstream consumers must not treat it as the confirmed-object list.
- Comparison FITS, diagnostic PNGs and residual/source catalogs: review evidence.
- `saturated_positional_review.json`: separate approximate saturated-source review;
  never a passing difference detection.
- `failure.json`: top-level errors, if the workflow cannot complete.

Pair results distinguish `quality_rejected`, `processing_error`,
`no_eligible_residuals`, `no_viable_pair`, `needs_third_epoch`, and
`two_epoch_candidate_requires_verification`.

Verification results distinguish `no_eligible_two_epoch_hypotheses`,
`no_usable_verification_epoch`, `tested_no_support`, `partial_verification_no_support`,
`ambiguous_after_verification`, `third_epoch_supported_review`, and `verification_error`.
Per-candidate `supported_but_competitors_unchecked` explicitly preserves ambiguity.

Exit codes: 0 = workflow ran; inspect scientific outcomes, 1 = processing/verification
error, 2 = no suitable triplet selected. A completed run need not contain a detection.


## Reuse older selected-pair inputs

`run_selected_pairs.py --root <prepared-inputs> --out <new-results>` still accepts
`INPUT_SELECTION_REPORT.json` from earlier pairs. Use `--verification-root` to search
an additional extracted dataset. For new work, prefer `run_real.py` joint selection.
The old `prepare_real_validation.py` pair selector, demos, tracking prototypes,
previous reports and old results are intentionally absent from this clean package.
