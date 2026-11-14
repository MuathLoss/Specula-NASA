# Real source catalog export

Every row is one source measurement, not a distinct object or confirmed moving track.
Read batch_summary.json first: complete=false means at least one patch was incomplete.
Each patch has measured_sources_0001.csv and further numbered parts when needed.
Read ALL parts; each has the same header. CSV chunks are at most 10 MiB each.
Join records within this batch using source_id; use a run ID as well across batches.
Preserve quality_flags and measurement_status, including saturated measurements.
Times are MJD days, sky positions degrees, wavelengths micrometres, and x/y are
zero-based FITS pixel coordinates. Signal-to-noise is not probability or photometry.
Optional recovery_matches.csv is a separate positional reference audit, not identity
confirmation. Its confirmed field remains false. Frame reports preserve input hashes.
Raw FITS, archive inputs, per-frame catalogs and environments are intentionally absent.
Source extraction does not perform the separate triplet/subtraction or track search.
