#!/usr/bin/env python3
"""
verify_spherex.py  -  Specula (NASA Space Apps 2026, "Planet X and SPHEREx")

Checks every downloaded photo against manifest_all.csv (standard library only).
For each manifest row: file exists, is a complete FITS file (every layer present, file size
exactly matches the layers), and its header matches the manifest (photo ID, detector, start time,
sky-position quality). Writes verify_report.csv (one row per photo) and prints a summary.

    python verify_spherex.py                 # checks data/raw/full
    python verify_spherex.py --mode cutout   # checks data/raw/cutout
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timedelta

BLOCK = 2880


def value(v):
    v = v.strip()
    if v.startswith("'"):
        end = v.find("'", 1)
        while end != -1 and end + 1 < len(v) and v[end + 1] == "'":
            end = v.find("'", end + 2)
        return (v[1:end] if end != -1 else v[1:]).strip()
    return v.split("/")[0].strip()


def walk(path):
    """Return (layers, computed_size). layers = [(name, dims, cards)]."""
    size = os.path.getsize(path)
    layers, off = [], 0
    with open(path, "rb") as f:
        while off < size:
            f.seek(off)
            cards, nblocks, end = {}, 0, False
            while not end:
                block = f.read(BLOCK)
                if len(block) < BLOCK:
                    raise ValueError("file ends inside a header (truncated)")
                nblocks += 1
                for i in range(0, BLOCK, 80):
                    card = block[i:i + 80].decode("latin-1")
                    key = card[:8].strip()
                    if key == "END":
                        end = True
                        break
                    if card.startswith("HIERARCH") and "=" in card:
                        k, v = card[8:].split("=", 1)
                        cards[k.strip()] = value(v)
                    elif card[8:10] == "= ":
                        cards[key] = value(card[10:])
            naxis = int(cards.get("NAXIS", "0") or 0)
            dims = [int(cards.get("NAXIS%d" % k, "0") or 0) for k in range(1, naxis + 1)]
            n = 0
            if naxis:
                n = 1
                for d in dims:
                    n *= d
            data = n * abs(int(cards.get("BITPIX", "8") or 8)) // 8 * int(cards.get("GCOUNT", "1") or 1) \
                + int(cards.get("PCOUNT", "0") or 0)
            name = cards.get("EXTNAME", "PRIMARY")
            if name == "COMPRESSED_IMAGE" or cards.get("ZIMAGE") == "T":
                name = cards.get("EXTNAME", "?")
            layers.append((name, "x".join(str(d) for d in dims) or "-", cards))
            off += nblocks * BLOCK + ((data + BLOCK - 1) // BLOCK) * BLOCK
    return layers, off, size


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["full", "cutout"], default="full")
    p.add_argument("--manifest", default="manifest_all.csv")
    p.add_argument("--out", default=os.path.join("data", "raw"))
    p.add_argument("--report", default="verify_report.csv")
    a = p.parse_args()

    with open(a.manifest, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    report, problems = [], 0
    counts, total_bytes, layer_sets = {}, 0, {}
    expected_files = set()
    for i, r in enumerate(rows, 1):
        path = os.path.join(a.out, a.mode, r["patch"], "%s_%s.fits" % (r["obs_id"], r["detector"]))
        expected_files.add(os.path.normcase(os.path.abspath(path)))
        issues, layers_txt, size = [], "", 0
        if not os.path.exists(path):
            issues.append("missing")
        else:
            try:
                layers, computed, size = walk(path)
                total_bytes += size
                if computed != size:
                    issues.append("size %d != layers %d" % (size, computed))
                names = [l[0] for l in layers]
                layers_txt = " ".join(names)
                layer_sets[layers_txt] = layer_sets.get(layers_txt, 0) + 1
                prim = layers[0][2]
                img = next((l[2] for l in layers if l[0] == "IMAGE"), None)
                if img is None:
                    issues.append("no IMAGE layer")
                else:
                    if img.get("OBSID") != r["obs_id"]:
                        issues.append("OBSID %s" % img.get("OBSID"))
                    if "D" + img.get("DETECTOR", "?") != r["detector"]:
                        issues.append("DETECTOR %s" % img.get("DETECTOR"))
                    db = img.get("DATE-BEG", "")
                    if db:
                        t_file = datetime.strptime(db[:19], "%Y-%m-%dT%H:%M:%S")
                        t_man = datetime.strptime(r["t_start_utc"], "%Y-%m-%dT%H:%M:%SZ")
                        if abs((t_file - t_man).total_seconds()) > 2:
                            issues.append("time %s" % db)
                    if img.get("FINAST", "") != r["finast"]:
                        issues.append("FINAST %s" % img.get("FINAST"))
                for need in ("IMAGE", "FLAGS", "VARIANCE", "ZODI", "WCS-WAVE"):
                    if need not in names:
                        issues.append("no %s" % need)
                if "PSF" not in names and "EPSF" not in names:
                    issues.append("no PSF/EPSF")
                if prim.get("VERSION") and r["pipeline_version"] and prim.get("VERSION") != r["pipeline_version"]:
                    issues.append("VERSION %s" % prim.get("VERSION"))
            except Exception as e:  # noqa: BLE001
                issues.append("unreadable: %s" % e)
        status = "ok" if not issues else "PROBLEM"
        problems += bool(issues)
        counts.setdefault(r["patch"], [0, 0])
        counts[r["patch"]][0] += 1
        counts[r["patch"]][1] += 0 if issues else 1
        report.append({"patch": r["patch"], "obs_id": r["obs_id"], "detector": r["detector"],
                       "release": r["release"], "status": status, "bytes": size, "layers": layers_txt,
                       "issues": "; ".join(issues), "path": path})
        if i % 200 == 0:
            print("  checked %d / %d" % (i, len(rows)))

    extra = []
    base = os.path.join(a.out, a.mode)
    for root, _, files in os.walk(base):
        for fn in files:
            fp = os.path.normcase(os.path.abspath(os.path.join(root, fn)))
            if fp not in expected_files:
                extra.append(os.path.join(root, fn))

    with open(a.report, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(report[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(report)

    print("\nVerification of %d photos (%s mode)" % (len(rows), a.mode))
    for p_, (n, ok) in sorted(counts.items()):
        print("  %-15s %4d / %4d ok" % (p_, ok, n))
    print("  Total size: %.1f GB" % (total_bytes / 1e9))
    print("  Layer sets found:")
    for k, v in sorted(layer_sets.items(), key=lambda kv: -kv[1]):
        print("    %4d x  %s" % (v, k))
    print("  Extra files not in the manifest: %d%s" % (len(extra), (" e.g. " + extra[0]) if extra else ""))
    print("\n%s  (details in %s)" % ("ALL OK" if problems == 0 and not extra else "%d PROBLEMS" % problems, a.report))
    sys.exit(0 if problems == 0 else 1)


if __name__ == "__main__":
    main()
