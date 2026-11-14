#!/usr/bin/env python3
"""
build_nep_manifest.py  -  Specula (NASA Space Apps 2026, "Planet X and SPHEREx")

Builds the North Ecliptic Pole (NEP) patch, option C ("daily sample"):
for every UTC day from 2026-07-01 to 2026-08-30 and every detector that photographed
our NEP square (centre RA 270.0, Dec +66.56, 0.5 deg wide) that day, keep ONE photo:
the one where our square sits most centrally, as long as its sky position is good
(FINAST 0) and at most 5% of its pixels were hit by cosmic rays or satellites
(otherwise the next most central one, up to 3 tries). If our square would be cut off
by the photo edge in every photo of that day/detector, that slot is skipped.

Needs only Python 3.8+ (no extra packages). Run it from the Specula folder:

    python build_nep_manifest.py              # build + add the NEP rows to manifest_all.csv
    python build_nep_manifest.py --no-merge   # build only, leave manifest_all.csv untouched

Writes:
    manifest_nep_cats_eye.csv   the chosen photos (same 25 columns as the other manifests)
    nep_candidates.csv          every candidate photo, its score, and why it was or wasn't chosen
    manifest_all.csv            updated with the NEP rows (the version before is kept in _backup_v2/)

Safe to re-run: the NEP rows are rebuilt from scratch and never duplicated.
"""
import argparse
import csv
import hashlib
import io
import math
import os
import random
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

IRSA = "https://irsa.ipac.caltech.edu"
AWS = "https://nasa-irsa-spherex.s3.amazonaws.com"
IRSA_SPHEREX = IRSA + "/ibe/data/spherex/"
UA = "Specula-SpaceApps2026-nep-builder/1.0"
RETRY_CODES = {429, 500, 502, 503, 504}
REWRITES = []                                   # (old_prefix, new_prefix) - only used for testing

PATCH, PATCH_TYPE = "nep-cats-eye", "fixed"
RA, DEC, SIZE_DEG = 270.0, 66.56, 0.5           # our square: Cat's Eye Nebula region at the NEP
T0_MJD, T1_MJD = 61222.0, 61283.0               # 2026-07-01 00:00 UTC up to (not incl.) 2026-08-31 00:00 UTC
COLLECTIONS = ("spherex_qr2_deep", "spherex_qr3_deep")
MIN_EDGE_DEG = SIZE_DEG / 2                     # our square's centre must be >= half a square from the photo edge
MAX_TRIES = 3
MAX_TRANSIENT_PCT = 5.0
NPIX = 2040 * 2040
EXPECTED = (306, "58cde76afe562187")            # independent check: (photos, fingerprint)

COLUMNS = ["patch", "patch_type", "release", "obs_id", "detector", "burst_id", "window_id",
           "t_start_utc", "t_start_mjd", "t_mid_mjd", "exp_s", "wl_min_um", "wl_max_um",
           "photo_ra", "photo_dec", "cutout_ra", "cutout_dec", "cutout_size_deg", "file_url",
           "cutout_url", "pipeline_version", "finast", "transient_pct", "full_file_mb", "quality"]
OUT_MANIFEST = "manifest_nep_cats_eye.csv"
OUT_CANDIDATES = "nep_candidates.csv"
ALL_MANIFEST = "manifest_all.csv"
BACKUP_DIR = "_backup_v2"

# ----------------------------------------------------------------------------- network
def rewrite(url):
    for old, new in REWRITES:
        if url.startswith(old):
            return new + url[len(old):]
    return url

def aws_url(file_url):
    if file_url.startswith(IRSA_SPHEREX):
        return AWS + "/" + file_url[len(IRSA_SPHEREX):]
    return None

