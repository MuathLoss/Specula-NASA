#!/usr/bin/env python3
"""
labels_moving.py  -  Specula stage 7b (NASA Space Apps 2026, "Planet X and SPHEREx")

Known-object labels for the MOVING patches (ceres, 3i-atlas): where every known asteroid/comet is
in every photo, so the detector team can tell "already known" from "new" there too.

Same method as labels_spherex.py (and it reuses that script's tested JPL functions), except:
  * one JPL question per BURST: each burst has its own grid, so the search box moves with it
    (grid + 0.1 deg margin, centred on that burst's grid);
  * POSITIONS ONLY: these photos still contain the stars (no difference images), so "seen" is not
    measured. diff_snr_peak, peak_dx, peak_dy and seen are left blank (= not measured);
  * 3I/ATLAS IS NEVER LABELLED (it is scored blind). Two locks:
      1. name filter: "3I/..." or "2025 N1" is removed before anything is written;
      2. position check against answer_key_3i_atlas.csv (read here, on the data side only): any
         object within 3 px of the true comet in at least half of its photos is removed too.
    Removed rows go to scoring_private/withheld_3i-atlas.csv (never packaged).
  * Ceres IS labelled (declared target, not scored blind). Self-test: its label must sit on the
    brightest pixel of Ceres in the photo (median offset printed).

Output (data/labels/<patch>/): labels.csv, known_objects.csv, jpl_cache/  (same columns as stage 7)
Afterwards run labels_confirm.py (adds the confirmation columns and rebuilds labels_all.csv).

Run from the Specula folder (internet: ssd.jpl.nasa.gov + ssd-api.jpl.nasa.gov):
    python labels_moving.py --plan            # show the bursts, no internet
    python labels_moving.py                   # both patches (resumes where it stopped)
"""
import argparse
import csv
import json
import math
import os
import re
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import labels_spherex as L      # tested helpers: get, hms, dms, parse_ra, parse_dec, horizons_vectors ...

MOVING = ["ceres", "3i-atlas"]
WITHHOLD_NAME = re.compile(r"(^|[^0-9])3I/|2025 N1(?![0-9A-Z])")
WITHHOLD_PX = 3.0
ANSWER_KEY = "answer_key_3i_atlas.csv"
PRIVATE_DIR = "scoring_private"
CERES = "1 Ceres"


def make_bursts(frames):
    """One group per grid (= per burst). Query time = mid of the burst, whole second (UTC)."""
    by = {}
    for r in frames:
        by.setdefault(r["grid_id"], []).append(r)
    out = []
    for gid, fr in by.items():
        ts = [float(r["t_mid_mjd"]) for r in fr]
        d = L.mjd_to_dt((min(ts) + max(ts)) / 2)
        d = (d + timedelta(microseconds=500000)).replace(microsecond=0)
        f0 = fr[0]
        half = float(f0["grid_px"]) * L.PIXEL_ARCSEC / 3600 / 2 + L.PAD_DEG
        c_ra, c_dec = float(f0["grid_ra"]), float(f0["grid_dec"])
        out.append({"time": d, "mjd": L.dt_to_mjd(d), "frames": sorted(fr, key=lambda r: float(r["t_mid_mjd"])),
                    "span_min": (max(ts) - min(ts)) * 1440, "grid_id": gid, "c_ra": c_ra, "c_dec": c_dec,
                    "half": half, "half_ra": min(half / math.cos(math.radians(c_dec)), 10.0)})
    out.sort(key=lambda g: g["mjd"])
    for i, g in enumerate(out, 1):
        g["key"] = "g%03d_%s" % (i, g["time"].strftime("%Y%m%dT%H%M%S"))
    return out


def sep_px(ra1, dec1, ra2, dec2):
    """Angular distance in pixels (small-angle, fine for a few pixels)."""
    dra = (ra1 - ra2 + 180.0) % 360.0 - 180.0
    d = math.hypot(dra * math.cos(math.radians((dec1 + dec2) / 2)), dec1 - dec2)
    return d * 3600.0 / L.PIXEL_ARCSEC


