import sys, math, pandas as pd, numpy as np
from scipy.spatial import cKDTree
run, patch = sys.argv[1], sys.argv[2]
AS = math.pi/180/3600
def unit(ra, dec):
    ra, dec = np.radians(ra), np.radians(dec); return np.c_[np.cos(dec)*np.cos(ra), np.cos(dec)*np.sin(ra), np.sin(dec)]
lab = pd.read_csv(f"../../pipeline/data/labels/{patch}/labels.csv"); lab = lab[lab.in_data == 1]
lab["frame_id"] = lab.file.str.replace(".fits", "", regex=False)
tr = pd.read_csv(f"{run}/{patch}_tracks.csv"); tr["frame_id"] = tr.file.str.replace(".fits", "", regex=False)
r = 2*math.sin(12*AS/2)
gl = lab.groupby("frame_id").indices
for tid, g in tr.groupby("track_id"):
    names = []
    for _, p in g.iterrows():
        li = gl.get(p.frame_id)
        if li is None: names.append(None); continue
        d, j = cKDTree(unit(lab.ra_deg.values[li], lab.dec_deg.values[li])).query(unit([p.ra_deg], [p.dec_deg]), distance_upper_bound=r)
        names.append((lab.object.values[li[j[0]]][:20], lab.v_mag.values[li[j[0]]]) if np.isfinite(d[0]) else None)
    c = pd.Series([n[0] for n in names if n]).value_counts()
    v = [n[1] for n in names if n]
    print(tid, "points", len(g), "bursts", g.burst_det.nunique(), "| matched points", sum(1 for n in names if n), "->", dict(c.head(3)), "V", (min(v) if v else None), "| snr med %.1f" % g.snr.median())
