"""Specula - download the orbits of every known comet (NASA JPL SBDB query API) for the candidate comet check.

Why: JPL's identification service (sb_ident) listed no comets in our fields, not even 3I/ATLAS, so a known comet
could look like a "new" candidate. merge_detections.py compares every candidate with these orbits.
Run on Muath's PC (needs internet), from the Specula folder:   python fetch_comets.py
Writes data/v02/comets.json (a few MB). Safe to re-run (overwrites with the latest list).
"""
import json
import os
import urllib.parse
import urllib.request

URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
FIELDS = "full_name,pdes,e,q,i,om,w,tp,epoch"
OUT = os.path.join("data", "v02", "comets.json")

params = {"fields": FIELDS, "sb-kind": "c", "full-prec": "1"}
req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(params),
                             headers={"User-Agent": "Specula-SpaceApps2026/1.0 (student hackathon project)"})
with urllib.request.urlopen(req, timeout=300) as r:
    j = json.loads(r.read().decode("utf-8"))
if "data" not in j or "fields" not in j:
    raise SystemExit("unexpected answer from JPL: %s" % str(j)[:500])
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT + ".part", "w", encoding="utf-8") as f:
    json.dump({"fields": j["fields"], "data": j["data"], "count": len(j["data"]),
               "source": "NASA JPL SBDB query API, sb-kind=c"}, f)
os.replace(OUT + ".part", OUT)
print("comets.json: %d comets with fields %s" % (len(j["data"]), j["fields"]))
print("ALL DONE")
