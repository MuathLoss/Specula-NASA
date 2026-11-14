"""Specula association: Omar's per-photo source catalog -> moving-object tracks.

No label, marker, orbit or target position is read here. Steps:
  1. star removal: a spot is static if another spot sits within R_STATIC of it in at least
     min(STATIC_MAX_NEED, max(1, STATIC_FRAC x covering bursts)) other bursts taken more than T_STATIC apart
  2. burst detections: transient spots of one burst within R_BURST of each other, in >= 2 different photos
  3. linking: pairs of burst detections 0.5-W_H hours apart define a straight-line motion (1-300 "/h);
     a track needs support in >= MIN_BURSTS bursts, residual RMS <= RMS_MAX and >= MIN_MOVE_PX total motion
Writes <out>/<patch>_tracks.csv in the merge contract (patch, frame, file, x, y, snr, track_id, is_target)
plus <patch>_bursts.csv (all burst detections) and <patch>_assoc.json (counts, settings).
"""
import argparse, glob, json, math, os, time
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

AS = math.pi / 180 / 3600
CFG = dict(REQUIRE_TESTED=False, SNR_MIN=0.0, STATIC_MAX_NEED=4, STATIC_FRAC=0.1, R_STATIC=9.0, T_STATIC_FIXED_D=2.0, T_STATIC_MOVING_D=0.08, R_BURST=15.0, MIN_FRAMES=2,
           W_H=50.0, MIN_GAP_H=0.5, RATE_MIN=1.0, RATE_MAX=300.0, TOL0=12.0, TOL_ACC=0.004,
           MIN_BURSTS=4, RMS_MAX=4.0, MIN_MOVE_PX=2.0, GHOST_SNR_MIN=150.0, GHOST_RATIO=5.0, GHOST_SEP_DEG=0.5,
           SCRAMBLE=False, SEED=1)
FIXED = {"ecliptic-virgo", "ecliptic-ra90", "nep-cats-eye"}


def unit(ra, dec):
    ra, dec = np.radians(ra), np.radians(dec)
    return np.c_[np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)]


def basis(c):
    c = c / np.linalg.norm(c)
    e = np.cross([0.0, 0.0, 1.0], c); e /= np.linalg.norm(e)
    n = np.cross(c, e)
    return c, e, n


def gnomonic(U, c):
    c, e, n = basis(c)
    w = U @ c
    return np.c_[(U @ e) / w, (U @ n) / w] / AS          # arcsec east, north


def load(exp, data, patch):
    cols = ["source_id", "frame", "file", "detector", "t_mid_mjd", "ra_deg", "dec_deg", "x", "y", "snr",
            "measurement_status", "quality_flags"]
    df = pd.concat([pd.read_csv(f, usecols=cols) for f in sorted(glob.glob(os.path.join(exp, patch, "measured_sources_*.csv")))],
                   ignore_index=True)
    t = json.load(open(os.path.join(data, patch, "timeline.json")))
    f2b = {f["frame_id"]: f["burst_id"] for f in t["frames"]}
    cen = {b["burst_id"]: (b["ra_center"], b["dec_center"]) for b in t["bursts"]}
    df["frame_id"] = df["file"].str.replace(".fits", "", regex=False)
    df["burst"] = df["frame_id"].map(f2b)
    assert df["burst"].notna().all()
    return df, cen


