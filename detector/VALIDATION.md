# Validation record

## Software checks

30 regression tests passed with Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0,
Astropy 8.0.2 and Matplotlib 3.10.8. The runtime records its actual versions in every
new `handoff.json`; `requirements.txt` declares minimum dependencies, not a lockfile.

Covered behavior: complete-operator covariance and aperture variance; compact-kernel
symmetry, mass and mask exclusion; competing associations; missing third-epoch
coverage; RA wrap; time/leverage limits; registration, wavelength and quality
rejection; joint triplet wavelength/mask checks; selected middle-frame inclusion;
exact input-byte preservation; overwrite protection; truthful partial/empty handoff.
Numerical fixtures are unit tests, not synthetic astronomical validation claims.

## Real observations processed locally

The complete new select/package/process/handoff workflow ran on the provided NEP
control observations. Of four time-compatible triples, it selected D2 frames
9 / 41 / 51. Shared valid, wavelength-compatible coverage with 7x7 neighborhoods
was **36.6993%**, confirmed at stride 1; the largest connected region was 21,427 pixels.
The endpoint comparison 9 / 51 completed with **56.6798%** usable area. It produced
73 negative and 78 positive residuals, with zero eligible residuals and zero passing
pairs. Consequently no candidate-level third-epoch match was attempted. This is a
successful pipeline/no-candidate test, not evidence of real moving-object recovery.

Endpoint SHA-256:
- Frame 9: `daa34c41ead18eb71155b27ad30289fd3064ecaff34dbe60433fdb6dde529c16`
- Frame 51: `1e2304211547555a5c9ad9f97a488f8fb59f59cedde0f296b025179942f0fe2a`

The four-frame RA90 input sample yielded **zero time-compatible triplets** under the
same model constraints. The workflow wrote a no-suitable-triplet handoff and returned
exit code 2, without fabricating observations or relaxing gates.

## Earlier real RA90 results supplied by the user

The uploaded `ra90_results_clean.zip` established:

| Pair | Usable area | Eligible two-epoch hypotheses | Third-epoch outcome |
| --- | ---: | ---: | --- |
| 111 / 177 | 43.1582% | 17 | 9 extra frames registered; 5 hypotheses tested without support, 12 unavailable |
| 78 / 109 | 33.7556% | 8 | 8 extra frames registered; all 8 hypotheses unavailable |

For 111/177, unavailable candidate/frame checks consisted of 91 wavelength mismatches
and 57 masked neighborhoods; five checks were usable but unsupported. For 78/109,
38 checks failed wavelength compatibility and 26 had masked neighborhoods. These
counts describe checks, not independent astronomical objects.

The updated joint selector addresses input coverage before subtraction. It has not
yet been run on the user's full RA90 image collection in this workspace. The four
uploaded sample images and result catalogs do not substitute for that full collection.

## Earlier masking regression evidence

Bounded-tail smoothing increased usable area on the same real comparisons:

| Pair | Previous area | Revised area | Revised two-epoch passing pairs |
| --- | ---: | ---: | ---: |
| RA90 111 / 177 | 33.73% | 43.16% | 0 |
| RA90 78 / 109 | 29.43% | 33.76% | 0 |
| NEP 1 / 51 | 40.28% | 49.38% | 0 |
| NEP 9 / 41 | 48.30% | 57.46% | 0 |
| Virgo 69 / 147 | 12.99% | 15.67% | rejected below the 20% quality threshold |
| Virgo 239 / 337 | 28.08% | 32.99% | 1 unconfirmed review candidate |

The Virgo candidate was absent under the previous mask footprint; it is not a known
positive and has no established identity. More usable area does not alone establish
better scientific detection accuracy.

## Completion boundary

Implemented and exercised: real FITS input handling, joint triplet selection,
registered endpoint comparison, uncertainty propagation, conservative verification
logic, explicit partial/no-data statuses, reproducible outputs and clean packaging.

Not established: a third-epoch-supported real moving object, an orbit or identity,
calibrated completeness/false-positive rates, or a successful full-RA90 triplet run.
The next full-data command is documented in README; its result must be assessed
before claiming scientific validation. No detections are manufactured to make the
project appear complete.

## Independent-frame Ceres audit added

The source-export/audit command was exercised on the two original Ceres FITS images
available locally: frames 133 and 135. Source detection ran without label access and
exported 99 measurements (53 and 46). The later reference comparison found one
saturated positional match to Ceres in each frame. These are not confirmed tracks,
unsaturated recovery successes, or a full 277-frame validation. The source catalog
contains 79 unsaturated measurements, 18 quality-flagged measurements and two
saturated positional measurements; the counts do not assign astronomical identities.

Five additional tests cover unconfirmed unique matches, reference/source saturation,
no-match and multiple-match outcomes, reference metadata/WCS checks, and source
exports without reference identities.


## Full five-patch source export

The original five aligned archives, five full frame tables and Ceres labels were
downloaded from the supplied Drive folder and matched the dataset SHA-256 checksums.
All 1,401 listed frames completed with zero frame errors. All 36 code tests passed.
Independent frames were processed in parallel with the same detection rules and settings: SNR 5,
maximum 100,000 peaks per frame, no detection-label access. Ceres reference auditing
was performed only after its independent source measurements were written.

| Patch | Completed frames | Source measurements |
| --- | ---: | ---: |
| ceres | 277 | 49,827 |
| 3i-atlas | 259 | 218,055 |
| ecliptic-ra90 | 218 | 1,151,444 |
| ecliptic-virgo | 341 | 355,406 |
| nep-cats-eye | 306 | 136,811 |

Total: **1,911,543 measurements**. CSV chunk rows were compared against the full
per-patch outputs, with exact field equality, unique source IDs and matching hashes.
No rows were sampled or silently dropped. The original 5,000-peak cap rejected dense
RA90 frames; the complete run uses 100,000 without changing SNR or quality gates.
Spatial indexing preserves the original duplicate-distance rule; 2,955 measurements
on an original ATLAS frame were exactly equal before and after this optimization.
Completed earlier frame measurements were reused only after original input-hash
verification; execution_details.json records this provenance. Runtime versions and code/input hashes
are recorded in the included reports. This source export does not rerun the separate
triplet/subtraction search and establishes no new confirmed objects or motion tracks.
Earlier validation sections remain records of their specific earlier runs.

Ceres has 49,827 measurements in this run, versus 49,826 in the earlier
user-provided run. The one-row difference is in frame 208 and was already present
before the spatial-index change. The Ceres reference-match category counts are
unchanged. Use this run as one consistent catalog; its dependency versions are
recorded rather than assuming bitwise equivalence across environments.
