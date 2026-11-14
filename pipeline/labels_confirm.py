"""Specula stage 8.1 - add a confirmation count to the known-object labels.

Why: one "seen" in a single photo can be luck (a noise spot or cosmic ray that happens to sit
within 1.5 px of the JPL position; ~1% chance per label at V 19-21).
A real asteroid is photographed several times inside the same 15-min group, so it is seen again.

Adds to data/labels/<patch>/labels.csv (in place, safe to re-run):
  seen_n_group  how many photos in the same group see this same object (0 if never)
  confirmed     1 if seen = 1 and seen_n_group >= 2, else 0
Adds to data/labels/<patch>/known_objects.csv:
  frames_confirmed
Rebuilds data/labels/labels_all.csv from the patch files.

The original columns are untouched. labels_spherex.py can always regenerate the originals from
jpl_cache in seconds with 0 JPL calls, so nothing is lost.

Run:  python labels_confirm.py            (all patches under data/labels)
      python labels_confirm.py --root X   (use another labels folder, for testing)
"""
import argparse, collections, csv, os, sys

NEW_LABEL_COLS = ["seen_n_group", "confirmed"]
NEW_OBJ_COLS = ["frames_confirmed"]
# known_objects.csv columns as labels_spherex.py writes them when a patch has objects; used when a patch
# has none (e.g. nep-cats-eye) so every patch file has the same header.
OBJ_COLS = ["object", "kind", "frames_on_grid", "frames_in_data", "frames_seen", "v_brightest",
            "first_utc", "last_utc", "motion_px_per_min"]
CONFIRM_MIN = 2


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def write_csv(path, cols, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def vbin(v):
    v = float(v)
    return "< 17" if v < 17 else "17-18" if v < 18 else "18-19" if v < 19 else "19-21"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.join("data", "labels"))
    a = ap.parse_args()
    patches = sorted(d for d in os.listdir(a.root) if os.path.isfile(os.path.join(a.root, d, "labels.csv")))
    if not patches:
        sys.exit("no data/labels/<patch>/labels.csv found - run labels_spherex.py first")
    all_cols, all_rows = None, []
    for p in patches:
        lpath = os.path.join(a.root, p, "labels.csv")
        cols, rows = read_csv(lpath)
        cols = [c for c in cols if c not in NEW_LABEL_COLS] + NEW_LABEL_COLS
        n_seen = collections.Counter((r["object"], r["group"]) for r in rows if r["seen"] == "1")
        for r in rows:
            if r["seen"] == "":          # not measured (moving patches: positions only)
                r["seen_n_group"], r["confirmed"] = "", ""
                continue
            k = n_seen.get((r["object"], r["group"]), 0)
            r["seen_n_group"] = k
            r["confirmed"] = int(r["seen"] == "1" and k >= CONFIRM_MIN)
        write_csv(lpath, cols, rows)

        opath = os.path.join(a.root, p, "known_objects.csv")
        if os.path.exists(opath):
            ocols, objs = read_csv(opath)
            if not objs:
                ocols = list(OBJ_COLS)
            ocols = [c for c in ocols if c not in NEW_OBJ_COLS] + NEW_OBJ_COLS
            conf = collections.Counter(r["object"] for r in rows if r["confirmed"] == 1)
            measured = {r["object"] for r in rows if r["seen"] != ""}
            for o in objs:
                name = o.get("object", "")
                o["frames_confirmed"] = conf.get(name, 0) if name in measured else ""
            write_csv(opath, ocols, objs)

        if rows and all(r["seen"] == "" for r in rows):
            print("%s: %d labels | positions only (seen not measured)" % (p, len(rows)))
            all_cols = all_cols or cols
            all_rows += rows
            continue
        print("%s: %d labels | seen %d | confirmed %d" % (
            p, len(rows), sum(r["seen"] == "1" for r in rows), sum(r["confirmed"] == 1 for r in rows)))
        tab = collections.defaultdict(lambda: [0, 0])
        for r in rows:
            if r["seen"] == "1":
                t = tab[vbin(r["v_mag"])]
                t[0] += 1
                t[1] += r["confirmed"] == 1
        for b in ["< 17", "17-18", "18-19", "19-21"]:
            if b in tab:
                s, c = tab[b]
                print("   V %-6s seen %4d -> confirmed %4d (%3.0f%% kept)" % (b, s, c, 100.0 * c / s))
        all_cols = all_cols or cols
        all_rows += rows
    if all_cols:
        write_csv(os.path.join(a.root, "labels_all.csv"), all_cols, all_rows)
        print("labels_all.csv: %d rows, columns now end with: %s" % (len(all_rows), ", ".join(all_cols[-3:])))


if __name__ == "__main__":
    main()
