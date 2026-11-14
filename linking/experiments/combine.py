"""Combine per-patch track files into one merge input (handoff/_incoming/detections.csv contract)."""
import sys, glob, os
import pandas as pd

run, out = sys.argv[1], sys.argv[2]
parts = [pd.read_csv(f) for f in sorted(glob.glob(os.path.join(run, "*_tracks.csv")))]
df = pd.concat([p for p in parts if len(p)], ignore_index=True)
df.to_csv(out, index=False)
print(out, len(df), "rows,", df.track_id.nunique(), "tracks", df.groupby("patch").track_id.nunique().to_dict())