def static_flags(df, cen, patch, cfg, log):
    U = unit(df.ra_deg.values, df.dec_deg.values)
    bursts = df.groupby("burst")
    bt = bursts.t_mid_mjd.mean()
    T = cfg["T_STATIC_FIXED_D"] if patch in FIXED else cfg["T_STATIC_MOVING_D"]
    r = 2 * math.sin(cfg["R_STATIC"] * AS / 2)
    trees, half = {}, {}
    for b, idx in bursts.indices.items():
        trees[b] = cKDTree(U[idx])
        half[b] = (max(df.x.values[idx].max(), df.y.values[idx].max()) + 1) / 2 * 6.15     # grid half-size (")
    static = np.zeros(len(df), bool)
    nfar = np.zeros(len(df), int)
    for b, idx in bursts.indices.items():
        far = [c for c in trees if abs(bt[c] - bt[b]) > T]
        hits = np.zeros(len(idx), int)
        cov = np.zeros(len(idx), int)
        for c in far:
            d, _ = trees[c].query(U[idx], distance_upper_bound=r)
            hits += np.isfinite(d)
            if patch in FIXED:
                cov += 1
            else:
                xy = gnomonic(U[idx], unit(*cen[c])[0])
                cov += (np.abs(xy[:, 0]) <= half[c]) & (np.abs(xy[:, 1]) <= half[c])
        need = np.minimum(cfg["STATIC_MAX_NEED"], np.maximum(1, np.round(cfg["STATIC_FRAC"] * cov)))
        static[idx] = (cov >= 1) & (hits >= need)
        nfar[idx] = cov
    log["spots"] = int(len(df)); log["static"] = int(static.sum()); log["transient"] = int((~static).sum())
    log["transient_no_far_coverage"] = int(((~static) & (nfar == 0)).sum())
    if cfg["REQUIRE_TESTED"] and patch not in FIXED:   # spots no other burst could check are not used (v3)
        static = static | (nfar == 0)
    return static, U


def burst_detections(df, U, static, cfg, log):
    rows = []
    r = 2 * math.sin(cfg["R_BURST"] * AS / 2)
    tr = df[~static]
    for b, idx in tr.groupby("burst").indices.items():
        gi = tr.index.values[idx]
        if len(gi) < 2:
            continue
        P = cKDTree(U[gi]).query_pairs(r, output_type="ndarray")
        if len(P) == 0:
            continue
        parent = np.arange(len(gi))

        def find(k):
            while parent[k] != k:
                parent[k] = parent[parent[k]]; k = parent[k]
            return k
        for a, c in P:
            ra_, rc = find(a), find(c)
            if ra_ != rc:
                parent[rc] = ra_
        roots = np.array([find(k) for k in range(len(gi))])
        for root in np.unique(roots):
            mem = gi[roots == root]
            if len(mem) < 2:
                continue
            sub = df.loc[mem].sort_values("snr", ascending=False).drop_duplicates("frame_id")   # best spot per photo
            if sub.frame_id.nunique() < cfg["MIN_FRAMES"] or sub.snr.median() < cfg["SNR_MIN"]:
                continue
            u = U[sub.index.values].mean(axis=0); u /= np.linalg.norm(u)
            rows.append(dict(burst=b, t_h=float(sub.t_mid_mjd.mean() * 24.0), ux=u[0], uy=u[1], uz=u[2],
                             n_frames=int(sub.frame_id.nunique()), snr=float(sub.snr.median()),
                             members=list(sub.index.values)))
    D = pd.DataFrame(rows)
    log["burst_detections"] = int(len(D))
    return D


