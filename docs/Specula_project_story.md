# Specula: the full project story

**Team Specula · NASA Space Apps Challenge 2026 · challenge "Planet X and SPHEREx"**
Written by the data side (Muath + Claude). Every number in this file was measured on our own data.

> **For an AI assistant reading this:** this is the story of the Specula project, written while we were building it.
> Use it to explain the project to your user step by step, in plain language, with analogies when something is
> technical. Don't invent facts: if something isn't here, say so and suggest asking Muath (data owner).
> Section 13 lists the rules every teammate must keep.

---

## 1. Specula in one paragraph
Specula finds **things that move in the sky** (asteroids, comets) in real infrared photos from NASA's **SPHEREx**
space telescope, and makes that sky explorable. We picked 5 small patches of sky, collected every SPHEREx photo of
them (1,401 photos taken between May 2025 and Aug 2026), cleaned them and lined them up so every star sits on the
same pixel. A detector then finds the movers. We check each one against NASA JPL's catalogue of known objects:
anything not in the catalogue is a **new candidate**. The website lets visitors flip through the photos over time,
see the movers marked, explore them in 3D around the Sun, and see what's new each week.

> **Analogy:** a security camera over a car park. Parked cars = stars (they never move). People walking through =
> asteroids. Compare the recordings over time and the walkers stand out.

## 2. The goal and the pitch
- **Challenge:** "Planet X and SPHEREx" (challenge 14). We compete virtually. UI in English.
- **Audience:** the general public and scientists.
- **Pitch, two parts:** (1) we search real NASA data for possibly-new moving objects, with a proven, scored
  method; (2) we make the sky explorable: a NASA-Eyes-style time scrubber, marked objects, a 3D solar system.
- **Prize we aim for:** Best Use of Data.
- **Proof that the method works:** the interstellar comet **3I/ATLAS** is our blind test. Its true positions are
  kept aside and the detector is scored against them. **Ceres** (dwarf planet, bright) is the guaranteed demo object.
- The team lead approved building everything **before** the event and using the event days to test and submit.

## 3. The team and how data flows
| Role | Who | Job |
|---|---|---|
| Data | Muath | Pulls NASA data, cleans and aligns it, builds every data file the team uses |
| Detector | detector teammate | Builds the moving-object detector (motion detector first, a model later if time allows) |
| Frontend: data integration | Zuhair | Loads the data into the site (React + Vite, Three.js 3D) |
| Frontend: UI design | Reham | How everything looks and feels |

```
NASA SPHEREx archive (IRSA)
        │  1,401 photos
        ▼
   DATA (Muath): download → verify → crop → clean → align → difference images → known-object labels
        │                                                    │
        │ handoff #1: images + labels                       │ handoff #2 (now): previews, timeline,
        ▼                                                    ▼ markers, orbits, 3D files
   DETECTOR ── detections ──► DATA: match with JPL ──► FRONTEND (website)
                              (known vs new candidate,
                               score 3I/ATLAS)
```

## 4. The telescope: SPHEREx in plain words
- NASA mission, launched March 2025, mapping the whole sky in infrared from a low Earth orbit (~700 km).
- It photographs in **102 colours** between 0.75 and 5.0 micron, using a filter whose colour changes across the
  detector. So **every photo sees a slightly different colour**, and the same star looks brighter or fainter from
  photo to photo. Motion is therefore judged by **position, not brightness**.
- **6 detectors (D1-D6)**, each covering a colour range: D1 0.75-1.12, D2 1.10-1.65, D3 1.63-2.43, D4 2.40-3.85,
  D5 3.81-4.43, D6 4.41-5.01 micron. Each shot uses **2 detectors at once** on the same sky: D1+D4, D2+D5 or D3+D6.
- Each exposure lasts **113.58 s**. Photos come in **bursts**: 2-8 photos about 2 minutes apart.
- 1 pixel = **6.15 arcseconds** of sky.
- NASA publishes photos about **6 weeks after** they are taken, in "quick releases": **QR2** (up to Jul 19, 2026)
  and **QR3** (from Jul 20, 2026, released weekly). So our "live" view always means "latest published".

