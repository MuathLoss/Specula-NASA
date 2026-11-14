"""Specula stage 8.3 - build handoff #1 (v0.5) for the detector teammate.

Output: handoff/Specula_handoff_v0.5/  (same layout as the Google Drive folder "detector data")
  images_aligned/aligned_<patch>.zip     x5  (aligned images, all 5 patches, + frames.csv)
  images_difference/diff_<patch>.zip     x3  (difference images, 3 fixed patches, + static_sky + diff_frames.csv)
  tables/              small CSVs (manifest, frames, labels, known objects, psf info)
  README.md, DATA_DICTIONARY.md, CLAUDE.md   (copied from handoff_docs/)
  checksums.sha256

Zips use STORE (no compression): FITS float images barely compress, so storing is much faster.
Inside each zip the paths are data/<kind>/<patch>/<file>, so unzipping all of them into one
folder rebuilds the same data/ tree we use.

Safe to re-run: a zip whose contents already match the source is skipped.
Leak guard: stops if anything from the 3I/ATLAS answer key would enter the package.

Run:  python package_handoff.py --dry   (show the plan, write nothing)
      python package_handoff.py         (build)
"""
import argparse, csv, hashlib, math, os, shutil, sys, time, zipfile

VERSION = "v0.5"
OUT = os.path.join("handoff", "Specula_handoff_" + VERSION)
FIXED = ["ecliptic-virgo", "ecliptic-ra90", "nep-cats-eye"]
MOVING = ["3i-atlas", "ceres"]
BIG = [("aligned", p) for p in FIXED + MOVING] + [("diff", p) for p in FIXED]
ZIP_DIR = {"aligned": "images_aligned", "diff": "images_difference"}
DOCS = [os.path.join("handoff_docs", d) for d in ("README.md", "DATA_DICTIONARY.md", "CLAUDE.md", "verify_and_unzip.py")]
FORBIDDEN_NAMES = ["answer_key"]
FORBIDDEN_COLS = ["comet_ra", "comet_dec"]
COMET_3I = ["3I/", "2025 N1"]


def gb(n):
    return "%.2f GB" % (n / 1e9)


def src_files(kind, patch):
    d = os.path.join("data", kind, patch)
    if not os.path.isdir(d):
        sys.exit("missing folder: " + d)
    return [(os.path.join(d, f), "data/%s/%s/%s" % (kind, patch, f))
            for f in sorted(os.listdir(d)) if os.path.isfile(os.path.join(d, f))]


def zip_matches(zpath, files):
    try:
        with zipfile.ZipFile(zpath) as z:
            have = {i.filename: i.file_size for i in z.infolist()}
    except (zipfile.BadZipFile, OSError):
        return False
    want = {arc: os.path.getsize(src) for src, arc in files}
    return have == want


def table_list():
    t = [("manifest_all.csv", "manifest_all.csv"), ("patches.csv", "patches.csv"),
         (os.path.join("data", "labels", "labels_all.csv"), "labels_all.csv"),
         (os.path.join("data", "psf_info.csv"), "psf_info.csv")]
    for p in FIXED + MOVING:
        t.append((os.path.join("data", "aligned", p, "frames.csv"), "frames_%s.csv" % p))
    for p in FIXED:
        t.append((os.path.join("data", "diff", p, "diff_frames.csv"), "diff_frames_%s.csv" % p))
    for p in FIXED + MOVING:
        t.append((os.path.join("data", "labels", p, "labels.csv"), "labels_%s.csv" % p))
        t.append((os.path.join("data", "labels", p, "known_objects.csv"), "known_objects_%s.csv" % p))
    return t


def comet_lock(problems):
    """Second lock: no label in the 3i-atlas table may follow the true comet (answer key read here only)."""
    key_path, lab_path = "answer_key_3i_atlas.csv", os.path.join("data", "labels", "3i-atlas", "labels.csv")
    if not (os.path.exists(key_path) and os.path.exists(lab_path)):
        return None
    key = {(r["obs_id"], r["detector"]): (float(r["comet_ra"]), float(r["comet_dec"]))
           for r in csv.DictReader(open(key_path, encoding="utf-8"))}
    near, total, closest = {}, {}, 1e9
    for r in csv.DictReader(open(lab_path, encoding="utf-8")):
        k = key.get((r["obs_id"], r["detector"]))
        if not k:
            continue
        ra, dec = float(r["ra_deg"]), float(r["dec_deg"])
        dra = (ra - k[0] + 180.0) % 360.0 - 180.0
        d = math.hypot(dra * math.cos(math.radians(dec)), dec - k[1]) * 3600.0 / 6.15
        closest = min(closest, d)
        total[r["object"]] = total.get(r["object"], 0) + 1
        near[r["object"]] = near.get(r["object"], 0) + (d <= 3.0)
    for o, n in total.items():
        if near.get(o, 0) >= 0.5 * n:
            problems.append("label '%s' follows the true 3I/ATLAS position in %d of %d photos" % (o, near[o], n))
    return closest


