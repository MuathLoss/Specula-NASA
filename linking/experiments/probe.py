import sys, json, glob, os, numpy as np, pandas as pd
from scipy.spatial import cKDTree
ROOT = sys.argv[1]; P = sys.argv[2]
EXP = os.path.join(ROOT, "detector/exports/all_sources", P)
DATA = os.path.join(ROOT, "specula/public/data", P)
df = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(EXP + "/measured_sources_*.csv"))], ignore_index=True)
t = json.load(open(DATA + "/timeline.json"))
f2b = {f["frame_id"]: f["burst_id"] for f in t["frames"]}
df["frame_id"] = df["file"].str.replace(".fits", "", regex=False)
df["burst"] = df["frame_id"].map(f2b)
print(P, "sources", len(df), "frames", df.frame_id.nunique(), "unmapped", df.burst.isna().sum())
print(df.measurement_status.value_counts().to_dict())
n = int(np.ceil(max(df.x.max(), df.y.max()))) + 4
print("grid guess n =", n)
ra, de = np.radians(df.ra_deg.values), np.radians(df.dec_deg.values)
U = np.c_[np.cos(de)*np.cos(ra), np.cos(de)*np.sin(ra), np.sin(de)]
tree = cKDTree(U)
r = np.radians(9/3600)
pairs = tree.query_pairs(r, output_type="ndarray")
b = pd.factorize(df.burst)[0]
i, j = pairs[:,0], pairs[:,1]
other = b[i] != b[j]
# distinct other bursts per source
from collections import defaultdict
ob = pd.DataFrame({"s": np.r_[i[other], j[other]], "b": np.r_[b[j[other]], b[i[other]]]}).drop_duplicates()
nob = ob.groupby("s").size().reindex(range(len(df)), fill_value=0).values
same = ~other
sb = np.zeros(len(df), int); np.add.at(sb, i[same], 1); np.add.at(sb, j[same], 1)
nb = df.burst.nunique()
print("bursts", nb, "| other-burst count quantiles", np.percentile(nob, [10,25,50,75,90]).tolist())
static = nob >= 2
trans = ~static
print("static", static.sum(), "transient", trans.sum(), "| transient with same-burst partner", (trans & (sb>0)).sum())
# known asteroids
m = json.load(open(DATA + "/markers.json")); m = pd.DataFrame(m["markers"] if isinstance(m, dict) else m)
vis = m[m.likely_visible == True]
print("markers", len(m), "likely visible", len(vis))
g = {k: v for k, v in df.groupby("frame_id").indices.items()}
def score(rows, conv):
    hit_any = hit_tr = hit_tr2 = 0
    for _, mk in rows.iterrows():
        idx = g.get(mk.frame_id)
        if idx is None: continue
        yy = (n-1) - mk.y if conv == "flip" else mk.y
        d = np.hypot(df.x.values[idx] - mk.x, df.y.values[idx] - yy)
        ok = idx[d < 2.0]
        hit_any += len(ok) > 0; hit_tr += trans[ok].any(); hit_tr2 += (trans[ok] & (sb[ok] > 0)).any()
    return hit_any, hit_tr, hit_tr2
for conv in ("flip", "noflip"):
    print(conv, "visible markers found (any / transient / transient+burst-partner):", score(vis, conv), "of", len(vis))
