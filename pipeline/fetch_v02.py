"""Specula v0.2 - download the raw data for the 3D files.

Run on Muath's PC (needs internet to NASA JPL and CDS), from the Specula folder:
    %run fetch_v02.py            (Jupyter)      or      python fetch_v02.py
Resumable: anything already downloaded is skipped. Re-run until it prints "ALL DONE".

Writes data/v02/:
  sbdb/<object_id>.json     NASA JPL Small-Body Database record per object (orbit, H, diameter, albedo):
                            the 666 known objects in our labels + 3I/ATLAS
  horizons_earth.json       Earth's position around the Sun at every burst time (357 bursts) -> pointings.json
  horizons_planets_bary.json  Mercury-Neptune system barycentre orbits (elements at 2026-01-01 TDB) -> orbits.json
  horizons_3i_elements.json   3I/ATLAS orbit at 2025-10-15 TDB (middle of our 3I photos) -> orbits.json
  horizons_reference.json   Ceres, 370 Modestia, 3I/ATLAS true positions at 5 dates -> reference_positions.json
  bsc5/catalog.gz, ReadMe   Yale Bright Star Catalogue, 5th ed. (CDS V/50) -> cosmos.json
All Horizons outputs: heliocentric, ecliptic J2000, AU. Nothing here reads or writes the 3I answer key.
"""
import csv
import gzip
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

OUT = os.path.join("data", "v02")
SBDB = "https://ssd-api.jpl.nasa.gov/sbdb.api"
HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"
BSC_BASES = ["https://cdsarc.cds.unistra.fr/ftp/V/50/", "https://cdsarc.u-strasbg.fr/ftp/cati/V/50/",
             "https://cdsarc.u-strasbg.fr/ftp/V/50/"]
UA = {"User-Agent": "Specula-SpaceApps2026/1.0 (student hackathon project)"}
PATCHES = ["ecliptic-virgo", "ecliptic-ra90", "nep-cats-eye", "ceres", "3i-atlas"]
PLANETS = [("mercury", "1"), ("venus", "2"), ("earth", "3"), ("mars", "4"),     # system barycentres: "3" = Earth-Moon
           ("jupiter", "5"), ("saturn", "6"), ("uranus", "7"), ("neptune", "8")]   # (Earth's centre wobbles with the Moon)
TRI_EPOCH_JD = 2460963.5      # 2025-10-15 TDB: middle of our 3I/ATLAS photos (Aug + Dec 2025)
PLANET_EPOCH_JD = 2461041.5   # 2026-01-01 00:00 TDB, middle of our data (May 2025 - Aug 2026)
REF_JD = [2460810.5, 2460919.5, 2461041.5, 2461131.5, 2461282.5]  # 2025-05-15, 09-01, 2026-01-01, 04-01, 08-30
REF_OBJECTS = [("1", ["'1;'"]), ("370", ["'370;'"]),
               ("3I", ["'DES=C/2025 N1;'", "'C/2025 N1;'", "'3I;'"])]
SBDB_ALT = {"3I": ["3I", "C/2025 N1"]}
MJD0 = datetime(1858, 11, 17, tzinfo=timezone.utc)


def get(url, params, timeout=120, tries=4, raw=False):
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    last = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(full, headers=UA), timeout=timeout) as r:
                data = r.read()
            return data if raw else json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (300, 400, 404):          # a real answer (ambiguous / bad name): don't retry
                raise RuntimeError("HTTP %d: %s" % (e.code, body[:400]))
            last = "HTTP %d" % e.code
            if e.code in (403, 429, 503):          # JPL says "too fast": wait longer
                time.sleep(15 * (k + 1))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last = repr(e)
        time.sleep(2 + 3 * k)
    raise RuntimeError("failed after %d tries: %s | %s" % (tries, last, full[:140]))


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(path + ".part", path)


def object_id(name):                       # same rule as build_previews.py / markers.json
    m = re.match(r"^(\d+) ", name)
    if m:
        return m.group(1)
    m = re.match(r"^\((.+)\)$", name.strip())
    return m.group(1) if m else name.strip()


def safe(oid):
    return oid.replace(" ", "_").replace("/", "-")


