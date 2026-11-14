"""Per-patch evidence cut, chosen from scramble (noise) trials only - no answer key.

For each patch: candidate cuts (min bursts, max RMS). A cut is allowed if, summed over all noise trials, at most
MAX_NOISE tracks pass it (i.e. < 1 expected false track per run). Among allowed cuts, pick the one keeping the most
tracks in the real run (ties: fewer bursts required, then looser RMS). Writes the kept tracks + a report.
"""
import json, os, sys, itertools
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
REAL = {"ecliptic-virgo": "final2", "ecliptic-ra90": "final2", "nep-cats-eye": "final2", "ceres": "final2",
        "3i-atlas": "final2"}
TRIALS = {"3i-atlas": ["v2rot1", "v2rot2", "v2rot3"],
          "ceres": ["v2rot1", "v2rot2", "v2rot3", "v2rot4", "v2rot5"],
          "ecliptic-virgo": ["rot1", "rot2", "rot3", "rot4", "rot5", "v2rot4", "v2rot5"],
          "ecliptic-ra90": ["rot1", "rot2", "rot3", "rot4", "rot5", "v2rot4", "v2rot5"],
          "nep-cats-eye": ["v2rot4", "v2rot5"]}
MAX_NOISE = 1
CUTS = [(mb, r) for mb in (4, 5, 6, 7, 8) for r in (4.0, 3.0, 2.5, 2.0, 1.5, 1.0)]


def summ(run, patch):
    p = os.path.join(BASE, "runs", run, "%s_assoc.json" % patch)
    return json.load(open(p))["track_summary"] if os.path.exists(p) else None


out_rows, report = [], {}
for patch, run in REAL.items():
    real = summ(run, patch) or []
    trials = [t for t in (summ(r, patch) for r in TRIALS[patch]) if t is not None]
    noise = [x for t in trials for x in t]
    best = None
    for mb, r in CUTS:
        n_noise = sum(1 for x in noise if x["n_bursts"] >= mb and x["rms_arcsec"] <= r)
        if n_noise > MAX_NOISE:
            continue
        keep = [x for x in real if x["n_bursts"] >= mb and x["rms_arcsec"] <= r]
        key = (len(keep), -mb, r)
        if best is None or key > best[0]:
            best = (key, mb, r, n_noise, keep)
    _, mb, r, n_noise, keep = best
    report[patch] = {"noise_trials": len(trials), "noise_tracks_total": len(noise),
                     "cut_min_bursts": mb, "cut_max_rms_arcsec": r,
                     "noise_tracks_passing_cut": n_noise,
                     "expected_false_tracks_per_run": round(n_noise / max(1, len(trials)), 2),
                     "real_tracks_before_cut": len(real), "real_tracks_kept": len(keep),
                     "kept": [k["track_id"] for k in keep]}
    tr = pd.read_csv(os.path.join(BASE, "runs", run, "%s_tracks.csv" % patch))
    out_rows.append(tr[tr.track_id.isin(report[patch]["kept"])])
os.makedirs(os.path.join(BASE, "runs", "release"), exist_ok=True)
pd.concat(out_rows, ignore_index=True).to_csv(os.path.join(BASE, "runs", "release", "detections.csv"), index=False)
json.dump(report, open(os.path.join(BASE, "runs", "release", "calibration_report.json"), "w"), indent=1)
print(json.dumps({p: {k: v for k, v in d.items() if k != "kept"} for p, d in report.items()}, indent=1))
