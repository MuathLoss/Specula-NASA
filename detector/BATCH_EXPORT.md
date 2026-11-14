# Run all five patches and commit the source catalogs

This workflow processes every frame listed in each requested patch's full frame table.
It does not run the separate pair/triplet moving-object search. Every output row is a
source measurement, not a confirmed object or track. No detection labels are required.

## Input folder

Create one root with `images_aligned/` and `tables/` directories. Keep images zipped.
Put exactly one aligned archive per patch in `images_aligned`:
- aligned_ceres.zip
- aligned_3i-atlas.zip
- aligned_ecliptic-ra90.zip
- aligned_ecliptic-virgo.zip
- aligned_nep-cats-eye.zip

Existing names with a suffix, such as aligned_ecliptic-ra90-007.zip, are supported.
Do not keep duplicate copies of the same image in multiple indexed archives.
The aligned archives must contain FITS files, not further nested ZIPs. Copy the
full frames_ceres.csv, frames_3i-atlas.csv, frames_ecliptic-ra90.csv,
frames_ecliptic-virgo.csv and frames_nep-cats-eye.csv into `tables/`.
PSF metadata and label files are not needed for this source-export mode.
For an optional separate Ceres reference audit, include tables/labels_ceres.csv
and pass --audit-ceres. Detection still never reads that label table.

## Run from the repository root

Install requirements in your chosen Python 3.12 environment, then:

```bat
python detector\export_all.py --root "C:\path\to\all_data" --out "detector\runs\all_sources" --bundle "detector\exports\all_sources" --max-sources-per-frame 100000 --audit-ceres
```

Both output directories must be new and in separate trees. Raw images are unchanged.
The default patches are all five above. To run a subset, explicitly pass, for example,
`--patches ceres nep-cats-eye`. A source cap of 5000 per frame is the default; exceeding
it is reported as a frame failure, never silently truncates the catalog.

Input checking fails before processing if any requested table/image is absent.
Per-patch failures are reported and the batch continues to the remaining patches.
The final complete flag is true only when every requested patch completed without
frame or audit errors. An interrupted run is not resumable in place; keep its partial
outputs, then use new output names for a retry or a requested subset.

## Files to push

Push `detector/exports/all_sources/`, not `detector/runs/` or input archives.
The export contains all source rows, split into numbered CSV files at most 10 MiB
per file, plus frame reports, summaries, a README and an optional Ceres audit CSV.
Every chunk repeats the CSV header. There is no sample truncation.
Read ALL measured_sources_*.csv parts for a patch. The summary records chunk counts,
byte sizes and SHA-256 hashes, runtime dependencies, code hashes and input table hashes.
Combine the batch identity and source_id when storing measurements from multiple runs.

Check `detector/exports/all_sources/batch_summary.json` before staging: complete must
be true for a complete-all-data claim. Check the staged paths and size before pushing.
CSV chunking bounds individual files, not total repository growth; retain only the
intended publication run in Git rather than committing every repeated experiment.

```bat
git add detector\audit_recovery.py detector\export_all.py detector\tests\test_export_all.py detector\BATCH_EXPORT.md detector\exports\all_sources
git diff --cached --stat
git status
git commit -m "Export measured sources from all five real-data patches"
git push -u origin HEAD
```

Use a feature branch for review. These commands do not stage the raw FITS, input ZIPs,
virtual environments, or per-frame diagnostic catalogs. If a team-level ignore rule
excludes the exports directory, inspect that rule rather than force-adding all outputs.
Source catalogs can be shared with teammates for display, matching and association;
scientific identity/motion confirmation remains separate.

## Checks for this addition

34 regression tests passed. A real two-frame Ceres ZIP batch completed and its
commit bundle preserved all 99 measured-source rows and unique source IDs. This
validates the batch/export mechanism on that sample, not a full five-patch run.


The bundled full-data results now supersede the sample-only completion limit above;
see the appended full-run section in VALIDATION.md.
