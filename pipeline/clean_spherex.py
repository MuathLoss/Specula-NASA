#!/usr/bin/env python3
"""
clean_spherex.py  -  Specula (NASA Space Apps 2026, "Planet X and SPHEREx")

Cleans every cropped photo in data/cut/ and writes data/clean/, one photo at a time:

  1. FLAGS    -> decide which pixels to trust
                 BAD       (instrument problems / artifacts)   -> set to NaN
                 SATURATED (OVERFLOW, NONLINEAR, BLOOM, plus SUR_ERROR next to them, or > 20x the noise
                            with a bright glow of normal pixels within 2 px: the core of a very bright object
                            such as Ceres) -> kept (value is a lower limit), marked
                 SUSPECT   (TRANSIENT, OUTLIER: cosmic ray... or a moving asteroid!) -> kept, marked
                 SOURCE    (a star/galaxy is here)            -> kept, marked (information only)
  2. ZODI     -> subtract the solar-system dust glow:  SCI = IMAGE - ZODI
  3. VARIANCE -> noise map ERR = sqrt(VARIANCE), and SNR = (SCI - sky level) / ERR

Output layers (same pixel grid and sky/detector/wavelength maps as the crop):
  SCI   cleaned brightness (MJy/sr), NaN where not trustworthy
  ERR   1-sigma noise per pixel (MJy/sr)
  SNR   signal-to-noise per pixel above the sky level: (SCI - BKG_MED) / ERR
  MASK  our simple mask: 1 = BAD, 2 = SUSPECT, 4 = SOURCE, 8 = NO DATA, 16 = SATURATED (kept)
  FLAGS NASA's original 32-bit flags (unchanged, for reference)
  ZODI  the glow that was subtracted (SCI + ZODI = original IMAGE)
  PSF/EPSF, WCS-WAVE   copied unchanged

Needs: python -m pip install astropy numpy
Run from the Specula folder:
    python clean_spherex.py --limit 3     # 3 photos per patch first
    python clean_spherex.py               # everything (finished ones are skipped)
"""
import argparse
import csv
import os
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

# NASA flag bits (same numbers in QR2 and QR3; the names are also read from each file's header)
DEFAULT_BITS = {"TRANSIENT": 0, "OVERFLOW": 1, "SUR_ERROR": 2, "PHANTOM": 4, "REFERENCE": 5, "NONFUNC": 6,
                "DICHROIC": 7, "MISSING_DATA": 9, "HOT": 10, "COLD": 11, "FULLSAMPLE": 12, "PHANMISS": 14,
                "NONLINEAR": 15, "PERSIST": 17, "OUTLIER": 19, "CROSSTALK": 20, "SOURCE": 21, "GHOST": 22,
                "GHOST_FPA": 23, "GHOST_EXT": 24, "STREAK": 25, "BLOOM": 26, "SNOWBALL": 27, "HALO": 28}
BAD = ["PHANTOM", "REFERENCE", "NONFUNC", "DICHROIC", "MISSING_DATA", "HOT", "COLD", "PHANMISS", "PERSIST",
       "CROSSTALK", "GHOST", "GHOST_FPA", "GHOST_EXT", "STREAK", "SNOWBALL", "HALO"]
SATURATE = ["OVERFLOW", "NONLINEAR", "BLOOM"]   # real light, too bright to measure exactly -> keep + mark
SUR = ["SUR_ERROR"]                              # bad, unless next to saturation or very bright (then saturated)
SUSPECT = ["TRANSIENT", "OUTLIER"]
INFO = ["SOURCE"]
M_BAD, M_SUSPECT, M_SOURCE, M_NODATA, M_SAT = 1, 2, 4, 8, 16

LOG_FIELDS = ["patch", "obs_id", "detector", "status", "pct_bad", "pct_sat", "pct_suspect", "pct_nodata", "zodi_med",
              "sci_bkg_med", "err_med", "pct_snr5", "mb", "seconds", "error"]


def flag_bits(header):
    """Name -> bit number, read from the FLAGS header (QR2: MP_NAME = bit, QR3: MSKNnnnn = NAME)."""
    bits = dict(DEFAULT_BITS)
    for k, v in header.items():
        if k.startswith("MP_") and isinstance(v, int):
            bits[k[3:]] = v
        elif k.startswith("MSKN") and k[4:].isdigit():
            bits[str(v).strip()] = int(k[4:])
    return bits


