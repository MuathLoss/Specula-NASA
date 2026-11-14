"""Specula - pack the frontend data (handoff #2) for Google Drive.

Output: handoff/Specula_frontend_v<version>/
  frontend_data_v<version>.zip   contents of handoff/frontend_data/ -> unzip straight into the site's public/data/
  README.md, CLAUDE.md, Specula_frontend_data_contract.md, Specula_project_story.md, Specula_UI_ideas.md
  (from handoff_frontend_docs/)
  checksums.sha256
Version comes from handoff/frontend_data/manifest.json. Zip is STORE (WebP is already compressed).
Guard: stops if the 3I/ATLAS answer key file itself (or its comet_ra/comet_dec columns) would be packed.
The 3I markers addon IS packed on purpose (frontend only; decision D3).
Run:  python package_frontend.py
Update pack (only files new or changed since an earlier zip, e.g. v0.2 on top of v0.1):
      python package_frontend.py --update-from handoff/Specula_frontend_v0.1/frontend_data_v0.1.zip
      (several earlier zips: comma-separated, oldest first, e.g. v0.1 zip,v0.2 update zip)
"""
import hashlib, json, os, shutil, sys, zipfile, zlib

SRC = os.path.join("handoff", "frontend_data")
DOCS = os.path.join("handoff_frontend_docs")
DOC_FILES = ["README.md", "CLAUDE.md", "Specula_frontend_data_contract.md", "Specula_project_story.md",
             "Specula_UI_ideas.md", "specula_orbit.js", "Specula_v0.3_update.md"]


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(8 << 20), b""):
            h.update(c)
    return h.hexdigest()


def changed_since(files, old_zips):
    old = {}
    for z in old_zips.split(","):                    # later zips override earlier ones (v0.1, then v0.2 update, ...)
        old.update({i.filename: (i.CRC, i.file_size) for i in zipfile.ZipFile(z).infolist()})
    keep = []
    for p, a in files:
        crc = 0
        with open(p, "rb") as f:
            for c in iter(lambda: f.read(8 << 20), b""):
                crc = zlib.crc32(c, crc)
        if old.get(a) != (crc & 0xFFFFFFFF, os.path.getsize(p)):
            keep.append((p, a))
    return keep


def main():
    update_from = sys.argv[sys.argv.index("--update-from") + 1] if "--update-from" in sys.argv else None
    ver = json.load(open(os.path.join(SRC, "manifest.json"), encoding="utf-8"))["version"]
    out = os.path.join("handoff", "Specula_frontend_v%s" % ver)
    files = []
    for root, _, fs in os.walk(SRC):
        for f in sorted(fs):
            if f.endswith(".part"):
                continue
            p = os.path.join(root, f)
            files.append((p, os.path.relpath(p, SRC).replace(os.sep, "/")))
    bad = [a for _, a in files if "answer_key" in a.lower()]
    for p, a in files:
        if a.endswith((".json", ".csv")) and os.path.getsize(p) < 50_000_000:
            t = open(p, encoding="utf-8").read()
            if "comet_ra" in t or "comet_dec" in t:
                bad.append(a)
    if bad:
        sys.exit("STOP - answer-key content would be packed: %s" % bad)
    os.makedirs(out, exist_ok=True)
    zpath = os.path.join(out, "frontend_data_v%s.zip" % ver)
    if update_from:
        files = changed_since(files, update_from)
        zpath = os.path.join(out, "frontend_update_v%s.zip" % ver)
        print("update pack: %d new/changed files: %s" % (len(files), ", ".join(a for _, a in files)))
    with zipfile.ZipFile(zpath + ".part", "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for p, a in files:
            z.write(p, a)
    os.replace(zpath + ".part", zpath)
    for d in DOC_FILES:
        shutil.copy2(os.path.join(DOCS, d), os.path.join(out, d))
    lines = []
    for f in sorted(os.listdir(out)):
        if f != "checksums.sha256":
            lines.append("%s  %s" % (sha256(os.path.join(out, f)), f))
    open(os.path.join(out, "checksums.sha256"), "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    with zipfile.ZipFile(zpath) as z:
        n = len(z.infolist())
        crc_bad = z.testzip()
    print("%s: zip %d entries (%.1f MB), CRC test %s | %d docs + checksums"
          % (out, n, os.path.getsize(zpath) / 1e6, "OK" if crc_bad is None else "FAILED: " + crc_bad, len(DOC_FILES)))


if __name__ == "__main__":
    main()
