"""Specula stage 9 - preview images + timeline + markers for the frontend (handoff #2).

Reads the aligned frames (data/aligned/<patch>/) and the known-object labels (data/labels/<patch>/) and writes,
in the layout of the frontend data contract (drops straight into the site's public/data/):

  handoff/frontend_data/<patch>/full/<frame_id>.webp            native size, north up, east left
  handoff/frontend_data/<patch>/thumb/<frame_id>.webp           128 px wide
  handoff/frontend_data/<patch>/composite/<burst_id>.webp       2-colour false colour of the burst
  handoff/frontend_data/<patch>/composite_thumb/<burst_id>.webp
  handoff/frontend_data/<patch>/timeline.json                   patch header + every frame + every burst
  handoff/frontend_data/<patch>/markers.json                    known objects per frame (image pixel convention)
  handoff/frontend_data/addons/3i-atlas_markers.json            3I/ATLAS true positions (frontend only!)
  handoff/frontend_data/manifest.json, history.json             entry point + update log (baseline)

Image rules
  * 1:1 with the aligned grid, no crop, no rescale. FITS row 0 = south edge, so each image is flipped vertically
    once: image row 0 = north edge. Pixel convention of every x, y written here: 0-based, origin top-left,
    y down, (0,0) = centre of the top-left pixel  ->  x_img = x, y_img = (size - 1) - y_numpy.
  * Brightness: one fixed asinh stretch per patch AND detector (each detector sees another colour), measured on
    the sky-subtracted frames (SCI - BKG_MED). Flipping through same-detector frames does not flicker.
  * No-data pixels (MASK 8 outside the footprint) and a 3 px rim along the photo's real edge are transparent.
    Bad pixels and saturated star cores are filled from their neighbours. Edge glow (SPHEREx detector edges,
    up to ~45 px) and smooth sky gradients are measured per frame and subtracted. All display only.
  * Composite: median per detector inside the burst; shorter-wavelength detector -> blue, longer -> red,
    their mean -> green; shown only where both colours have data. Bursts with one detector -> greyscale.

Only numpy + Pillow (no astropy), so it runs on any PC. Safe to re-run: existing images are skipped
(--redo rebuilds). Run from the Specula folder:
    python build_previews.py --patch ceres        # one patch (the sample pack)
    python build_previews.py                      # all 5 patches
    python build_previews.py --test-webp          # lossy vs lossless check on faint known asteroids
"""
import argparse, csv, json, math, os, re, sys, time
from datetime import datetime, timedelta, timezone
import numpy as np
from PIL import Image

PATCHES = {
    "ecliptic-virgo": {"name": "Ecliptic (Virgo)", "kind": "fixed", "followed_object": None},
    "ecliptic-ra90": {"name": "Ecliptic (RA 90, Milky Way)", "kind": "fixed", "followed_object": None},
    "nep-cats-eye": {"name": "North Ecliptic Pole (Cat's Eye)", "kind": "fixed", "followed_object": None},
    "ceres": {"name": "Ceres", "kind": "moving", "followed_object": "1"},
    "3i-atlas": {"name": "3I/ATLAS", "kind": "moving", "followed_object": "3I"},
}
OUT = os.path.join("handoff", "frontend_data")
PIXEL_ARCSEC = 6.15
THUMB_W = 128
WEBP_Q = 90          # lossy quality for full + composite (see --test-webp)
STRETCH_FILE = os.path.join("data", "preview_stretch.json")
BKG_BLOCK = 48       # px; display-only background flattening (removes sky gradients)
EDGE_RIM = 3         # px; display-only rim hidden along the photo's real edge (edge pixels are unreliable)
EDGE_GLOW_MAX = 80   # px; edge glow measured and subtracted up to this distance from the real edge
STYLE_TS = 1794083907.0  # images older than this (epoch s) were made with an older style and are rebuilt


# ---------------------------------------------------------------- FITS (numpy only)
def read_layers(path, names):
    """Return ({extname: 2-D array}, {extname: header dict}) for the requested image layers."""
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
                    k = c[:8].strip()
                    if k == "END":
                        end = True
                        break
                    if c[8:10] == "= ":
                        v = c[10:]
                        if v.strip().startswith("'"):
                            v = v.strip()[1:].split("'")[0]
                        else:
                            v = v.split("/")[0]
                        hdr[k] = v.strip()
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


