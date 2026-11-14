"""Specula data package - step 1: check every file arrived intact, then unzip.

Run it in the top folder of the download (where README.md is):
    python verify_and_unzip.py
The folder layout doesn't matter: files are found by name, so it also works if Google Drive
split the download into several zip parts and you unzipped them all into the same folder.

1. Checks every file against checksums.sha256 (a fingerprint per file). Any damaged or
   missing file is listed, and nothing is unzipped until all files pass.
2. Unzips the 8 zips into this folder. They rebuild data/aligned/<patch>/ and data/diff/<patch>/.
   Zip entries carry their own check (CRC), so a damaged entry would also stop the unzip.
3. Prints what you now have.

Needs ~15 GB free disk next to the zips. After it says OK you may delete the .zip files.
Safe to re-run: files already unzipped with the right size are skipped.
"""
import hashlib, os, sys, zipfile


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    if not os.path.exists("checksums.sha256"):
        sys.exit("checksums.sha256 not found - run this inside the package folder")
    lines = [l.split(maxsplit=1) for l in open("checksums.sha256", encoding="utf-8") if l.strip()]
    found = {}                                   # file name -> where it is (any sub-folder, data/ excluded)
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if not (root == "." and d == "data")]
        for f in files:
            found.setdefault(f, os.path.join(root, f))
    print("1/3 Checking %d files (reads ~14 GB, a few minutes) ..." % len(lines), flush=True)
    bad, zips = [], []
    for i, (want, name) in enumerate(lines, 1):
        name = name.strip()
        path = name if os.path.exists(name) else found.get(os.path.basename(name))
        if not path:
            bad.append("MISSING  " + name)
        elif sha256(path) != want:
            bad.append("DAMAGED  " + name)
        elif path.endswith(".zip"):
            zips.append(path)
        if name.endswith(".zip"):
            print("    %2d/%d %s" % (i, len(lines), name), flush=True)
    if bad:
        print("\nSTOP - download these again, then re-run:")
        for b in bad:
            print("   " + b)
        sys.exit(1)
    print("    all %d files OK" % len(lines))

    print("2/3 Unzipping ...", flush=True)
    for z in sorted(zips):
        with zipfile.ZipFile(z) as zf:
            todo = [i for i in zf.infolist()
                    if not (os.path.exists(i.filename) and os.path.getsize(i.filename) == i.file_size)]
            for i in todo:
                zf.extract(i, ".")
            print("    %-30s %4d files (%d new)" % (os.path.basename(z), len(zf.infolist()), len(todo)), flush=True)

    print("3/3 You now have:")
    for kind in ("aligned", "diff"):
        for p in sorted(os.listdir(os.path.join("data", kind))):
            d = os.path.join("data", kind, p)
            photos = [f for f in os.listdir(d) if f.endswith(".fits") and f[:4].isdigit()]
            static = [f for f in os.listdir(d) if f.startswith("static_sky")]
            print("    data/%s/%-16s %4d photos%s" % (kind, p, len(photos),
                                                   " + %d static-sky files" % len(static) if static else ""))
    print("Done. Next: read README.md (people) or CLAUDE.md (AI assistant).")


if __name__ == "__main__":
    main()