def main():
    p = argparse.ArgumentParser(description="Known-object labels (positions only) for the moving patches.")
    p.add_argument("--aligned", default=os.path.join("data", "aligned"))
    p.add_argument("--out", default=os.path.join("data", "labels"))
    p.add_argument("--patch", action="append", help="one of: " + ", ".join(MOVING))
    p.add_argument("--vmag", type=float, default=21.0)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--plan", action="store_true", help="only show the bursts (no internet)")
    p.add_argument("--offline", action="store_true", help="use cached JPL answers only")
    a = p.parse_args()
    patches = a.patch or MOVING
    for pt in patches:
        if pt not in MOVING:
            sys.exit("%s is not a moving patch. Choose from: %s" % (pt, ", ".join(MOVING)))

    t_all = time.time()
    for patch in patches:
        idx = os.path.join(a.aligned, patch, "frames.csv")
        if not os.path.exists(idx):
            sys.exit("Missing %s" % idx)
        frames = list(csv.DictReader(open(idx, encoding="utf-8")))
        groups = make_bursts(frames)
        print("\n%s: %d frames in %d bursts (longest %.1f min) | search box %.2f deg (+%.1f margin) per burst"
              % (patch, len(frames), len(groups), max(g["span_min"] for g in groups),
                 2 * (groups[0]["half"] - L.PAD_DEG), L.PAD_DEG), flush=True)
        if a.plan:
            for g in groups[:5]:
                print("  %s  %d frames  %.1f min  centre %.4f %+.4f" % (g["key"], len(g["frames"]), g["span_min"],
                                                                       g["c_ra"], g["c_dec"]))
            print("  ...")
            continue

        try:
            import numpy as np
            from astropy.io import fits
            from astropy.wcs import WCS
            from astropy import log
        except ImportError:
            sys.exit("astropy is missing - run:  python -m pip install astropy numpy")
        log.setLevel("ERROR")
        warnings.simplefilter("ignore")

        out_dir = os.path.join(a.out, patch)
        cache = os.path.join(out_dir, "jpl_cache")
        os.makedirs(cache, exist_ok=True)

        # ---- 1. SPHEREx position at every burst time (cached)
        hfile = os.path.join(cache, "horizons_spherex.json")
        hz = json.load(open(hfile)) if os.path.exists(hfile) else {}
        need = [g["mjd"] for g in groups if "%.8f" % g["mjd"] not in hz]
        if need and not a.offline:
            print("  JPL Horizons: SPHEREx position at %d times ..." % len(need), flush=True)
            hz.update(L.horizons_vectors(need))
            json.dump(hz, open(hfile + ".part", "w"), indent=0)
            os.replace(hfile + ".part", hfile)

        # ---- 2. objects in view per burst (cached)
        def query(g):
            path = os.path.join(cache, g["key"] + ".json")
            if os.path.exists(path):
                return g["key"], json.load(open(path)), True
            if a.offline:
                return g["key"], None, True
            st = hz["%.8f" % g["mjd"]]
            j = L.get(L.SBIDENT, {"xobs": ",".join("%.6f" % v for v in st),
                                  "obs-time": g["time"].strftime("%Y-%m-%d_%H:%M:%S"),
                                  "fov-ra-center": L.hms(g["c_ra"]), "fov-dec-center": L.dms(g["c_dec"]),
                                  "fov-ra-hwidth": "%.4f" % g["half_ra"], "fov-dec-hwidth": "%.4f" % g["half"],
                                  "two-pass": "true", "suppress-first-pass": "true", "vmag-lim": "%g" % a.vmag})
            empty = "no matching" in str(j.get("warning", ""))
            if not empty and "data_second_pass" not in j and "n_second_pass" not in j:
                raise RuntimeError("unexpected JPL answer: %s" % json.dumps(j)[:300])
            j["_specula"] = {"group": g["key"], "grid_id": g["grid_id"], "obs_time_utc": g["time"].isoformat(),
                             "mjd": g["mjd"], "xobs": st, "vmag_lim": a.vmag,
                             "box": [g["c_ra"], g["c_dec"], g["half_ra"], g["half"]]}
            json.dump(j, open(path + ".part", "w"))
            os.replace(path + ".part", path)
            return g["key"], j, False

        answers, t0, failed = {}, time.time(), []
        todo = [g for g in groups if "%.8f" % g["mjd"] in hz]
        n_cached = sum(os.path.exists(os.path.join(cache, g["key"] + ".json")) for g in todo)
        print("  JPL sb_ident: %d bursts (%d cached, %d to ask, ~30-180 s each, %d at a time)"
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
                                  % (i, len(futs), key, len(j.get("data_second_pass") or []), time.time() - t0),
                                  flush=True)
                    except Exception as e:  # noqa: BLE001
                        failed.append(g["key"])
                        print("    [%d/%d] %s  FAILED: %s" % (i, len(futs), g["key"], e), flush=True)
        except KeyboardInterrupt:
            sys.exit("\nStopped. Re-run the same command to continue (finished queries are cached).")

        # ---- 3. predicted pixel of every object in every photo (positions only)
        key3i = {}
        if patch == "3i-atlas":
            if not os.path.exists(ANSWER_KEY):
                sys.exit("Missing %s - needed for the 3I/ATLAS position lock." % ANSWER_KEY)
            for r in csv.DictReader(open(ANSWER_KEY, encoding="utf-8")):
                key3i[(r["obs_id"], r["detector"])] = (float(r["comet_ra"]), float(r["comet_dec"]))
        wcs_cache, rows, held, ceres_off = {}, [], [], []
        missing = [g["key"] for g in groups if answers.get(g["key"]) is None]
        for g in groups:
            j = answers.get(g["key"])
            if j is None:
                continue
            objs = []
            for d in j.get("data_second_pass") or []:
                name = d[0].strip()
                objs.append({"name": name, "ra": L.parse_ra(d[1]), "dec": L.parse_dec(d[2]),
                             "v": d[6].strip(), "rr": float(d[7]), "dr": float(d[8]),
                             "kind": "comet" if "/" in name.split("(")[0] else "asteroid"})
            if not objs:
                continue
            for fr in g["frames"]:
                with fits.open(os.path.join(a.aligned, patch, fr["file"])) as h:
                    gid = fr["grid_id"]
                    if gid not in wcs_cache:
                        wcs_cache[gid] = WCS(h["SCI"].header).celestial
                    w = wcs_cache[gid]
                    sci = h["SCI"].data
                    msk = h["MASK"].data
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
                    rate = math.hypot(o["rr"], o["dr"]) / 60.0 / L.PIXEL_ARCSEC
                    row = {"frame": fr["frame"], "patch": patch, "obs_id": fr["obs_id"], "detector": fr["detector"],
                           "t_mid_utc": fr["t_mid_utc"], "t_mid_mjd": fr["t_mid_mjd"], "object": o["name"],
                           "kind": o["kind"], "ra_deg": "%.6f" % ra, "dec_deg": "%.6f" % dec,
                           "x": "%.2f" % x, "y": "%.2f" % y, "in_data": int(in_data), "mask": m,
                           "v_mag": o["v"], "ra_rate_arcsec_h": "%.3f" % o["rr"],
                           "dec_rate_arcsec_h": "%.3f" % o["dr"], "motion_px_per_min": "%.4f" % rate,
                           "diff_snr_peak": "", "peak_dx": "", "peak_dy": "", "seen": "",
                           "group": g["key"], "file": fr["file"]}
                    k = key3i.get((fr["obs_id"], fr["detector"]))
                    row["_sep"] = sep_px(ra, dec, k[0], k[1]) if k else None
                    if o["name"].startswith(CERES) and in_data:
                        # light-weighted centre of Ceres in a 7 x 7 box (saturated core is kept, MASK 16)
                        y0, y1, x0, x1 = max(0, iy - 3), min(ny, iy + 4), max(0, ix - 3), min(nx, ix + 4)
                        box = np.nan_to_num(sci[y0:y1, x0:x1].astype(float) - np.nanmedian(sci[y0:y1, x0:x1]))
                        box[box < 0] = 0.0
                        if box.sum() > 0:
                            yy, xx = np.mgrid[y0:y1, x0:x1]
                            cx, cy = (box * xx).sum() / box.sum(), (box * yy).sum() / box.sum()
                            ceres_off.append(math.hypot(cx - x, cy - y))
                    rows.append(row)

        # ---- 4. 3I/ATLAS locks
        n_name = n_pos = 0
        if patch == "3i-atlas":
            by_obj = {}
            for r in rows:
                by_obj.setdefault(r["object"], []).append(r)
            drop = set()
            for name, rs in by_obj.items():
                seps = [r["_sep"] for r in rs if r["_sep"] is not None]
                near = sum(s <= WITHHOLD_PX for s in seps)
                if WITHHOLD_NAME.search(name):
                    drop.add(name)
                    n_name += 1
                elif seps and near >= 0.5 * len(seps):
                    drop.add(name)
                    n_pos += 1
            held = [r for r in rows if r["object"] in drop]
            rows = [r for r in rows if r["object"] not in drop]
            if held:
                os.makedirs(PRIVATE_DIR, exist_ok=True)
                with open(os.path.join(PRIVATE_DIR, "withheld_3i-atlas.csv"), "w", newline="", encoding="utf-8") as f:
                    wr = csv.DictWriter(f, fieldnames=L.LABEL_FIELDS + ["sep_from_key_px"], extrasaction="ignore",
                                        lineterminator="\n")
                    wr.writeheader()
                    for r in held:
                        r["sep_from_key_px"] = "" if r["_sep"] is None else "%.2f" % r["_sep"]
                        wr.writerow(r)
            left = [r["_sep"] for r in rows if r["_sep"] is not None]
            closest = min(left) if left else float("nan")

        # ---- 5. write
        rows.sort(key=lambda r: (int(r["frame"]), r["object"]))
        with open(os.path.join(out_dir, "labels.csv"), "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=L.LABEL_FIELDS, extrasaction="ignore", lineterminator="\n")
            wr.writeheader()
            wr.writerows(rows)
        objs = {}
        for r in rows:
            o = objs.setdefault(r["object"], {"object": r["object"], "kind": r["kind"], "frames_on_grid": 0,
                                              "frames_in_data": 0, "frames_seen": "", "v_brightest": 99.0,
                                              "first_utc": r["t_mid_utc"], "last_utc": r["t_mid_utc"],
                                              "motion_px_per_min": r["motion_px_per_min"]})
            o["frames_on_grid"] += 1
            o["frames_in_data"] += r["in_data"]
            o["v_brightest"] = min(o["v_brightest"], L.vnum(r["v_mag"]))
            o["first_utc"] = min(o["first_utc"], r["t_mid_utc"])
            o["last_utc"] = max(o["last_utc"], r["t_mid_utc"])
        ol = sorted(objs.values(), key=lambda o: (o["v_brightest"], o["object"]))
        ocols = ["object", "kind", "frames_on_grid", "frames_in_data", "frames_seen", "v_brightest",
                 "first_utc", "last_utc", "motion_px_per_min"]
        with open(os.path.join(out_dir, "known_objects.csv"), "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=ocols, lineterminator="\n")
            wr.writeheader()
            wr.writerows(ol)

        kinds = {}
        for o in ol:
            kinds[o["kind"]] = kinds.get(o["kind"], 0) + 1
        print("  -> %d bursts answered (%d missing) | %d objects %s | %d labels on the grid, %d on real data"
              % (len(groups) - len(missing), len(missing), len(ol), kinds, len(rows),
                 sum(r["in_data"] for r in rows)), flush=True)
        if patch == "ceres":
            if ceres_off:
                s = sorted(ceres_off)
                ok = s[len(s) // 2] <= 0.75
                print("     self-test: Ceres labelled in %d photos; label sits %.2f px (median), %.2f px (max) from "
                      "Ceres's measured centre -> %s" % (len(s), s[len(s) // 2], s[-1], "PASS" if ok else "CHECK"))
            else:
                print("     self-test: Ceres NOT found in the JPL answers -> CHECK")
        if patch == "3i-atlas":
            print("     3I/ATLAS lock: %d object(s) withheld by name, %d by position (%d rows -> %s/)"
                  % (n_name, n_pos, len(held), PRIVATE_DIR))
            print("     closest remaining label to the true comet: %.1f px (must be > %.0f)" % (closest, WITHHOLD_PX))
        if missing:
            print("     re-run to finish: %d bursts not answered yet" % len(missing))
    print("\nDone in %.1f min. Next: python labels_confirm.py" % ((time.time() - t_all) / 60))


if __name__ == "__main__":
    main()
