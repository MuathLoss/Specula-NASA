import time, importlib.util, json, numpy as np, pandas as pd
spec = importlib.util.spec_from_file_location("a", "assoc.py"); a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
O = "../omar_results/Specula-omar-all-data-results"; p = "3i-atlas"; cfg = dict(a.CFG); log = {}
t = time.time(); df, cen = a.load(O + "/detector/exports/all_sources", O + "/specula/public/data", p); print("load", round(time.time()-t,1), flush=True)
t = time.time(); st, U = a.static_flags(df, cen, p, cfg, log); print("static", round(time.time()-t,1), {k: log[k] for k in log}, flush=True)
t = time.time(); D = a.burst_detections(df, U, st, cfg, log); print("bursts", round(time.time()-t,1), log["burst_detections"], flush=True)
print(D.groupby("burst").size().describe().to_dict(), flush=True)
D.to_pickle("prof3i_D.pkl")
