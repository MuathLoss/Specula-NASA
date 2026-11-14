#!/usr/bin/env python3
"""
labels_spherex.py  -  Specula (NASA Space Apps 2026, "Planet X and SPHEREx")

Known-object labels: where every KNOWN asteroid/comet is in every frame of the fixed patches,
so the detector team can (a) train/test on real movers and (b) tell "new" from "already known".

For each FIXED patch (ecliptic-virgo, ecliptic-ra90, nep-cats-eye):
  1. GROUP the frames: frames taken within 15 min of each other form one group (= one SPHEREx burst).
  2. WHERE WAS SPHEREx? JPL Horizons gives SPHEREx's position + velocity (spacecraft ID -163182,
     relative to Earth's centre) at each group's mid-time. SPHEREx is 700 km up: for close asteroids
     that changes the apparent position, so we ask JPL from SPHEREx's real location, not from Earth.
  3. WHICH OBJECTS WERE IN VIEW? JPL's Small-Body Identification API (sb_ident, precise "two-pass" mode)
     lists every known asteroid/comet inside our square (+0.1 deg margin) with position, brightness (V)
     and motion ("/hour).
  4. Each object is moved to each frame's exact time with its motion, converted to a pixel (x, y)
     on the aligned grid, and checked against our data: is the pixel real data? what does the
     difference image show there (DIFF_SNR peak within 2 px)? seen = peak >= 5 within 1.5 px,
     on real data, not on a bright star.

Output (data/labels/<patch>/):
  labels.csv          one row per (frame, object) with the object inside the grid
  known_objects.csv   one row per object: frames on grid, frames seen, brightest V, motion
  jpl_cache/          the raw JPL answers (re-runs reuse them: nothing is asked twice)
  data/labels/labels_all.csv  all patches together

Pixel convention: x = column, y = row, 0-based, pixel centre = integer -> numpy data[round(y), round(x)].

Needs: python -m pip install astropy numpy      (internet: ssd.jpl.nasa.gov + ssd-api.jpl.nasa.gov)
Run from the Specula folder:
    python labels_spherex.py --plan                   # show the groups, no internet
    python labels_spherex.py --patch nep-cats-eye     # one patch first
    python labels_spherex.py                          # all three (resumes where it stopped)
"""
import argparse
import csv
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

FIXED = ["ecliptic-virgo", "ecliptic-ra90", "nep-cats-eye"]
SPHEREX_ID = "-163182"
HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"
SBIDENT = "https://ssd-api.jpl.nasa.gov/sb_ident.api"
GROUP_MIN = 15.0        # frames within 15 min of a group's first frame share one JPL query
PAD_DEG = 0.1           # search margin around the grid (objects move during a burst)
PIXEL_ARCSEC = 6.15
SEEN_SNR = 5.0
PEAK_R = 2              # look for the DIFF_SNR peak within +-2 px of the predicted position
SEEN_DIST = 1.5         # ... and call it "seen" only if that peak is within 1.5 px (JPL accuracy here ~0.3 px)
MJD0 = datetime(1858, 11, 17)
UA = {"User-Agent": "Specula-SpaceApps2026/1.0 (labels_spherex.py)"}

LABEL_FIELDS = ["frame", "patch", "obs_id", "detector", "t_mid_utc", "t_mid_mjd", "object", "kind",
                "ra_deg", "dec_deg", "x", "y", "in_data", "mask", "v_mag", "ra_rate_arcsec_h",
                "dec_rate_arcsec_h", "motion_px_per_min", "diff_snr_peak", "peak_dx", "peak_dy", "seen",
                "group", "file"]


def mjd_to_dt(m):
    return MJD0 + timedelta(days=m)


def dt_to_mjd(d):
    return (d - MJD0).total_seconds() / 86400.0