def link(D, cfg, log, rng=None):
    if len(D) == 0:
        log["tracks"] = 0
        return []
    D = D.copy()
    bt = D.groupby("burst").t_h.mean().sort_values()
    U = D[["ux", "uy", "uz"]].values.copy()
    if cfg["SCRAMBLE"]:        # false-link test: rotate each burst's detections by a random angle about its centre
        for b, idx in D.groupby("burst").indices.items():
            c = U[idx].mean(axis=0); c /= np.linalg.norm(c)
            th = rng.uniform(0, 2 * np.pi)
            K = np.array([[0, -c[2], c[1]], [c[2], 0, -c[0]], [-c[1], c[0], 0]])
            R = np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K
            U[idx] = U[idx] @ R.T
    blist = list(bt.index)
    bidx = D.groupby("burst").indices
    cands = []
    for ii, bi in enumerate(blist):
        A = bidx[bi]
        for bj in blist[ii + 1:]:
            dt = bt[bj] - bt[bi]
            if dt < cfg["MIN_GAP_H"]:
                continue
            if dt > cfg["W_H"]:
                break
            B = bidx[bj]
            c = U[A].mean(axis=0)
            win = [bk for bk in blist if bk not in (bi, bj) and bt[bi] - cfg["W_H"] <= bt[bk] <= bt[bj] + cfg["W_H"]]
            XA, XB = gnomonic(U[A], c), gnomonic(U[B], c)
            tA, tB = D.t_h.values[A], D.t_h.values[B]
            V = (XB[None, :, :] - XA[:, None, :]) / (tB[None, :, None] - tA[:, None, None])
            rate = np.hypot(V[..., 0], V[..., 1])
            ia, ib = np.nonzero((rate >= cfg["RATE_MIN"]) & (rate <= cfg["RATE_MAX"]))
            if len(ia) == 0:
                continue
            # supports: same rule as before, vectorised (identical results, much faster)
            hit_s, hit_k = [], []
            for bk in win:
                K = bidx[bk]
                XK = gnomonic(U[K], c)
                tk = bt[bk]
                ext = np.minimum(np.abs(tk - tA[ia]), np.abs(tk - tB[ib]))
                span = max(tk, tB.max()) - min(tk, tA.min())
                inner = (tk > bt[bi]) & (tk < bt[bj])
                tol = cfg["TOL0"] + (0 if inner else 1) * (2.0 * math.sqrt(2) * 2.0 / dt) * ext + cfg["TOL_ACC"] * span ** 2
                tol = np.broadcast_to(tol, ia.shape)
                pred = XA[ia] + V[ia, ib] * (tk - tA[ia])[:, None]
                lo, hi = XK.min(axis=0), XK.max(axis=0)          # skip predictions that cannot reach any detection
                box = np.all((pred >= lo - tol[:, None]) & (pred <= hi + tol[:, None]), axis=1)
                q = np.nonzero(box)[0]
                if len(q) == 0:
                    continue
                d, j = cKDTree(XK).query(pred[q], distance_upper_bound=float(np.max(tol[q])))
                ok = np.isfinite(d) & (d <= tol[q])
                hit_s.append(q[ok]); hit_k.append(K[j[ok]])
            if not hit_s:
                continue
            hs, hk = np.concatenate(hit_s), np.concatenate(hit_k)
            cnt = np.bincount(hs, minlength=len(ia))
            for s in np.nonzero(cnt + 2 >= cfg["MIN_BURSTS"])[0]:
                cands.append([A[ia[s]], B[ib[s]]] + hk[hs == s].tolist())
    # refit, filter, de-duplicate
    tracks = []
    seen = set()
    for m in cands:
        key = tuple(sorted(set(m)))
        if key in seen:
            continue
        seen.add(key)
        m = np.array(key)
        if D.burst.values[m].tolist().__len__() != len(set(D.burst.values[m])):
            continue                                     # one detection per burst
        c = U[m].mean(axis=0)
        X = gnomonic(U[m], c)
        t = D.t_h.values[m]
        tc = t - t.mean()
        deg = 2 if (len(m) >= 5 and np.ptp(t) > 30) else 1
        res = np.concatenate([X[:, k] - np.polyval(np.polyfit(tc, X[:, k], deg), tc) for k in (0, 1)])
        rms = float(np.sqrt(np.sum(res ** 2) / max(1, 2 * len(m) - 2 * (deg + 1)))) if len(m) > deg + 1 else 0.0
        move = float(np.hypot(*(X[np.argmax(t)] - X[np.argmin(t)]))) / 6.15
        vx, vy = np.polyfit(tc, X[:, 0], 1)[0], np.polyfit(tc, X[:, 1], 1)[0]
        if rms <= cfg["RMS_MAX"] and move >= cfg["MIN_MOVE_PX"]:
            v3 = np.array([np.polyfit(tc, U[m][:, k], 1)[0] for k in range(3)]) / AS      # "/h, 3-D
            tracks.append(dict(dets=m, n_bursts=len(m), rms=rms, rate=float(math.hypot(vx, vy)),
                               span_h=float(np.ptp(t)), snr=float(np.median(D.snr.values[m])), v3=v3,
                               u=c / np.linalg.norm(c), bursts=set(D.burst.values[m])))
    tracks.sort(key=lambda r: (-r["n_bursts"], r["rms"]))
    used, final = set(), []
    for tr in tracks:
        if used & set(tr["dets"].tolist()):
            continue
        used |= set(tr["dets"].tolist())
        final.append(tr)
    # in most of its bursts within 0.5 deg of a saturated-bright MOVING detection (e.g. Ceres): likely its artifact
    ghosts = []
    bright = np.nonzero(D.snr.values >= cfg["GHOST_SNR_MIN"])[0]
    for a in final:
        near = 0
        for d in a["dets"]:
            bb = bright[(D.burst.values[bright] == D.burst.values[d]) & (D.snr.values[bright] >= cfg["GHOST_RATIO"] * a["snr"])]
            bb = bb[bb != d]
            if len(bb) and np.degrees(np.arccos(np.clip(U[bb] @ U[d], -1, 1))).min() < cfg["GHOST_SEP_DEG"]:
                near += 1
        if near >= max(2, math.ceil(0.5 * len(a["dets"]))):
            ghosts.append(a)
    log["rejected_as_ghost_of_bright_track"] = len(ghosts)
    final = [tr for tr in final if not any(tr is g for g in ghosts)]
    log["seed_tracks"] = len(cands); log["tracks"] = len(final)
    return final