def mask_of(flags, bits, names):
    m = 0
    for n in names:
        if n in bits:
            m |= 1 << bits[n]
    return (flags.astype(np.int64) & m) != 0


def grow(m):
    """m plus its 8 neighbours (a 3x3 dilation, numpy only)."""
    g = m.copy()
    g[1:, :] |= m[:-1, :]
    g[:-1, :] |= m[1:, :]
    g[:, 1:] |= m[:, :-1]
    g[:, :-1] |= m[:, 1:]
    g[1:, 1:] |= m[:-1, :-1]
    g[:-1, :-1] |= m[1:, 1:]
    g[1:, :-1] |= m[:-1, 1:]
    g[:-1, 1:] |= m[1:, :-1]
    return g


def clean_one(src, dst, rec):
    from astropy import log
    from astropy.io import fits
    log.setLevel("ERROR")
    warnings.simplefilter("ignore")
    t0 = time.time()
    with fits.open(src, memmap=False) as h:
        img = h["IMAGE"].data.astype(np.float32)
        var = h["VARIANCE"].data.astype(np.float32)
        zodi = h["ZODI"].data.astype(np.float32)
        flags = h["FLAGS"].data
        bits = flag_bits(h["FLAGS"].header)

        hard_bad = mask_of(flags, bits, BAD)
        sat_core = mask_of(flags, bits, SATURATE)
        sur = mask_of(flags, bits, SUR)
        near_sat = grow(sat_core)
        with np.errstate(invalid="ignore"):
            noise = float(np.nanmedian(np.sqrt(var[np.isfinite(var) & (var > 0)]))) if np.isfinite(var).any() else 0.0
            very_bright = (img - zodi) > 20.0 * noise       # far above the noise: the core of a bright object
            # a real bright object has a glow of normal (unflagged) bright pixels around its core;
            # an isolated glitch does not
            wing = very_bright & ~sur & ~hard_bad & ~sat_core
        keep_sur = sur & (near_sat | (very_bright & grow(grow(wing))))   # bright core with a glow = saturation
        bad = hard_bad | (sur & ~keep_sur)                  # SUR_ERROR anywhere else = a real readout failure
        sat = (sat_core | keep_sur) & ~bad                  # saturated core of a bright object: keep, mark
        suspect = mask_of(flags, bits, SUSPECT)
        source = mask_of(flags, bits, INFO)
        nodata = ~np.isfinite(img) | ~np.isfinite(var) | ~np.isfinite(zodi) | (var <= 0)
        drop = bad | nodata

        sci = img - zodi
        sci[drop] = np.nan
        with np.errstate(invalid="ignore", divide="ignore"):
            err = np.sqrt(var)
        err[drop] = np.nan
        mask = (bad * M_BAD | suspect * M_SUSPECT | source * M_SOURCE | nodata * M_NODATA | sat * M_SAT).astype(np.uint8)

        good_bg = ~drop & ~source & ~suspect & ~sat
        zodi_med = float(np.nanmedian(zodi[~nodata])) if (~nodata).any() else float("nan")
        bkg_med = float(np.nanmedian(sci[good_bg])) if good_bg.any() else 0.0
        # S/N above the remaining sky level (glow the ZODI model does not cover, e.g. the Milky Way)
        with np.errstate(invalid="ignore", divide="ignore"):
            snr = (sci - bkg_med) / err
        err_med = float(np.nanmedian(err[~drop])) if (~drop).any() else float("nan")
        valid = ~drop
        pct = lambda m: 100.0 * float(m.sum()) / m.size
        pct_snr5 = 100.0 * float((snr[valid] > 5).sum()) / max(1, int(valid.sum()))

        # check: on kept pixels, SCI + ZODI must give back the original IMAGE
        if valid.any() and not np.allclose(sci[valid] + zodi[valid], img[valid], rtol=1e-5, atol=1e-6):
            raise ValueError("SCI + ZODI does not reproduce IMAGE")

        hdr = h["IMAGE"].header.copy()
        hdr["BUNIT"] = "MJy / sr"
        hdr["CLEANED"] = (True, "Specula clean_spherex.py")
        hdr["ZODISUB"] = (True, "SCI = IMAGE - ZODI")
        hdr["ZODI_MED"] = (round(zodi_med, 6), "[MJy/sr] median zodiacal glow removed")
        hdr["BKG_MED"] = (round(bkg_med, 6), "[MJy/sr] median SCI of clean empty-sky pixels")
        hdr["ERR_MED"] = (round(err_med, 6), "[MJy/sr] median 1-sigma noise")
        hdr["PCT_BAD"] = (round(pct(bad), 3), "% pixels BAD (set to NaN)")
        hdr["PCT_SAT"] = (round(pct(sat), 3), "% pixels SATURATED (kept, lower limit)")
        hdr["PCT_SUSP"] = (round(pct(suspect), 3), "% pixels SUSPECT (kept)")
        hdr["PCT_NOD"] = (round(pct(nodata), 3), "% pixels NO DATA")
        hdr["MASK1"] = ("BAD", "MASK bit value 1: " + ",".join(BAD)[:40])
        hdr["MASK2"] = ("SUSPECT", "MASK bit value 2: TRANSIENT, OUTLIER")
        hdr["MASK4"] = ("SOURCE", "MASK bit value 4: star/galaxy present")
        hdr["MASK8"] = ("NODATA", "MASK bit value 8: outside photo or no value")
        hdr["MASK16"] = ("SATURATED", "MASK bit value 16: too bright, value is a lower limit")

        def layer(data, name, unit, comment):
            hh = hdr.copy()
            hh["BUNIT"] = unit
            hh["CONTENT"] = comment
            return fits.ImageHDU(data, header=hh, name=name)

        out = fits.HDUList([fits.PrimaryHDU(header=h[0].header)])
        out.append(layer(sci.astype(np.float32), "SCI", "MJy / sr", "cleaned brightness"))
        out.append(layer(err.astype(np.float32), "ERR", "MJy / sr", "1-sigma noise"))
        out.append(layer(snr.astype(np.float32), "SNR", "", "signal-to-noise = (SCI - BKG_MED) / ERR"))
        out.append(layer(mask, "MASK", "", "1=BAD 2=SUSPECT 4=SOURCE 8=NODATA 16=SATURATED"))
        out.append(fits.ImageHDU(flags, header=h["FLAGS"].header.copy(), name="FLAGS"))
        out.append(fits.ImageHDU(zodi, header=h["ZODI"].header.copy(), name="ZODI"))
        names = [x.name for x in h]
        for name in ("PSF", "EPSF", "WCS-WAVE"):
            if name in names:
                out.append(h[name].copy())

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        out.writeto(dst + ".part", overwrite=True)
    os.replace(dst + ".part", dst)
    rec.update({"status": "ok", "pct_bad": "%.3f" % pct(bad), "pct_sat": "%.3f" % pct(sat), "pct_suspect": "%.3f" % pct(suspect),
                "pct_nodata": "%.3f" % pct(nodata), "zodi_med": "%.5f" % zodi_med, "sci_bkg_med": "%.5f" % bkg_med,
                "err_med": "%.5f" % err_med, "pct_snr5": "%.2f" % pct_snr5,
                "mb": "%.2f" % (os.path.getsize(dst) / 1e6), "seconds": "%.2f" % (time.time() - t0), "error": ""})
    return rec


