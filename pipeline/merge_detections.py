"""Specula v0.3 - merge the detector teammate's results into the frontend data.

Input  : his detections.csv (format from handoff #1, handoff_docs/CLAUDE.md), one row per detection per photo:
         patch, frame, file, x, y, snr, track_id, is_target     (x, y = 0-based numpy pixels: data[round(y), round(x)])
Output (default handoff/frontend_data/; --out <dir> for tests):
  detections.json  every track (2+ points): "known" (matched to NASA JPL labels / 3I/ATLAS truth) or "candidate",
                   contract format; x, y converted to IMAGE pixels (same as markers.json, north up)
  scoring.json     3I/ATLAS blind-test score, Ceres check, known-asteroid recovery, candidate counts
  objects.csv      + one row per candidate (earlier candidate rows replaced)
  manifest.json    file list refreshed (only when writing into handoff/frontend_data)
Candidates also get: sky motion; an APPROXIMATE distance range (decision D2: statistical ranging assuming a circular,
low-inclination orbit, using SPHEREx's real position); a V magnitude estimated from our difference images (calibrated
on known asteroids); a size range (albedo 0.05-0.25); a comet check against data/v02/comets.json (fetch_comets.py).
Run:   python merge_detections.py --input detections.csv [--out <dir>] [--pretend-unknown id1,id2] [--budget 150]
Resumable: finished candidates are cached in handoff/_checks/merge_cache/; if the time budget runs out it prints
"NOT DONE" and writes nothing - run the same command again until it prints the summary.
numpy only.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone

import numpy as np

FRONT = os.path.join("handoff", "frontend_data")
PATCHES = ["ecliptic-virgo", "ecliptic-ra90", "nep-cats-eye", "ceres", "3i-atlas"]
FIXED = ["ecliptic-virgo", "ecliptic-ra90", "nep-cats-eye"]
PIX_DEG = 6.15 / 3600.0
MATCH_PX = 3.0            # detection <-> known-object label match radius (18.5")
TARGET_PX = 3.0           # 3I/ATLAS and Ceres scoring radius
SIGMA_PX = 0.5            # position error assumed for ranging (3.1")
I_MAX_DEG = 30.0          # "low inclination" for D2 ranging
DELTA_GRID = np.geomspace(0.01, 40.0, 300)   # trial distances from SPHEREx (AU)
K_GAUSS = 0.01720209895   # AU^1.5 / day
AU_KM = 149597870.7
EPS = math.radians(84381.448 / 3600.0)
ALB_MIN, ALB_MAX, G_SLOPE = 0.05, 0.25, 0.15
COMET_RADIUS_DEG = 1.0
MAX_RANGE_RATIO = 30.0    # wider ranges are reported as "not constrained" (null) instead of a meaningless range
MAX_LINK_RATE_SIGMA = 70.0  # "/h: a track can be linked to another burst only if its motion is measured this well
MAX_LINK_DMAG = 1.5         # and only to a track of similar brightness (estimated V within 1.5 mag)
DCHI2 = 6.18              # chi-square step for a 95% region with 2 free parameters (distance, direction of motion)


# ---------------- small helpers ----------------
def read_layers(path, names):
    """Return ({extname: 2-D array}, {extname: header}) for the requested FITS image layers (numpy only)."""
    out, hdrs = {}, {}
    with open(path, "rb") as f:
        while len(out) < len(names):
            hdr, end = {}, False
            while not end:
                blk = f.read(2880)
                if len(blk) < 2880:
                    return out, hdrs
                for i in range(36):
                    c = blk[i * 80:(i + 1) * 80].decode("ascii", "replace")
                    if c[:8].strip() == "END":
                        end = True
                        break
                    if c[8:10] == "= ":
                        v = c[10:]
                        v = v.strip()[1:].split("'")[0] if v.strip().startswith("'") else v.split("/")[0]
                        hdr[c[:8].strip()] = v.strip()
            naxis, bitpix = int(hdr.get("NAXIS", 0)), int(hdr.get("BITPIX", 8))
            dims = [int(hdr["NAXIS%d" % (i + 1)]) for i in range(naxis)]
            size = (abs(bitpix) // 8) * int(np.prod(dims)) if naxis else 0
            size += int(hdr.get("PCOUNT", 0) or 0)
            name = hdr.get("EXTNAME", "PRIMARY")
            if name in names and naxis == 2:
                dt = {8: ">u1", 16: ">i2", 32: ">i4", -32: ">f4", -64: ">f8"}[bitpix]
                a = np.frombuffer(f.read(size), dtype=dt).reshape(dims[1], dims[0])
                f.seek((-size) % 2880, 1)
                if "BSCALE" in hdr or "BZERO" in hdr:
                    a = a * float(hdr.get("BSCALE", 1)) + float(hdr.get("BZERO", 0))
                out[name], hdrs[name] = a, hdr
            else:
                f.seek(size + ((-size) % 2880), 1)
    return out, hdrs


_LAYERS = {}


def layer(path, name):
    k = (path, name)
    if k not in _LAYERS:
        if len(_LAYERS) > 96:
            _LAYERS.pop(next(iter(_LAYERS)))
        _LAYERS[k] = read_layers(path, [name])[0][name]
    return _LAYERS[k]


class Budget(Exception):
    pass


class Cache:
    """Finished candidate results, keyed by input file + this script's code, so re-runs continue."""
    def __init__(self, inp, budget_s):
        h = hashlib.sha256(open(inp, "rb").read() + open(__file__, "rb").read()).hexdigest()[:16]
        self.path = os.path.join("handoff", "_checks", "merge_cache", h + ".json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.d = jload(self.path) if os.path.exists(self.path) else {}
        self.t0, self.budget = time.time(), budget_s

    def save(self):
        jsave(self.path, self.d)

    def tick(self):
        if time.time() - self.t0 > self.budget:
            self.save()
            raise Budget()

def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def jsave(p, obj):
    with open(p + ".part", "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(p + ".part", p)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def jd_iso(s):
    return 2440587.5 + datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() / 86400.0


def iso_from_mjd(m):
    return iso(datetime.fromtimestamp((m - 40587.0) * 86400.0, tz=timezone.utc))


def object_id(name):                        # same rule as build_previews.py / markers.json
    m = re.match(r"^(\d+) ", name)
    if m:
        return m.group(1)
    m = re.match(r"^\((.+)\)$", name.strip())
    return m.group(1) if m else name.strip()


def frame_id(f):
    return os.path.splitext(os.path.basename(f))[0]


def equ_to_ecl(v):
    v = np.asarray(v, float)
    c, s = math.cos(EPS), math.sin(EPS)
    return np.stack([v[..., 0], c * v[..., 1] + s * v[..., 2], -s * v[..., 1] + c * v[..., 2]], axis=-1)


def radec_vec(ra, dec):
    ra, dec = np.radians(ra), np.radians(dec)
    return np.stack([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)], axis=-1)


def pix_to_radec(x, y_np, gra, gdec, n):
    """Our grids: north-up TAN, 6.15"/px, centre (gra, gdec) at pixel ((n-1)/2, (n-1)/2); y_np = numpy row."""
    c = (n - 1) / 2.0
    xi = math.radians((c - x) * PIX_DEG)
    eta = math.radians((c - ((n - 1) - y_np)) * PIX_DEG)
    a0, d0 = math.radians(gra), math.radians(gdec)
    rho = math.hypot(xi, eta)
    if rho == 0:
        return gra, gdec
    cc = math.atan(rho)
    dec = math.asin(math.cos(cc) * math.sin(d0) + eta * math.sin(cc) * math.cos(d0) / rho)
    ra = a0 + math.atan2(xi * math.sin(cc), rho * math.cos(d0) * math.cos(cc) - eta * math.sin(d0) * math.sin(cc))
    return math.degrees(ra) % 360.0, math.degrees(dec)


# ---------------- inputs ----------------
class Data:
    def __init__(self):
        self.frames, self.by_num = {}, {}                      # frame_id -> info ; (patch, frame#) -> frame_id
        for p in PATCHES:
            with open(os.path.join("data", "aligned", p, "frames.csv"), newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    fid = frame_id(r["file"])
                    self.frames[fid] = {"patch": p, "file": r["file"], "mjd": float(r["t_mid_mjd"]),
                                        "utc": r["t_mid_utc"], "burst": r["burst_id"], "det": r["detector"],
                                        "gra": float(r["grid_ra"]), "gdec": float(r["grid_dec"]), "n": int(r["grid_px"])}
                    self.by_num[(p, int(r["frame"]))] = fid
        self.labels = defaultdict(list)                         # frame_id -> [(object_id, name, x, y_np, v)]
        self.calib_rows = []
        for p in PATCHES:
            with open(os.path.join("data", "labels", p, "labels.csv"), newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r["in_data"] != "1":
                        continue
                    fid = frame_id(r["file"])
                    v = float(r["v_mag"]) if r["v_mag"] else 99.0
                    self.labels[fid].append((object_id(r["object"]), r["object"], float(r["x"]), float(r["y"]), v))
                    if p in FIXED and r.get("confirmed") == "1" and r.get("diff_snr_peak"):
                        self.calib_rows.append((r["detector"], v, float(r["diff_snr_peak"])))
        self.tri = {}                                           # 3I/ATLAS truth (frontend addon, image y)
        for r in jload(os.path.join(FRONT, "addons", "3i-atlas_markers.json")):
            n = self.frames[r["frame_id"]]["n"]
            self.tri[r["frame_id"]] = {"x": r["x"], "y_np": (n - 1) - r["y"], "in_data": r["in_data"],
                                       "visible": r["likely_visible"]}
        self.markers = {p: jload(os.path.join(FRONT, p, "markers.json")) for p in PATCHES}
        # observer = Earth (Horizons, per burst) + SPHEREx's geocentric offset (Horizons, per group)
        he = jload(os.path.join("data", "v02", "horizons_earth.json"))
        rows = [v["row"] for v in he["bursts"].values()]
        self.earth_jd = np.array([float(r[0]) for r in rows])
        self.earth_pv = np.array([[float(x) for x in r[2:8]] for r in rows])
        self.sx = {}
        for p in PATCHES:
            d = jload(os.path.join("data", "labels", p, "jpl_cache", "horizons_spherex.json"))
            self.sx[p] = (np.array([float(k) for k in d]), np.array([d[k] for k in d], float))
        self.orbits = {o["object_id"]: o for o in jload(os.path.join(FRONT, "orbits.json"))["objects"]}
        with open(os.path.join(FRONT, "objects.csv"), newline="", encoding="utf-8") as f:
            self.objects = list(csv.DictReader(f))
        self.calib = self.fit_calibration()
        cpath = os.path.join("data", "v02", "comets.json")
        self.comets = jload(cpath) if os.path.exists(cpath) else None

    def observer(self, fid):
        """SPHEREx heliocentric ecliptic J2000 position (AU) at the frame's mid time."""
        fr = self.frames[fid]
        jd = fr["mjd"] + 2400000.5
        k = int(np.argmin(np.abs(self.earth_jd - jd)))
        if abs(self.earth_jd[k] - jd) > 0.05:
            raise RuntimeError("no Earth position near %s" % fid)
        e = self.earth_pv[k, :3] + self.earth_pv[k, 3:] * (jd - self.earth_jd[k])
        keys, st = self.sx[fr["patch"]]
        j = int(np.argmin(np.abs(keys - fr["mjd"])))
        if abs(keys[j] - fr["mjd"]) > 0.05:
            raise RuntimeError("no SPHEREx position near %s" % fid)
        r0, v0 = st[j, :3], st[j, 3:]
        w = np.linalg.norm(v0) / np.linalg.norm(r0)             # near-circular orbit around Earth
        dt = (fr["mjd"] - keys[j]) * 86400.0
        r = r0 * math.cos(w * dt) + v0 / w * math.sin(w * dt)
        return e + equ_to_ecl(r) / AU_KM

    def fit_calibration(self):
        """V magnitude from difference-image S/N, per detector: V = a + b * (-2.5 log10 snr), fixed patches."""
        out, allrows = {}, [(v, s) for _, v, s in self.calib_rows if s > 0]
        def fit(rows):
            v = np.array([a for a, _ in rows])
            x = -2.5 * np.log10(np.array([b for _, b in rows]))
            A = np.vstack([np.ones_like(x), x]).T
            coef = np.linalg.lstsq(A, v, rcond=None)[0]
            return float(coef[0]), float(coef[1]), float(np.std(v - A @ coef))
        glob = fit(allrows)
        for d in sorted({d for d, _, _ in self.calib_rows}):
            rows = [(v, s) for dd, v, s in self.calib_rows if dd == d and s > 0]
            if len(rows) >= 8:
                a, b, s = fit(rows)
                out[d] = (a, b, s) if (b > 0.5 and s < 1.0) else glob
            else:
                out[d] = glob
        out["all"] = glob
        return out


# ---------------- orbit maths (same as build_v02.py / specula_orbit.js) ----------------
def kepler_xyz(o, jd):
    jd = np.atleast_1d(np.asarray(jd, float))
    e, i, om, w = o["e"], math.radians(o["i_deg"]), math.radians(o["node_deg"]), math.radians(o["peri_deg"])
    n = math.radians(o["n_deg_day"])
    if o["orbit_type"] == "elliptic":
        a = o["a_au"]
        M = np.radians(o["M_deg"]) + n * (jd - o["epoch_jd_tdb"])
        M = np.remainder(M + np.pi, 2 * np.pi) - np.pi
        E = M + e * np.sin(M) if e < 0.8 else np.pi * np.sign(M + 1e-30)
        for _ in range(60):
            E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
        xp, yp = a * (np.cos(E) - e), a * math.sqrt(1 - e * e) * np.sin(E)
    else:
        a = o["q_au"] / (1 - e)
        M = n * (jd - o["tp_jd_tdb"])
        H = np.arcsinh(M / e)
        for _ in range(100):
            H = H - (e * np.sinh(H) - H - M) / (e * np.cosh(H) - 1)
        xp, yp = a * (np.cosh(H) - e), -a * math.sqrt(e * e - 1) * np.sinh(H)
    co, so, ci, si, cw, sw = math.cos(om), math.sin(om), math.cos(i), math.sin(i), math.cos(w), math.sin(w)
    return np.stack([(co * cw - so * sw * ci) * xp + (-co * sw - so * cw * ci) * yp,
                     (so * cw + co * sw * ci) * xp + (-so * sw + co * cw * ci) * yp,
                     (sw * si) * xp + (cw * si) * yp], axis=-1)


# ---------------- D2: statistical ranging ----------------
SPEED_MIN, SPEED_MAX = 0.8, 1.2        # speed / circular speed allowed (near-circular orbits, e <~ 0.2)
GAMMA_MAX = math.radians(12.0)         # largest flight-path angle (radial part of the velocity)
VR_GRID = np.linspace(-1.4, 1.4, 57)   # line-of-sight speed / circular speed, scanned


def ranging(times_jd, meas_vec, obs_pos, sigma_px=SIGMA_PX, i_max=I_MAX_DEG, burst_ids=None):
    """D2 statistical ranging. For each trial distance (and each line-of-sight speed) the across-the-sky
    velocity is FITTED to the measured positions (Gauss-Newton), with SPHEREx's real position at every photo
    and the Sun's pull. A trial is allowed if its orbit is near-circular (speed 0.8-1.2 x circular, flight-path
    angle <= 12 deg) and low-inclination (<= 30 deg, prograde). Keeps the 95% region (delta chi2 6.18) around
    the best allowed fit.  Returns (dmin, dmax, accepted dict, status) with status ok / short / nofit."""
    t = np.asarray(times_jd, float)
    m = np.asarray(meas_vec, float)
    O = np.asarray(obs_pos, float)
    if t.max() - t.min() < 1e-4:                                   # all photos at the same moment
        return None, None, None, "short"
    bid = np.asarray(burst_ids) if burst_ids is not None else np.zeros(len(t), int)
    tmid = 0.5 * (t.min() + t.max())
    centres = {b: t[bid == b].mean() for b in set(bid.tolist())}
    b0 = min(centres, key=lambda b: abs(centres[b] - tmid))
    sel = bid == b0
    t0 = float(t[sel].mean())
    u0 = m[sel].mean(axis=0)
    u0 /= np.linalg.norm(u0)
    O0 = O[sel].mean(axis=0)
    e1 = np.cross([0.0, 0.0, 1.0], u0)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(u0, e1)
    dt = t - t0
    # measured angular motion and observer velocity (straight-line fits) -> starting guess
    q1, q2 = m @ e1, m @ e2
    mu = np.array([np.polyfit(dt, q1, 1)[0], np.polyfit(dt, q2, 1)[0]])            # rad/day
    Odot = np.array([np.polyfit(dt, O[:, k], 1)[0] for k in range(3)])               # AU/day
    # residual frame per point
    t1 = np.cross([0.0, 0.0, 1.0], m)
    t1 /= np.linalg.norm(t1, axis=1)[:, None]
    t2 = np.cross(m, t1)
    sig = math.radians(sigma_px * PIX_DEG)
    D_, VR_ = np.meshgrid(DELTA_GRID, VR_GRID, indexing="ij")
    D_, VR_ = D_.ravel(), VR_.ravel()
    P0 = O0[None, :] + D_[:, None] * u0[None, :]
    r = np.linalg.norm(P0, axis=1)
    vc = K_GAUSS / np.sqrt(r)
    acc0 = -(K_GAUSS ** 2) * P0 / r[:, None] ** 3
    vr = VR_ * vc
    a = np.stack([D_ * mu[0] + Odot @ e1, D_ * mu[1] + Odot @ e2], axis=1)           # (C,2) tangential velocity

    def resid(a_):
        V = a_[:, 0:1] * e1 + a_[:, 1:2] * e2 + vr[:, None] * u0                   # (C,3)
        P = P0[:, None, :] + V[:, None, :] * dt[None, :, None] + 0.5 * acc0[:, None, :] * (dt ** 2)[None, :, None]
        d = P - O[None, :, :]
        d /= np.linalg.norm(d, axis=2)[..., None]
        return np.stack([np.sum(d * t1[None], axis=2), np.sum(d * t2[None], axis=2)], axis=2).reshape(len(a_), -1)

    for _ in range(4):                                                              # Gauss-Newton on (a1, a2)
        r0 = resid(a)
        h = 1e-7
        J = np.stack([(resid(a + [h, 0.0]) - r0) / h, (resid(a + [0.0, h]) - r0) / h], axis=2)   # (C,2K,2)
        JT = np.transpose(J, (0, 2, 1))
        A = JT @ J + 1e-30 * np.eye(2)
        g = (JT @ r0[..., None])[..., 0]
        a = a - np.linalg.solve(A, g[..., None])[..., 0]
    r0 = resid(a)
    chi2_best = np.sum((r0 / sig) ** 2, axis=1)
    h = 1e-7
    J = np.stack([(resid(a + [h, 0.0]) - r0) / h, (resid(a + [0.0, h]) - r0) / h], axis=2)
    cov = sig ** 2 * np.linalg.inv(np.transpose(J, (0, 2, 1)) @ J + 1e-30 * np.eye(2))      # (C,2,2)
    L = np.linalg.cholesky(cov + 1e-40 * np.eye(2))
    # the best-fit velocity may break the orbit rules only because of noise: let it move within its errors
    # (z = offset in standard deviations; chi2 grows by |z|^2) and keep the smallest allowed chi2
    pen = np.full(len(a), np.inf)
    zz = np.arange(-3.0, 3.01, 0.5)
    for z1 in zz:
        for z2 in zz:
            q = z1 * z1 + z2 * z2
            if q > 9.0:
                continue
            az = a + (L @ np.array([z1, z2]))
            V = az[:, 0:1] * e1 + az[:, 1:2] * e2 + vr[:, None] * u0
            sp = np.linalg.norm(V, axis=1)
            gam = np.arcsin(np.clip(np.sum(V * P0, axis=1) / (sp * r), -1, 1))
            hvec = np.cross(P0, V)
            inc = np.degrees(np.arccos(np.clip(hvec[:, 2] / np.linalg.norm(hvec, axis=1), -1, 1)))
            ok = (sp >= SPEED_MIN * vc) & (sp <= SPEED_MAX * vc) & (np.abs(gam) <= GAMMA_MAX) & (inc <= i_max)
            pen = np.where(ok & (q < pen), q, pen)
    chi2 = chi2_best + pen
    n = len(t)
    if not np.isfinite(chi2).any():
        return None, None, None, "nofit"
    cmin = float(chi2.min())
    if cmin > 2 * n + 3 * math.sqrt(4 * n):
        return None, None, None, "nofit"
    keep = chi2 <= cmin + DCHI2
    return (float(D_[keep].min()), float(D_[keep].max()),
            {"delta": D_[keep], "r": r[keep], "P": P0[keep], "O": O0}, "ok")


def phase_term(alpha_rad):
    ta = np.tan(alpha_rad / 2.0)
    phi1, phi2 = np.exp(-3.33 * ta ** 0.63), np.exp(-1.87 * ta ** 1.22)
    return -2.5 * np.log10((1 - G_SLOPE) * phi1 + G_SLOPE * phi2)


def size_range(v_mag, v_sig, acc):
    """H range from V (+-1 sigma) over all accepted ranging solutions, then diameter with albedo 0.05-0.25."""
    d, r, P, O = acc["delta"], acc["r"], acc["P"], acc["O"]
    to_sun, to_obs = -P, O[None, :] - P
    cosa = np.sum(to_sun * to_obs, axis=1) / (np.linalg.norm(to_sun, axis=1) * np.linalg.norm(to_obs, axis=1))
    alpha = np.arccos(np.clip(cosa, -1, 1))
    Hs = v_mag - 5 * np.log10(r * d) - phase_term(alpha)
    hmin, hmax = float(Hs.min() - v_sig), float(Hs.max() + v_sig)
    dmin = 1329.0 / math.sqrt(ALB_MAX) * 10 ** (-hmax / 5)
    dmax = 1329.0 / math.sqrt(ALB_MIN) * 10 ** (-hmin / 5)
    return hmin, hmax, dmin, dmax


def sig2(x):
    if x is None:
        return None
    return round(x, 3) if x < 0.1 else (round(x, 2) if x < 10 else round(x, 1))


# ---------------- comets ----------------
def comet_positions(c, jd):
    """Heliocentric ecliptic J2000 positions of many comets at one time (two-body). c: dict of arrays."""
    e, q, inc, om, w, tp = c["e"], c["q"], np.radians(c["i"]), np.radians(c["om"]), np.radians(c["w"]), c["tp"]
    dt = jd - tp
    xp, yp = np.full(e.shape, np.nan), np.full(e.shape, np.nan)
    ell = e < 0.999
    a = q[ell] / (1 - e[ell])
    M = np.remainder(K_GAUSS / a ** 1.5 * dt[ell] + np.pi, 2 * np.pi) - np.pi
    E = np.where(e[ell] < 0.8, M + e[ell] * np.sin(M), np.pi * np.sign(M + 1e-30))
    for _ in range(80):
        E = E - (E - e[ell] * np.sin(E) - M) / (1 - e[ell] * np.cos(E))
    xp[ell], yp[ell] = a * (np.cos(E) - e[ell]), a * np.sqrt(1 - e[ell] ** 2) * np.sin(E)
    hyp = e > 1.001
    a = q[hyp] / (1 - e[hyp])
    M = K_GAUSS / (-a) ** 1.5 * dt[hyp]
    H = np.arcsinh(M / e[hyp])
    for _ in range(100):
        H = H - (e[hyp] * np.sinh(H) - H - M) / (e[hyp] * np.cosh(H) - 1)
    xp[hyp], yp[hyp] = a * (np.cosh(H) - e[hyp]), -a * np.sqrt(e[hyp] ** 2 - 1) * np.sinh(H)
    par = ~ell & ~hyp                                          # near-parabolic: Barker's equation
    W = 3 * K_GAUSS / math.sqrt(2) * dt[par] / q[par] ** 1.5
    Y = np.cbrt(W / 2 + np.sqrt(W ** 2 / 4 + 1))
    s = Y - 1 / Y                                              # tan(nu/2)
    xp[par], yp[par] = q[par] * (1 - s ** 2), 2 * q[par] * s
    co, so, ci, si, cw, sw = np.cos(om), np.sin(om), np.cos(inc), np.sin(inc), np.cos(w), np.sin(w)
    return np.stack([(co * cw - so * sw * ci) * xp + (-co * sw - so * cw * ci) * yp,
                     (so * cw + co * sw * ci) * xp + (-so * sw + co * cw * ci) * yp,
                     (sw * si) * xp + (cw * si) * yp], axis=-1)


def comet_check(D, jd, u, O):
    if D.comets is None:
        return "not checked (run fetch_comets.py)"
    c = D.comets["_arrays"]
    pos = comet_positions(c, jd)
    d = pos - O[None, :]
    d /= np.linalg.norm(d, axis=1)[:, None]
    sep = np.degrees(np.arccos(np.clip(d @ u, -1, 1)))
    sep[~np.isfinite(sep)] = 999
    k = int(np.argmin(sep))
    if sep[k] <= COMET_RADIUS_DEG:
        return "possible known comet: %s (%.2f deg away, two-body estimate)" % (c["name"][k], sep[k])
    return "no known comet within %.0f deg (nearest %s, %.1f deg)" % (COMET_RADIUS_DEG, c["name"][k], sep[k])


def load_comets(D):
    if D.comets is None:
        return
    j = D.comets
    f = j["fields"]
    rows = [r for r in j["data"] if all(r[f.index(k)] not in (None, "") for k in ("e", "q", "i", "om", "w", "tp"))]
    D.comets["_arrays"] = {k: np.array([float(r[f.index(k)]) for r in rows]) for k in ("e", "q", "i", "om", "w", "tp")}
    D.comets["_arrays"]["name"] = [r[f.index("full_name")].strip() for r in rows]


# ---------------- brightness ----------------
def v_estimate(D, pts):
    """V from the S/N at the detection in our difference image (fixed patches) or SNR layer (moving patches)."""
    vs, sigs = [], []
    for p in pts:
        fr = D.frames[p["fid"]]
        lay, path = ("DIFF_SNR", os.path.join("data", "diff", fr["patch"], fr["file"])) if fr["patch"] in FIXED \
            else ("SNR", os.path.join("data", "aligned", fr["patch"], fr["file"]))
        try:
            img = layer(path, lay)
        except Exception:                                    # noqa: BLE001
            continue
        iy, ix = int(round(p["y"])), int(round(p["x"]))
        box = img[max(0, iy - 2):iy + 3, max(0, ix - 2):ix + 3]
        if not np.isfinite(box).any():
            continue
        s = float(np.nanmax(box))
        if s <= 0.5:
            continue
        a, b, sd = D.calib.get(fr["det"], D.calib["all"])
        vs.append(a + b * (-2.5 * math.log10(s)))
        sigs.append(sd + (0.5 if fr["patch"] not in FIXED else 0.0))
    if not vs:
        return None, None
    return float(np.median(vs)), float(np.median(sigs))


# ---------------- main merge ----------------
def load_input(D, path):
    tracks, single, unknown_frames, raw = defaultdict(list), 0, 0, []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fid = frame_id(r["file"]) if r.get("file") else D.by_num.get((r["patch"], int(float(r["frame"]))))
            if fid not in D.frames:
                unknown_frames += 1
                continue
            pt = {"fid": fid, "x": float(r["x"]), "y": float(r["y"]), "snr": float(r["snr"]) if r.get("snr") else None,
                  "is_target": str(r.get("is_target", "0")).strip() in ("1", "true", "True"), "patch": r["patch"]}
            tracks[(r["patch"], str(r["track_id"]))].append(pt)
            raw.append(pt)
    out = {}
    for k, pts in tracks.items():
        pts.sort(key=lambda p: D.frames[p["fid"]]["mjd"])
        if len(pts) < 2:
            single += 1
            continue
        out[k] = pts
    return out, single, unknown_frames, raw


def match_track(D, patch, pts, pretend_unknown):
    hits, seps = [], []
    for p in pts:
        best = None
        for oid, name, x, y, v in D.labels.get(p["fid"], []):
            if oid in pretend_unknown:
                continue
            d = math.hypot(x - p["x"], y - p["y"])
            if d <= MATCH_PX and (best is None or d < best[0]):
                best = (d, oid, name, v)
        t = D.tri.get(p["fid"])
        if t and t["in_data"] and "3I" not in pretend_unknown:
            d = math.hypot(t["x"] - p["x"], t["y_np"] - p["y"])
            if d <= MATCH_PX and (best is None or d < best[0]):
                best = (d, "3I", "3I/ATLAS (C/2025 N1)", None)
        p["match"] = best
        if best:
            hits.append(best[1])
            seps.append(best[0])
    if not hits:
        return None, None
    oid, n = Counter(hits).most_common(1)[0]
    if n >= max(2, math.ceil(0.5 * len(pts))):
        return oid, float(np.median([p["match"][0] for p in pts if p["match"] and p["match"][1] == oid])) * 6.15
    return None, None


def sky_offsets(pts):
    ra = np.array([p["ra"] for p in pts])
    dec = np.array([p["dec"] for p in pts])
    ra0 = ra[0] + float(np.mean((ra - ra[0] + 180) % 360 - 180))
    dec0 = float(dec.mean())
    x = ((ra - ra0 + 180) % 360 - 180) * math.cos(math.radians(dec0)) * 3600.0     # arcsec east
    y = (dec - dec0) * 3600.0                                                      # arcsec north
    return ra0 % 360, dec0, x, y


def seg_sigma_px(D, seg):
    """Scatter of one burst's points around a straight line (px), or None if too few points."""
    if len(seg) < 4:
        return None
    t = np.array([D.frames[p["fid"]]["mjd"] for p in seg])
    if t.max() - t.min() < 1e-6:
        return None
    _, _, x, y = sky_offsets(seg)
    res = [v - np.polyval(np.polyfit(t - t.mean(), v, 1), t - t.mean()) for v in (x, y)]
    return math.sqrt(float(np.sum(np.square(res))) / max(1, 2 * len(seg) - 4)) / 6.15


def track_sigma(D, pts):
    """Position error used for ranging: 0.5 px, or the track's own per-burst scatter if larger."""
    by = defaultdict(list)
    for p in pts:
        by[D.frames[p["fid"]]["burst"]].append(p)
    s = [v for v in (seg_sigma_px(D, seg) for seg in by.values()) if v is not None]
    return max(SIGMA_PX, float(np.median(s))) if s else SIGMA_PX


def sky_motion(D, pts):
    """Mean time (h), mean position, motion vector (arcsec/h east, north) and its 1-sigma error."""
    t = np.array([D.frames[p["fid"]]["mjd"] for p in pts]) * 24.0
    ra0, dec0, x, y = sky_offsets(pts)
    tm = float(t.mean())
    ss = float(np.sum((t - tm) ** 2))
    if t.max() - t.min() < 1e-4:
        return {"tm": tm, "ra0": ra0, "dec0": dec0, "vx": None, "vy": None, "sv": float("inf")}
    vx = float(np.polyfit(t - tm, x, 1)[0])
    vy = float(np.polyfit(t - tm, y, 1)[0])
    return {"tm": tm, "ra0": ra0, "dec0": dec0, "vx": vx, "vy": vy,
            "sv": track_sigma(D, pts) * 6.15 / math.sqrt(ss)}


def link_candidates(cands):
    """Join candidate tracks of the same patch seen 1-48 h apart when the jump between them matches the earlier
    track's measured motion (within 3 sigma + 3"/h, motion measured to <= 70"/h) and the later track's own motion
    when it has one, and their brightness agrees (V within 1.5 mag). Returns groups of indices."""
    pairs = []
    for i, A in enumerate(cands):
        if A["vx"] is None or A["sv"] > MAX_LINK_RATE_SIGMA:
            continue
        for j, B in enumerate(cands):
            if j == i or B["patch"] != A["patch"]:
                continue
            dt = B["tm"] - A["tm"]
            if not 1.0 <= dt <= 48.0:
                continue
            dx = ((B["ra0"] - A["ra0"] + 180) % 360 - 180) * math.cos(math.radians(A["dec0"])) * 3600.0
            rx, ry = dx / dt, (B["dec0"] - A["dec0"]) * 3600.0 / dt
            if math.hypot(rx, ry) > 600:
                continue
            ea = math.hypot(rx - A["vx"], ry - A["vy"]) / (A["sv"] + 3.0)
            b_rate = B["vx"] is not None and B["sv"] <= MAX_LINK_RATE_SIGMA       # B without its own motion: A decides
            eb = math.hypot(rx - B["vx"], ry - B["vy"]) / (B["sv"] + 3.0) if b_rate else 0.0
            if A.get("v") is not None and B.get("v") is not None and abs(A["v"] - B["v"]) > MAX_LINK_DMAG:
                continue
            if ea <= 3.0 and eb <= 3.0:
                pairs.append((ea + eb, i, j))
    parent = list(range(len(cands)))

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k
    used_next, used_prev = set(), set()
    for _, i, j in sorted(pairs):
        if i in used_next or j in used_prev or find(i) == find(j):
            continue
        parent[find(j)] = find(i)
        used_next.add(i)
        used_prev.add(j)
    groups = defaultdict(list)
    for k in range(len(cands)):
        groups[find(k)].append(k)
    return list(groups.values())


def base_record(D, patch, tid, pts, oid, sep):
    mo = sky_motion(D, pts)
    rate = None if mo["vx"] is None else math.hypot(mo["vx"], mo["vy"])
    pa = None if mo["vx"] is None else math.degrees(math.atan2(mo["vx"], mo["vy"])) % 360.0
    snrs = [p["snr"] for p in pts if p["snr"] is not None]
    med_snr = float(np.median(snrs)) if snrs else 0.0
    score = (1 - math.exp(-med_snr / 10.0)) * min(1.0, len(pts) / 4.0)
    return {"track_id": tid, "patch": patch, "status": "known" if oid else "candidate", "object_id": oid,
            "match_sep_arcsec": None if sep is None else round(sep, 1),
            "motion_arcsec_per_hr": None if rate is None else round(rate, 2),
            "direction_deg": None if pa is None else round(pa, 1), "score": round(score, 2),
            "first_seen_utc": D.frames[pts[0]["fid"]]["utc"], "size_min_km": None, "size_max_km": None,
            "distance_min_au": None, "distance_max_au": None,
            "is_target_claimed": any(p["is_target"] for p in pts), "n_points": len(pts), "comet_check": None,
            "points": []}


def add_points(D, rec, pts, oid, vmag):
    for p in pts:
        fr = D.frames[p["fid"]]
        mag = None
        if oid and p.get("match") and p["match"][3] is not None and p["match"][1] == oid:
            mag = p["match"][3]
        elif not oid and vmag is not None:
            mag = round(vmag, 1)
        rec["points"].append({"frame_id": p["fid"], "x": round(p["x"], 2), "y": round((fr["n"] - 1) - p["y"], 2),
                              "ra": round(p["ra"], 6), "dec": round(p["dec"], 6), "mag": mag,
                              "is_target": p["is_target"]})


PHYS_KEYS = ("position_error_px", "arc_hours", "v_mag_est", "note", "distance_min_au", "distance_max_au",
             "size_min_km", "size_max_km", "H_range")


def candidate_physics(D, rec, pts, cache=None):
    """D2 distance range, V, size range and comet check for one (possibly linked) candidate."""
    jd = np.array([D.frames[p["fid"]]["mjd"] + 2400000.5 for p in pts])
    mv = equ_to_ecl(radec_vec(np.array([p["ra"] for p in pts]), np.array([p["dec"] for p in pts])))
    ob = np.array([D.observer(p["fid"]) for p in pts])
    key = "g|" + rec["patch"] + "|" + rec["track_id"]
    if cache is not None and key in cache.d:
        rec.update({k: v for k, v in cache.d[key].items() if k != "_vmag"})
        u = mv.mean(axis=0)
        rec["comet_check"] = comet_check(D, float(jd.mean()), u / np.linalg.norm(u), ob.mean(axis=0))
        return cache.d[key]["_vmag"]
    sig = track_sigma(D, pts)
    rec["position_error_px"] = round(sig, 2)
    rec["arc_hours"] = round(float(jd.max() - jd.min()) * 24.0, 2)
    dmin, dmax, acc, status = ranging(jd, mv, ob, sigma_px=sig,
                                      burst_ids=[D.frames[p["fid"]]["burst"] for p in pts])
    vmag, vsig = v_estimate(D, pts)
    rec["v_mag_est"] = None if vmag is None else round(vmag, 1)
    if status == "short":
        rec["note"] = "distance not constrained: all points at one moment (needs the object in 2+ photo times)"
    elif acc is None:
        rec["note"] = "no near-circular low-inclination orbit fits this motion (very close object, or not real)"
    elif dmin <= DELTA_GRID[0] * 1.001 or dmax >= DELTA_GRID[-1] * 0.999 or dmax / dmin > MAX_RANGE_RATIO:
        rec["note"] = ("distance not constrained: only %.0f min of motion (needs the object in 2+ bursts)"
                       % (rec["arc_hours"] * 60) if rec["arc_hours"] < 1 else
                       "distance not constrained: possible range %.2f-%.1f AU is too wide to show" % (dmin, dmax))
    else:
        rec["distance_min_au"], rec["distance_max_au"] = sig2(dmin), sig2(dmax)
        if vmag is not None:
            hmin, hmax, smin, smax = size_range(vmag, vsig, acc)
            rec["size_min_km"], rec["size_max_km"] = sig2(smin), sig2(smax)
            rec["H_range"] = [round(hmin, 1), round(hmax, 1)]
    u = mv.mean(axis=0)
    rec["comet_check"] = comet_check(D, float(jd.mean()), u / np.linalg.norm(u), ob.mean(axis=0))
    if cache is not None:
        cache.d[key] = dict({k: rec[k] for k in PHYS_KEYS if k in rec}, _vmag=vmag)
        cache.tick()
    return vmag


def process(D, inp, pretend_unknown=(), cache=None):
    tracks, single, unknown_frames, raw = load_input(D, inp)
    known_sizes = {o["object_id"]: o for o in D.objects}
    dets, cands = [], []
    for (patch, tid), pts in sorted(tracks.items(), key=lambda kv: D.frames[kv[1][0]["fid"]]["mjd"]):
        for p in pts:
            fr = D.frames[p["fid"]]
            p["ra"], p["dec"] = pix_to_radec(p["x"], p["y"], fr["gra"], fr["gdec"], fr["n"])
        oid, sep = match_track(D, patch, pts, set(pretend_unknown))
        if oid:
            rec = base_record(D, patch, tid, pts, oid, sep)
            o = known_sizes.get(oid)
            if o and o["size_min_km"]:
                rec["size_min_km"], rec["size_max_km"] = float(o["size_min_km"]), float(o["size_max_km"])
            add_points(D, rec, pts, oid, None)
            dets.append(rec)
        else:
            vk = "v|%s|%s" % (patch, tid)
            if cache is not None and vk in cache.d:
                v = cache.d[vk]
            else:
                v = v_estimate(D, pts)[0]
                if cache is not None:
                    cache.d[vk] = v
                    cache.tick()
            cands.append(dict(sky_motion(D, pts), patch=patch, tid=tid, pts=pts, v=v))
    cand_n = Counter()
    groups = link_candidates(cands)
    groups.sort(key=lambda g: min(D.frames[cands[i]["pts"][0]["fid"]]["mjd"] for i in g))
    for g in groups:
        pts = sorted([p for i in g for p in cands[i]["pts"]], key=lambda p: D.frames[p["fid"]]["mjd"])
        patch = cands[g[0]]["patch"]
        rec = base_record(D, patch, "+".join(cands[i]["tid"] for i in g), pts, None, None)
        cand_n[patch] += 1
        rec["object_id"] = "cand-%s-%03d" % (patch, cand_n[patch])
        rec["linked_tracks"] = len(g)
        vmag = candidate_physics(D, rec, pts, cache)
        add_points(D, rec, pts, None, vmag)
        dets.append(rec)
    dets.sort(key=lambda d: (d["first_seen_utc"], d["track_id"]))
    return dets, raw, single, unknown_frames


def scoring(D, dets, raw, single, unknown_frames, inp):
    """Scores use EVERY detection row (single-photo detections too): a lone sighting of 3I/ATLAS still counts."""
    pts_by_frame = defaultdict(list)
    for p in raw:
        pts_by_frame[p["fid"]].append(p)

    claims = any(p["is_target"] for p in raw)
    # input with no target claims (association output): the target is identified afterwards by position only

    def sel(p):
        return p["is_target"] if claims else True

    def target_score(truth_xy, patch_name):
        hit_vis = hit = 0
        errs, false_t = [], 0
        on = [f for f, t in truth_xy.items() if t["in_data"]]
        for f in on:
            t = truth_xy[f]
            cl = [p for p in pts_by_frame.get(f, []) if sel(p)]
            ds = [math.hypot(p["x"] - t["x"], p["y"] - t["y_np"]) for p in cl]
            if ds and min(ds) <= TARGET_PX:
                hit += 1
                hit_vis += 1 if t.get("visible") else 0
                errs.append(min(ds) * 6.15)
        for p in raw:
            if p["patch"] == patch_name and sel(p):
                t = truth_xy.get(p["fid"])
                if not t or math.hypot(p["x"] - t["x"], p["y"] - t["y_np"]) > TARGET_PX:
                    false_t += 1
        vis = sum(1 for f in on if truth_xy[f].get("visible"))
        return {"mode": "claimed points only" if claims else "position only: no point claims the target; every "
                "reported point in this patch counts, and points away from the target count as false",
                "frames_on_data": len(on), "frames_likely_visible": vis, "frames_found": hit,
                "score_vs_all_frames": round(hit / len(on), 3) if on else None,
                "score_vs_visible_frames": round(hit_vis / vis, 3) if vis else None,
                "false_target_points": false_t,
                "median_position_error_arcsec": round(float(np.median(errs)), 2) if errs else None}

    ceres = {}
    for f, labs in D.labels.items():
        if D.frames[f]["patch"] != "ceres":
            continue
        for oid, name, x, y, v in labs:
            if oid == "1":
                ceres[f] = {"x": x, "y_np": y, "in_data": True, "visible": True}
    rec = Counter()
    tot = Counter()
    for patch in ("ecliptic-virgo", "ecliptic-ra90"):
        for m in D.markers[patch]:
            if not m["likely_visible"]:
                continue
            fr = D.frames[m["frame_id"]]
            y_np = (fr["n"] - 1) - m["y"]
            vm = m["v_mag"] if m["v_mag"] is not None else 99.0
            vb = "V<15" if vm < 15 else ("V15-17" if vm < 17 else "V>=17")
            tot[vb] += 1
            if any(math.hypot(p["x"] - m["x"], p["y"] - y_np) <= MATCH_PX for p in pts_by_frame.get(m["frame_id"], [])):
                rec[vb] += 1
    by_patch = defaultdict(Counter)
    for d in dets:
        by_patch[d["patch"]][d["status"]] += 1
    return {
        "generated_utc": iso(datetime.now(timezone.utc)), "input_file": os.path.basename(inp),
        "rules": {"match_radius_px": MATCH_PX, "target_radius_px": TARGET_PX,
                  "track_min_points": 2,
                  "ranging": "D2 statistical ranging: near-circular orbit (speed %.1f-%.1f x circular, flight-path "
                             "angle <= %.0f deg), inclination <= %.0f deg, SPHEREx's real position; 95%% region "
                             "(delta chi2 %.2f); position error %.1f px or the track's own scatter; ranges wider than "
                             "%.0fx reported as not constrained"
                  % (SPEED_MIN, SPEED_MAX, math.degrees(GAMMA_MAX), I_MAX_DEG, DCHI2, SIGMA_PX, MAX_RANGE_RATIO),
                  "linking": "candidate tracks 1-48 h apart joined when the jump matches their motion and brightness"},
        "3I_ATLAS_blind_test": dict(target_score(D.tri, "3i-atlas"),
                                    note="a perfect detector finds 3I/ATLAS in the ~207 frames where it is visible "
                                         "(S/N >= 5): score_vs_visible_frames is the fair score"),
        "ceres_check": target_score(ceres, "ceres"),
        "known_asteroids_recovered": {k: {"recovered": rec[k], "visible": tot[k],
                                          "fraction": round(rec[k] / tot[k], 3) if tot[k] else None}
                                      for k in ("V<15", "V15-17", "V>=17")},
        "tracks": {"total": len(dets), "known": sum(d["status"] == "known" for d in dets),
                   "candidates": sum(d["status"] == "candidate" for d in dets),
                   "single_point_dropped": single, "rows_with_unknown_frame": unknown_frames,
                   "by_patch": {p: dict(c) for p, c in by_patch.items()}},
        "nep_note": "No known asteroid crosses the North Ecliptic Pole patch: every candidate there is either a rare "
                    "real object or a false alarm. Count them as the false-alarm test.",
    }


def write_objects(D, dets, out):
    keep = [o for o in D.objects if o["kind"] != "candidate"]
    cols = list(D.objects[0].keys())
    for d in dets:
        if d["status"] != "candidate":
            continue
        t = [p["frame_id"] for p in d["points"]]
        times = sorted(D.frames[f]["utc"] for f in t)
        keep.append({"object_id": d["object_id"], "name": "Candidate %s" % d["object_id"][5:], "kind": "candidate",
                     "status": "candidate", "H_mag": "" if "H_range" not in d else round(sum(d["H_range"]) / 2, 1),
                     "size_min_km": "" if d["size_min_km"] is None else d["size_min_km"],
                     "size_max_km": "" if d["size_max_km"] is None else d["size_max_km"],
                     "size_source": "estimated from brightness + approximate distance (albedo %.2f-%.2f)" % (ALB_MIN, ALB_MAX)
                     if d["size_min_km"] is not None else "unknown",
                     "distance_min_au": "" if d["distance_min_au"] is None else d["distance_min_au"],
                     "distance_max_au": "" if d["distance_max_au"] is None else d["distance_max_au"],
                     "show_in_3d": "true" if d["distance_min_au"] is not None else "false",
                     "patches": d["patch"], "n_frames": len(set(t)),
                     "first_utc": times[0], "last_utc": times[-1]})
    path = os.path.join(out, "objects.csv")
    with open(path + ".part", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(keep)
    os.replace(path + ".part", path)


def refresh_manifest():
    path = os.path.join(FRONT, "manifest.json")
    m = jload(path)
    files = []
    for root, _, fs in os.walk(FRONT):
        for f in fs:
            if f.endswith(".part") or f == "manifest.json":
                continue
            p = os.path.join(root, f)
            files.append({"path": os.path.relpath(p, FRONT).replace(os.sep, "/"), "bytes": os.path.getsize(p)})
    m["files"] = sorted(files, key=lambda d: d["path"])
    m["generated_utc"] = iso(datetime.now(timezone.utc))
    jsave(path, m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default=FRONT)
    ap.add_argument("--pretend-unknown", default="", help="test only: object ids to treat as unknown")
    ap.add_argument("--budget", type=float, default=150.0, help="seconds before saving progress and stopping")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    D = Data()
    load_comets(D)
    cache = Cache(a.input, a.budget)
    try:
        dets, raw, single, unknown = process(D, a.input, [x for x in a.pretend_unknown.split(",") if x], cache)
    except Budget:
        print("NOT DONE: %d results saved in %s - run the same command again" % (len(cache.d), cache.path))
        sys.exit(2)
    cache.save()
    sc = scoring(D, dets, raw, single, unknown, a.input)
    jsave(os.path.join(a.out, "detections.json"), dets)
    jsave(os.path.join(a.out, "scoring.json"), sc)
    write_objects(D, dets, a.out)
    if os.path.abspath(a.out) == os.path.abspath(FRONT):
        refresh_manifest()
    t3 = sc["3I_ATLAS_blind_test"]
    print("tracks %d (known %d, candidates %d, single-point dropped %d, unknown frames %d)"
          % (sc["tracks"]["total"], sc["tracks"]["known"], sc["tracks"]["candidates"], single, unknown))
    print("3I/ATLAS: found in %d of %d frames on data (%.0f%% of the %d visible) | false target points %d | error %s\""
          % (t3["frames_found"], t3["frames_on_data"], 100 * (t3["score_vs_visible_frames"] or 0),
             t3["frames_likely_visible"], t3["false_target_points"], t3["median_position_error_arcsec"]))
    print("known asteroids recovered:", {k: "%d/%d" % (v["recovered"], v["visible"])
                                         for k, v in sc["known_asteroids_recovered"].items()})
    for d in dets:
        if d["status"] == "candidate":
            print("  %s: %d pts in %d track(s), arc %.1f h, %.1f\"/h, V~%s, distance %s-%s AU, size %s-%s km%s"
                  % (d["object_id"], d["n_points"], d["linked_tracks"], d["arc_hours"], d["motion_arcsec_per_hr"] or 0,
                     d.get("v_mag_est"), d["distance_min_au"], d["distance_max_au"], d["size_min_km"],
                     d["size_max_km"], "" if "note" not in d else " | " + d["note"]))
    print("written to", a.out)


if __name__ == "__main__":
    main()
