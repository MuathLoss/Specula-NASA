#!/usr/bin/env python3
"""
crop_spherex.py  -  Specula (NASA Space Apps 2026, "Planet X and SPHEREx")

Cuts our square out of every downloaded full SPHEREx photo (the same thing IRSA's cutout
service would do), one photo at a time:

    for each row of manifest_all.csv:
        open data/raw/full/<patch>/<obs_id>_<detector>.fits
        cut the square centred on (cutout_ra, cutout_dec), side cutout_size_deg,
            from IMAGE, FLAGS, VARIANCE and ZODI (same box for all four)
        fix all three maps: sky (by Cutout2D), detector (A) and wavelength (W) (shifted by us)
        copy PSF/EPSF and WCS-WAVE unchanged
        check: centre pixel points at the target, and the wavelength map still agrees
        save data/cut/<patch>/<obs_id>_<detector>.fits

Needs: python -m pip install astropy numpy
Run it from the Specula folder:

    python crop_spherex.py --limit 10      # try 10 photos first
    python crop_spherex.py                 # all photos (finished ones are skipped)
    python crop_spherex.py --patch ceres   # one patch only

Squares that stick out over the photo edge keep their full size; the missing part is
filled with NaN ("no data") and the share that is inside is recorded (COVERAGE).
Every photo is logged in crop_log.csv.
"""
import argparse
import csv
import os
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np

PIXEL_ARCSEC = 6.15
MARGIN = 1.42
LOG_FIELDS = ["patch", "obs_id", "detector", "status", "width_px", "height_px", "coverage",
              "x0", "y0", "centre_error_px", "wave_error_um", "mb", "seconds", "error"]


def quiet():
    from astropy import log
    from astropy.wcs import FITSFixedWarning
    log.setLevel("ERROR")
    warnings.simplefilter("ignore", FITSFixedWarning)
    warnings.simplefilter("ignore", RuntimeWarning)