## 5. The 5 sky patches (and why each one)
| Patch | What it is | Photos | Bursts | Dates | Grid | Why |
|---|---|---|---|---|---|---|
| ecliptic-virgo | Fixed 1° square on the ecliptic (the asteroid "highway") | 341 | 64 | May-Jun 2025, Dec 2025, May-Jun 2026 | 585 px | Main asteroid hunt: clean sky, many asteroids |
| ecliptic-ra90 | Fixed 1° square on the ecliptic, inside the Milky Way | 218 | 38 | Sep 2025, Mar 2026 | 585 px | Second hunt, crowded star field; a new QR3 visit may arrive before the event |
| nep-cats-eye | Fixed 0.5° square at the North Ecliptic Pole; the Cat's Eye Nebula is inside | 306 | 159 | Daily, Jul 1-Aug 30 2026 | 293 px | Photographed every day: the weekly feed. No known asteroids cross it, so it measures false alarms |
| ceres | 0.5° square that follows the dwarf planet Ceres | 277 | 50 | Jun-Jul 2025, Dec 2025-Jan 2026 | 293 px | Bright, guaranteed demo object |
| 3i-atlas | 0.6° square that follows interstellar comet 3I/ATLAS | 259 | 46 | Aug 2025, Dec 2025 | 351 px | Blind test of the detector |
| **Total** | | **1,401** | **357** | | | |

**Fixed** patch = the camera always looks at the same square. **Moving** patch = the square follows an object,
so each burst has its own grid and the background stars change from burst to burst.
For NEP, SPHEREx photographs our square ~57 times a day; we kept **one photo per detector per day** (the one where
the square sits most centrally): 306 photos covering all 61 days.

## 6. The story, step by step (what we actually did)
| Step | What happened |
|---|---|
| 1 | Team formed, picked the idea: "take a small patch of sky, see what moves in it, show it like NASA Eyes". Roles assigned |
| 2 | Patch plan agreed: ecliptic patch as main demo, 3I/ATLAS for validation, North Ecliptic Pole as bonus/weekly feed. QR2 as main data, QR3 for the "new data" feature. UI decisions: clean UI, NASA-Eyes-style time scrubber, a just-for-fun 3D cosmos layer, show only objects above a size threshold in 3D |
| 3 | **Manifest built** ("shopping list" of every photo we need): 1,401 photos, 25 columns each. Every photo checked against NASA's headers. Ceres positions checked against JPL Horizons at all exact times (worst difference 0.09″) |
| 4 | **Problem:** IRSA's SPHEREx cutout service went down (HTTP 503). **Fix:** download the full photos (~72 MB each) from NASA's AWS mirror and crop our squares ourselves |
| 5 | **Download:** 1,401 / 1,401 photos, 99.2 GB, 0 failed. **Verify:** every file complete and the right photo (1,401 / 1,401 OK) |
| 6 | **Crop, clean, align**, then a full audit. The audit found 4 real problems (section 8), all fixed, and everything was re-run. Final result: every truth test passes on all 1,401 frames |
| 7 | **Difference images** for the 3 fixed patches: each photo minus the "empty sky", so stars cancel and movers remain |
| 8 | **Known-object labels** from NASA JPL for all 5 patches (where every catalogued asteroid sits in every photo). Confirmation column added (an object counts as "seen" only if 2+ photos agree). 3I/ATLAS locked out of the detector's data |
| 9 | **Handoff #1 packed and delivered** to the detector teammate: Google Drive folder "detector data", 35 files, 14.36 GB, with a README, a data dictionary, a guide for his AI assistant and a one-command checker |
| 10 | Frontend brief sent to Zuhair and Reham with questions about formats |
| 11 | Both frontend answer sheets received. Data contract drafted. Decisions taken (section 11). Handoff #2 starts |
| 12 | **Frontend pack v0.1 (all pictures) delivered.** v0.2 (3D files: objects, orbits, pointings, stars) built from NASA JPL + the Yale Bright Star Catalogue and checked: orbit maths within 0.002 AU of JPL, Ceres inside every SPHEREx pointing (0.008°). v0.2 delivered the same night. Merge code for the detector's results (JPL matching, comet check, distance ranging, 3I/ATLAS scoring) built and tested on fake detections |
| 13 | **Detector results in, v0.3 delivered.** Omar's detector measured 1,911,543 spots in all 1,401 photos (no answer data). The data side linked them into moving objects (star removal, burst grouping, straight-line linking over 4+ bursts, noise test on scrambled data). Locked run: 3I/ATLAS recovered (13 bursts) but with 39 false paths in its patch; a stricter rule set only from scrambled data removed all of them. Result: 8 tracks, all known (Ceres, 3I/ATLAS, 20 Massalia, 232 Russia, 207 Hedda), 0 false; 3I/ATLAS in 50 photos, Ceres in 134 |