def leak_check(tables, big_files):
    problems = []
    every = [s for s, _ in tables] + [s for fl in big_files for s, _ in fl] + DOCS
    for path in every:
        if any(k in os.path.basename(path).lower() for k in FORBIDDEN_NAMES):
            problems.append("forbidden file: " + path)
    for src, _ in tables:
        if not os.path.exists(src):
            problems.append("missing table: " + src)
            continue
        with open(src, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            bad = [c for c in (r.fieldnames or []) if c.lower() in FORBIDDEN_COLS]
            if bad:
                problems.append("answer-key columns %s in %s" % (bad, src))
            if "object" in (r.fieldnames or []):
                for row in r:
                    if any(k in row["object"] for k in COMET_3I):
                        problems.append("3I/ATLAS row in " + src)
                        break
    return problems


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    big = [src_files(k, p) for k, p in BIG]
    tables = table_list()

    print("Leak guard ...")
    problems = leak_check(tables, big)
    closest = comet_lock(problems)
    if problems:
        print("STOP - nothing written:")
        for p in problems:
            print("   " + p)
        sys.exit(1)
    print("   ok: no answer-key file, no comet_ra/comet_dec column, no 3I/ATLAS label row")
    if closest is not None:
        print("   ok: no 3i-atlas label follows the true comet (closest label %.1f px from it)" % closest)

    total = 0
    for (k, p), fl in zip(BIG, big):
        n = sum(os.path.getsize(s) for s, _ in fl)
        total += n
        print("   %-8s %-15s %4d files  %s" % (k, p, len(fl), gb(n)))
    print("   tables: %d files | docs: %s" % (len(tables), ", ".join(
        d + ("" if os.path.exists(d) else " (MISSING)") for d in DOCS)))
    print("   total ~%s -> %s" % (gb(total), OUT))
    free = shutil.disk_usage(".").free
    print("   free disk here: %s" % gb(free))
    if a.dry:
        print("Dry run: nothing written.")
        return
    if free < total * 1.05:
        sys.exit("not enough free disk")

    os.makedirs(os.path.join(OUT, "tables"), exist_ok=True)
    for i, ((k, p), fl) in enumerate(zip(BIG, big), 1):
        sub = os.path.join(OUT, ZIP_DIR[k])
        os.makedirs(sub, exist_ok=True)
        zpath = os.path.join(sub, "%s_%s.zip" % (k, p))
        if os.path.exists(zpath) and zip_matches(zpath, fl):
            print("[%d/%d] %s already done - skipped" % (i, len(BIG), os.path.basename(zpath)))
            continue
        part = zpath + ".part"
        t = time.time()
        with zipfile.ZipFile(part, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            for j, (src, arc) in enumerate(fl, 1):
                z.write(src, arc)
                if j % 100 == 0:
                    print("      %s: %d/%d files" % (os.path.basename(zpath), j, len(fl)), flush=True)
        os.replace(part, zpath)
        print("[%d/%d] %s  %s  (%.0f s)" % (i, len(BIG), os.path.basename(zpath),
                                          gb(os.path.getsize(zpath)), time.time() - t), flush=True)

    for src, name in tables:
        shutil.copy2(src, os.path.join(OUT, "tables", name))
    for d in DOCS:
        if os.path.exists(d):
            shutil.copy2(d, os.path.join(OUT, os.path.basename(d)))
    print("tables + docs copied")

    print("checksums (reads every file once) ...", flush=True)
    lines = []
    for root, _, files in os.walk(OUT):
        for f in sorted(files):
            if f == "checksums.sha256" or f.endswith(".part"):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, OUT).replace(os.sep, "/")
            lines.append("%s  %s" % (sha256(path), rel))
    with open(os.path.join(OUT, "checksums.sha256"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(lines, key=lambda s: s[66:])) + "\n")
    missing = [d for d in DOCS if not os.path.exists(d)]
    print("Done in %.1f min | %d files in %s" % ((time.time() - t0) / 60, len(lines), OUT))
    if missing:
        print("NOTE: %s not written yet - re-run this script after they exist (zips are skipped)." % missing)


if __name__ == "__main__":
    main()
