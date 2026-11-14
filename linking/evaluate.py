"""Score association output against known asteroids (labels.csv: JPL positions per photo). Tuning patches only."""
import sys, json, math, os, glob
import numpy as np, pandas as pd
from scipy.spatial import cKDTree

run, labels_root, exp, patch = sys.argv[1:5]
W_H = 50.0
AS = math.pi / 180 / 3600


def unit(ra, dec):
    ra, dec = np.radians(ra), np.radians(dec)
    return np.c_[np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)]


lab = pd.read_csv(os.path.join(labels_root, patch, "labels.csv"))
lab = lab[lab.in_data == 1].copy()
lab["frame_id"] = lab.file.str.replace(".fits", "", regex=False)
fr = pd.read_csv(os.path.join(labels_root.replace("labels", "aligned"), patch, "frames.csv"))
fr["frame_id"] = fr.file.str.replace(".fits", "", regex=False)
f2b = dict(zip(fr.frame_id, fr.burst_id))
lab["burst"] = lab.frame_id.map(f2b)
cols = ["frame", "file", "ra_deg", "dec_deg", "snr", "t_mid_mjd"]
src = pd.concat([pd.read_csv(f, usecols=cols) for f in sorted(glob.glob(os.path.join(exp, patch, "measured_sources_*.csv")))], ignore_index=True)
src["frame_id"] = src.file.str.replace(".fits", "", regex=False)
r12 = 2 * math.sin(6 * AS / 2)
lab = lab[lab.v_mag <= 18.5]
# 1) which label rows have a catalog spot within 12" (= the object was measured in that photo)
seen = np.zeros(len(lab), bool)
U_l = unit(lab.ra_deg.values, lab.dec_deg.values)
for f, idx in src.groupby("frame_id").indices.items():
    li = np.nonzero(lab.frame_id.values == f)[0]
    if len(li) == 0:
        continue
    d, _ = cKDTree(unit(src.ra_deg.values[idx], src.dec_deg.values[idx])).query(U_l[li], distance_upper_bound=r12)
    seen[li] = np.isfinite(d)
lab["measured"] = seen
# detectable burst sightings: object measured in >= 2 photos of a burst
g = lab[lab.measured].groupby(["object", "burst"])
bs = g.agg(n=("frame_id", "nunique"), ra=("ra_deg", "mean"), dec=("dec_deg", "mean"), t=("t_mid_mjd", "mean"),
           v=("v_mag", "median")).reset_index()
bs = bs[bs.n >= 2]
# 2) burst detections (from the association run)
bd = pd.read_csv(os.path.join(run, "%s_bursts.csv" % patch))
src_key = src.set_index(["file", "frame"]) if False else None
# position of each burst detection: mean of member spots (look them up by file + x,y is enough via the catalog ra/dec)
bdp = bd.groupby("burst_det").agg(burst=("burst", "first"), ra=("ra_deg", "mean"), dec=("dec_deg", "mean")).reset_index()
tr = pd.read_csv(os.path.join(run, "%s_tracks.csv" % patch))
det2trk = tr.drop_duplicates("burst_det").set_index("burst_det").track_id.to_dict()
# match burst sightings <-> burst detections (same burst, within 15")
r15 = 2 * math.sin(15 * AS / 2)
bs["det"] = -1
for b, idx in bs.groupby("burst").indices.items():
    cand = bdp[bdp.burst == b]
    if len(cand) == 0:
        continue
    d, j = cKDTree(unit(cand.ra.values, cand.dec.values)).query(unit(bs.ra.values[idx], bs.dec.values[idx]), distance_upper_bound=r15)
    ok = np.isfinite(d)
    bs.iloc[idx[ok], bs.columns.get_loc("det")] = cand.burst_det.values[j[ok]]
bs["track"] = bs.det.map(det2trk)
# recoverable objects: >= 3 detectable burst sightings with consecutive gaps <= W_H
bt = fr.groupby("burst_id").t_mid_mjd.mean() * 24


def chains(ts):
    ts = sorted(ts); best = cur = 1
    for a, b in zip(ts, ts[1:]):
        cur = cur + 1 if 0.5 <= b - a <= W_H else 1
        best = max(best, cur)
    return best


obj = bs.groupby("object").agg(n_bs=("burst", "size"), v=("v", "median")).reset_index()
obj["max_chain"] = [chains(bt[bs[bs.object == o].burst].values) for o in obj.object]
obj["chain_found"] = [chains(bt[bs[(bs.object == o) & (bs.det >= 0)].burst].values) for o in obj.object]
obj["in_track"] = [bs[(bs.object == o)].track.dropna().value_counts().max() if bs[(bs.object == o)].track.notna().any() else 0 for o in obj.object]
rec = obj[obj.max_chain >= 3]
out = {"patch": patch,
       "detectable_burst_sightings": int(len(bs)),
       "found_as_burst_detection": int((bs.det >= 0).sum()),
       "objects_with_3plus_linkable_sightings": int(len(rec)),
       "objects_whose_burst_detections_still_chain_3plus": int((rec.chain_found >= 3).sum()),
       "objects_recovered_as_track(3+ bursts)": int((rec.in_track >= 3).sum()),
       "tracks": int(tr.track_id.nunique())}
# purity: track -> object (majority of its burst detections matched to one known object)
lab_by_burst = {}
pur = []
for t_id, grp in tr.groupby("track_id"):
    dets = grp.burst_det.unique()
    hits = bs[bs.det.isin(dets)].object.value_counts()
    pur.append((t_id, len(dets), hits.index[0] if len(hits) else None, int(hits.iloc[0]) if len(hits) else 0))
out["tracks_matching_known"] = sum(1 for p in pur if p[3] >= 2)
out["track_detail"] = pur
out["missed_examples"] = rec[rec.in_track < 3].sort_values("v").head(10)[["object", "v", "n_bs", "max_chain", "chain_found", "in_track"]].values.tolist()
print(json.dumps(out, indent=1, default=str))
