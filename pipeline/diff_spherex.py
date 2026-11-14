#!/usr/bin/env python3
"""
diff_spherex.py  -  Specula (NASA Space Apps 2026, "Planet X and SPHEREx")

Difference images: remove everything that never moves, so moving objects stand out.

For each FIXED patch (ecliptic-virgo, ecliptic-ra90, nep-cats-eye) and each detector (D1..D6):
  1. STATIC SKY (template) = the median, pixel by pixel, of all aligned frames of that detector
     (after subtracting each frame's leftover sky level BKG_MED). Stars are in every frame, so they
     stay; an asteroid is somewhere else in each frame, so the median erases it.
  2. DIFFERENCE = frame - static sky. Stars cancel; whatever moved or changed remains.
  3. DIFF_ERR = noise of the difference, DIFF_SNR = DIFF / DIFF_ERR (> 5 = real change).

Moving patches (ceres, 3i-atlas) are skipped on purpose: their grids follow the object, so a median
over their frames would erase the very object we want to see.

Output:
  data/diff/<patch>/NNNN_<obs_id>_<detector>.fits   DIFF, DIFF_ERR, DIFF_SNR, MASK (same frame numbers)
  data/diff/<patch>/static_sky_<detector>.fits       STATIC, NFRAMES (how many frames went into each pixel)
  data/diff/<patch>/diff_frames.csv                  frames.csv + how many strong leftovers each frame has

MASK = the aligned MASK plus 32 = STAR_RESIDUE (a bright static star sits here: leftovers expected,
because every SPHEREx frame sees a slightly different colour).

Needs: python -m pip install astropy numpy
Run from the Specula folder:
    python diff_spherex.py --patch nep-cats-eye     # one patch first
    python diff_spherex.py                          # all three fixed patches
"""
import argparse
import csv
import os
import sys
import time
import warnings

import numpy as np

FIXED = ["ecliptic-virgo", "ecliptic-ra90", "nep-cats-eye"]
M_STAR_RESIDUE = 32
MIN_FRAMES = 5           # a static sky needs at least this many frames of the same detector
STAR_SNR = 10.0          # static-sky pixels brighter than this (in noise units) are marked STAR_RESIDUE


def grow(m, n=1):
    for _ in range(n):
        g = m.copy()
        g[1:, :] |= m[:-1, :]
        g[:-1, :] |= m[1:, :]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        m = g
    return m


