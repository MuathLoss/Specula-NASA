#!/usr/bin/env python3
"""
download_spherex.py  -  Specula (NASA Space Apps 2026, "Planet X and SPHEREx")

Downloads the SPHEREx photos listed in manifest_all.csv.
Needs only Python 3.8+ (no extra packages). Run it from the Specula folder.

    python download_spherex.py check              # is everything reachable? how fast? enough disk?
    python download_spherex.py test               # download 1 photo per patch and show what is inside
    python download_spherex.py all                # download everything as cutouts (~9 GB)
    python download_spherex.py all --mode full    # download the full photos instead (~78 GB)

Useful options:
    --patch ceres            only one patch (repeatable: --patch ceres --patch 3i-atlas)
    --workers 4              parallel downloads (default 4)
    --source aws|irsa        where full photos come from (default aws = NASA's Amazon mirror)
    --limit 20               only the first N photos (good for a trial run)

Safe to stop with Ctrl+C and re-run the same command: finished files are skipped,
failed ones are retried. Every attempt is recorded in download_log.csv.
"""
import argparse
import csv
import os
import random
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone

IRSA = "https://irsa.ipac.caltech.edu"
AWS = "https://nasa-irsa-spherex.s3.amazonaws.com"
IRSA_SPHEREX = IRSA + "/ibe/data/spherex/"
UA = "Specula-SpaceApps2026-downloader/1.0"
FITS_BLOCK = 2880
RETRY_CODES = {429, 500, 502, 503, 504}
PIXEL_ARCSEC = 6.15
PSF_MB = 4.94          # the PSF layer is always included at full size in a cutout
REWRITES = []          # (old_prefix, new_prefix) - only used for testing


# ----------------------------------------------------------------------------- helpers
def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rewrite(url):
    for old, new in REWRITES:
        if url.startswith(old):
            return new + url[len(old):]
    return url