def get(url, params, timeout=900, tries=5):
    """GET -> parsed JSON, with patient retries (JPL is a shared public service)."""
    full = url + "?" + urllib.parse.urlencode(params)
    for k in range(1, tries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(full, headers=UA), timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code in (400, 404):
                raise RuntimeError("JPL refused the request (HTTP %d): %s" % (e.code, body))
            err = "HTTP %d" % e.code
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:   # ValueError: busy page, not JSON
            err = str(e)
        if k == tries:
            raise RuntimeError("JPL not reachable after %d tries: %s" % (tries, err))
        time.sleep(30 * k)


def hms(deg):
    """RA degrees -> 'hh-mm-ss.ss' (sb_ident format)."""
    s = (deg % 360.0) / 15.0 * 3600.0
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return "%02d-%02d-%05.2f" % (h, m, s)


def dms(deg):
    """Dec degrees -> 'dd-mm-ss.s', 'M' prefix for minus (sb_ident format)."""
    sign = "M" if deg < 0 else ""
    s = abs(deg) * 3600.0
    d, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return "%s%02d-%02d-%04.1f" % (sign, d, m, s)


def parse_ra(t):          # '11:58:11.68'
    h, m, s = t.split(":")
    return (float(h) + float(m) / 60 + float(s) / 3600) * 15.0


def parse_dec(t):         # '+00 09\'00.3"'  or '-00 20\'31.9"'
    t = t.strip().replace("'", " ").replace('"', " ")
    sign = -1.0 if t.startswith("-") else 1.0
    d, m, s = t.lstrip("+-").split()
    return sign * (float(d) + float(m) / 60 + float(s) / 3600)


def horizons_vectors(mjds):
    """SPHEREx geocentric state (km, km/s, ICRF) at UTC times (MJD). Returns {mjd: [x,y,z,vx,vy,vz]}."""
    out = {}
    for i in range(0, len(mjds), 40):
        chunk = mjds[i:i + 40]
        j = get(HORIZONS, {"format": "json", "COMMAND": "'%s'" % SPHEREX_ID, "EPHEM_TYPE": "VECTORS",
                           "CENTER": "'500@399'", "REF_PLANE": "FRAME", "OUT_UNITS": "KM-S", "VEC_TABLE": "2",
                           "CSV_FORMAT": "YES", "TIME_TYPE": "UT", "TLIST_TYPE": "MJD",
                           "TLIST": " ".join("'%.8f'" % m for m in chunk)}, timeout=300)
        res = j.get("result", "")
        if "$$SOE" not in res:
            raise RuntimeError("Horizons gave no vectors: %s" % (j.get("error") or res[-400:]))
        rows = [ln for ln in res.split("$$SOE")[1].split("$$EOE")[0].strip().splitlines() if ln.strip()]
        if len(rows) != len(chunk):
            raise RuntimeError("Horizons returned %d rows for %d times" % (len(rows), len(chunk)))
        for ln in rows:
            p = [x.strip() for x in ln.split(",")]
            jd = float(p[0])
            m = min(chunk, key=lambda c: abs(c + 2400000.5 - jd))
            if abs(m + 2400000.5 - jd) > 2e-6:
                raise RuntimeError("Horizons time mismatch: JD %s" % p[0])
            out["%.8f" % m] = [float(x) for x in p[2:8]]
    return out


def vnum(v):
    try:
        return float(v)
    except ValueError:
        return 99.0


def make_groups(frames):
    frames = sorted(frames, key=lambda r: float(r["t_mid_mjd"]))
    groups = []
    for r in frames:
        t = float(r["t_mid_mjd"])
        if not groups or (t - float(groups[-1][0]["t_mid_mjd"])) * 1440 > GROUP_MIN:
            groups.append([r])
        else:
            groups[-1].append(r)
    out = []
    for i, g in enumerate(groups, 1):
        ts = [float(r["t_mid_mjd"]) for r in g]
        d = mjd_to_dt((min(ts) + max(ts)) / 2)
        d = (d + timedelta(microseconds=500000)).replace(microsecond=0)   # whole second
        out.append({"key": "g%03d_%s" % (i, d.strftime("%Y%m%dT%H%M%S")), "time": d, "mjd": dt_to_mjd(d),
                    "frames": g, "span_min": (max(ts) - min(ts)) * 1440})
    return out


def main():
    p = argparse.ArgumentParser(description="Known asteroid/comet labels for the fixed patches (Specula).")
    p.add_argument("--aligned", default=os.path.join("data", "aligned"))
    p.add_argument("--diff", default=os.path.join("data", "diff"))
    p.add_argument("--out", default=os.path.join("data", "labels"))
    p.add_argument("--patch", action="append", help="one of: " + ", ".join(FIXED))
    p.add_argument("--vmag", type=float, default=21.0, help="faintest V magnitude to list (default 21)")
    p.add_argument("--workers", type=int, default=2, help="JPL queries at the same time (default 2, be polite)")
    p.add_argument("--plan", action="store_true", help="only show the groups (no internet)")
    p.add_argument("--offline", action="store_true", help="use cached JPL answers only")
    a = p.parse_args()
    try:
        import numpy as np
        from astropy.io import fits
        from astropy.wcs import WCS
        from astropy import log
    except ImportError:
        sys.exit("astropy is missing - run:  python -m pip install astropy numpy")
    log.setLevel("ERROR")
    warnings.simplefilter("ignore")
    patches = a.patch or FIXED
    for pt in patches:
        if pt not in FIXED:
            sys.exit("%s is not a fixed patch. Choose from: %s" % (pt, ", ".join(FIXED)))

    t_all = time.time()
    for patch in patches:
        idx = os.path.join(a.aligned, patch, "frames.csv")
        if not os.path.exists(idx):
            sys.exit("Missing %s - run align_spherex.py first." % idx)
        frames = list(csv.DictReader(open(idx, encoding="utf-8")))
        groups = make_groups(frames)
        out_dir = os.path.join(a.out, patch)
        cache = os.path.join(out_dir, "jpl_cache")

        # search box = the aligned grid (one grid per fixed patch) + margin
        f0 = frames[0]
        half = float(f0["grid_px"]) * PIXEL_ARCSEC / 3600 / 2 + PAD_DEG
        c_ra, c_dec = float(f0["grid_ra"]), float(f0["grid_dec"])
        half_ra = min(half / math.cos(math.radians(c_dec)), 10.0)
        print("\n%s: %d frames in %d groups (longest %.1f min) | search box %.2f x %.2f deg around %.4f %+.4f"
              % (patch, len(frames), len(groups), max(g["span_min"] for g in groups), 2 * half_ra, 2 * half,
                 c_ra, c_dec), flush=True)
        if a.plan:
            for g in groups[:5]:
                print("  %s  %d frames  %.1f min" % (g["key"], len(g["frames"]), g["span_min"]))
            print("  ...")
            continue
        os.makedirs(cache, exist_ok=True)

        # ---- 1. SPHEREx position at every group time (cached)
        hfile = os.path.join(cache, "horizons_spherex.json")
        hz = json.load(open(hfile)) if os.path.exists(hfile) else {}
        need = [g["mjd"] for g in groups if "%.8f" % g["mjd"] not in hz]
        if need and not a.offline:
            print("  JPL Horizons: SPHEREx position at %d times ..." % len(need), flush=True)
            hz.update(horizons_vectors(need))
            json.dump(hz, open(hfile + ".part", "w"), indent=0)
            os.replace(hfile + ".part", hfile)

        # ---- 2. objects in view per group (cached, a few at a time)
        def query(g):
            path = os.path.join(cache, g["key"] + ".json")
            if os.path.exists(path):
                return g["key"], json.load(open(path)), True
            if a.offline:
                return g["key"], None, True
            st = hz["%.8f" % g["mjd"]]
            j = get(SBIDENT, {"xobs": ",".join("%.6f" % v for v in st),
                              "obs-time": g["time"].strftime("%Y-%m-%d_%H:%M:%S"),
                              "fov-ra-center": hms(c_ra), "fov-dec-center": dms(c_dec),
                              "fov-ra-hwidth": "%.4f" % half_ra, "fov-dec-hwidth": "%.4f" % half,
                              "two-pass": "true", "suppress-first-pass": "true", "vmag-lim": "%g" % a.vmag})
            empty = "no matching" in str(j.get("warning", ""))          # JPL's answer when nothing is in view
            if not empty and "data_second_pass" not in j and "n_second_pass" not in j:
                raise RuntimeError("unexpected JPL answer: %s" % json.dumps(j)[:300])
            j["_specula"] = {"group": g["key"], "obs_time_utc": g["time"].isoformat(), "mjd": g["mjd"],
                             "xobs": st, "vmag_lim": a.vmag, "box": [c_ra, c_dec, half_ra, half]}
            json.dump(j, open(path + ".part", "w"))
            os.replace(path + ".part", path)
            return g["key"], j, False

        answers, t0, failed = {}, time.time(), []
        todo = [g for g in groups if "%.8f" % g["mjd"] in hz]
        n_cached = sum(os.path.exists(os.path.join(cache, g["key"] + ".json")) for g in todo)
        print("  JPL sb_ident: %d groups (%d cached, %d to ask, ~30-180 s each, %d at a time)"
              % (len(groups), n_cached, 0 if a.offline else len(todo) - n_cached, a.workers), flush=True)
        try:
            with ThreadPoolExecutor(max_workers=max(1, a.workers)) as pool:
                futs = {pool.submit(query, g): g for g in todo}
                for i, fut in enumerate(as_completed(futs), 1):
                    g = futs[fut]
                    try:
                        key, j, cached = fut.result()
                        answers[key] = j
                        if not cached:
                            print("    [%d/%d] %s  %d objects  (%.0f s since start)"
                                  % (i, len(futs), key, len(j.get("data_second_pass") or []),
                                     time.time() - t0), flush=True)
                    except Exception as e:  # noqa: BLE001
                        failed.append(g["key"])
                        print("    [%d/%d] %s  FAILED: %s" % (i, len(futs), g["key"], e), flush=True)
        except KeyboardInterrupt:
            sys.exit("\nStopped. Re-run the same command to continue (finished queries are cached).")

        # ---- 3. predicted pixel of every object in every frame
        wcs_cache = {}
        rows = []
        missing = [g["key"] for g in groups if answers.get(g["key"]) is None]
        for g in groups:
            j = answers.get(g["key"])
            if j is None:
                continue
            objs = []
            for d in j.get("data_second_pass") or []:
                name = d[0].strip()
                objs.append({"name": name, "ra": parse_ra(d[1]), "dec": parse_dec(d[2]),
                             "v": d[6].strip(), "rr": float(d[7]), "dr": float(d[8]),
                             "kind": "comet" if "/" in name.split("(")[0] else "asteroid"})
            for fr in g["frames"]:
                if not objs:
                    continue
                apath = os.path.join(a.aligned, patch, fr["file"])
                dpath = os.path.join(a.diff, patch, fr["file"])
                with fits.open(apath) as h:
                    gid = fr["grid_id"]
                    if gid not in wcs_cache:
                        wcs_cache[gid] = WCS(h["SCI"].header).celestial
                    w = wcs_cache[gid]
                    sci = h["SCI"].data
                    msk = h["MASK"].data
                dsnr = None
                if os.path.exists(dpath):
                    with fits.open(dpath) as h:
                        dsnr = h["DIFF_SNR"].data.astype(float)
                        msk = h["MASK"].data          # includes 32 = STAR_RESIDUE
                ny, nx = sci.shape
                dt_h = (float(fr["t_mid_mjd"]) - g["mjd"]) * 24.0
                for o in objs:
                    dec = o["dec"] + o["dr"] * dt_h / 3600.0
                    ra = o["ra"] + o["rr"] * dt_h / 3600.0 / math.cos(math.radians(o["dec"]))
                    x, y = (float(v) for v in w.world_to_pixel_values(ra, dec))
                    if not (-0.5 <= x < nx - 0.5 and -0.5 <= y < ny - 0.5):
                        continue
                    ix, iy = int(round(x)), int(round(y))
                    m = int(msk[iy, ix])
                    in_data = bool(np.isfinite(sci[iy, ix])) and not (m & 8)
                    peak, pdx, pdy = "", "", ""
                    if dsnr is not None:
                        y0, y1, x0, x1 = max(0, iy - PEAK_R), min(ny, iy + PEAK_R + 1), max(0, ix - PEAK_R), min(nx, ix + PEAK_R + 1)
                        box = dsnr[y0:y1, x0:x1]
                        if np.isfinite(box).any():
                            k = int(np.nanargmax(box))
                            by, bx = divmod(k, box.shape[1])
                            peak = float(box[by, bx])
                            pdx, pdy = x0 + bx - x, y0 + by - y
                    seen = (peak != "" and peak >= SEEN_SNR and math.hypot(pdx, pdy) <= SEEN_DIST
                            and in_data and not (m & 32))
                    rate = math.hypot(o["rr"], o["dr"]) / 60.0 / PIXEL_ARCSEC
                    rows.append({"frame": fr["frame"], "patch": patch, "obs_id": fr["obs_id"],
                                 "detector": fr["detector"], "t_mid_utc": fr["t_mid_utc"],
                                 "t_mid_mjd": fr["t_mid_mjd"], "object": o["name"], "kind": o["kind"],
                                 "ra_deg": "%.6f" % ra, "dec_deg": "%.6f" % dec, "x": "%.2f" % x, "y": "%.2f" % y,
                                 "in_data": int(in_data), "mask": m, "v_mag": o["v"],
                                 "ra_rate_arcsec_h": "%.3f" % o["rr"], "dec_rate_arcsec_h": "%.3f" % o["dr"],
                                 "motion_px_per_min": "%.4f" % rate,
                                 "diff_snr_peak": "" if peak == "" else "%.2f" % peak,
                                 "peak_dx": "" if pdx == "" else "%.2f" % pdx,
                                 "peak_dy": "" if pdy == "" else "%.2f" % pdy,
                                 "seen": int(seen), "group": g["key"], "file": fr["file"]})
        rows.sort(key=lambda r: (int(r["frame"]), r["object"]))
        with open(os.path.join(out_dir, "labels.csv"), "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=LABEL_FIELDS, lineterminator="\n")
            wr.writeheader()
            wr.writerows(rows)
        objs = {}
        for r in rows:
            o = objs.setdefault(r["object"], {"object": r["object"], "kind": r["kind"], "frames_on_grid": 0,
                                              "frames_in_data": 0, "frames_seen": 0, "v_brightest": 99.0,
                                              "first_utc": r["t_mid_utc"], "last_utc": r["t_mid_utc"],
                                              "motion_px_per_min": r["motion_px_per_min"]})
            o["frames_on_grid"] += 1
            o["frames_in_data"] += r["in_data"]
            o["frames_seen"] += r["seen"]
            try:
                o["v_brightest"] = min(o["v_brightest"], float(r["v_mag"]))
            except ValueError:
                pass
            o["first_utc"] = min(o["first_utc"], r["t_mid_utc"])
            o["last_utc"] = max(o["last_utc"], r["t_mid_utc"])
        ol = sorted(objs.values(), key=lambda o: (o["v_brightest"], o["object"]))
        with open(os.path.join(out_dir, "known_objects.csv"), "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=list(ol[0].keys()) if ol else ["object"], lineterminator="\n")
            wr.writeheader()
            wr.writerows(ol)

        seen = [r for r in rows if r["seen"]]
        offs = sorted(math.hypot(float(r["peak_dx"]), float(r["peak_dy"])) for r in seen)
        print("  -> %d groups answered (%d missing) | %d objects | %d labels on the grid, %d on real data, "
              "%d seen in the difference image (S/N >= %g)" % (len(groups) - len(missing), len(missing), len(objs),
                                                              len(rows), sum(r["in_data"] for r in rows), len(seen),
                                                              SEEN_SNR), flush=True)
        if offs:
            print("     seen objects: peak sits %.2f px (median) from the JPL position" % offs[len(offs) // 2])
        for lo, hi in ((0, 17), (17, 18), (18, 19), (19, 99)):
            b = [r for r in rows if r["in_data"] and not (r["mask"] & 32) and lo <= vnum(r["v_mag"]) < hi]
            if b:
                print("     V %4.1f-%-4.1f: seen in %3d of %4d frames on clean data (%.0f%%)"
                      % (lo, min(hi, 21.0), sum(r["seen"] for r in b), len(b), 100.0 * sum(r["seen"] for r in b) / len(b)))
        if missing:
            print("     re-run to finish: %d groups not answered yet" % len(missing))

    if not a.plan:
        # labels_all.csv = every patch that has a labels.csv (also from earlier runs)
        merged = []
        for pt in FIXED:
            fn = os.path.join(a.out, pt, "labels.csv")
            if os.path.exists(fn):
                merged += list(csv.DictReader(open(fn, encoding="utf-8")))
        if merged:
            with open(os.path.join(a.out, "labels_all.csv"), "w", newline="", encoding="utf-8") as f:
                wr = csv.DictWriter(f, fieldnames=LABEL_FIELDS, lineterminator="\n")
                wr.writeheader()
                wr.writerows(merged)
            print("labels_all.csv: %d rows" % len(merged))
    print("\nDone in %.1f min." % ((time.time() - t_all) / 60))


if __name__ == "__main__":
    main()