def count_blobs(mask):
    """Number of separate groups of True pixels (4-connected), numpy + plain Python only."""
    seen = np.zeros_like(mask, dtype=bool)
    ny, nx = mask.shape
    n = 0
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        n += 1
        stack = [(y, x)]
        seen[y, x] = True
        while stack:
            cy, cx = stack.pop()
            for yy, xx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                if 0 <= yy < ny and 0 <= xx < nx and mask[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True
                    stack.append((yy, xx))
    return n


def main():
    p = argparse.ArgumentParser(description="Difference images for the fixed patches (Specula).")
    p.add_argument("--aligned", default=os.path.join("data", "aligned"))
    p.add_argument("--out", default=os.path.join("data", "diff"))
    p.add_argument("--patch", action="append", help="one of: " + ", ".join(FIXED))
    a = p.parse_args()
    try:
        from astropy.io import fits
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
        out_dir = os.path.join(a.out, patch)
        os.makedirs(out_dir, exist_ok=True)
        print("\n%s: %d frames" % (patch, len(frames)), flush=True)
        rows_out = []
        for det in sorted({r["detector"] for r in frames}):
            fr = [r for r in frames if r["detector"] == det]
            if len(fr) < MIN_FRAMES:
                print("  %s: only %d frames - skipped (a static sky needs %d)" % (det, len(fr), MIN_FRAMES))
                continue
            # ---- 1. load this detector's frames (sky level removed)
            sci, err, msk, hdrs = [], [], [], []
            for r in fr:
                with fits.open(os.path.join(a.aligned, patch, r["file"])) as h:
                    bkg = float(h["SCI"].header.get("BKG_MED", 0.0) or 0.0)
                    sci.append(h["SCI"].data.astype(np.float32) - bkg)
                    err.append(h["ERR"].data.astype(np.float32))
                    msk.append(h["MASK"].data.copy())
                    hdrs.append(h["SCI"].header.copy())
            cube = np.stack(sci)
            # ---- 2. static sky = median over time, pixel by pixel
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                static = np.nanmedian(cube, axis=0).astype(np.float32)
                nfr = np.isfinite(cube).sum(axis=0).astype(np.int16)
                err_med = np.nanmedian(np.stack(err), axis=0)
            static[nfr < MIN_FRAMES] = np.nan
            # uncertainty of a median of n values ~ 1.253 * sigma / sqrt(n)
            with np.errstate(invalid="ignore", divide="ignore"):
                static_err = (1.253 * err_med / np.sqrt(np.maximum(nfr, 1))).astype(np.float32)
                star = grow((static / err_med) > STAR_SNR, 1)
            sh = hdrs[0].copy()
            for k in ("OBSID", "DATE-BEG", "DATE-END", "MJD-BEG", "MJD-END", "FRAME", "COVERAGE", "SRCFILE",
                      "BKG_MED", "ZODI_MED", "ERR_MED", "PCT_BAD", "WL_UM"):
                sh.remove(k, ignore_missing=True)
            sh["DETECTOR"] = det[1]
            sh["NFRAMES"] = (len(fr), "frames combined into the static sky")
            sh["CONTENT"] = "static sky = median of all frames of this detector (sky level removed)"
            shdu = fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(static, header=sh, name="STATIC"),
                                 fits.ImageHDU(static_err, header=sh, name="STATIC_ERR"),
                                 fits.ImageHDU(nfr, header=sh, name="NFRAMES")])
            spath = os.path.join(out_dir, "static_sky_%s.fits" % det)
            shdu.writeto(spath + ".part", overwrite=True)
            os.replace(spath + ".part", spath)
            # ---- 3. difference = frame - static sky
            leftovers = []
            for r, s, e, m, hd in zip(fr, sci, err, msk, hdrs):
                diff = (s - static).astype(np.float32)
                with np.errstate(invalid="ignore"):
                    derr = np.sqrt(e * e + static_err * static_err).astype(np.float32)
                    dsnr = (diff / derr).astype(np.float32)
                mask = m | (star * M_STAR_RESIDUE).astype(np.uint8)
                # strong positive leftovers away from stars and bad pixels = things that moved or changed
                strong = (dsnr > 5) & ~star & ((m & (1 | 8)) == 0)
                n_blobs = count_blobs(strong)
                leftovers.append(n_blobs)
                dh = hd.copy()
                dh["CONTENT"] = "difference = (SCI - BKG_MED) - static sky of this detector"
                dh["STATICSK"] = (os.path.basename(spath), "static sky used")
                dh["NLEFT5"] = (n_blobs, "groups of pixels with DIFF_SNR > 5 away from stars")
                dh["MASK32"] = ("STAR_RESIDUE", "MASK bit value 32: bright static star here")
                hdu = fits.HDUList([fits.PrimaryHDU()])
                for data, name, unit in ((diff, "DIFF", "MJy / sr"), (derr, "DIFF_ERR", "MJy / sr"),
                                         (dsnr, "DIFF_SNR", ""), (mask, "MASK", "")):
                    hh = dh.copy()
                    hh["BUNIT"] = unit
                    hdu.append(fits.ImageHDU(data, header=hh, name=name))
                dpath = os.path.join(out_dir, r["file"])
                hdu.writeto(dpath + ".part", overwrite=True)
                os.replace(dpath + ".part", dpath)
                row = dict(r)
                row["leftovers_snr5"] = n_blobs
                rows_out.append(row)
            # how well do stars cancel? fraction of star pixels with |DIFF_SNR| < 5
            res = []
            for s in sci:
                with np.errstate(invalid="ignore"):
                    d = (s - static) / np.sqrt(err_med ** 2 + static_err ** 2)
                v = np.abs(d[star & np.isfinite(d)])
                if v.size:
                    res.append(float((v < 5).mean()))
            print("  %s: %3d frames -> static sky written | star pixels cancelled (|S/N| < 5): %4.1f%% | "
                  "leftovers per frame (median): %d" % (det, len(fr), 100 * np.median(res) if res else float("nan"),
                                                        int(np.median(leftovers))), flush=True)
        rows_out.sort(key=lambda r: int(r["frame"]))
        if rows_out:
            with open(os.path.join(out_dir, "diff_frames.csv"), "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()), lineterminator="\n")
                w.writeheader()
                w.writerows(rows_out)
        print("  -> %d difference images in %s" % (len(rows_out), out_dir), flush=True)
    print("\nDone in %.1f min." % ((time.time() - t_all) / 60))


if __name__ == "__main__":
    main()