def open_url(url, timeout=60, headers=None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    return urllib.request.urlopen(urllib.request.Request(rewrite(url), headers=h), timeout=timeout)


def aws_url(file_url):
    """Same photo on NASA's Amazon (AWS) mirror."""
    if file_url.startswith(IRSA_SPHEREX):
        return AWS + "/" + file_url[len(IRSA_SPHEREX):]
    return None


def human(nbytes):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if nbytes < 1000 or unit == "TB":
            return "%.1f %s" % (nbytes, unit)
        nbytes /= 1000.0


def rm(path):
    try:
        os.remove(path)
    except OSError:
        pass


def looks_like_fits(path):
    try:
        size = os.path.getsize(path)
        if size < FITS_BLOCK or size % FITS_BLOCK:
            return False
        with open(path, "rb") as f:
            return f.read(9) == b"SIMPLE  ="
    except OSError:
        return False


def fits_layers(path, max_hdus=12):
    """List the layers (HDUs) inside a FITS file using only the standard library."""
    layers = []
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        off = 0
        while off < size and len(layers) < max_hdus:
            f.seek(off)
            cards, nblocks, end = {}, 0, False
            while not end:
                block = f.read(FITS_BLOCK)
                if len(block) < FITS_BLOCK:
                    return layers
                nblocks += 1
                for i in range(0, FITS_BLOCK, 80):
                    card = block[i:i + 80].decode("latin-1")
                    key = card[:8].strip()
                    if key == "END":
                        end = True
                        break
                    if card[8:10] == "= ":
                        cards[key] = card[10:].split("/")[0].strip().strip("'").strip()
            naxis = int(cards.get("NAXIS", "0") or 0)
            dims = [int(cards.get("NAXIS%d" % k, "0") or 0) for k in range(1, naxis + 1)]
            n = 1
            for d in dims:
                n *= d
            if naxis == 0:
                n = 0
            data = n * abs(int(cards.get("BITPIX", "8") or 8)) // 8 + int(cards.get("PCOUNT", "0") or 0)
            layers.append((cards.get("EXTNAME", "PRIMARY"), "x".join(str(d) for d in dims) or "-", cards))
            off += nblocks * FITS_BLOCK + ((data + FITS_BLOCK - 1) // FITS_BLOCK) * FITS_BLOCK
    return layers


def est_bytes(row, mode):
    if mode == "full":
        try:
            return float(row.get("full_file_mb") or 71.6) * 1e6
        except ValueError:
            return 71.6e6
    try:
        px = float(row["cutout_size_deg"]) * 3600 / PIXEL_ARCSEC
    except (KeyError, ValueError):
        px = 585
    return (PSF_MB + px * px * 16 / 1e6) * 1e6


def dest_path(out_dir, mode, row):
    return os.path.join(out_dir, mode, row["patch"], "%s_%s.fits" % (row["obs_id"], row["detector"]))


def sources_for(row, mode, source):
    if mode == "cutout":
        return [row["cutout_url"]]
    urls = []
    a = aws_url(row["file_url"])
    if source == "aws" and a:
        urls = [a, row["file_url"]]          # AWS first, IRSA as backup
    else:
        urls = [row["file_url"]] + ([a] if a else [])
    return urls


# ----------------------------------------------------------------------------- download one file
class Stopped(Exception):
    pass


def fetch(url, dest, stop, attempts=5, timeout=120, chunk=1 << 20):
    """Download url -> dest. Returns (status, http_code, nbytes, error)."""
    tmp = dest + ".part"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    delay, code, err = 5, None, ""
    for attempt in range(1, attempts + 1):
        if stop.is_set():
            return "stopped", code, 0, "stopped"
        try:
            with open_url(url, timeout=timeout) as r, open(tmp, "wb") as f:
                code = getattr(r, "status", 200)
                expected = r.headers.get("Content-Length")
                n, head = 0, b""
                while True:
                    if stop.is_set():
                        raise Stopped()
                    buf = r.read(chunk)
                    if not buf:
                        break
                    if len(head) < 9:
                        head += buf[:9]
                        if len(head) >= 9 and not head.startswith(b"SIMPLE  ="):
                            raise ValueError("server did not send a FITS file (got %r)" % head[:40])
                    f.write(buf)
                    n += len(buf)
            if expected is not None and int(expected) != n:
                raise ValueError("incomplete: got %d of %s bytes" % (n, expected))
            if n < FITS_BLOCK or n % FITS_BLOCK:
                raise ValueError("size %d is not a valid FITS size" % n)
            os.replace(tmp, dest)
            return "ok", code, n, ""
        except Stopped:
            rm(tmp)
            return "stopped", code, 0, "stopped"
        except urllib.error.HTTPError as e:
            rm(tmp)
            code, err = e.code, "HTTP %d" % e.code
            if e.code not in RETRY_CODES:
                return "failed", code, 0, err
        except (urllib.error.URLError, socket.timeout, ConnectionError, ValueError, OSError) as e:
            rm(tmp)
            err = str(e)[:200]
        if attempt < attempts:
            until = time.time() + delay + random.uniform(0, 2)
            while time.time() < until:
                if stop.is_set():
                    return "stopped", code, 0, "stopped"
                time.sleep(0.5)
            delay = min(delay * 3, 120)
    return "failed", code, 0, err


# ----------------------------------------------------------------------------- manifest + log
def load_manifest(path, patches=None, limit=None):
    if not os.path.exists(path):
        sys.exit("Cannot find %s - run this script from the Specula folder." % path)
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    need = {"patch", "obs_id", "detector", "file_url", "cutout_url", "cutout_size_deg"}
    missing = need - set(rows[0].keys()) if rows else need
    if missing:
        sys.exit("Manifest is missing columns: %s" % ", ".join(sorted(missing)))
    for r in rows:
        if not r["cutout_url"].startswith(r["file_url"] + "?center="):
            sys.exit("Broken cutout_url for %s %s - was the CSV re-saved in Excel?" % (r["obs_id"], r["detector"]))
    if patches:
        known = sorted({r["patch"] for r in rows})
        bad = [p for p in patches if p not in known]
        if bad:
            sys.exit("Unknown patch %s. Choose from: %s" % (bad, ", ".join(known)))
        rows = [r for r in rows if r["patch"] in patches]
    if limit:
        rows = rows[:limit]
    return rows


class Log:
    FIELDS = ["time_utc", "patch", "obs_id", "detector", "mode", "status", "http_code",
              "bytes", "seconds", "url", "local_path", "error"]

    def __init__(self, path):
        self.path, self.lock = path, threading.Lock()
        if not os.path.exists(path):
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(self.FIELDS)

    def write(self, **kw):
        with self.lock, open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([kw.get(k, "") for k in self.FIELDS])


# ----------------------------------------------------------------------------- service checks
def probe(url, headers=None, timeout=30):
    t0 = time.time()
    try:
        with open_url(url, timeout=timeout, headers=headers) as r:
            body = r.read()
            return getattr(r, "status", 200), body, time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, b"", time.time() - t0
    except Exception as e:  # noqa: BLE001
        return None, str(e).encode()[:120], time.time() - t0


def cutout_service_ok(row):
    tiny = row["file_url"] + "?center=%s,%s&size=0.01" % (row["cutout_ra"], row["cutout_dec"])
    code, body, _ = probe(tiny)
    return code == 200 and body.startswith(b"SIMPLE  ="), code


def cmd_check(rows, args):
    r0 = rows[0]
    print("\nChecking the services this download needs (sample photo %s %s)\n" % (r0["obs_id"], r0["detector"]))
    tests = [
        ("IRSA image search (SIA)", IRSA + "/SIA?COLLECTION=spherex_qr2&POS=circle+180+0+0.0003&RESPONSEFORMAT=CSV&MAXREC=1", None, b"s_ra"),
        ("IRSA file server (full photos)", r0["file_url"], {"Range": "bytes=0-79"}, b"SIMPLE"),
        ("AWS mirror (full photos)", aws_url(r0["file_url"]) or "", {"Range": "bytes=0-79"}, b"SIMPLE"),
        ("SPHEREx cutout service", r0["file_url"] + "?center=%s,%s&size=0.01" % (r0["cutout_ra"], r0["cutout_dec"]), None, b"SIMPLE"),
        ("Control: 2MASS cutout (other mission)", IRSA + "/ibe/data/twomass/allsky/allsky/000105s/s019/image/hi0190056.fits.gz?center=83.9124,-43.1616deg&size=90pix", None, b"\x1f\x8b"),
    ]
    status = {}
    for name, url, hdr, magic in tests:
        code, body, secs = probe(url, hdr)
        ok = code in (200, 206) and body.startswith(magic)
        status[name] = ok
        print("  %-40s %s  (HTTP %s, %.1fs)" % (name, "OK  " if ok else "DOWN", code, secs))

    print("\nSpeed test (8 MB from each source)...")
    speeds = {}
    for name, url in (("AWS", aws_url(r0["file_url"])), ("IRSA", r0["file_url"])):
        code, body, secs = probe(url, {"Range": "bytes=0-7999999"}, timeout=120)
        if code in (200, 206) and len(body) > 1e6:
            speeds[name] = len(body) / secs / 1e6
            print("  %-5s %.1f MB/s per download stream" % (name, speeds[name]))
        else:
            print("  %-5s failed (HTTP %s)" % (name, code))

    need_cut = sum(est_bytes(r, "cutout") for r in rows)
    need_full = sum(est_bytes(r, "full") for r in rows)
    free = shutil.disk_usage(os.path.abspath(args.out) if os.path.exists(args.out) else os.getcwd()).free
    print("\nDisk: %s free here. Needed: cutouts ~%s, full photos ~%s" % (human(free), human(need_cut), human(need_full)))
    best = max(speeds.values()) if speeds else None
    if best:
        par = best * min(args.workers, 4) * 0.8
        print("Estimated time with %d parallel downloads: cutouts ~%.0f min, full photos ~%.0f min"
              % (args.workers, need_cut / par / 1e6 / 60, need_full / par / 1e6 / 60))

    print("\nVerdict:")
    if status.get("SPHEREx cutout service"):
        print("  Cutouts work -> run:  python download_spherex.py test   then   python download_spherex.py all")
    elif status.get("AWS mirror (full photos)") or status.get("IRSA file server (full photos)"):
        if status.get("Control: 2MASS cutout (other mission)"):
            print("  SPHEREx cutouts are DOWN on IRSA's side (other missions' cutouts work, so it is not your internet).")
        else:
            print("  Cutouts are DOWN (also for other missions) - IRSA's cutout system or your connection to it.")
        print("  Full photos work -> either wait and re-run 'check' later, or run:")
        print("      python download_spherex.py test --mode full    then    python download_spherex.py all --mode full")
    else:
        print("  Cannot reach SPHEREx data at all - check your internet connection and try again.")


# ----------------------------------------------------------------------------- download many
def run_downloads(rows, args, log, label):
    stop = threading.Event()
    todo, skipped = [], 0
    for r in rows:
        d = dest_path(args.out, args.mode, r)
        if looks_like_fits(d):
            skipped += 1
        else:
            todo.append((r, d))
    print("\n%s: %d photos | already downloaded: %d | to download: %d | mode: %s%s"
          % (label, len(rows), skipped, len(todo), args.mode,
             (" | source: %s" % args.source) if args.mode == "full" else ""))
    if not todo:
        return [], skipped

    need = sum(est_bytes(r, args.mode) for r, _ in todo)
    os.makedirs(args.out, exist_ok=True)
    free = shutil.disk_usage(os.path.abspath(args.out)).free
    print("Expected size: ~%s | free disk: %s" % (human(need), human(free)))
    if need * 1.1 > free and not args.force:
        sys.exit("Not enough free disk space (use --force to try anyway).")

    if args.mode == "cutout":
        ok, code = cutout_service_ok(todo[0][0])
        if not ok:
            sys.exit("\nSPHEREx cutout service is not working right now (HTTP %s).\n"
                     "Either try again later, or download full photos instead:\n"
                     "    python download_spherex.py %s --mode full" % (code, args.command))

    results, done = [], [0]
    lock = threading.Lock()
    consecutive_503 = [0]
    t_start = time.time()

    def work(item):
        r, d = item
        last = ("failed", None, 0, "no source")
        used = ""
        for url in sources_for(r, args.mode, args.source):
            if stop.is_set():
                break
            t0 = time.time()
            last = fetch(url, d, stop)
            used = url
            if last[0] in ("ok", "stopped"):
                break
        status, code, n, err = last
        secs = time.time() - t0 if used else 0
        log.write(time_utc=utc_now(), patch=r["patch"], obs_id=r["obs_id"], detector=r["detector"],
                  mode=args.mode, status=status, http_code=code or "", bytes=n, seconds="%.1f" % secs,
                  url=used, local_path=d if status == "ok" else "", error=err)
        with lock:
            done[0] += 1
            if args.mode == "cutout":
                consecutive_503[0] = consecutive_503[0] + 1 if code == 503 and status == "failed" else 0
                if consecutive_503[0] >= 3:
                    stop.set()
            if status != "stopped":
                print("  [%d/%d] %-6s %-14s %s %s  %s  %s" % (
                    done[0], len(todo), status, r["patch"], r["obs_id"], r["detector"],
                    human(n) if n else "", err))
        return r, d, status

    pool = ThreadPoolExecutor(max_workers=args.workers)
    pending = {pool.submit(work, it) for it in todo}
    try:
        while pending:
            finished, pending = wait(pending, timeout=1.0, return_when=FIRST_COMPLETED)
            for fut in finished:
                results.append(fut.result())
    except KeyboardInterrupt:
        print("\nStopping... (partial files are discarded; re-run the same command to continue)")
        stop.set()
        for fut in pending:
            fut.cancel()
    finally:
        pool.shutdown(wait=True)

    okn = sum(1 for _, _, s in results if s == "ok")
    failed = [(r, s) for r, _, s in results if s == "failed"]
    total = sum(os.path.getsize(d) for _, d, s in results if s == "ok")
    print("\nDone in %.1f min: %d downloaded (%s), %d skipped, %d failed."
          % ((time.time() - t_start) / 60, okn, human(total), skipped, len(failed)))
    if args.mode == "cutout" and consecutive_503[0] >= 3:
        print("Stopped early: the cutout service started refusing requests (HTTP 503). Try later or use --mode full.")
    if failed:
        print("Failed photos are listed in download_log.csv - just re-run the same command to retry them.")
    return results, skipped


def cmd_test(rows, args, log):
    picks, seen = [], set()
    for r in rows:
        if r["patch"] not in seen and r.get("quality", "ok") == "ok":
            picks.append(r)
            seen.add(r["patch"])
    run_downloads(picks, args, log, "Test (1 photo per patch)")
    print("\nWhat is inside each test file:")
    for r in picks:
        d = dest_path(args.out, args.mode, r)
        if not looks_like_fits(d):
            print("\n  %s: not downloaded" % r["patch"])
            continue
        print("\n  %s  %s %s  (%s)  -> %s" % (r["patch"], r["obs_id"], r["detector"], human(os.path.getsize(d)), d))
        for name, dims, cards in fits_layers(d):
            extra = ""
            if name == "IMAGE":
                extra = "  detector=%s  time=%s  sky-position-quality(FINAST)=%s" % (
                    cards.get("DETECTOR", "?"), cards.get("DATE-BEG", cards.get("DATE-OBS", "?")), cards.get("FINAST", "?"))
            print("     %-9s %-14s%s" % (name, dims, extra))
    print("\nIf every patch shows IMAGE, FLAGS, VARIANCE, ZODI, PSF and WCS-WAVE layers, the test passed.")


# ----------------------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description="Download SPHEREx photos listed in the manifest (Specula).")
    p.add_argument("command", choices=["check", "test", "all"])
    p.add_argument("--mode", choices=["cutout", "full"], default="cutout",
                   help="cutout = only our square (~9 GB total), full = whole photos (~78 GB total)")
    p.add_argument("--source", choices=["aws", "irsa"], default="aws", help="for --mode full: where to download from")
    p.add_argument("--patch", action="append", help="only this patch (repeatable)")
    p.add_argument("--limit", type=int, help="only the first N photos")
    p.add_argument("--workers", type=int, default=4, help="parallel downloads (default 4, max 8)")
    p.add_argument("--manifest", default="manifest_all.csv")
    p.add_argument("--out", default=os.path.join("data", "raw"))
    p.add_argument("--log", default="download_log.csv")
    p.add_argument("--force", action="store_true", help="skip the free-disk-space check")
    p.add_argument("--rewrite", action="append", default=[], help=argparse.SUPPRESS)  # testing only: OLD=NEW
    args = p.parse_args()
    args.workers = max(1, min(args.workers, 8))
    for rw in args.rewrite:
        old, new = rw.split("=", 1)
        REWRITES.append((old, new))

    rows = load_manifest(args.manifest, args.patch, args.limit)
    print("Manifest: %d photos from %s" % (len(rows), args.manifest))
    if args.command == "check":
        cmd_check(rows, args)
        return
    log = Log(args.log)
    if args.command == "test":
        cmd_test(rows, args, log)
    else:
        run_downloads(rows, args, log, "Full download")


if __name__ == "__main__":
    main()