# ---------------------------------------------------------------- helpers
def frame_id(file):
    return os.path.splitext(file)[0]


def object_id(name):
    m = re.match(r"^(\d+) ", name)
    if m:
        return m.group(1)
    m = re.match(r"^\((.+)\)$", name.strip())
    return m.group(1) if m else name.strip()


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def mjd_to_iso(m):
    return iso(datetime(1858, 11, 17, tzinfo=timezone.utc) + timedelta(days=m))


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, path)


def save_webp(img, path, lossless=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    if lossless:
        img.save(tmp, "WEBP", lossless=True, quality=100, method=6)
    else:
        img.save(tmp, "WEBP", quality=WEBP_Q, method=6, alpha_quality=100)
    os.replace(tmp, path)


def to_rgba(chan, alpha):
    """chan: float HxW in [0,1] (or HxWx3); alpha: bool HxW. Returns a north-up RGBA PIL image."""
    c = np.clip(np.nan_to_num(chan, nan=0.0), 0, 1)
    if c.ndim == 2:
        c = np.repeat(c[:, :, None], 3, axis=2)
    rgba = np.dstack([(c * 255 + 0.5).astype(np.uint8), (alpha * 255).astype(np.uint8)])
    return Image.fromarray(np.flipud(rgba), "RGBA")


def fresh(path):
    return os.path.exists(path) and os.path.getmtime(path) >= STYLE_TS


def thumb(img):
    w, h = img.size
    return img.resize((THUMB_W, max(1, round(h * THUMB_W / w))), Image.LANCZOS)


# ---------------------------------------------------------------- stretch
def measure_stretch(patch, frames):
    """One asinh stretch per detector: lo = -1 sigma, soft = 3 sigma, hi = 99.7th percentile of sky-subtracted SCI."""
    rng = np.random.default_rng(7)
    res = {}
    for det in sorted({r["detector"] for r in frames}):
        fr = [r for r in frames if r["detector"] == det]
        pick = [fr[i] for i in sorted(rng.choice(len(fr), size=min(30, len(fr)), replace=False))]
        vals, sig = [], []
        for r in pick:
            d, h = read_layers(os.path.join("data", "aligned", patch, r["file"]), ["SCI"])
            v = d["SCI"].astype(np.float64) - float(h["SCI"].get("BKG_MED", 0))
            v = v[np.isfinite(v)]
            if v.size:
                vals.append(rng.choice(v, size=min(20000, v.size), replace=False))
            sig.append(float(h["SCI"].get("ERR_MED", "nan")))
        allv = np.concatenate(vals)
        s = float(np.nanmedian(sig))
        res[det] = {"sigma": s, "lo": -1.0 * s, "soft": 3.0 * s, "hi": float(np.percentile(allv, 99.7))}
    return res


def apply_stretch(v, p):
    x = (v - p["lo"]) / p["soft"]
    return np.arcsinh(np.clip(x, 0, None)) / math.asinh((p["hi"] - p["lo"]) / p["soft"])


def fill_bad(v, nodata, rounds=4):
    """Display only: fill bad (NaN) pixels with the mean of their valid neighbours, so stars have no holes."""
    v = v.copy()
    for _ in range(rounds):
        bad = ~np.isfinite(v) & ~nodata
        if not bad.any():
            break
        p = np.pad(v, 1, constant_values=np.nan)
        nb = np.stack([p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx]
                       for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])
        cnt = np.isfinite(nb).sum(axis=0)
        mean = np.where(cnt > 0, np.nansum(nb, axis=0) / np.maximum(cnt, 1), np.nan)
        v[bad] = mean[bad]
    return np.where(np.isfinite(v), v, 0.0)


def box_mean(m, r):
    """Mean of a boolean map over (2r+1)^2 boxes (integral image, numpy only)."""
    p = np.pad(m.astype(np.float64), r + 1, mode="edge")
    c = p.cumsum(0).cumsum(1)
    k = 2 * r + 1
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return s[:m.shape[0], :m.shape[1]] / (k * k)


