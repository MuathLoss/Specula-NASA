#!/usr/bin/env python3
"""
align_spherex.py  -  Specula (NASA Space Apps 2026, "Planet X and SPHEREx")

Puts every cleaned photo onto a shared sky grid, so the same star lands on the same pixel,
and numbers all photos of a patch from past to future.

The grid: north up, east left, 6.15" per pixel (SPHEREx's own pixel size), same size as the crop.
  fixed patches  (ecliptic-virgo, ecliptic-ra90, nep-cats-eye): ONE grid per patch, centred on the
                 patch centre -> every photo of the patch is pixel-to-pixel comparable (any two dates).
  moving patches (ceres, 3i-atlas): ONE grid per burst (photos taken minutes apart), centred on the
                 burst's first crop -> stars are locked inside a burst, the object drifts slightly.
                 (3i-atlas uses the crop centre, never the comet position, so the test stays fair.)

For each output pixel we ask the photo's own map where that sky point fell in the photo, and read the
value there (bilinear interpolation; MASK uses the nearest pixel). Output layers:
  SCI  cleaned brightness (MJy/sr)      ERR  1-sigma noise        SNR  (SCI - BKG_MED) / ERR
  MASK 1 bad, 2 suspect, 4 source, 8 no data                      WAVE wavelength seen by each pixel (um)
Files: data/aligned/<patch>/<frame>_<obs_id>_<detector>.fits  (frame 0001 = oldest photo)
Index: data/aligned/<patch>/frames.csv  (one row per photo, in time order)

Needs: python -m pip install astropy numpy
Run from the Specula folder:
    python align_spherex.py --patch nep-cats-eye --limit 20     # quick test
    python align_spherex.py                                      # everything
"""
import argparse
import csv
import os
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta

import numpy as np

PIXEL_ARCSEC = 6.15
FIXED = {"ecliptic-virgo", "ecliptic-ra90", "nep-cats-eye"}
M_NODATA = 8
FRAME_FIELDS = ["frame", "patch", "t_mid_utc", "t_mid_mjd", "window_id", "burst_id", "obs_id", "detector",
                "wl_um", "grid_id", "grid_ra", "grid_dec", "grid_px", "coverage", "shift_px", "quality", "file"]


def mjd_to_utc(mjd):
    return (datetime(1858, 11, 17) + timedelta(days=mjd)).strftime("%Y-%m-%dT%H:%M:%SZ")


def grid_wcs(ra, dec, n):
    from astropy.wcs import WCS
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = [(n + 1) / 2.0, (n + 1) / 2.0]
    w.wcs.cdelt = [-PIXEL_ARCSEC / 3600.0, PIXEL_ARCSEC / 3600.0]
    w.wcs.cunit = ["deg", "deg"]
    w.wcs.radesys = "ICRS"
    return w


def bilinear(data, x, y):
    """Sample data at float pixel positions (0-based) by bilinear interpolation.
    Missing (NaN) neighbours are skipped; the result is NaN only if they carry half the weight or more."""
    ny, nx = data.shape
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx, fy = x - x0, y - y0
    out = np.full(x.shape, np.nan, dtype=np.float64)
    ok = (x0 >= -1) & (y0 >= -1) & (x0 < nx) & (y0 < ny)
    xi, yi, ax, ay = x0[ok], y0[ok], fx[ok], fy[ok]
    acc = np.zeros(xi.shape)
    wsum = np.zeros(xi.shape)
    for dx, dy, wgt in ((0, 0, (1 - ax) * (1 - ay)), (1, 0, ax * (1 - ay)), (0, 1, (1 - ax) * ay), (1, 1, ax * ay)):
        xx, yy = xi + dx, yi + dy
        inside = (xx >= 0) & (yy >= 0) & (xx < nx) & (yy < ny)
        v = np.full(xi.shape, np.nan)
        v[inside] = data[yy[inside], xx[inside]]
        good = np.isfinite(v)
        acc[good] += v[good] * wgt[good]
        wsum[good] += wgt[good]
    res = np.full(xi.shape, np.nan)
    keep = wsum > 0.5
    res[keep] = acc[keep] / wsum[keep]
    out[ok] = res
    return out


