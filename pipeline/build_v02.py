"""Specula v0.2 - build the 3D files for the frontend from the raw downloads in data/v02/ (made by fetch_v02.py).

Writes into handoff/frontend_data/:
  objects.csv               every known object in our photos (+ 3I/ATLAS): size range, show_in_3d, where/when seen
  orbits.json               orbit elements for those objects (NASA JPL SBDB) + the 8 planets (JPL Horizons)
  reference_positions.json  JPL Horizons true positions of Ceres, 370 Modestia, 3I/ATLAS (test answers)
  pointings.json            where SPHEREx looked for each of the 357 bursts + Earth's position
  cosmos.json               stars to V 6.5 (Yale Bright Star Catalogue), Milky Way band, ecliptic/galactic lines, labels
and updates manifest.json (version 0.2 + file list; history.json is not touched). Then runs the checks.
3D frame: heliocentric ecliptic J2000 (same as JPL), AU, degrees; orbit times JD TDB.
numpy only.   Run:  python build_v02.py          Checks only:  python build_v02.py --check
"""
import csv
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

import numpy as np

RAW = os.path.join("data", "v02")
OUT = os.path.join("handoff", "frontend_data")
PATCHES = ["ecliptic-virgo", "ecliptic-ra90", "nep-cats-eye", "ceres", "3i-atlas"]
EPS_DEG = 84381.448 / 3600.0            # J2000 obliquity of the ecliptic (JPL Horizons' ecliptic frame)
EPS = math.radians(EPS_DEG)
GAL = np.array([[-0.0548755604, -0.8734370902, -0.4838350155],      # ICRS -> galactic rotation
                [0.4941094279, -0.4448296300, 0.7469822445],          # (Hipparcos catalogue, ESA 1997)
                [-0.8676661490, -0.1980763734, 0.4559837762]])
ALB_MIN, ALB_MAX = 0.05, 0.25          # albedo range for sizes estimated from H
SIZE_3D_KM = 10.0                      # show_in_3d threshold (plus Ceres and 3I/ATLAS)
STAR_VMAX = 6.5
BAND_HALF_WIDTH_DEG = 10.0
PROPER_NAMES = [("Sirius", "Alp CMa"), ("Canopus", "Alp Car"), ("Arcturus", "Alp Boo"), ("Vega", "Alp Lyr"),
                ("Capella", "Alp Aur"), ("Rigel", "Bet Ori"), ("Procyon", "Alp CMi"), ("Betelgeuse", "Alp Ori"),
                ("Achernar", "Alp Eri"), ("Altair", "Alp Aql"), ("Aldebaran", "Alp Tau"), ("Antares", "Alp Sco"),
                ("Spica", "Alp Vir"), ("Pollux", "Bet Gem"), ("Fomalhaut", "Alp PsA"), ("Deneb", "Alp Cyg"),
                ("Regulus", "Alp Leo"), ("Polaris", "Alp UMi")]
SOURCES = {"sbdb": "NASA JPL Small-Body Database API (ssd-api.jpl.nasa.gov/sbdb.api)",
           "horizons": "NASA JPL Horizons API (ssd.jpl.nasa.gov/api/horizons.api)",
           "bsc": "Yale Bright Star Catalogue, 5th revised ed. (Hoffleit & Warren 1991, CDS V/50), JSON copy from "
                  "github.com/brettonw/YaleBrightStarCatalog"}


# ---------- small helpers ----------
def jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def jsave(path, obj):
    with open(path + ".part", "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(path + ".part", path)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def jd_from_iso(s):
    t = datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return 2440587.5 + t.timestamp() / 86400.0


def safe(oid):
    return oid.replace(" ", "_").replace("/", "-")


def r6(x, n=10):
    return float("%.*g" % (n, x))


def sig_round(x):
    return round(x, 2) if x < 10 else round(x, 1)


def radec_to_vec(ra, dec):
    ra, dec = np.radians(ra), np.radians(dec)
    return np.stack([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)], axis=-1)