def edge_glow(v, nodata, star, sigma, max_r=EDGE_GLOW_MAX):
    """Display only: SPHEREx frames can glow along their real edge (up to ~45 px, measured). Measure the sky's
    excess as a function of distance to the edge (5 px bins) and return it as a map to subtract, so the data
    there stays visible (an asteroid near the edge is not hidden). Also returns the thin rim that is hidden."""
    big = nodata & (box_mean(nodata, 4) > 0.5)              # real edges, not isolated no-data specks
    zero = np.zeros(v.shape)
    if not big.any():
        return zero, np.zeros_like(nodata)
    dist = np.full(nodata.shape, max_r + 1, dtype=np.int32)
    cur = big.copy()
    for k in range(1, max_r + 1):
        p = np.pad(cur, 1)
        grow = p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:] | cur
        dist[grow & ~cur] = k
        cur = grow
    ok = np.isfinite(v) & ~nodata & ~star
    inner = ok & (dist > max_r)
    ref = np.median(v[inner]) if inner.sum() > 500 else np.median(v[ok & (dist > max_r - 20)])
    centres, excess = [], []
    for lo in range(1, max_r + 1, 5):
        sel = ok & (dist >= lo) & (dist < lo + 5)
        if sel.sum() > 50:
            centres.append(lo + 2.0)
            e = np.median(v[sel]) - ref
            excess.append(e if e > 2 * sigma else 0.0)
    if not centres or max(excess) == 0:
        return zero, (dist <= EDGE_RIM) & ~nodata
    centres.append(max_r + 1.0)
    excess.append(0.0)
    corr = np.interp(dist.astype(float), centres, excess, left=excess[0], right=0.0)
    return np.where(nodata, 0.0, corr), (dist <= EDGE_RIM) & ~nodata