def nearest(data, x, y, fill):
    ny, nx = data.shape
    xi = np.rint(x).astype(np.int64)
    yi = np.rint(y).astype(np.int64)
    ok = (xi >= 0) & (yi >= 0) & (xi < nx) & (yi < ny)
    out = np.full(x.shape, fill, dtype=data.dtype)
    out[ok] = data[yi[ok], xi[ok]]
    return out


def phase_shift(a, b):
    """Shift (pixels) that best lines up image b with image a (stars only, via cross-correlation)."""
    def prep(im):
        im = np.nan_to_num(im, nan=0.0)
        return np.clip(im, 0, 50)              # use SNR, keep stars, ignore extreme values
    A, B = np.fft.fft2(prep(a)), np.fft.fft2(prep(b))
    r = A * np.conj(B)
    r /= np.abs(r) + 1e-12
    cc = np.fft.ifft2(r).real
    iy, ix = np.unravel_index(np.argmax(cc), cc.shape)
    ny, nx = cc.shape
    dy = iy if iy <= ny // 2 else iy - ny
    dx = ix if ix <= nx // 2 else ix - nx
    return float(np.hypot(dx, dy))


def align_one(job):
    from astropy import log
    from astropy.io import fits
    from astropy.wcs import WCS
    log.setLevel("ERROR")
    warnings.simplefilter("ignore")
    t0 = time.time()
    src, dst, g_ra, g_dec, n, meta = job
    gw = grid_wcs(g_ra, g_dec, n)
    with fits.open(src) as h:
        hdr = h["SCI"].header
        w = WCS(hdr)
        yy, xx = np.mgrid[0:n, 0:n]
        sky = gw.pixel_to_world(xx.ravel(), yy.ravel())
        px, py = w.world_to_pixel(sky)                       # where each grid pixel falls in the photo
        sci = bilinear(h["SCI"].data.astype(np.float64), px, py)
        err = h["ERR"].data.astype(np.float64)
        var = bilinear(err * err, px, py)
        mask = nearest(h["MASK"].data, px, py, M_NODATA)
        sci = sci.reshape(n, n)
        err = np.sqrt(var).reshape(n, n)
        mask = mask.reshape(n, n)
        lost = ~np.isfinite(sci) & ((mask & (1 | M_NODATA)) == 0)   # NaN after interpolation next to a gap
        mask[lost] |= M_NODATA
        bkg = float(hdr.get("BKG_MED", 0.0) or 0.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            snr = (sci - bkg) / err
        wave = np.full(n * n, np.nan)
        try:
            ww = WCS(hdr, fobj=h, key="W")
            ww.sip = None
            # only where the detector really exists (2040 x 2040 pixels); outside it the map just extrapolates
            dx = px + float(hdr.get("CROP_X0", 0))
            dy = py + float(hdr.get("CROP_Y0", 0))
            inside = (dx >= -0.5) & (dy >= -0.5) & (dx <= 2039.5) & (dy <= 2039.5)
            wave[inside] = ww.pixel_to_world_values(px[inside], py[inside])[0]
        except Exception:  # noqa: BLE001
            pass
        wave = wave.reshape(n, n)
        coverage = float(np.isfinite(sci).mean())
        c = n // 2
        wl = float(np.nanmedian(wave[c - 5:c + 6, c - 5:c + 6])) if np.isfinite(wave[c - 5:c + 6, c - 5:c + 6]).any() \
            else float(np.nanmedian(wave)) if np.isfinite(wave).any() else float("nan")

        out_hdr = gw.to_header()
        for k in ("PATCH", "CROP_RA", "CROP_DEC", "CROP_DEG", "DETECTOR", "OBSID", "DATE-BEG", "DATE-END",
                  "MJD-BEG", "MJD-END", "BKG_MED", "ZODI_MED", "ERR_MED", "PCT_BAD"):
            if k in hdr:
                out_hdr[k] = hdr[k]
        out_hdr["FRAME"] = (meta["frame"], "position in time order within the patch (1 = oldest)")
        out_hdr["GRID_ID"] = (meta["grid_id"], "photos with the same GRID_ID share pixels exactly")
        out_hdr["COVERAGE"] = (round(coverage, 4), "share of the grid with data")
        out_hdr["WL_UM"] = (round(wl, 4) if np.isfinite(wl) else -1, "[um] wavelength at grid centre")
        out_hdr["SRCFILE"] = os.path.basename(src)
        out_hdr["ALIGNED"] = (True, "Specula align_spherex.py, bilinear, north up")

        def layer(data, name, unit):
            hh = out_hdr.copy()
            hh["BUNIT"] = unit
            return fits.ImageHDU(data, header=hh, name=name)

        out = fits.HDUList([fits.PrimaryHDU(header=h[0].header)])
        out.append(layer(sci.astype(np.float32), "SCI", "MJy / sr"))
        out.append(layer(err.astype(np.float32), "ERR", "MJy / sr"))
        out.append(layer(snr.astype(np.float32), "SNR", ""))
        out.append(layer(mask.astype(np.uint8), "MASK", ""))
        out.append(layer(wave.astype(np.float32), "WAVE", "um"))
        names = [x.name for x in h]
        for name in ("PSF", "EPSF"):
            if name in names:
                out.append(h[name].copy())
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        out.writeto(dst + ".part", overwrite=True)
    os.replace(dst + ".part", dst)
    meta = dict(meta)
    meta.update({"coverage": "%.4f" % coverage, "wl_um": "%.4f" % wl if np.isfinite(wl) else "",
                 "status": "ok", "seconds": "%.2f" % (time.time() - t0)})
    return meta


def safe_align(job):
    try:
        return align_one(job)
    except Exception as e:  # noqa: BLE001
        try:
            os.remove(job[1] + ".part")
        except OSError:
            pass
        m = dict(job[5])
        m.update({"status": "failed", "error": ("%s: %s" % (type(e).__name__, e))[:300]})
        return m


def main():
    p = argparse.ArgumentParser(description="Align cleaned SPHEREx photos onto shared sky grids (Specula).")
    p.add_argument("--manifest", default="manifest_all.csv")
    p.add_argument("--clean", default=os.path.join("data", "clean"))
    p.add_argument("--out", default=os.path.join("data", "aligned"))
    p.add_argument("--patch", action="append")
    p.add_argument("--limit", type=int, help="only the first N photos (in time order) of each patch")
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
    by = {}
    for r in rows:
        by.setdefault(r["patch"], []).append(r)

    jobs, plan, skipped = [], {}, 0
    for patch, rs in by.items():
        rs.sort(key=lambda r: (float(r["t_mid_mjd"]), r["detector"]))     # past -> future
        if a.limit:
            rs = rs[:a.limit]
        first_of_burst = {}
        for r in rs:
            first_of_burst.setdefault(r["burst_id"], r)
        plan[patch] = []
        for i, r in enumerate(rs, 1):
            n = int(round(float(r["cutout_size_deg"]) * 3600 / PIXEL_ARCSEC))
            if patch in FIXED:
                g_ra, g_dec, grid_id = float(r["cutout_ra"]), float(r["cutout_dec"]), patch
            else:
                f = first_of_burst[r["burst_id"]]
                g_ra, g_dec, grid_id = float(f["cutout_ra"]), float(f["cutout_dec"]), "%s:%s" % (patch, r["burst_id"])
            name = "%s_%s.fits" % (r["obs_id"], r["detector"])
            src = os.path.join(a.clean, patch, name)
            out_name = "%04d_%s" % (i, name)
            dst = os.path.join(a.out, patch, out_name)
            meta = {"frame": i, "patch": patch, "t_mid_utc": mjd_to_utc(float(r["t_mid_mjd"])),
                    "t_mid_mjd": r["t_mid_mjd"], "window_id": r["window_id"], "burst_id": r["burst_id"],
                    "obs_id": r["obs_id"], "detector": r["detector"], "grid_id": grid_id,
                    "grid_ra": "%.6f" % g_ra, "grid_dec": "%.6f" % g_dec, "grid_px": n,
                    "quality": r.get("quality", ""), "file": out_name}
            plan[patch].append(meta)
            if not os.path.exists(src):
                sys.exit("Missing cleaned photo %s - run clean_spherex.py first." % src)
            if os.path.exists(dst) and not a.redo:
                skipped += 1
            else:
                jobs.append((src, dst, g_ra, g_dec, n, meta))

    print("Photos: %d | already aligned: %d | to align now: %d | workers: %d"
          % (sum(len(v) for v in plan.values()), skipped, len(jobs), a.workers), flush=True)
    t0, results = time.time(), {}
    try:
        with ProcessPoolExecutor(max_workers=max(1, a.workers)) as pool:
            futs = [pool.submit(safe_align, j) for j in jobs]
            for i, fut in enumerate(as_completed(futs), 1):
                m = fut.result()
                results[(m["patch"], m["frame"])] = m
                if m["status"] != "ok" or i % 100 == 0 or i == len(futs):
                    print("  [%d/%d] %-6s %-14s frame %4d  %s" % (i, len(futs), m["status"], m["patch"], m["frame"],
                                                              m.get("error", "")), flush=True)
    except KeyboardInterrupt:
        print("\nStopped. Re-run the same command to continue (finished files are kept).")

    # ---- registration check + frames.csv (always rebuilt from what is on disk)
    from astropy.io import fits
    failed = [m for m in results.values() if m["status"] != "ok"]
    print("\nChecking that stars line up and writing the time-ordered index...", flush=True)
    for patch, metas in plan.items():
        refs, shifts = {}, []
        for m in metas:
            path = os.path.join(a.out, patch, m["file"])
            if not os.path.exists(path):
                m["coverage"], m["shift_px"] = "", ""
                continue
            with fits.open(path) as h:
                snr = h["SNR"].data
                m["coverage"] = "%.4f" % h["SCI"].header["COVERAGE"]
                wl = h["SCI"].header.get("WL_UM", -1)
                m["wl_um"] = "%.4f" % wl if wl and wl > 0 else ""
                ref = refs.get(m["grid_id"])
                if ref is None and float(m["coverage"]) > 0.75:
                    refs[m["grid_id"]] = snr
                    m["shift_px"] = "0.0"
                elif ref is not None and float(m["coverage"]) > 0.5:
                    s = phase_shift(ref, snr)
                    m["shift_px"] = "%.1f" % s
                    shifts.append(s)
                else:
                    m["shift_px"] = ""
        os.makedirs(os.path.join(a.out, patch), exist_ok=True)
        with open(os.path.join(a.out, patch, "frames.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FRAME_FIELDS, extrasaction="ignore", lineterminator="\n")
            w.writeheader()
            w.writerows(metas)
        grids = len({m["grid_id"] for m in metas})
        ok_shift = sum(1 for s in shifts if s <= 1.0)
        print("  %-15s %4d frames  %3d grid(s)  %s -> %s   stars line up (shift <= 1 px): %d / %d checked"
              % (patch, len(metas), grids, metas[0]["t_mid_utc"][:10], metas[-1]["t_mid_utc"][:10], ok_shift, len(shifts)))
    print("\nDone in %.1f min: %d aligned now, %d failed, %d skipped (already done)."
          % ((time.time() - t0) / 60, len(results) - len(failed), len(failed), skipped))
    print("Index per patch: %s" % os.path.join(a.out, "<patch>", "frames.csv"))


if __name__ == "__main__":
    main()