def vec_to_radec(v):
    v = np.asarray(v, float)
    ra = np.degrees(np.arctan2(v[..., 1], v[..., 0])) % 360.0
    dec = np.degrees(np.arcsin(np.clip(v[..., 2] / np.linalg.norm(v, axis=-1), -1, 1)))
    return ra, dec


def equ_to_ecl(v):
    v = np.asarray(v, float)
    c, s = math.cos(EPS), math.sin(EPS)
    return np.stack([v[..., 0], c * v[..., 1] + s * v[..., 2], -s * v[..., 1] + c * v[..., 2]], axis=-1)


def ecl_to_equ(v):
    v = np.asarray(v, float)
    c, s = math.cos(EPS), math.sin(EPS)
    return np.stack([v[..., 0], c * v[..., 1] - s * v[..., 2], s * v[..., 1] + c * v[..., 2]], axis=-1)


def angle_deg(a, b):
    a = a / np.linalg.norm(a, axis=-1, keepdims=True)
    b = b / np.linalg.norm(b, axis=-1, keepdims=True)
    return np.degrees(np.arccos(np.clip(np.sum(a * b, axis=-1), -1, 1)))


# ---------- the same two-body maths the browser will do ----------
def kepler_xyz(o, jd):
    """Heliocentric ecliptic J2000 position (AU) from one orbits.json entry at JD TDB (array)."""
    jd = np.atleast_1d(np.asarray(jd, float))
    e, i, om, w = o["e"], math.radians(o["i_deg"]), math.radians(o["node_deg"]), math.radians(o["peri_deg"])
    n = math.radians(o["n_deg_day"])
    if o["orbit_type"] == "elliptic":
        a = o["a_au"]
        M = np.radians(o["M_deg"]) + n * (jd - o["epoch_jd_tdb"])
        M = np.remainder(M + np.pi, 2 * np.pi) - np.pi
        E = M + e * np.sin(M) if e < 0.8 else np.where(M == 0, 0.0, np.pi * np.sign(M))
        for _ in range(60):
            E = E - (E - e * np.sin(E) - M) / (1 - e * np.cos(E))
        xp, yp = a * (np.cos(E) - e), a * math.sqrt(1 - e * e) * np.sin(E)
    else:                                                     # hyperbolic (3I/ATLAS)
        a = o["q_au"] / (1 - e)                               # negative
        M = n * (jd - o["tp_jd_tdb"])
        H = np.arcsinh(M / e)
        for _ in range(100):
            H = H - (e * np.sinh(H) - H - M) / (e * np.cosh(H) - 1)
        xp, yp = a * (np.cosh(H) - e), -a * math.sqrt(e * e - 1) * np.sinh(H)
    co, so, ci, si, cw, sw = math.cos(om), math.sin(om), math.cos(i), math.sin(i), math.cos(w), math.sin(w)
    x = (co * cw - so * sw * ci) * xp + (-co * sw - so * cw * ci) * yp
    y = (so * cw + co * sw * ci) * xp + (-so * sw + co * cw * ci) * yp
    z = (sw * si) * xp + (cw * si) * yp
    return np.stack([x, y, z], axis=-1)


# ---------- inputs ----------
def load_timelines():
    tls = {p: jload(os.path.join(OUT, p, "timeline.json")) for p in PATCHES}
    ftime = {f["frame_id"]: f["time_utc"] for t in tls.values() for f in t["frames"]}
    return tls, ftime


def sbdb_elements(j):
    el = {e["name"]: e["value"] for e in j["orbit"]["elements"]}
    pp = {p["name"]: p for p in j.get("phys_par", [])}
    return el, pp


