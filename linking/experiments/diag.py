import sys, math, glob, os, json, numpy as np, pandas as pd
from scipy.spatial import cKDTree
sys.argv = ["x"] + sys.argv[1:]
import importlib.util
spec = importlib.util.spec_from_file_location("a", "assoc.py"); a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
O = "../omar_results/Specula-omar-all-data-results"; patch = sys.argv[1]
df, cen = a.load(O + "/detector/exports/all_sources", O + "/specula/public/data", patch)
log = {}
static, U = a.static_flags(df, cen, patch, a.CFG, log)
lab = pd.read_csv(f"../../pipeline/data/labels/{patch}/labels.csv"); lab = lab[lab.in_data == 1]
lab["frame_id"] = lab.file.str.replace(".fits", "", regex=False)
AS = math.pi/180/3600; r = 2*math.sin(6*AS/2)
gi = df.groupby("frame_id").indices
res = []
for f, li in lab.groupby("frame_id").indices.items():
    idx = gi.get(f)
    if idx is None: continue
    d, j = cKDTree(U[idx]).query(a.unit(lab.ra_deg.values[li], lab.dec_deg.values[li]), distance_upper_bound=r)
    for k, (dd, jj) in enumerate(zip(d, j)):
        row = lab.iloc[li[k]]
        res.append(dict(obj=row.object, v=row.v_mag, conf=row.get("confirmed", None), found=np.isfinite(dd),
                        static=bool(static[idx[jj]]) if np.isfinite(dd) else None, snr=float(df.snr.values[idx[jj]]) if np.isfinite(dd) else None))
R = pd.DataFrame(res)
R["vbin"] = pd.cut(R.v, [0, 15, 16, 17, 18, 19, 20, 30])
print(R.groupby("vbin", observed=True).agg(rows=("found", "size"), found=("found", "sum"), static=("static", lambda s: int((s == True).sum()))))
print("confirmed==1 rows:", int((R.conf == 1).sum()), "found:", int(R[R.conf == 1].found.sum()), "static among found:", int((R[R.conf == 1].static == True).sum()))
print("---- bright static cases")
B = R[(R.v <= 15) & (R.static == True)]
print(B.obj.value_counts().to_dict())
B2 = R[(R.v <= 15) & (R.static == False)]
print("bright transient:", B2.obj.value_counts().to_dict())
# for one static bright case, list the far-burst neighbours
bt = df.groupby("burst").t_mid_mjd.mean()
rr = 2*math.sin(9*AS/2)
tree = cKDTree(U)
shown = 0
for f, li in lab[lab.v_mag <= 15].groupby("frame_id").indices.items():
    idx = gi.get(f)
    if idx is None: continue
    d, j = cKDTree(U[idx]).query(a.unit(lab.ra_deg.values[li], lab.dec_deg.values[li]), distance_upper_bound=r)
    for k in range(len(li)):
        if not np.isfinite(d[k]) or not static[idx[j[k]]]: continue
        s = idx[j[k]]
        nb = tree.query_ball_point(U[s], rr)
        nbdf = df.iloc[nb]
        far = nbdf[np.abs(nbdf.t_mid_mjd - df.t_mid_mjd.values[s]) > 2]
        print(lab.iloc[li[k]].object, f, "snr %.0f status %s" % (df.snr.values[s], df.measurement_status.values[s]),
              "| far neighbours:", len(far), "in bursts", far.burst.nunique(), "median snr %.1f" % far.snr.median(),
              "dist\" med %.1f" % (np.degrees(np.arccos(np.clip(U[far.index.values] @ U[s], -1, 1)))*3600).mean())
        shown += 1
        if shown >= 8: break
    if shown >= 8: break