def crop_one(row, src, dst):
    """Crop one photo. Returns a dict for the log."""
    quiet()
    from astropy.io import fits
    from astropy.wcs import WCS
    from astropy.coordinates import SkyCoord
    from astropy.nddata import Cutout2D
    import astropy.units as u

    t0 = time.time()
    rec = {"patch": row["patch"], "obs_id": row["obs_id"], "detector": row["detector"]}
    target = SkyCoord(float(row["cutout_ra"]), float(row["cutout_dec"]), unit="deg")
    # our square is cut with a margin (x MARGIN, default 1.42 = sqrt(2)) so that it still fills a north-up
    # square of the patch size after alignment, whatever the photo's rotation
    margin = float(row.get("_margin", MARGIN))
    npix = int(round(float(row["cutout_size_deg"]) * margin * 3600 / PIXEL_ARCSEC))   # 1 deg -> 831 px

    with fits.open(src, memmap=True) as h:
        img = h["IMAGE"]
        w = WCS(img.header)
        cut = Cutout2D(img.data, target, (npix, npix), wcs=w, mode="partial", fill_value=np.nan, copy=True)
        so, sc = cut.slices_original, cut.slices_cutout
        # where the crop's pixel (0,0) sits in the original photo (can be negative at an edge)
        x0, y0 = so[1].start - sc[1].start, so[0].start - sc[0].start
        shape = cut.data.shape

        def crop_header(header):
            hdr = header.copy()
            hdr.update(cut.wcs.to_header(relax=True))
            for k in ("CRPIX1A", "CRPIX1W"):
                if k in hdr:
                    hdr[k] = hdr[k] - x0
            for k in ("CRPIX2A", "CRPIX2W"):
                if k in hdr:
                    hdr[k] = hdr[k] - y0
            hdr["CROP_X0"] = (x0, "crop origin x in original photo (0-based)")
            hdr["CROP_Y0"] = (y0, "crop origin y in original photo (0-based)")
            hdr["CROP_RA"] = (float(row["cutout_ra"]), "[deg] centre of our square")
            hdr["CROP_DEC"] = (float(row["cutout_dec"]), "[deg] centre of our square")
            hdr["CROP_DEG"] = (float(row["cutout_size_deg"]), "[deg] side of our square (before margin)")
            hdr["CROP_MRG"] = (margin, "crop side = CROP_DEG x CROP_MRG")
            hdr["PATCH"] = (row["patch"], "Specula patch")
            return hdr

        def cropped(name, fill):
            src_data = h[name].data
            out = np.full(shape, fill, dtype=src_data.dtype)
            out[sc] = src_data[so]
            return out

        inside = np.zeros(shape, dtype=bool)
        inside[sc] = True
        coverage = float(inside.mean())

        new = fits.HDUList([fits.PrimaryHDU(header=h[0].header)])
        image = cut.data.astype(img.data.dtype)
        image[~inside] = np.nan
        ih = crop_header(img.header)
        ih["COVERAGE"] = (round(coverage, 4), "share of the square inside the photo")
        new.append(fits.ImageHDU(image, header=ih, name="IMAGE"))
        new.append(fits.ImageHDU(cropped("FLAGS", 0), header=crop_header(h["FLAGS"].header), name="FLAGS"))
        for name in ("VARIANCE", "ZODI"):
            new.append(fits.ImageHDU(cropped(name, np.nan), header=crop_header(h[name].header), name=name))
        names = [x.name for x in h]
        for name in ("PSF", "EPSF", "WCS-WAVE"):
            if name in names:
                new.append(h[name].copy())

        # ---- checks: centre points at the target; wavelength map agrees with the original
        cw = WCS(ih)
        cx, cy = cw.world_to_pixel(target)
        tx, ty = w.world_to_pixel(target)
        centre_err = float(np.hypot((cx + x0) - tx, (cy + y0) - ty))
        wave_err = ""
        try:
            ww = WCS(img.header, fobj=h, key="W")
            ww.sip = None
            px, py = shape[1] // 2, shape[0] // 2
            if inside[py, px]:
                cww = WCS(ih, fobj=new, key="W")
                cww.sip = None
                a = ww.pixel_to_world_values(px + x0, py + y0)[0]
                b = cww.pixel_to_world_values(px, py)[0]
                wave_err = float(abs(a - b))
        except Exception:  # noqa: BLE001  (wavelength check is informative only)
            wave_err = ""

        os.makedirs(os.path.dirname(dst), exist_ok=True)
        tmp = dst + ".part"
        new.writeto(tmp, overwrite=True)
    os.replace(tmp, dst)

    problems = []
    if centre_err > 0.01:
        problems.append("centre off by %.3f px" % centre_err)
    if wave_err != "" and wave_err > 1e-6:
        problems.append("wavelength map off by %g um" % wave_err)
    rec.update({"status": "ok" if not problems else "check", "width_px": shape[1], "height_px": shape[0],
                "coverage": "%.4f" % coverage, "x0": x0, "y0": y0, "centre_error_px": "%.4f" % centre_err,
                "wave_error_um": "" if wave_err == "" else "%.2e" % wave_err,
                "mb": "%.2f" % (os.path.getsize(dst) / 1e6), "seconds": "%.2f" % (time.time() - t0),
                "error": "; ".join(problems)})
    return rec


def safe_crop(args):
    row, src, dst = args
    try:
        return crop_one(row, src, dst)
    except Exception as e:  # noqa: BLE001
        try:
            os.remove(dst + ".part")
        except OSError:
            pass
        return {"patch": row["patch"], "obs_id": row["obs_id"], "detector": row["detector"],
                "status": "failed", "error": ("%s: %s" % (type(e).__name__, e))[:300]}