def fnum(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------- 1. objects.csv + orbits.json ----------
def build_objects(tls, ftime):
    seen = {}                                                    # object_id -> info from markers.json
    for p in PATCHES:
        for m in jload(os.path.join(OUT, p, "markers.json")):
            s = seen.setdefault(m["object_id"], {"name": m["name"], "patches": [], "frames": set()})
            if p not in s["patches"]:
                s["patches"].append(p)
            s["frames"].add(m["frame_id"])
    tri = [r for r in jload(os.path.join(OUT, "addons", "3i-atlas_markers.json")) if r["in_data"]]
    seen["3I"] = {"name": "3I/ATLAS (C/2025 N1)", "patches": ["3i-atlas"], "frames": {r["frame_id"] for r in tri}}

    rows, orbits, missing = [], [], []
    for oid in sorted(seen, key=lambda k: (not k.isdigit(), int(k) if k.isdigit() else 0, k)):
        s = seen[oid]
        path = os.path.join(RAW, "sbdb", safe(oid) + ".json")
        if not os.path.exists(path):
            missing.append(oid)
            continue
        el, pp = sbdb_elements(jload(path))
        kind = "dwarf_planet" if oid == "1" else ("interstellar" if oid == "3I" else "asteroid")
        H = fnum(pp["H"]["value"]) if "H" in pp else None
        size_min = size_max = None
        if "diameter" in pp and fnum(pp["diameter"]["value"]):
            d, sg = fnum(pp["diameter"]["value"]), fnum(pp["diameter"].get("sigma")) or 0.0
            size_min, size_max, src = sig_round(max(d - sg, 0.01)), sig_round(d + sg), "measured (JPL)"
        elif H is not None:
            size_min = sig_round(1329.0 / math.sqrt(ALB_MAX) * 10 ** (-H / 5))
            size_max = sig_round(1329.0 / math.sqrt(ALB_MIN) * 10 ** (-H / 5))
            src = "estimated from H (albedo %.2f-%.2f)" % (ALB_MIN, ALB_MAX)
        else:
            src = "unknown (comet: nucleus hidden by its coma)" if oid == "3I" else "unknown"
        show = oid in ("1", "3I") or (size_max is not None and size_max >= SIZE_3D_KM)
        times = sorted(ftime[f] for f in s["frames"])
        rows.append({"object_id": oid, "name": s["name"], "kind": kind, "status": "known",
                     "H_mag": "" if H is None else H,
                     "size_min_km": "" if size_min is None else size_min,
                     "size_max_km": "" if size_max is None else size_max, "size_source": src,
                     "distance_min_au": "", "distance_max_au": "", "show_in_3d": "true" if show else "false",
                     "patches": ";".join(s["patches"]), "n_frames": len(s["frames"]),
                     "first_utc": times[0], "last_utc": times[-1]})
        e = fnum(el["e"])
        tri = os.path.join(RAW, "horizons_3i_elements.json")
        if oid == "3I" and os.path.exists(tri):                  # orbit at 2025-10-15: best where our 3I photos are
            h = jload(tri)
            c = {k: v for k, v in zip(h["columns"], h["row"])}
            e = float(c["EC"])
            orbits.append({"object_id": oid, "name": s["name"], "e": r6(e), "i_deg": r6(float(c["IN"])),
                           "node_deg": r6(float(c["OM"])), "peri_deg": r6(float(c["W"])),
                           "n_deg_day": r6(float(c["N"])), "orbit_type": "hyperbolic", "q_au": r6(float(c["QR"])),
                           "a_au": r6(float(c["A"])), "tp_jd_tdb": r6(float(c["Tp"]), 15),
                           "elements_epoch_jd_tdb": h["epoch_jd_tdb"], "source": "JPL Horizons"})
            continue
        common = {"object_id": oid, "name": s["name"], "e": r6(e), "i_deg": r6(fnum(el["i"])),
                  "node_deg": r6(fnum(el["om"])), "peri_deg": r6(fnum(el["w"])), "n_deg_day": r6(fnum(el["n"]))}
        if e < 1:
            orbits.append(dict(common, orbit_type="elliptic", a_au=r6(fnum(el["a"])), M_deg=r6(fnum(el["ma"])),
                               epoch_jd_tdb=fnum(jload(path)["orbit"]["epoch"])))
        else:
            orbits.append(dict(common, orbit_type="hyperbolic", q_au=r6(fnum(el["q"])), a_au=r6(fnum(el["a"])),
                               tp_jd_tdb=r6(fnum(el["tp"]), 15)))
    return rows, orbits, missing


def build_planets():
    hp = jload(os.path.join(RAW, "horizons_planets_bary.json"))
    out = []
    for name, p in hp["planets"].items():
        c = {k: v for k, v in zip(p["columns"], p["row"])}
        label = "Earth (Earth-Moon barycentre)" if name == "earth" else name.capitalize()
        out.append({"object_id": "planet-" + name, "name": label, "orbit_type": "elliptic",
                    "a_au": r6(float(c["A"])), "e": r6(float(c["EC"])), "i_deg": r6(float(c["IN"])),
                    "node_deg": r6(float(c["OM"])), "peri_deg": r6(float(c["W"])), "M_deg": r6(float(c["MA"])),
                    "n_deg_day": r6(float(c["N"])), "epoch_jd_tdb": float(c["JDTDB"])})
    return out


# ---------- 2. reference_positions.json ----------
def build_reference(names, orbits):
    by = {o["object_id"]: o for o in orbits}
    hr = jload(os.path.join(RAW, "horizons_reference.json"))
    out = []
    for oid, o in hr["objects"].items():
        idx = {k: n for n, k in enumerate(o["columns"])}
        pos = [{"jd_tdb": float(r[idx["JDTDB"]]), "date_tdb": r[idx["Calendar Date (TDB)"]].replace("A.D. ", ""),
                "x_au": float(r[idx["X"]]), "y_au": float(r[idx["Y"]]), "z_au": float(r[idx["Z"]])} for r in o["rows"]]
        tb = kepler_xyz(by[oid], np.array([p["jd_tdb"] for p in pos]))
        for p, v in zip(pos, tb):
            p["two_body_x_au"], p["two_body_y_au"], p["two_body_z_au"] = [round(float(x), 9) for x in v]
            p["two_body_error_au"] = round(float(np.linalg.norm(v - [p["x_au"], p["y_au"], p["z_au"]])), 6)
        out.append({"object_id": oid, "name": names.get(oid, o["target"]), "positions": pos})
    return out


# ---------- 3. pointings.json ----------
def build_pointings(tls):
    he = jload(os.path.join(RAW, "horizons_earth.json"))
    idx = {k: n for n, k in enumerate(he["columns"])}
    allrows = [v["row"] for v in he["bursts"].values()]            # Horizons sorts rows by time: match by time
    rjd = np.array([float(r[0]) for r in allrows])
    out = []
    for p in PATCHES:
        t = tls[p]
        fov = round(t["patch"]["size_px"] * t["patch"]["pixel_scale_arcsec"] / 3600.0, 3)
        for b in t["bursts"]:
            jd_b = jd_from_iso(b["time_utc"])
            k = int(np.argmin(np.abs(rjd - jd_b)))
            if abs(rjd[k] - jd_b) > 2e-6:
                raise RuntimeError("no Earth position for burst %s" % b["burst_id"])
            r = allrows[k]
            d = equ_to_ecl(radec_to_vec(b["ra_center"], b["dec_center"]))
            out.append({"burst_id": b["burst_id"], "patch_id": p, "time_utc": b["time_utc"],
                        "jd": round(jd_from_iso(b["time_utc"]), 6), "ra_deg": b["ra_center"],
                        "dec_deg": b["dec_center"], "fov_deg": fov, "dir_ecl": [round(float(x), 7) + 0.0 for x in d],
                        "earth_au": [round(float(r[idx[k]]), 9) for k in ("X", "Y", "Z")]})
    out.sort(key=lambda x: x["time_utc"])
    return out


# ---------- 4. cosmos.json ----------
def hms(s):
    h, m, sec = [float(x) for x in re.findall(r"[\d.]+", s)[:3]]
    return 15.0 * (h + m / 60 + sec / 3600)


def dms(s):
    sign = -1.0 if s.strip().startswith("-") else 1.0
    d, m, sec = [float(x) for x in re.findall(r"[\d.]+", s)[:3]]
    return sign * (d + m / 60 + sec / 3600)


def gal_to_radec(l_deg, b_deg):
    v = radec_to_vec(np.asarray(l_deg), np.asarray(b_deg))           # same formula, galactic angles
    return vec_to_radec(v @ GAL)                                       # galactic -> ICRS = GAL transposed


def build_cosmos(tls):
    cat = jload(os.path.join(RAW, "bsc5", "bsc5.json"))
    stars, bright = [], {}
    for s in cat:
        v = fnum(s.get("Vmag"))
        if v is None or v > STAR_VMAX or not s.get("RA"):
            continue
        ra, dec = hms(s["RA"]), dms(s["Dec"])
        bv = fnum(s.get("B-V"))
        stars.append([round(ra, 4), round(dec, 4), v, None if bv is None else bv])
        bayer = re.sub(r"^\d+", "", (s.get("Name") or "")).strip()
        if bayer:
            bright.setdefault(bayer, []).append((ra, dec, v))
    stars.sort(key=lambda x: x[2])
    labels, lost = [], []
    for proper, bayer in PROPER_NAMES:
        hit = bright.get(bayer, [])
        if len(hit) != 1:
            lost.append(proper)
            continue
        labels.append({"text": proper, "kind": "star", "ra_deg": round(hit[0][0], 4), "dec_deg": round(hit[0][1], 4),
                       "vmag": hit[0][2]})
    for p in PATCHES:
        t = tls[p]
        bs = t["bursts"]
        mid = bs[len(bs) // 2]
        labels.append({"text": t["patch"]["name"], "kind": "patch", "patch_id": p, "moving": t["patch"]["kind"] == "moving",
                       "ra_deg": mid["ra_center"], "dec_deg": mid["dec_center"]})
    nep = vec_to_radec(ecl_to_equ(np.array([0.0, 0.0, 1.0])))
    labels.append({"text": "North Ecliptic Pole", "kind": "pole", "ra_deg": round(float(nep[0]), 4),
                   "dec_deg": round(float(nep[1]), 4)})
    labels.append({"text": "South Ecliptic Pole", "kind": "pole", "ra_deg": round((float(nep[0]) + 180) % 360, 4),
                   "dec_deg": round(-float(nep[1]), 4)})
    gc = gal_to_radec(0.0, 0.0)
    labels.append({"text": "Galactic Centre", "kind": "galaxy", "ra_deg": round(float(gc[0]), 4),
                   "dec_deg": round(float(gc[1]), 4)})
    lgrid = np.arange(0.0, 360.0, 2.0)
    gra, gdec = gal_to_radec(lgrid, np.zeros_like(lgrid))
    lam = np.radians(np.arange(0.0, 360.0, 2.0))
    era, edec = vec_to_radec(ecl_to_equ(np.stack([np.cos(lam), np.sin(lam), np.zeros_like(lam)], axis=-1)))
    return {
        "frame_note": "Star and line positions are RA/Dec J2000 (equatorial). To place them in the 3D scene "
                      "(heliocentric ecliptic J2000): unit vector (cos dec cos ra, cos dec sin ra, sin dec), then "
                      "rotate about x by -obliquity: x' = x, y' = y cos(eps) + z sin(eps), z' = -y sin(eps) + z cos(eps).",
        "obliquity_deg": round(EPS_DEG, 7),
        "source": {"stars": SOURCES["bsc"]},
        "star_columns": ["ra_deg", "dec_deg", "vmag", "bv"],
        "stars": stars,
        "galactic_band": {"half_width_deg": BAND_HALF_WIDTH_DEG,
                          "note": "the Milky Way as a band of this half-width around the galactic equator; "
                                  "points every 2 deg of galactic longitude l (0 = Galactic Centre)",
                          "columns": ["ra_deg", "dec_deg", "l_deg"],
                          "points": [[round(float(a), 4), round(float(d), 4), float(l)]
                                     for a, d, l in zip(gra, gdec, lgrid)]},
        "lines": {"ecliptic": [[round(float(a), 4), round(float(d), 4)] for a, d in zip(era, edec)],
                  "galactic_equator": [[round(float(a), 4), round(float(d), 4)] for a, d in zip(gra, gdec)]},
        "labels": labels,
    }, lost


# ---------- manifest ----------
def update_manifest():
    path = os.path.join(OUT, "manifest.json")
    m = jload(path)
    files = []
    for root, _, fs in os.walk(OUT):
        for f in fs:
            if f.endswith(".part") or f == "manifest.json":
                continue
            p = os.path.join(root, f)
            files.append({"path": os.path.relpath(p, OUT).replace(os.sep, "/"), "bytes": os.path.getsize(p)})
    files.sort(key=lambda d: d["path"])
    m["version"] = "0.2"
    m["generated_utc"] = iso(datetime.now(timezone.utc))
    m["files"] = files
    jsave(path, m)
    return len(files), sum(f["bytes"] for f in files)


# ---------- checks ----------
def checks():
    bad = []
    orb = jload(os.path.join(OUT, "orbits.json"))
    by = {o["object_id"]: o for o in orb["objects"] + orb["planets"]}
    ref = jload(os.path.join(OUT, "reference_positions.json"))
    print("1. Two-body orbit maths vs JPL Horizons (reference_positions.json):")
    worst = 0.0
    for o in ref["objects"]:
        jd = np.array([p["jd_tdb"] for p in o["positions"]])
        truth = np.array([[p["x_au"], p["y_au"], p["z_au"]] for p in o["positions"]])
        err = np.linalg.norm(kepler_xyz(by[o["object_id"]], jd) - truth, axis=1)
        worst = max(worst, float(err.max()))
        print("   %-24s errors (AU): %s" % (o["name"][:24], " ".join("%.5f" % x for x in err)))
    pts = jload(os.path.join(OUT, "pointings.json"))
    jd = np.array([p["jd"] for p in pts]) + 69.2 / 86400.0            # UTC -> TDB (69.2 s in 2025-26)
    earth = np.array([p["earth_au"] for p in pts])
    err = np.linalg.norm(kepler_xyz(by["planet-earth"], jd) - earth, axis=1)
    print("2. Earth from planet orbit vs Horizons, 357 bursts: median %.5f, max %.5f AU" % (np.median(err), err.max()))
    if err.max() > 0.002:
        bad.append("Earth orbit error %.4f AU" % err.max())
    for pid, oid, lim in (("ceres", "1", 0.05), ("3i-atlas", "3I", 0.45)):
        sel = [p for p in pts if p["patch_id"] == pid]
        jdp = np.array([p["jd"] for p in sel]) + 69.2 / 86400.0
        los = kepler_xyz(by[oid], jdp) - np.array([p["earth_au"] for p in sel])
        ang = angle_deg(los, np.array([p["dir_ecl"] for p in sel]))
        print("3. %s: angle between pointing and the object's direction from Earth, %d bursts: median %.3f, max %.3f deg"
              % (pid, len(sel), np.median(ang), ang.max()))
        if ang.max() > lim:
            bad.append("%s pointing off by %.3f deg" % (pid, ang.max()))
    cos = jload(os.path.join(OUT, "cosmos.json"))
    gc = next(x for x in cos["labels"] if x["text"] == "Galactic Centre")
    print("4. Galactic Centre at RA %.3f, Dec %.3f (expected about 266.405, -28.936)" % (gc["ra_deg"], gc["dec_deg"]))
    cat = [s for s in jload(os.path.join(RAW, "bsc5", "bsc5.json")) if s.get("RA") and s.get("GLON")]
    ra = np.array([hms(s["RA"]) for s in cat])
    dec = np.array([dms(s["Dec"]) for s in cat])
    gv = radec_to_vec(ra, dec) @ GAL.T
    gl, gb = vec_to_radec(gv)
    dl = np.abs((gl - np.array([float(s["GLON"]) for s in cat]) + 180) % 360 - 180) * np.cos(np.radians(gb))
    db = np.abs(gb - np.array([float(s["GLAT"]) for s in cat]))
    print("   galactic coords vs the catalogue's own GLON/GLAT, %d stars: median %.3f, max %.3f deg"
          % (len(cat), np.median(np.hypot(dl, db)), np.hypot(dl, db).max()))
    if np.median(np.hypot(dl, db)) > 0.05:
        bad.append("galactic transform")
    with open(os.path.join(OUT, "objects.csv"), newline="", encoding="utf-8") as f:
        objs = list(csv.DictReader(f))
    ids = {o["object_id"] for o in objs}
    mk = set()
    for p in PATCHES:
        mk |= {m["object_id"] for m in jload(os.path.join(OUT, p, "markers.json"))}
    print("5. objects.csv: %d objects (%d show_in_3d), every markers.json object listed: %s, every object has an orbit: %s"
          % (len(objs), sum(o["show_in_3d"] == "true" for o in objs), mk <= ids, ids <= set(by)))
    if not mk <= ids:
        bad.append("objects missing: %s" % sorted(mk - ids)[:10])
    if not ids <= set(by):
        bad.append("orbits missing")
    print("6. stars: %d (V <= %.1f), labels: %d" % (len(cos["stars"]), STAR_VMAX, len(cos["labels"])))
    print("\nCHECKS: " + ("ALL PASSED" if not bad else "PROBLEMS: " + "; ".join(bad)))
    return worst


def main():
    tls, ftime = load_timelines()
    rows, orbits, missing = build_objects(tls, ftime)
    planets = build_planets()
    names = {r["object_id"]: r["name"] for r in rows}
    cols = ["object_id", "name", "kind", "status", "H_mag", "size_min_km", "size_max_km", "size_source",
            "distance_min_au", "distance_max_au", "show_in_3d", "patches", "n_frames", "first_utc", "last_utc"]
    with open(os.path.join(OUT, "objects.csv.part"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(os.path.join(OUT, "objects.csv.part"), os.path.join(OUT, "objects.csv"))
    jsave(os.path.join(OUT, "orbits.json"), {
        "frame": "heliocentric ecliptic J2000 (same as JPL); AU, degrees, JD TDB",
        "how_to": "elliptic: M = M_deg + n_deg_day*(t - epoch_jd_tdb); solve E - e*sin(E) = M; x' = a(cos E - e), "
                  "y' = a*sqrt(1-e^2)*sin E. hyperbolic: M = n_deg_day*(t - tp_jd_tdb) (radians!); solve "
                  "e*sinh(H) - H = M; a = q/(1-e) < 0; x' = a(cosh H - e), y' = -a*sqrt(e^2-1)*sinh H. Then rotate "
                  "(x', y', 0) by peri, inclination, node (see the contract). t = JD TDB (UTC + 69.2 s).",
        "source": {"objects": SOURCES["sbdb"], "planets": SOURCES["horizons"] + " (osculating elements, planet centres)"},
        "objects": orbits, "planets": planets})
    ref = build_reference(names, orbits)
    jsave(os.path.join(OUT, "reference_positions.json"), {
        "frame": "heliocentric ecliptic J2000, AU", "time_scale": "TDB", "source": SOURCES["horizons"],
        "note": "x/y/z_au = JPL's true position (includes every planet's pull). two_body_*_au = what plain "
                "two-body maths from orbits.json gives (our solver). Test: your solver must match two_body_* to "
                "~1e-6 AU; two_body_error_au shows how far plain two-body maths is from the truth (invisible in 3D).",
        "objects": ref})
    pts = build_pointings(tls)
    jsave(os.path.join(OUT, "pointings.json"), pts)
    cosmos, lost = build_cosmos(tls)
    jsave(os.path.join(OUT, "cosmos.json"), cosmos)
    print("objects.csv %d rows | orbits %d objects + %d planets | reference %d objects | pointings %d bursts | "
          "cosmos %d stars, %d labels"
          % (len(rows), len(orbits), len(planets), len(ref), len(pts), len(cosmos["stars"]), len(cosmos["labels"])))
    if missing:
        print("NOT IN SBDB DOWNLOAD YET (%d): %s" % (len(missing), " ".join(missing)))
    if lost:
        print("proper names not matched: %s" % lost)
    worst = checks()
    r = jload(os.path.join(OUT, "reference_positions.json"))
    r["two_body_max_error_au"] = round(worst, 5)
    jsave(os.path.join(OUT, "reference_positions.json"), r)
    n, tot = update_manifest()
    print("manifest.json: version 0.2, %d files, %.1f MB" % (n, tot / 1e6))


if __name__ == "__main__":
    if "--check" in sys.argv:
        checks()
    else:
        main()