def run_patch(exp, data, patch, out, cfg):
    t0 = time.time()
    log = {"patch": patch, "settings": cfg}
    df, cen = load(exp, data, patch)
    static, U = static_flags(df, cen, patch, cfg, log)
    D = burst_detections(df, U, static, cfg, log)
    tracks = link(D, cfg, log, np.random.default_rng(cfg["SEED"]))
    os.makedirs(out, exist_ok=True)
    rows = []
    for k, tr in enumerate(tracks, 1):
        tid = "%s-trk-%04d" % (patch, k)
        for d in tr["dets"]:
            for s in D.members.values[d]:
                r = df.loc[s]
                rows.append(dict(patch=patch, frame=int(r.frame), file=r.file, x=r.x, y=r.y, snr=r.snr,
                                 track_id=tid, is_target=0, source_id=r.source_id, ra_deg=r.ra_deg, dec_deg=r.dec_deg,
                                 burst_det=int(d)))
    pd.DataFrame(rows, columns=["patch", "frame", "file", "x", "y", "snr", "track_id", "is_target", "source_id",
                                "ra_deg", "dec_deg", "burst_det"]).to_csv(
        os.path.join(out, "%s_tracks.csv" % patch), index=False)
    bd = []
    for d in range(len(D)):
        for s in D.members.values[d]:
            r = df.loc[s]
            bd.append(dict(patch=patch, frame=int(r.frame), file=r.file, x=r.x, y=r.y, snr=r.snr,
                           source_id=r.source_id, ra_deg=r.ra_deg, dec_deg=r.dec_deg, burst_det=d, burst=D.burst.values[d], n_frames=int(D.n_frames.values[d])))
    pd.DataFrame(bd).to_csv(os.path.join(out, "%s_bursts.csv" % patch), index=False)
    log["track_summary"] = [dict(track_id="%s-trk-%04d" % (patch, k), n_bursts=tr["n_bursts"], rms_arcsec=round(tr["rms"], 2),
                                 rate_arcsec_h=round(tr["rate"], 1), span_h=round(tr["span_h"], 1), snr=round(tr["snr"], 1))
                            for k, tr in enumerate(tracks, 1)]
    log["seconds"] = round(time.time() - t0, 1)
    json.dump(log, open(os.path.join(out, "%s_assoc.json" % patch), "w"), indent=1, default=str)
    return log


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp", required=True); ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--patches", nargs="+", required=True)
    ap.add_argument("--set", nargs="*", default=[], help="KEY=VALUE overrides")
    a = ap.parse_args()
    cfg = dict(CFG)
    for kv in a.set:
        k, v = kv.split("="); cfg[k] = type(CFG[k])(v) if not isinstance(CFG[k], bool) else v in ("1", "true", "True")
    for p in a.patches:
        lg = run_patch(a.exp, a.data, p, a.out, cfg)
        print(p, {k: lg[k] for k in ("spots", "static", "transient", "transient_no_far_coverage", "burst_detections", "seed_tracks", "rejected_as_ghost_of_bright_track", "tracks", "seconds") if k in lg})