def flatten(v, valid, block=BKG_BLOCK):
    """Display only: subtract a smooth background (median of block x block cells, bilinear upsampled)."""
    n0, n1 = v.shape
    p0, p1 = -n0 % block, -n1 % block
    w = np.pad(np.where(valid, v, np.nan), ((0, p0), (0, p1)), constant_values=np.nan)
    cells = w.reshape(w.shape[0] // block, block, w.shape[1] // block, block).transpose(0, 2, 1, 3)
    cells = cells.reshape(cells.shape[0], cells.shape[1], -1)
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            med = np.nanmedian(cells, axis=2)
    med = np.where(np.isfinite(med), med, np.nanmedian(med) if np.isfinite(med).any() else 0.0)
    bg = np.asarray(Image.fromarray(med.astype(np.float32), "F").resize((w.shape[1], w.shape[0]), Image.BILINEAR))
    return v - bg[:n0, :n1]


def load_frame(patch, r, stretch):
    d, h = read_layers(os.path.join("data", "aligned", patch, r["file"]), ["SCI", "MASK"])
    sci, msk = d["SCI"].astype(np.float64), d["MASK"].astype(np.int64)
    nodata = ((msk & 8) > 0) & ((msk & 16) == 0)    # saturated star cores also carry bit 8: fill, don't hide
    v = sci - float(h["SCI"].get("BKG_MED", 0))
    v[(msk & 16) > 0] = np.nan                      # saturated cores are lower limits: fill from their bright ring
    v = fill_bad(v, nodata, rounds=6)
    glow, rim = edge_glow(v, nodata, (msk & 4) > 0, stretch[r["detector"]]["sigma"])
    v = flatten(v - glow, ~(nodata | rim))
    img = apply_stretch(v, stretch[r["detector"]])
    return img, ~(nodata | rim)


# ---------------------------------------------------------------- per patch
def ingest_times():
    t = {}
    for r in csv.DictReader(open("download_log.csv", encoding="utf-8")):
        if r["status"] == "ok":
            t[(r["obs_id"], r["detector"])] = r["time_utc"]
    return t


def build_patch(patch, a, ingest, stretch_all):
    meta = PATCHES[patch]
    frames = list(csv.DictReader(open(os.path.join("data", "aligned", patch, "frames.csv"), encoding="utf-8")))
    size = int(frames[0]["grid_px"])
    pdir = os.path.join(OUT, patch)
    if patch not in stretch_all or a.redo:
        print("  measuring the brightness stretch ...", flush=True)
        stretch_all[patch] = measure_stretch(patch, frames)
        write_json(STRETCH_FILE, stretch_all)
    stretch = stretch_all[patch]
    t0, made = time.time(), 0
    bursts = {}
    for r in frames:
        bursts.setdefault(r["burst_id"], []).append(r)

    # frames
    for i, r in enumerate(frames, 1):
        fid = frame_id(r["file"])
        fp, tp = os.path.join(pdir, "full", fid + ".webp"), os.path.join(pdir, "thumb", fid + ".webp")
        if a.redo or not (fresh(fp) and fresh(tp)):
            img, alpha = load_frame(patch, r, stretch)
            im = to_rgba(img, alpha)
            save_webp(im, fp)
            save_webp(thumb(im), tp)
            made += 1
        if i % 50 == 0:
            print("    frames %d/%d (%.0f s)" % (i, len(frames), time.time() - t0), flush=True)

    # composites
    for bid, fr in bursts.items():
        cp, ctp = os.path.join(pdir, "composite", bid + ".webp"), os.path.join(pdir, "composite_thumb", bid + ".webp")
        if not a.redo and fresh(cp) and fresh(ctp):
            continue
        per_det = {}
        for r in fr:
            img, alpha = load_frame(patch, r, stretch)
            per_det.setdefault(r["detector"], []).append(np.where(alpha, img, np.nan))
        med = {d: np.nanmedian(np.stack(v), axis=0) for d, v in per_det.items()}
        dets = sorted(med, key=lambda d: int(d[1:]))
        if len(dets) == 1:
            chan, alpha = med[dets[0]], np.isfinite(med[dets[0]])
        else:
            b, rr = med[dets[0]], med[dets[-1]]
            alpha = np.isfinite(b) & np.isfinite(rr)       # only where both colours exist (no false-colour edges)
            chan = np.dstack([rr, (rr + b) / 2, b])
        im = to_rgba(chan, alpha)
        save_webp(im, cp)
        save_webp(thumb(im), ctp)

    # timeline.json
    tl_frames = []
    for r in frames:
        fid = frame_id(r["file"])
        tl_frames.append({
            "frame_id": fid, "burst_id": r["burst_id"], "time_utc": r["t_mid_utc"],
            "mjd": float(r["t_mid_mjd"]), "detector": r["detector"],
            "wavelength_um": float(r["wl_um"]) if r["wl_um"] else None,
            "image": "full/%s.webp" % fid, "thumb": "thumb/%s.webp" % fid,
            "ra_center": float(r["grid_ra"]), "dec_center": float(r["grid_dec"]),
            "coverage": float(r["coverage"]) if r["coverage"] else None,
            "quality": r["quality"], "update_id": "u000",
            "added_utc": ingest.get((r["obs_id"], r["detector"]))})
    tl_bursts = []
    for bid, fr in bursts.items():
        ms = [float(r["t_mid_mjd"]) for r in fr]
        tl_bursts.append({
            "burst_id": bid, "time_utc": mjd_to_iso((min(ms) + max(ms)) / 2),
            "frame_ids": [frame_id(r["file"]) for r in fr],
            "detectors": sorted({r["detector"] for r in fr}, key=lambda d: int(d[1:])),
            "ra_center": float(fr[0]["grid_ra"]), "dec_center": float(fr[0]["grid_dec"]),
            "composite": "composite/%s.webp" % bid, "composite_thumb": "composite_thumb/%s.webp" % bid,
            "representative": "composite/%s.webp" % bid})
    timeline = {
        "patch": {"patch_id": patch, "name": meta["name"], "kind": meta["kind"],
                  "followed_object": meta["followed_object"], "size_px": size,
                  "pixel_scale_arcsec": PIXEL_ARCSEC, "north_up": True, "projection": "TAN",
                  "date_start": frames[0]["t_mid_utc"], "date_end": frames[-1]["t_mid_utc"],
                  "n_frames": len(frames), "n_bursts": len(bursts)},
        "frames": tl_frames, "bursts": tl_bursts}
    write_json(os.path.join(pdir, "timeline.json"), timeline)

    # markers.json (known objects, image pixel convention)
    markers = []
    lpath = os.path.join("data", "labels", patch, "labels.csv")
    if os.path.exists(lpath):
        for r in csv.DictReader(open(lpath, encoding="utf-8")):
            if r["in_data"] != "1":
                continue
            v = float(r["v_mag"]) if r["v_mag"] else None
            if meta["kind"] == "fixed":
                vis = r.get("confirmed") == "1"
            else:
                vis = v is not None and v < 17.0
            markers.append({"frame_id": frame_id(r["file"]), "object_id": object_id(r["object"]),
                            "name": r["object"], "x": round(float(r["x"]), 2),
                            "y": round((size - 1) - float(r["y"]), 2), "v_mag": v, "likely_visible": vis})
    write_json(os.path.join(pdir, "markers.json"), markers)
    print("  %s: %d frames (%d new images), %d bursts, %d markers, %.0f s"
          % (patch, len(frames), made, len(bursts), len(markers), time.time() - t0), flush=True)
    return timeline


def build_3i_addon():
    """3I/ATLAS true positions as markers (frontend only, never for the detector teammate)."""
    key = {(r["obs_id"], r["detector"]): r for r in csv.DictReader(open("answer_key_3i_atlas.csv", encoding="utf-8"))}
    frames = list(csv.DictReader(open(os.path.join("data", "aligned", "3i-atlas", "frames.csv"), encoding="utf-8")))
    rows = []
    for r in frames:
        k = key.get((r["obs_id"], r["detector"]))
        if not k:
            continue
        ra, dec = math.radians(float(k["comet_ra"])), math.radians(float(k["comet_dec"]))
        a0, d0 = math.radians(float(r["grid_ra"])), math.radians(float(r["grid_dec"]))
        cosc = math.sin(d0) * math.sin(dec) + math.cos(d0) * math.cos(dec) * math.cos(ra - a0)
        xi = math.degrees(math.cos(dec) * math.sin(ra - a0) / cosc)
        eta = math.degrees((math.cos(d0) * math.sin(dec) - math.sin(d0) * math.cos(dec) * math.cos(ra - a0)) / cosc)
        n = int(r["grid_px"])
        c = (n - 1) / 2.0
        x, y_img = c - xi * 3600 / PIXEL_ARCSEC, c - eta * 3600 / PIXEL_ARCSEC
        d, _ = read_layers(os.path.join("data", "aligned", "3i-atlas", r["file"]), ["SCI", "SNR", "MASK"])
        ix, iy = int(round(x)), int(round((n - 1) - y_img))
        in_data = (0 <= ix < n and 0 <= iy < n and bool(np.isfinite(d["SCI"][iy, ix]))
                   and not (int(d["MASK"][iy, ix]) & 8))
        snr = None
        if in_data:
            box = d["SNR"][max(0, iy - 2):iy + 3, max(0, ix - 2):ix + 3]
            snr = float(np.nanmax(box)) if np.isfinite(box).any() else None
        rows.append({"frame_id": frame_id(r["file"]), "object_id": "3I", "name": "3I/ATLAS (C/2025 N1)",
                     "x": round(x, 2), "y": round(y_img, 2), "in_data": bool(in_data),
                     "snr_peak": None if snr is None else round(snr, 1),
                     "likely_visible": bool(in_data and snr is not None and snr >= 5)})
    write_json(os.path.join(OUT, "addons", "3i-atlas_markers.json"), rows)
    print("  addons/3i-atlas_markers.json: %d frames, %d on data, %d likely visible"
          % (len(rows), sum(r["in_data"] for r in rows), sum(r["likely_visible"] for r in rows)), flush=True)


def write_manifest(ingest):
    patches, files = [], []
    for p in PATCHES:
        tpath = os.path.join(OUT, p, "timeline.json")
        if not os.path.exists(tpath):
            continue
        h = json.load(open(tpath, encoding="utf-8"))["patch"]
        patches.append({"patch_id": p, "name": h["name"], "kind": h["kind"], "n_frames": h["n_frames"],
                        "n_bursts": h["n_bursts"], "date_start": h["date_start"], "date_end": h["date_end"],
                        "folder": p + "/"})
    for root, _, fs in os.walk(OUT):
        for f in fs:
            if f.endswith(".part") or f == "manifest.json":
                continue
            path = os.path.join(root, f)
            files.append({"path": os.path.relpath(path, OUT).replace(os.sep, "/"), "bytes": os.path.getsize(path)})
    files.sort(key=lambda d: d["path"])
    latest = max(ingest.values())
    write_json(os.path.join(OUT, "history.json"), [{
        "update_id": "u000", "ingested_utc": latest, "baseline": True,
        "data_through_utc": max(p["date_end"] for p in patches) if patches else None,
        "n_frames": sum(p["n_frames"] for p in patches), "frames_added": "all frames in the baseline",
        "note": "Baseline: SPHEREx QR2 + QR3 photos. Baseline frames are never NEW."}])
    write_json(os.path.join(OUT, "manifest.json"), {
        "version": "0.1", "generated_utc": iso(datetime.now(timezone.utc)),
        "data_through_utc": max(p["date_end"] for p in patches) if patches else None,
        "latest_ingest_utc": latest, "new_badge_days": 7,
        "new_badge_rule": "a frame is NEW if its update_id is not a baseline update and that update's "
                          "ingested_utc >= latest_ingest_utc - 7 days (dataset clock, not the visitor's clock)",
        "patches": patches, "files": files})
    tot = sum(f["bytes"] for f in files)
    print("manifest.json: %d patches, %d files, %.1f MB" % (len(patches), len(files), tot / 1e6))


def test_webp():
    """Faint known asteroids: does lossy WebP keep them? Compare a 5x5 box around each label."""
    rows = [r for r in csv.DictReader(open(os.path.join("data", "labels", "ecliptic-virgo", "labels.csv")))
            if r["confirmed"] == "1" and 17.5 <= float(r["v_mag"]) < 19.5][:12]
    frames = {r["file"]: r for r in csv.DictReader(open(os.path.join("data", "aligned", "ecliptic-virgo", "frames.csv")))}
    st = json.load(open(STRETCH_FILE))["ecliptic-virgo"]
    import io
    print("object                     V     peak-minus-sky (0-255): original / lossy q%d / lossless" % WEBP_Q)
    for r in rows:
        img, alpha = load_frame("ecliptic-virgo", frames[r["file"]], st)
        im = to_rgba(img, alpha)
        n = im.size[0]
        x, y = int(round(float(r["x"]))), int(round((n - 1) - float(r["y"])))
        res = []
        for mode in ("orig", "lossy", "lossless"):
            if mode == "orig":
                arr = np.asarray(im)[:, :, 0].astype(float)
            else:
                b = io.BytesIO()
                im.save(b, "WEBP", lossless=(mode == "lossless"), quality=100 if mode == "lossless" else WEBP_Q, method=6)
                arr = np.asarray(Image.open(io.BytesIO(b.getvalue())).convert("RGBA"))[:, :, 0].astype(float)
            box = arr[y - 2:y + 3, x - 2:x + 3]
            ring = np.concatenate([arr[y - 6:y + 7, x - 6].ravel(), arr[y - 6:y + 7, x + 6].ravel()])
            res.append(box.max() - np.median(ring))
        print("%-26s %4.1f  %5.1f / %5.1f / %5.1f" % (r["object"][:26], float(r["v_mag"]), *res))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patch", action="append", choices=list(PATCHES))
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--test-webp", action="store_true")
    a = ap.parse_args()
    stretch_all = json.load(open(STRETCH_FILE)) if os.path.exists(STRETCH_FILE) else {}
    if a.test_webp:
        if "ecliptic-virgo" not in stretch_all:
            fr = list(csv.DictReader(open(os.path.join("data", "aligned", "ecliptic-virgo", "frames.csv"))))
            stretch_all["ecliptic-virgo"] = measure_stretch("ecliptic-virgo", fr)
            write_json(STRETCH_FILE, stretch_all)
        test_webp()
        return
    ingest = ingest_times()
    t0 = time.time()
    for p in a.patch or list(PATCHES):
        print("\n%s" % p, flush=True)
        build_patch(p, a, ingest, stretch_all)
        if p == "3i-atlas":
            build_3i_addon()
    write_manifest(ingest)
    print("Done in %.1f min" % ((time.time() - t0) / 60))


if __name__ == "__main__":
    main()