def main():
    p = argparse.ArgumentParser(description="Crop our squares out of the full SPHEREx photos (Specula).")
    p.add_argument("--manifest", default="manifest_all.csv")
    p.add_argument("--raw", default=os.path.join("data", "raw", "full"))
    p.add_argument("--out", default=os.path.join("data", "cut"))
    p.add_argument("--log", default="crop_log.csv")
    p.add_argument("--patch", action="append", help="only this patch (repeatable)")
    p.add_argument("--limit", type=int, help="only the first N photos of each patch")
    p.add_argument("--workers", type=int, default=max(1, min(4, (os.cpu_count() or 2) - 1)))
    p.add_argument("--redo", action="store_true", help="crop again even if the output exists")
    p.add_argument("--margin", type=float, default=1.42, help="crop side = patch size x margin (default 1.42)")
    a = p.parse_args()

    try:
        import astropy  # noqa: F401
    except ImportError:
        sys.exit("astropy is missing - run:  python -m pip install astropy numpy")
    if not os.path.exists(a.manifest):
        sys.exit("Cannot find %s - run this script from the Specula folder." % a.manifest)

    with open(a.manifest, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
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
        src = os.path.join(a.raw, r["patch"], name)
        dst = os.path.join(a.out, r["patch"], name)
        if not os.path.exists(src):
            missing.append(src)
        elif os.path.exists(dst) and not a.redo:
            skipped += 1
        else:
            r = dict(r)
            r["_margin"] = a.margin
            jobs.append((r, src, dst))
    print("Photos: %d | already cropped: %d | missing originals: %d | to crop now: %d | workers: %d"
          % (len(rows), skipped, len(missing), len(jobs), a.workers))
    if missing:
        print("  e.g. missing:", missing[0])

    if os.path.dirname(a.log):
        os.makedirs(os.path.dirname(a.log), exist_ok=True)
    new_log = not os.path.exists(a.log)
    logf = open(a.log, "a", newline="", encoding="utf-8")
    log = csv.DictWriter(logf, fieldnames=LOG_FIELDS, extrasaction="ignore", lineterminator="\n")
    if new_log:
        log.writeheader()

    t0, results = time.time(), []
    try:
        with ProcessPoolExecutor(max_workers=max(1, a.workers)) as pool:
            futs = [pool.submit(safe_crop, j) for j in jobs]
            for i, fut in enumerate(as_completed(futs), 1):
                rec = fut.result()
                results.append(rec)
                log.writerow(rec)
                logf.flush()
                if rec["status"] != "ok" or i % 25 == 0 or i == len(futs):
                    print("  [%d/%d] %-6s %-14s %s %s  %s" % (i, len(futs), rec["status"], rec["patch"],
                                                           rec["obs_id"], rec["detector"], rec.get("error", "")))
    except KeyboardInterrupt:
        print("\nStopped. Re-run the same command to continue (finished crops are kept).")
    finally:
        logf.close()

    ok = sum(1 for r in results if r["status"] == "ok")
    print("\nDone in %.1f min: %d cropped OK, %d need checking, %d failed, %d skipped (already done)."
          % ((time.time() - t0) / 60, ok, sum(1 for r in results if r["status"] == "check"),
             sum(1 for r in results if r["status"] == "failed"), skipped))
    per = {}
    for r in results:
        if r["status"] == "ok":
            d = per.setdefault(r["patch"], {"n": 0, "mb": 0.0, "partial": 0, "sizes": set()})
            d["n"] += 1
            d["mb"] += float(r["mb"])
            d["partial"] += float(r["coverage"]) < 0.9999
            d["sizes"].add("%sx%s" % (r["width_px"], r["height_px"]))
    for k in sorted(per):
        d = per[k]
        print("  %-15s %4d crops  %7.1f MB  size %s  touching the photo edge: %d"
              % (k, d["n"], d["mb"], ",".join(sorted(d["sizes"])), d["partial"]))
    print("Details per photo: %s" % a.log)


if __name__ == "__main__":
    main()
