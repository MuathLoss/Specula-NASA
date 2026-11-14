"""Score the frozen association run on 3I/ATLAS (answer key = frontend addon markers). Run only after the 3I run."""
import json, glob, sys, os
import numpy as np, pandas as pd

# usage: python score_3i.py <run folder> <folder holding detector/exports/all_sources> <pipeline folder holding data/ and handoff/>
run = sys.argv[1]
O = sys.argv[2] if len(sys.argv) > 2 else ".."
UP = sys.argv[3] if len(sys.argv) > 3 else "../pipeline"
R = 3.0
fr = pd.read_csv(f"{UP}/data/aligned/3i-atlas/frames.csv")
fr["frame_id"] = fr.file.str.replace(".fits", "", regex=False)
n = dict(zip(fr.frame_id, fr.grid_px)); f2b = dict(zip(fr.frame_id, fr.burst_id))
key = pd.DataFrame(json.load(open(f"{UP}/handoff/frontend_data/addons/3i-atlas_markers.json")))
key["y_np"] = [(n[f] - 1) - y for f, y in zip(key.frame_id, key.y)]
src = pd.concat([pd.read_csv(f, usecols=["frame", "file", "x", "y", "snr", "measurement_status"]) for f in
                 sorted(glob.glob(f"{O}/detector/exports/all_sources/3i-atlas/measured_sources_*.csv"))])
src["frame_id"] = src.file.str.replace(".fits", "", regex=False)
bd = pd.read_csv(f"{run}/3i-atlas_bursts.csv"); bd["frame_id"] = bd.file.str.replace(".fits", "", regex=False)
tr = pd.read_csv(f"{run}/3i-atlas_tracks.csv"); tr["frame_id"] = tr.file.str.replace(".fits", "", regex=False)


def near(tab, k):
    t = tab[tab.frame_id == k.frame_id]
    if len(t) == 0:
        return t
    d = np.hypot(t.x - k.x, t.y - k.y_np)
    return t[d <= R]


rows = []
for _, k in key.iterrows():
    s, b, t = near(src, k), near(bd, k), near(tr, k)
    rows.append(dict(frame_id=k.frame_id, burst=f2b[k.frame_id], in_data=bool(k.in_data), visible=bool(k.likely_visible),
                     in_catalog=len(s) > 0, snr=float(s.snr.max()) if len(s) else None,
                     in_burst_det=len(b) > 0, in_track=len(t) > 0, track=t.track_id.iloc[0] if len(t) else None))
S = pd.DataFrame(rows)
on = S[S.in_data]
vis = on[on.visible]
tracks = tr.groupby("track_id").agg(points=("frame_id", "size"))
hit_tracks = S.track.dropna().value_counts()
out = {
    "photos_with_3I_on_data": int(len(on)),
    "of_which_likely_visible": int(len(vis)),
    "omar_catalog_has_a_spot_at_3I": int(on.in_catalog.sum()),
    "  ...in_visible_photos": int(vis.in_catalog.sum()),
    "survived_star_removal_and_burst_grouping": int(on.in_burst_det.sum()),
    "linked_into_a_track": int(on.in_track.sum()),
    "bursts_with_3I_on_data": int(on.burst.nunique()),
    "bursts_where_3I_is_in_a_track": int(on[on.in_track].burst.nunique()),
    "tracks_in_patch": int(len(tracks)),
    "tracks_that_are_3I(points at 3I)": hit_tracks.to_dict(),
    "track_purity": {t: f"{int(hit_tracks.get(t, 0))}/{int(tracks.points[t])} points at 3I" for t in tracks.index},
    "median_snr_at_3I": float(on.snr.median()) if on.snr.notna().any() else None,
}
print(json.dumps(out, indent=1))
S.to_csv(f"{run}/3i_score_rows.csv", index=False)