def http_get(url, headers=None, timeout=120, attempts=4, max_bytes=None):
    """GET with retries. max_bytes: stop reading after this many bytes."""
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    delay, last = 5, ""
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(rewrite(url), headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if not max_bytes:
                    return r.read()
                buf = b""
                while len(buf) < max_bytes:
                    chunk = r.read(max_bytes - len(buf))
                    if not chunk:
                        break
                    buf += chunk
                return buf
        except urllib.error.HTTPError as e:
            last = "HTTP %d" % e.code
            if e.code not in RETRY_CODES:
                raise IOError(last)
        except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as e:
            last = str(e)[:150]
        if attempt < attempts:
            time.sleep(delay + random.uniform(0, 1))
            delay *= 3
    raise IOError("gave up after %d tries: %s" % (attempts, last))

# ----------------------------------------------------------------------------- geometry
def gnomonic(ra, dec):
    """Project (ra, dec) onto a flat plane touching the sky at our square's centre. Returns degrees."""
    a0, d0, a, d = math.radians(RA), math.radians(DEC), math.radians(ra), math.radians(dec)
    cc = math.sin(d0) * math.sin(d) + math.cos(d0) * math.cos(d) * math.cos(a - a0)
    x = math.cos(d) * math.sin(a - a0) / cc
    y = (math.cos(d0) * math.sin(d) - math.sin(d0) * math.cos(d) * math.cos(a - a0)) / cc
    return math.degrees(x), math.degrees(y)

def edge_distance(s_region):
    """Distance (deg) from our square's centre to the nearest edge of the photo outline
    (negative if the centre is outside the photo)."""
    parts = s_region.split()
    nums = []
    for p in parts:
        try:
            nums.append(float(p))
        except ValueError:
            pass                                 # skips the words POLYGON / ICRS
    if len(nums) < 6:
        return None
    v = [gnomonic(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
    best, inside = float("inf"), False
    for i in range(len(v)):
        ax, ay = v[i]
        bx, by = v[(i + 1) % len(v)]
        if (ay > 0) != (by > 0) and 0 < ax + (0 - ay) * (bx - ax) / (by - ay):
            inside = not inside                  # ray from the centre towards +x crosses this edge
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        if l2 == 0:
            continue
        t = max(0.0, min(1.0, -(ax * dx + ay * dy) / l2))
        best = min(best, math.hypot(ax + t * dx, ay + t * dy))
    return best if inside else -best

# ----------------------------------------------------------------------------- FITS header
def _value(v):
    v = v.strip()
    if v.startswith("'"):
        end = v.find("'", 1)
        while end != -1 and end + 1 < len(v) and v[end + 1] == "'":
            end = v.find("'", end + 2)
        return (v[1:end] if end != -1 else v[1:]).strip()
    return v.split("/")[0].strip()

def parse_cards(buf, start):
    """Read one FITS header starting at byte `start`. Returns (cards, start_of_next_block) or (None, None)."""
    cards, pos = {}, start
    while pos + 80 <= len(buf):
        card = buf[pos:pos + 80].decode("latin-1")
        pos += 80
        key = card[:8].strip()
        if key == "END":
            return cards, start + ((pos - start + 2879) // 2880) * 2880
        if card.startswith("HIERARCH"):
            body = card[8:]
            if "=" in body:
                k, v = body.split("=", 1)
                cards[k.strip()] = _value(v)
        elif card[8:10] == "= ":
            cards[key] = _value(card[10:])
    return None, None

def read_header(url):
    data = http_get(url, headers={"Range": "bytes=0-39999"}, timeout=60, attempts=3, max_bytes=40000)
    if not data.startswith(b"SIMPLE  ="):
        raise IOError("not a FITS file")
    prim, nxt = parse_cards(data, 0)
    if prim is None:
        raise IOError("primary header incomplete")
    img, _ = parse_cards(data, nxt)
    if img is None:
        raise IOError("image header incomplete")
    try:
        n_tr = int(img.get("L2 N_TRANSIENT", ""))
    except ValueError:
        n_tr = None
    try:
        finast = int(img.get("FINAST", ""))
    except ValueError:
        finast = None
    return {"version": prim.get("VERSION", ""), "finast": finast, "n_transient": n_tr,
            "date_beg": img.get("DATE-BEG", ""), "h_obsid": img.get("OBSID", ""),
            "h_detector": img.get("DETECTOR", "")}

# ----------------------------------------------------------------------------- steps
def mjd_to_dt(mjd):
    return datetime(1858, 11, 17) + timedelta(days=mjd)

def query_sia(collection):
    params = urllib.parse.urlencode({
        "COLLECTION": collection,
        "POS": "circle %g %g 0.0003" % (RA, DEC),
        "TIME": "%g %g" % (T0_MJD, T1_MJD),
        "RESPONSEFORMAT": "CSV",
        "MAXREC": "100000",
    })
    text = http_get(IRSA + "/SIA?" + params, timeout=300).decode("utf-8", "replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    need = {"obs_id", "energy_bandpassname", "t_min", "t_max", "t_exptime", "s_ra", "s_dec",
            "em_min", "em_max", "access_url", "access_estsize", "s_region", "obs_collection"}
    if rows and not need <= set(rows[0].keys()):
        sys.exit("IRSA's answer is missing columns: %s" % ", ".join(sorted(need - set(rows[0].keys()))))
    if len(rows) >= 100000:
        sys.exit("IRSA hit its row limit for %s - tell Claude." % collection)
    return rows

def to_candidate(r):
    det = r["energy_bandpassname"].replace("SPHEREx-", "").strip()
    c = {
        "obs_id": r["obs_id"].strip(), "detector": det, "collection": r["obs_collection"].strip(),
        "t_min": float(r["t_min"]), "t_max": float(r["t_max"]), "t_exptime": float(r["t_exptime"]),
        "s_ra": float(r["s_ra"]), "s_dec": float(r["s_dec"]),
        "em_min": float(r["em_min"]), "em_max": float(r["em_max"]),
        "url": r["access_url"].strip(), "estsize": r["access_estsize"].strip(),
        "edge": edge_distance(r["s_region"]),
        "checked": "no", "note": "",
    }
    c["release"] = "qr2" if c["collection"].startswith("spherex_qr2") else "qr3"
    c["day"] = int(math.floor(c["t_min"]))
    return c

def check_slot(cands):
    """Pick the best photo of one (day, detector) slot. Returns (pick or None, quality)."""
    tried = []
    eligible = [c for c in cands if c["edge"] is not None and c["edge"] >= MIN_EDGE_DEG]
    for c in eligible[:MAX_TRIES]:
        h, err = None, ""
        for url in (c["url"], aws_url(c["url"])):
            if not url:
                continue
            try:
                h = read_header(url)
                break
            except Exception as e:  # noqa: BLE001
                err = str(e)[:120]
        if h is None:
            c["checked"], c["note"] = "failed", "header unreadable: " + err
            continue
        if h["h_obsid"] != c["obs_id"] or ("D" + h["h_detector"]) != c["detector"]:
            raise RuntimeError("header does not match IRSA's list for %s %s (got %s D%s)"
                               % (c["obs_id"], c["detector"], h["h_obsid"], h["h_detector"]))
        c.update(h)
        c["checked"] = "yes"
        c["pct"] = 100.0 * h["n_transient"] / NPIX if h["n_transient"] is not None else None
        tried.append(c)
        if c["finast"] == 0 and c["pct"] is not None and c["pct"] <= MAX_TRANSIENT_PCT:
            return c, "ok"
        c["note"] = "failed quality: FINAST=%s, transients %s%%" % (
            c["finast"], "?" if c["pct"] is None else "%.2f" % c["pct"])
    if not tried:
        return None, ""
    tried.sort(key=lambda c: (c["finast"] != 0, c["pct"] if c["pct"] is not None else 999.0, -c["edge"]))
    b = tried[0]
    if b["pct"] is None or b["pct"] > MAX_TRANSIENT_PCT:
        return b, "warn_transients"
    return b, ("warn_astrometry" if b["finast"] != 0 else "ok")

def make_row(c, quality):
    file_url = c["url"]
    if c.get("date_beg"):
        t_start_utc = c["date_beg"][:19] + "Z"
    else:
        t_start_utc = mjd_to_dt(c["t_min"]).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        full_mb = "%.1f" % (float(c["estsize"]) / 1000.0)
    except ValueError:
        full_mb = ""
    centre = "%.6f,%.6f" % (RA, DEC)
    return {
        "patch": PATCH, "patch_type": PATCH_TYPE, "release": c["release"],
        "obs_id": c["obs_id"], "detector": c["detector"], "burst_id": c["obs_id"].rsplit("_", 1)[0],
        "window_id": "1",                        # the NEP is photographed every day: one continuous window
        "t_start_utc": t_start_utc, "t_start_mjd": "%.6f" % c["t_min"],
        "t_mid_mjd": "%.6f" % ((c["t_min"] + c["t_max"]) / 2.0), "exp_s": "%.2f" % c["t_exptime"],
        "wl_min_um": "%.4f" % (c["em_min"] * 1e6), "wl_max_um": "%.4f" % (c["em_max"] * 1e6),
        "photo_ra": "%.6f" % c["s_ra"], "photo_dec": "%.6f" % c["s_dec"],
        "cutout_ra": "%.6f" % RA, "cutout_dec": "%.6f" % DEC, "cutout_size_deg": "%g" % SIZE_DEG,
        "file_url": file_url, "cutout_url": file_url + "?center=%s&size=%g" % (centre, SIZE_DEG),
        "pipeline_version": c.get("version", ""), "finast": str(c.get("finast", "")),
        "transient_pct": "%.2f" % c["pct"] if c.get("pct") is not None else "",
        "full_file_mb": full_mb, "quality": quality,
    }

def write_csv(path, fieldnames, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)

def merge_into_all(new_rows):
    with open(ALL_MANIFEST, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cols, rows = reader.fieldnames, list(reader)
    if cols != COLUMNS:
        sys.exit("%s has unexpected columns - was it re-saved in Excel? (not changed)" % ALL_MANIFEST)
    keep = [r for r in rows if r["patch"] != PATCH]
    backup = os.path.join(BACKUP_DIR, ALL_MANIFEST)
    if not os.path.exists(backup):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copy2(ALL_MANIFEST, backup)
    write_csv(ALL_MANIFEST, COLUMNS, keep + new_rows)
    with open(ALL_MANIFEST, newline="", encoding="utf-8") as f:
        check = list(csv.DictReader(f))
    counts = {}
    for r in check:
        counts[r["patch"]] = counts.get(r["patch"], 0) + 1
        if not r["cutout_url"].startswith(r["file_url"] + "?center="):
            sys.exit("Verification failed after writing %s - restore it from %s" % (ALL_MANIFEST, backup))
    if counts.get(PATCH, 0) != len(new_rows) or len(check) != len(keep) + len(new_rows):
        sys.exit("Verification failed after writing %s - restore it from %s" % (ALL_MANIFEST, backup))
    return len(rows) - len(keep), counts, backup

# ----------------------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description="Build the NEP daily-sample manifest (Specula, option C).")
    p.add_argument("--no-merge", action="store_true", help="do not add the NEP rows to manifest_all.csv")
    p.add_argument("--workers", type=int, default=8, help="parallel header reads (default 8)")
    p.add_argument("--rewrite", action="append", default=[], help=argparse.SUPPRESS)  # testing only: OLD=NEW
    args = p.parse_args()
    for rw in args.rewrite:
        old, new = rw.split("=", 1)
        REWRITES.append((old, new))
    if not args.no_merge and not os.path.exists(ALL_MANIFEST):
        sys.exit("Cannot find %s - run this script from the Specula folder." % ALL_MANIFEST)

    t_start = time.time()
    d0 = mjd_to_dt(T0_MJD).strftime("%Y-%m-%d")
    d1 = mjd_to_dt(T1_MJD - 1).strftime("%Y-%m-%d")
    print("\n1) Asking IRSA for every photo of our NEP square, %s to %s..." % (d0, d1))
    cands, per_coll = [], {}
    for coll in COLLECTIONS:
        rows = query_sia(coll)
        per_coll[coll] = len(rows)
        print("   %-18s %6d photos" % (coll, len(rows)))
        cands += [to_candidate(r) for r in rows]
    cands = [c for c in cands if T0_MJD <= c["t_min"] < T1_MJD]
    seen, uniq = set(), []
    for c in cands:
        k = (c["obs_id"], c["detector"])
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    cands = uniq
    if not cands:
        sys.exit("IRSA returned no photos - try again later.")

    print("2) Scoring how central our square is in each of the %d photos..." % len(cands))
    slots = {}
    for c in cands:
        slots.setdefault((c["day"], c["detector"]), []).append(c)
    for k in slots:
        slots[k].sort(key=lambda c: (-(c["edge"] if c["edge"] is not None else -1.0), c["t_min"], c["obs_id"]))
        for i, c in enumerate(slots[k], 1):
            c["rank"] = i
            if c["edge"] is None or c["edge"] < MIN_EDGE_DEG:
                c["note"] = "our square would be cut off by the photo edge"
    print("   %d day x detector slots" % len(slots))

    print("3) Reading the header of the most central photo in each slot (quality check)...")
    lock, done, picks = threading.Lock(), [0], {}

    def work(key):
        pick, quality = check_slot(slots[key])
        with lock:
            done[0] += 1
            if done[0] % 50 == 0 or done[0] == len(slots):
                print("   %d / %d slots checked" % (done[0], len(slots)))
            if pick is not None:
                picks[key] = (pick, quality)

    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 16))) as pool:
        list(pool.map(work, sorted(slots)))

    chosen = [make_row(c, q) for c, q in picks.values()]
    chosen.sort(key=lambda r: (float(r["t_start_mjd"]), r["detector"]))
    for c, q in picks.values():
        c["note"] = "CHOSEN: most central photo that passed the quality check" if q == "ok" else \
                    "CHOSEN (%s): best of the photos checked" % q
    chosen_keys = {(c["obs_id"], c["detector"]) for c, _ in picks.values()}

    cand_rows = []
    for k in sorted(slots):
        slot_ok = k in picks and picks[k][1] == "ok"
        for c in slots[k]:
            if c["checked"] == "no" and not c["note"]:
                c["note"] = "not needed (a more central photo passed)" if slot_ok else \
                            "not checked (limit of %d tries per slot)" % MAX_TRIES
            cand_rows.append({
                "day_utc": mjd_to_dt(c["day"]).strftime("%Y-%m-%d"), "detector": c["detector"],
                "rank_in_slot": c["rank"], "obs_id": c["obs_id"], "release": c["release"],
                "t_start_mjd": "%.6f" % c["t_min"],
                "edge_deg": "" if c["edge"] is None else "%.3f" % c["edge"],
                "square_fits": "yes" if (c["edge"] is not None and c["edge"] >= MIN_EDGE_DEG) else "no",
                "header_checked": c["checked"], "finast": c.get("finast", ""),
                "transient_pct": "%.2f" % c["pct"] if c.get("pct") is not None else "",
                "chosen": "yes" if (c["obs_id"], c["detector"]) in chosen_keys else "no", "note": c["note"],
            })

    write_csv(OUT_MANIFEST, COLUMNS, chosen)
    write_csv(OUT_CANDIDATES, list(cand_rows[0].keys()), cand_rows)

    # ------------------------------------------------------------- summary
    n_skipped = sum(1 for k in slots if k not in picks)
    days = {}
    for c, _ in picks.values():
        days.setdefault(c["day"], set()).add(c["detector"])
    per_det, per_rel, per_q, per_ver = {}, {}, {}, {}
    for r in chosen:
        per_det[r["detector"]] = per_det.get(r["detector"], 0) + 1
        per_rel[r["release"]] = per_rel.get(r["release"], 0) + 1
        per_q[r["quality"]] = per_q.get(r["quality"], 0) + 1
        per_ver[r["pipeline_version"]] = per_ver.get(r["pipeline_version"], 0) + 1
    full_gb = sum(float(r["full_file_mb"] or 0) for r in chosen) / 1000.0
    fp = hashlib.sha256("\n".join(sorted("%s_%s" % (r["obs_id"], r["detector"]) for r in chosen))
                        .encode("utf-8")).hexdigest()[:16]
    n_days = int(T1_MJD - T0_MJD)
    fmt = lambda d: ", ".join("%s %d" % (k, d[k]) for k in sorted(d))

    print("\nNEP daily sample (option C)")
    print("  Photos from IRSA:   %d  (%s)" % (len(cands), ", ".join("%s %d" % kv for kv in per_coll.items())))
    print("  Day x detector:     %d slots | %d skipped (square cut off by photo edge) | %d chosen"
          % (len(slots), n_skipped, len(chosen)))
    print("  Days covered:       %d of %d | days with all 6 detectors: %d"
          % (len(days), n_days, sum(1 for s in days.values() if len(s) == 6)))
    print("  Per detector:       " + fmt(per_det))
    print("  Release:            " + fmt(per_rel) + "   (pipeline versions: " + fmt(per_ver) + ")")
    print("  Quality:            " + fmt(per_q))
    print("  Download size:      full photos ~%.1f GB" % full_gb)
    match = (len(chosen), fp) == EXPECTED
    print("  Fingerprint:        %s -> %s" % (fp, "MATCHES Claude's independent check (%d photos)" % EXPECTED[0]
                                             if match else "DIFFERENT from Claude's check (%d photos, %s) - tell Claude"
                                             % EXPECTED))
    print("\nWrote %s (%d rows) and %s (%d rows)." % (OUT_MANIFEST, len(chosen), OUT_CANDIDATES, len(cand_rows)))

    if args.no_merge:
        print("manifest_all.csv was NOT changed (--no-merge).")
    else:
        try:
            removed, counts, backup = merge_into_all(chosen)
        except PermissionError:
            sys.exit("Could not write %s - close it in Excel and run this script again." % ALL_MANIFEST)
        print("Updated %s: %d rows (%s)%s. Previous version kept in %s."
              % (ALL_MANIFEST, sum(counts.values()), fmt(counts),
                 " - replaced %d old NEP rows" % removed if removed else "", backup))
    print("Done in %.1f min." % ((time.time() - t_start) / 60))
    print("\nNext: python download_spherex.py all --mode full   (already-downloaded photos are skipped)")

if __name__ == "__main__":
    main()