def safe_clean(job):
    src, dst, rec = job
    try:
        return clean_one(src, dst, dict(rec))
    except Exception as e:  # noqa: BLE001
        try:
            os.remove(dst + ".part")
        except OSError:
            pass
        r = dict(rec)
        r.update({"status": "failed", "error": ("%s: %s" % (type(e).__name__, e))[:300]})
        return r


def main():
    p = argparse.ArgumentParser(description="Clean the cropped SPHEREx photos (Specula).")
    p.add_argument("--manifest", default="manifest_all.csv")
    p.add_argument("--cut", default=os.path.join("data", "cut"))
    p.add_argument("--out", default=os.path.join("data", "clean"))
    p.add_argument("--log", default="clean_log.csv")
    p.add_argument("--patch", action="append")
    p.add_argument("--limit", type=int, help="only the first N photos of each patch")
    p.add_argument("--workers", type=int, default=max(1, min(4, (os.cpu_count() or 2) - 1)))
    p.add_argument("--redo", action="store_true")
    a = p.parse_args()
    try:
        import astropy  # noqa: F401
    except ImportError:
        sys.exit("astropy is missing - run:  python -m pip install astropy numpy")
    if not os.path.exists(a.manifest):
        sys.exit("Cannot find %s - run this script from the Specula folder." % a.manifest)

    rows = list(csv.DictReader(open(a.manifest, newline="", encoding="utf-8")))
    if a.patch:
        rows = [r for r in rows if r["patch"] in a.patch]
    if a.limit:
        per, kept = {}, []
        for r in rows:
            per[r["patch"]] = per.get(r["patch"], 0) + 1
            if per[r["patch"]] <= a.limit:
                kept.append(r)
        rows = kept

    jobs, skipped, missing = [], 0, []
    for r in rows:
        name = "%s_%s.fits" % (r["obs_id"], r["detector"])
        src, dst = os.path.join(a.cut, r["patch"], name), os.path.join(a.out, r["patch"], name)
        rec = {"patch": r["patch"], "obs_id": r["obs_id"], "detector": r["detector"]}
        if not os.path.exists(src):
            missing.append(src)
        elif os.path.exists(dst) and not a.redo:
            skipped += 1
        else:
            jobs.append((src, dst, rec))
    print("Photos: %d | already cleaned: %d | missing crops: %d | to clean now: %d | workers: %d"
          % (len(rows), skipped, len(missing), len(jobs), a.workers), flush=True)
    if missing:
        print("  e.g. missing:", missing[0], "(run crop_spherex.py first)")

    if os.path.dirname(a.log):
        os.makedirs(os.path.dirname(a.log), exist_ok=True)
    if os.path.exists(a.log):
        with open(a.log, encoding="utf-8") as f:
            same_columns = f.readline().strip().split(",") == LOG_FIELDS
        if a.redo or not same_columns:                 # start a fresh log; keep the old one as .bak
            os.replace(a.log, a.log + ".bak")
    new_log = not os.path.exists(a.log)
    logf = open(a.log, "a", newline="", encoding="utf-8")
    log = csv.DictWriter(logf, fieldnames=LOG_FIELDS, extrasaction="ignore", lineterminator="\n")
    if new_log:
        log.writeheader()

    t0, results = time.time(), []
    try:
        with ProcessPoolExecutor(max_workers=max(1, a.workers)) as pool:
            futs = [pool.submit(safe_clean, j) for j in jobs]
            for i, fut in enumerate(as_completed(futs), 1):
                rec = fut.result()
                results.append(rec)
                log.writerow(rec)
                logf.flush()
                if rec["status"] != "ok" or i % 100 == 0 or i == len(futs):
                    print("  [%d/%d] %-6s %-14s %s %s  %s" % (i, len(futs), rec["status"], rec["patch"],
                                                           rec["obs_id"], rec["detector"], rec.get("error", "")),
                          flush=True)
    except KeyboardInterrupt:
        print("\nStopped. Re-run the same command to continue (finished files are kept).")
    finally:
        logf.close()

    ok = [r for r in results if r["status"] == "ok"]
    print("\nDone in %.1f min: %d cleaned OK, %d failed, %d skipped (already done)."
          % ((time.time() - t0) / 60, len(ok), len(results) - len(ok), skipped))
    per = {}
    for r in ok:
        per.setdefault(r["patch"], []).append(r)
    if per:
        print("  %-15s %5s %7s %6s %9s %8s %10s %9s %8s" % ("patch", "n", "%bad", "%sat", "%suspect", "%nodata",
                                                           "zodi_med", "noise", "%S/N>5"))
    for k in sorted(per):
        rs = per[k]
        med = lambda f: float(np.median([float(r[f]) for r in rs]))
        print("  %-15s %5d %7.2f %6.3f %9.2f %8.2f %10.4f %9.4f %8.2f" % (k, len(rs), med("pct_bad"), med("pct_sat"), med("pct_suspect"),
              med("pct_nodata"), med("zodi_med"), med("err_med"), med("pct_snr5")))
    print("(values are medians per patch)  Details per photo: %s" % a.log)


if __name__ == "__main__":
    main()
