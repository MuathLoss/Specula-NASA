"""Specula helper - one row per aligned frame describing its PSF (the shape a point of light makes).

Why: the PSF layer comes in two formats and its models are indexed by position on the ORIGINAL
detector, which the aligned (north-up) frames no longer show. This table gives, per frame:
  psf_layer       PSF  = QR2 photos: image cube (121 models = 11 x 11 detector zones, 101 x 101 px, 10x oversampled)
                  EPSF = QR3 photos: binary table (441 rows = 21 x 21 zones, column EPSF = 33 x 33, 5x oversampled)
  psf_zone        0-based index of the model nearest our square's centre (cube plane, or table row)
  psf_fwhm_arcsec SPHEREx's median PSF width for that photo (header PSF_FWHM); psf_fwhm_px = / 6.15
  crop_x0/y0, det_x/det_y  where our square sits on the original detector (pixels, 0-based)
Reads headers only (fast). Output: data/psf_info.csv
"""
import csv, os, re, struct

PIX = 6.15
PATCHES = ["ecliptic-virgo", "ecliptic-ra90", "nep-cats-eye", "3i-atlas", "ceres"]


def headers(path, want_table_centres=False):
    """Walk the FITS file header by header (skipping data). Returns {extname: header dict}."""
    out = {}
    with open(path, "rb") as f:
        while True:
            hdr, raw = {}, b""
            while True:
                blk = f.read(2880)
                if not blk:
                    return out
                raw += blk
                end = False
                for i in range(36):
                    c = blk[i * 80:(i + 1) * 80].decode("ascii", "replace")
                    k = c[:8].strip()
                    if k == "END":
                        end = True
                        break
                    if c[8:10] == "= ":
                        hdr[k] = c[10:].split("/")[0].strip().strip("'").strip()
                if end:
                    break
            n = int(hdr.get("NAXIS", 0))
            size = abs(int(hdr.get("BITPIX", 8))) // 8
            for i in range(n):
                size *= int(hdr["NAXIS%d" % (i + 1)])
            if n == 0:
                size = 0
            size += int(hdr.get("PCOUNT", 0) or 0)
            name = hdr.get("EXTNAME", "PRIMARY").strip()
            if name == "EPSF" and want_table_centres:
                rowlen, nrow = int(hdr["NAXIS1"]), int(hdr["NAXIS2"])
                data = f.read(rowlen * nrow)
                hdr["_centres"] = [struct.unpack(">ff", data[r * rowlen + 8:r * rowlen + 16]) for r in range(nrow)]
                f.seek(size - rowlen * nrow + ((-size) % 2880), 1)
            else:
                f.seek(size + ((-size) % 2880), 1)
            out[name] = hdr


def cut_keys(path):
    b = open(path, "rb").read(200000)
    g = lambda k: float(re.search((k + r"\s*=\s*([-+0-9.Ee]+)").encode(), b).group(1))
    return g("CROP_X0"), g("CROP_Y0"), g("PSF_FWHM"), int(g("NAXIS1")), int(g("NAXIS2"))


def main():
    rel = {(r["obs_id"], r["detector"]): r["release"] for r in csv.DictReader(open("manifest_all.csv"))}
    epsf_centres = None
    rows = []
    for p in PATCHES:
        for fr in csv.DictReader(open(os.path.join("data", "aligned", p, "frames.csv"))):
            apath = os.path.join("data", "aligned", p, fr["file"])
            cpath = os.path.join("data", "cut", p, "%s_%s.fits" % (fr["obs_id"], fr["detector"]))
            need_tab = epsf_centres is None and rel[(fr["obs_id"], fr["detector"])] == "qr3"
            hs = headers(apath, want_table_centres=need_tab)
            x0, y0, fwhm, nx, ny = cut_keys(cpath)
            dx, dy = x0 + (nx - 1) / 2.0, y0 + (ny - 1) / 2.0
            if "PSF" in hs:
                h = hs["PSF"]
                cen = [(float(h["XCTR_%d" % k]), float(h["YCTR_%d" % k])) for k in range(1, int(h["NAXIS3"]) + 1)]
                layer = "PSF"
            else:
                if need_tab:
                    epsf_centres = hs["EPSF"]["_centres"]
                cen, layer = epsf_centres, "EPSF"
            zone = min(range(len(cen)), key=lambda k: (cen[k][0] - dx) ** 2 + (cen[k][1] - dy) ** 2)
            rows.append({"patch": p, "frame": fr["frame"], "file": fr["file"], "detector": fr["detector"],
                         "release": rel[(fr["obs_id"], fr["detector"])], "psf_layer": layer,
                         "psf_zone": zone, "psf_fwhm_arcsec": "%.2f" % fwhm, "psf_fwhm_px": "%.2f" % (fwhm / PIX),
                         "crop_x0": int(x0), "crop_y0": int(y0), "det_x": "%.1f" % dx, "det_y": "%.1f" % dy})
    cols = list(rows[0].keys())
    with open(os.path.join("data", "psf_info.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    fw = sorted(float(r["psf_fwhm_px"]) for r in rows)
    print("psf_info.csv: %d rows | PSF layer: %d PSF (QR2) + %d EPSF (QR3) | FWHM px: min %.2f median %.2f max %.2f"
          % (len(rows), sum(r["psf_layer"] == "PSF" for r in rows), sum(r["psf_layer"] == "EPSF" for r in rows),
             fw[0], fw[len(fw) // 2], fw[-1]))


if __name__ == "__main__":
    main()
