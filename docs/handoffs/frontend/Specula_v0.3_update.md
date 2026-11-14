# Specula v0.3: the real detections

**From:** Muath (data) · **For:** Zuhair, Reham, Amera (frontend)

## Install (1 minute)
Unzip `frontend_update_v0.3.zip` into `public/data/`, on top of v0.1 and v0.2, and say yes to replacing `manifest.json`.
It holds 3 files: `detections.json` (new), `scoring.json` (new) and `manifest.json` (now version 0.3, 3,537 files in total).

## How the results were made
1. **Omar's detector** measured every bright spot in every photo: **1,911,543 spots** in all **1,401 photos**, with no
   answer data used.
2. **The data side then linked the spots into moving objects.** It works like a party photo album: stars are the people
   who stand in the same spot in every photo, and asteroids are the ones who walk across the room.
   - Spots that sit at the same sky position days apart are stars, so they're removed.
   - What's left is grouped inside each burst, then linked across bursts into straight-line paths.
   - A path is kept only if it's seen in **4+ bursts** and passes a **noise test**: the same steps run on scrambled data,
     where nothing real can move in a line, give ~0 fake paths.
3. Each kept path is matched by position with NASA JPL's known objects.

## The results (`scoring.json`)
| Check | Result |
|---|---|
| Tracks found | **8, all known objects**: Ceres (4 tracks), **3I/ATLAS**, 20 Massalia, 232 Russia, 207 Hedda |
| New candidates | **0** (with 0 false alarms) |
| 3I/ATLAS | Found in **50 photos** (8 bursts) = 24% of the 207 photos where it is visible. 0 wrong points. Error 2.8″ |
| Ceres | Found in **134 of 273 photos** (49%). Error 0.6″ |
| Known asteroids brighter than V 15 | 62% of their visible photos |
| Known asteroids V 15-17 | 47% |
| Known asteroids fainter than V 17 | 0% (too faint for the spot list) |

## What changes in the UI
- **`detections.json` replaces `detections_mock.json`.** It's the same format: a list of tracks, each with `points[]`
  (`frame_id, x, y, ra, dec, mag`). x and y are image pixels, as in `markers.json`.
- **All 8 tracks are `status: "known"`.** Draw them as circles along their path, and use `object_id` to find each one's
  orbit in `orbits.json`. Ceres is `"1"`, 3I/ATLAS is `"3I"`, and the others are `"20"`, `"232"` and `"207"`.
  `distance_*` is null for known objects (use their orbit).
- **No candidate (orange diamond) appears in v0.3.** Keep that code path: it still works with the mock for testing, but
  don't show `MOCK-` data in the demo. When there are no candidates, a line like "No new objects: every moving thing we
  found is already known to NASA" is a real result.
- `is_target_claimed` is false everywhere. The pipeline never says "this is 3I". 3I/ATLAS is recognised afterwards by
  position, like every known object. `scoring.json` says this in its `mode` field.

## How to say it (honest wording)
- ✅ "Our pipeline **recovered** 3I/ATLAS, the interstellar comet, in SPHEREx photos, with zero false alarms."
- ✅ "It also recovered Ceres and three known main-belt asteroids, and found no false objects in any patch."
- ❌ Not "discovered", and not "blind". The settings were locked before the 3I check. That first locked run found 3I
  **plus 39 false paths**. A stricter rule, set only from the scrambled-data test, then removed all the false paths and
  kept 3I. That makes it a **validation**, not a blind discovery.
- Sizes and distances stay ranges ("estimated"). Use "latest published", not "live".

## Rules (unchanged until Muath says otherwise)
The same 3I/ATLAS rule applies to the new files: `detections.json` and `scoring.json` contain 3I/ATLAS positions too.
Questions: ask Muath.