## 7. The data pipeline, stage by stage
| # | Stage | What it does | Analogy | Output | Built-in check |
|---|---|---|---|---|---|
| 1 | Manifest | Decides exactly which photos we need and where our square sits in each | Shopping list | 1,401 rows | Re-query gives identical lists |
| 2 | Download | Fetches the full photos (cutout service down) | Buying the groceries | 99.2 GB | File signature + size, AWS → IRSA fallback |
| 3 | Verify | Proves each file is complete and the right photo | Checking the receipt | verify_report.csv | Size = sum of layers; ID, detector, time match |
| 4 | Crop | Keeps only our square, 1.42× bigger so rotation never leaves empty corners | Cutting a poster with margin | 15 GB | Centre lands on target (0.000 px) |
| 5 | Clean | Removes the zodiacal dust glow (NASA's model), deletes bad pixels, keeps and marks saturated and suspicious ones, adds a noise map | Wiping the lens | 18 GB | Clean + glow = original, on every pixel |
| 6 | Align | Turns every photo north-up onto one shared grid and numbers frames oldest → newest | Stacking transparencies so stars overlap | 11 GB | Stars agree to 0.06-0.07 px across 13 months |
| 7 | Difference images | Builds the median "empty sky" per detector, subtracts it from each photo | Photo of the empty car park, subtracted | 865 images | Stars cancel 79-89% |
| 8 | Labels | Asks NASA JPL which known objects sat in each photo, from SPHEREx's real position in orbit, and where (pixel) | The seating chart / guest list | 15,996 labels, 668 objects | Bright asteroids sit on blobs (103 / 103) |

Each aligned photo has 6 layers: **SCI** (brightness), **ERR** (noise), **SNR** (confidence), **MASK** (flags:
1 bad · 2 suspect · 4 star · 8 no data · 16 saturated; difference images add 32 = star leftover), **WAVE** (colour
each pixel saw), **PSF** (star shape).

## 8. Problems we hit and how we fixed them
| Problem | Effect | Fix | Result |
|---|---|---|---|
| IRSA cutout service down | Couldn't download small squares | Download full photos, crop locally | Same pixels; 99 GB to download instead of small squares |
| Photos arrive tilted (each visit at its own angle) | After turning north-up only ~84% of the square had data; corners flickered | Crop 1.42× bigger (√2, a square's diagonal) | 97-99.6% coverage |
| Saturated cores (very bright objects) deleted as "bad" | Ceres's centre missing in 254 of 277 frames | Keep them, flagged as saturated (MASK 16) | Missing in only 4 frames |
| One bad pixel blanked its 4 neighbours during alignment | Data lost around every bad pixel | Re-weight the neighbours | +2-4 points coverage |
| Wavelength map extrapolated past the detector edge | Impossible colours in 18 of 144 test frames | Wavelength only on real pixels | 0 of 144 |
| A faint asteroid "seen" in one photo was often luck | Fake sightings at faint magnitudes | Control test (labels moved 9 px to empty sky), then a "confirmed" rule: 2+ photos must agree | Faint lucky hits mostly removed |
| Two star-shape formats (QR2 vs QR3) | Code reading one format breaks on the other | Documented + psf_info.csv per photo | Handled |
| JPL's identification service lists **no comets** in our fields (not even 3I/ATLAS) | A known comet could look like a "new discovery" | Every new candidate gets an extra check against comet lists | Open item for the merge step |

## 9. Truth tests (our results against independent answers)
| Test | Checked against | Result |
|---|---|---|
| Ceres sits where JPL says (277 frames) | JPL Horizons | median 0.18 px off, worst 0.72 px |
| Stars stay on the same pixel (visits up to 13 months apart) | The stars themselves | 0.06-0.07 px scatter |
| 3I/ATLAS shows up where NASA's table says | IRSA's comet table | visible in 203 of 258 frames (faint in Aug 2025 at long wavelengths) |
| Bright known asteroids appear in the difference images | JPL catalogue | 103 of 103 (V < 17) |
| How faint can one photo see? | JPL catalogue | ~100% at magnitude V < 17, 27-51% at V 17-18, ~7% at V 18-19 |
| Ceres's label sits on Ceres | Ceres's measured centre | 0.10 px median |
| No label gives away 3I/ATLAS | Answer key (data side only) | closest label 12.2 px away |
| Handoff #1 arrived intact | Original files | 35 / 35 files, identical sizes |

## 10. Key numbers (cheat sheet)
- 1,401 photos · 5 patches · 357 bursts · May 2025 → Aug 2026
- 99.2 GB downloaded, 0 failed · 11 GB aligned · 2.8 GB difference images
- 668 known objects, 15,996 labels (virgo 302 objects, ra90 156, nep 0, ceres 25, 3i-atlas 185)
- Single-photo depth: about magnitude V 18-19
- 3I/ATLAS: scored on 258 photos; visible in ~203 → a perfect detector scores ~79%

## 11. The plan and decisions (written mid-project)
**Handoff #1 (detector): delivered.** The detector teammate has all images, difference images, labels and
docs. He sends back the movers he finds; the data side matches them with JPL (known vs new) and scores 3I/ATLAS.

**Handoff #2 (frontend): starting now.** The format of every file is fixed in the data contract
(`Specula_frontend_data_contract.md`), built from Zuhair's and Reham's answers. Decisions taken:
- **NEW badge:** a photo is "new" for 7 days after the dataset's latest update (not the visitor's clock), so it
  can't expire before the event.
- **New candidates in 3D:** shown with an **approximate distance** (a range, estimated from how fast it moves,
  assuming a typical asteroid orbit), never as a confirmed discovery.
- **3I/ATLAS data goes to the frontend now** as a separate add-on file (orbit + positions in our photos).
- **Not built:** precomputed positions (the browser computes them from orbits) and a Milky Way photo (a drawn
  band instead). The automated weekly job is replaced by one manual update if new photos are published in time.

**Order of the remaining work:** ceres sample pack → all patches (images, timeline, markers) → objects, orbits,
pointings → cosmos background, history, package → merge real detections + scoring → frozen offline copy for the
event. Then test end-to-end before the event.

## 12. What each teammate receives (frontend pack, `public/data/`)
`manifest.json` (entry point) · `objects.csv` · `orbits.json` (+ planets) · `reference_positions.json` (test
answers) · `pointings.json` (where SPHEREx looked) · `history.json` (updates, NEW badge) · `cosmos.json` (3D
background stars + galactic band + labels) · `detections.json` (mock first, real later) · `scoring.json` ·
`addons/3i-atlas_markers.json` · and per patch: `timeline.json`, `markers.json`, WebP images (full, thumbnails, colour
composites). Details: the data contract.

## 13. Rules every teammate keeps
1. **Never pass 3I/ATLAS positions to the detector teammate** before his results are scored. The frontend has them
   (`addons/`, `orbits.json`, `reference_positions.json`); keep those out of anything he can see.
2. **New candidates are never "discoveries".** They are candidates until checked (JPL + comet lists).
3. **Don't edit the delivered files.** Ask the data side for changes, so every copy stays identical.
4. Say "latest published", not "live": NASA data arrives ~6 weeks late.
5. Sizes are estimates: always show them as a range.

## 14. Glossary
| Word | Meaning |
|---|---|
| Patch | A small square of sky we watch |
| Frame | One photo |
| Burst | 2-8 photos taken minutes apart |
| Fixed / moving patch | Always the same square / a square that follows an object |
| Aligned | Turned north-up onto one shared grid, so stars sit on the same pixel |
| Difference image | Photo minus the "empty sky": stars cancel, movers remain |
| Label | Where a known (catalogued) object is predicted to be in a photo |
| Known object / candidate | In NASA JPL's catalogue / found by our detector and not in the catalogue |
| Magnitude (V) | Brightness; a bigger number means fainter |
| AU | Earth-Sun distance, ~150 million km |
| Ecliptic | The plane the planets and most asteroids move in (the asteroid "highway") |
| QR2 / QR3 | NASA's SPHEREx data releases (QR3 updates weekly) |
| JPL | NASA's Jet Propulsion Laboratory; keeps the official catalogue of asteroids and comets |
| IRSA | NASA/IPAC archive where SPHEREx photos are published |