# ---------- 1. SBDB: one record per object ----------
def sbdb_all():
    names = []
    with open(os.path.join("data", "labels", "labels_all.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["object"] not in names:
                names.append(r["object"])
    ids = [object_id(n) for n in names] + ["3I"]
    folder = os.path.join(OUT, "sbdb")
    os.makedirs(folder, exist_ok=True)
    todo = [i for i in ids if not os.path.exists(os.path.join(folder, safe(i) + ".json"))]
    print("SBDB: %d objects, %d already saved, %d to fetch" % (len(ids), len(ids) - len(todo), len(todo)))

    slow = len(todo) <= 50                     # retry pass: one at a time, gently (JPL gave 403 when 4 ran at once)

    def one(oid):
        if slow:
            time.sleep(1.5)
        err = ""
        for s in SBDB_ALT.get(oid, [oid]):
            for params in ({"sstr": s, "phys-par": "1", "full-prec": "1"}, {"sstr": s, "phys-par": "1"}):
                try:
                    j = get(SBDB, params)
                except RuntimeError as e:
                    err = str(e)
                    continue
                if "orbit" in j:
                    j["_query"] = params
                    save_json(os.path.join(folder, safe(oid) + ".json"), j)
                    return oid, ""
                err = str(j)[:300]
        return oid, err

    fails = []
    with ThreadPoolExecutor(max_workers=1 if slow else 4) as ex:
        futs = [ex.submit(one, i) for i in todo]
        for n, fu in enumerate(as_completed(futs), 1):
            oid, err = fu.result()
            if err:
                fails.append((oid, err))
            if n % 50 == 0 or n == len(todo):
                print("  SBDB %d / %d done, %d failed" % (n, len(todo), len(fails)))
    for oid, err in fails:
        print("  SBDB FAILED %s: %s" % (oid, err))
    have = len([i for i in ids if os.path.exists(os.path.join(folder, safe(i) + ".json"))])
    return have, len(ids)


# ---------- 2. Horizons helpers ----------
def horizons_rows(params):
    j = get(HORIZONS, dict({"format": "json", "CSV_FORMAT": "YES", "CENTER": "'500@10'",
                            "REF_PLANE": "ECLIPTIC", "REF_SYSTEM": "ICRF", "OUT_UNITS": "AU-D"}, **params),
            timeout=300)
    res = j.get("result", "")
    if "$$SOE" not in res:
        raise RuntimeError("Horizons gave no table: %s" % (j.get("error") or res[-600:]))
    head = res.split("$$SOE")[0].strip().splitlines()
    cols = [c.strip() for c in head[-2].split(",")] if len(head) >= 2 else []
    rows = [[x.strip() for x in ln.split(",")]
            for ln in res.split("$$SOE")[1].split("$$EOE")[0].strip().splitlines() if ln.strip()]
    target = next((ln.strip() for ln in head if ln.startswith("Target body name")), "")
    return cols, rows, target


def earth_at_bursts():
    path = os.path.join(OUT, "horizons_earth.json")
    if os.path.exists(path):
        print("Earth positions: already saved")
        return True
    bursts = []
    for p in PATCHES:
        with open(os.path.join("handoff", "frontend_data", p, "timeline.json"), encoding="utf-8") as f:
            for b in json.load(f)["bursts"]:
                t = datetime.strptime(b["time_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                bursts.append((p, b["burst_id"], b["time_utc"], (t - MJD0).total_seconds() / 86400.0))
    out, cols = {}, None
    for i in range(0, len(bursts), 40):
        chunk = bursts[i:i + 40]
        cols, rows, _ = horizons_rows({"COMMAND": "'399'", "EPHEM_TYPE": "VECTORS", "VEC_TABLE": "2",
                                       "TIME_TYPE": "UT", "TLIST_TYPE": "MJD",
                                       "TLIST": " ".join("'%.8f'" % b[3] for b in chunk)})
        if len(rows) != len(chunk):
            raise RuntimeError("Earth: %d rows for %d times" % (len(rows), len(chunk)))
        for b in chunk:                       # Horizons returns rows sorted by time: match by time, not by order
            jd = b[3] + 2400000.5
            r = min(rows, key=lambda x: abs(float(x[0]) - jd))
            if abs(float(r[0]) - jd) > 2e-6:
                raise RuntimeError("Earth: no row for %s" % b[1])
            out[b[1]] = {"patch_id": b[0], "time_utc": b[2], "mjd_utc": b[3], "row": r}
        print("  Earth positions %d / %d" % (len(out), len(bursts)))
    save_json(path, {"columns": cols, "bursts": out, "frame": "heliocentric ecliptic J2000, AU, AU/day"})
    return True


def planets():
    path = os.path.join(OUT, "horizons_planets_bary.json")
    if os.path.exists(path):
        print("Planets: already saved")
        return True
    out = {}
    for name, cmd in PLANETS:
        cols, rows, target = horizons_rows({"COMMAND": "'%s'" % cmd, "EPHEM_TYPE": "ELEMENTS",
                                            "TIME_TYPE": "TDB", "TLIST_TYPE": "JD",
                                            "TLIST": "'%.1f'" % PLANET_EPOCH_JD})
        out[name] = {"command": cmd, "target": target, "columns": cols, "row": rows[0]}
        print("  planet %s: %s" % (name, target))
    save_json(path, {"epoch_jd_tdb": PLANET_EPOCH_JD, "planets": out,
                     "frame": "heliocentric ecliptic J2000, AU, deg"})
    return True


def tri_elements():
    path = os.path.join(OUT, "horizons_3i_elements.json")
    if os.path.exists(path):
        print("3I/ATLAS orbit (Oct 2025): already saved")
        return True
    cols, rows, target = horizons_rows({"COMMAND": "'DES=C/2025 N1;'", "EPHEM_TYPE": "ELEMENTS",
                                        "TIME_TYPE": "TDB", "TLIST_TYPE": "JD", "TLIST": "'%.1f'" % TRI_EPOCH_JD})
    save_json(path, {"epoch_jd_tdb": TRI_EPOCH_JD, "target": target, "columns": cols, "row": rows[0],
                     "frame": "heliocentric ecliptic J2000, AU, deg"})
    print("  3I/ATLAS orbit at 2025-10-15: %s" % target)
    return True


def reference():
    path = os.path.join(OUT, "horizons_reference.json")
    if os.path.exists(path):
        print("Reference positions: already saved")
        return True
    out = {}
    for oid, commands in REF_OBJECTS:
        err = ""
        for cmd in commands:
            try:
                cols, rows, target = horizons_rows({"COMMAND": cmd, "EPHEM_TYPE": "VECTORS", "VEC_TABLE": "2",
                                                    "TIME_TYPE": "TDB", "TLIST_TYPE": "JD",
                                                    "TLIST": " ".join("'%.1f'" % t for t in REF_JD)})
            except RuntimeError as e:
                err = str(e)
                continue
            if len(rows) == len(REF_JD):
                out[oid] = {"command": cmd, "target": target, "columns": cols, "rows": rows}
                print("  reference %s: %s" % (oid, target))
                break
            err = "%d rows" % len(rows)
        if oid not in out:
            raise RuntimeError("reference %s failed: %s" % (oid, err[-600:]))
    save_json(path, {"jd_tdb": REF_JD, "objects": out, "frame": "heliocentric ecliptic J2000, AU, AU/day"})
    return True


# ---------- 3. Yale Bright Star Catalogue ----------
def bsc():
    folder = os.path.join(OUT, "bsc5")
    cat, readme = os.path.join(folder, "catalog.gz"), os.path.join(folder, "ReadMe")
    if (os.path.exists(cat) and os.path.exists(readme)) or os.path.exists(os.path.join(folder, "bsc5.json")):
        print("Bright Star Catalogue: already saved")
        return True
    os.makedirs(folder, exist_ok=True)
    err = ""
    for base in BSC_BASES:
        try:
            gz = get(base + "catalog.gz", None, raw=True)
            n = len(gzip.decompress(gz).decode("latin-1").splitlines())
            rd = get(base + "ReadMe", None, raw=True)
        except Exception as e:                     # noqa: BLE001 (try the next mirror)
            err = "%s: %s" % (base, e)
            continue
        if n < 9000:
            err = "%s: only %d lines" % (base, n)
            continue
        with open(cat, "wb") as f:
            f.write(gz)
        with open(readme, "wb") as f:
            f.write(rd)
        print("  Bright Star Catalogue: %d stars from %s" % (n, base))
        return True
    raise RuntimeError("Bright Star Catalogue failed: " + err)


if __name__ == "__main__":
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    status = {}
    have, total = sbdb_all()
    status["sbdb"] = have == total
    for name, fn in [("earth", earth_at_bursts), ("planets", planets), ("3i_orbit", tri_elements),
                     ("reference", reference), ("bsc", bsc)]:
        try:
            status[name] = fn()
        except Exception as e:                     # noqa: BLE001 (report and keep going)
            print("%s FAILED: %s" % (name, e))
            status[name] = False
    print("\nSBDB %d / %d objects | %s | %.0f s" % (have, total,
          " ".join("%s=%s" % (k, "OK" if v else "MISSING") for k, v in status.items()), time.time() - t0))
    print("ALL DONE" if all(status.values()) else "NOT DONE: re-run this cell (finished parts are skipped)")
