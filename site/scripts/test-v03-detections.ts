import type { Burst } from "../types/specula";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { parseTracks } from "../lib/parse-tracks";
import { factsFromTracks, parseScoring, pipelineCopy } from "../lib/scoring";
import { burstIdFromFrameId, burstIndexForPatch } from "../lib/timeline";
import {
  countDetectionsInView,
  isMockTrackId,
  liveTracks,
  unrollTracks,
  detectionsAtBurst,
} from "../lib/tracks";

const dataDir = resolve(process.cwd(), "public/data");

function fail(message: string): never {
  console.error(message);
  process.exit(1);
}

const tracks = parseTracks(
  JSON.parse(readFileSync(resolve(dataDir, "detections.json"), "utf8")),
);
const scoring = parseScoring(
  JSON.parse(readFileSync(resolve(dataDir, "scoring.json"), "utf8")),
);
const pointings = JSON.parse(
  readFileSync(resolve(dataDir, "pointings.json"), "utf8"),
) as Array<{ patch_id: string; burst_id: string; time_utc: string }>;

if (tracks.length !== 8) fail(`expected 8 tracks, got ${tracks.length}.`);
if (tracks.some((track) => track.status !== "known")) fail("every v0.3 track is known.");
if (tracks.some((track) => isMockTrackId(track.track_id))) {
  fail("detections.json must not contain MOCK- tracks.");
}
if (liveTracks(tracks).length !== 8) fail("liveTracks should keep the real tracks.");

const ids = tracks.map((track) => track.object_id);
for (const objectId of ["1", "3I", "20", "232", "207"]) {
  if (!ids.includes(objectId)) fail(`missing object ${objectId}.`);
}
if (tracks.filter((track) => track.object_id === "1").length !== 4) {
  fail("Ceres should have 4 tracks.");
}
for (const track of tracks) {
  if (track.distance_min_au !== null || track.distance_max_au !== null) {
    fail(`${track.track_id} should have null distances.`);
  }
  if (track.is_target_claimed) fail(`${track.track_id} claims a target.`);
  if (track.n_points !== track.points.length) {
    fail(`${track.track_id} n_points does not match its points.`);
  }
  if (track.points.some((point) => point.is_target)) {
    fail(`${track.track_id} has a point that claims a target.`);
  }
}

const atlas = tracks.find((track) => track.object_id === "3I");
if (!atlas) fail("3I/ATLAS track is missing.");
if (atlas.points.some((point) => point.mag !== null)) {
  fail("3I/ATLAS magnitudes in this pack are null and must not become 0.");
}
const atlasBurst = burstIdFromFrameId(atlas.points[0]?.frame_id ?? "");
if (!atlasBurst) fail("3I/ATLAS point has no burst id.");
if (burstIndexForPatch("3i-atlas", atlasBurst, pointings) !== 37) {
  fail(
    `3I/ATLAS should open on burst 37, not ${burstIndexForPatch("3i-atlas", atlasBurst, pointings)}.`,
  );
}

const virgo = tracks.filter((track) => track.patch === "ecliptic-virgo");
if (virgo.length !== 3) fail("ecliptic-virgo should have 3 known tracks.");
const russia = virgo.find((track) => track.object_id === "232");
if (!russia) fail("232 Russia is missing.");
const allDetections = unrollTracks(tracks, new Map(), new Map());
if (
  detectionsAtBurst(
    allDetections.filter((d) => d.patch_id === "ecliptic-virgo"),
    {
      index: 0,
      burst_id: "2025W20_2D_0234",
      patch_id: "ecliptic-virgo",
      time_utc: "2025-05-16",
      frame_ids: ["2025W20_2D_0234_1_D3"],
    },
  ).length !== 0
) {
  fail("a fixed patch must not draw its whole track on an unrelated burst.");
}
const moving = detectionsAtBurst(
  allDetections.filter((d) => d.patch_id === "3i-atlas"),
  {
    index: 37,
    burst_id: atlasBurst,
    patch_id: "3i-atlas",
    time_utc: "",
    frame_ids: atlas.points
      .filter((point) => burstIdFromFrameId(point.frame_id) === atlasBurst)
      .map((point) => point.frame_id),
  },
);
if (moving.length === 0 || moving.length === atlas.points.length) {
  fail("a moving patch should draw only the current burst.");
}

const russiaBurst = burstIdFromFrameId(russia.points[0]?.frame_id ?? "");
const timeline = JSON.parse(
  readFileSync(resolve(dataDir, "ecliptic-virgo/timeline.json"), "utf8"),
) as { bursts: Burst[] };
const burst = timeline.bursts.find((item) => item.burst_id === russiaBurst);
if (!burst) fail("232 Russia's first burst is missing from the timeline.");
const russiaComposite = detectionsAtBurst(allDetections, burst);
if (
  russiaComposite.length !== 1 ||
  russiaComposite[0].x !== 573.16 ||
  russiaComposite[0].y !== 65.855
) {
  fail("232 Russia must have exactly one mean position across its entire first burst.");
}
if (
  countDetectionsInView(virgo, { mode: "composite", frameIds: burst.frame_ids }) !== 1
) {
  fail("232 Russia's burst should count one track.");
}

if (scoring.atlas?.framesFound !== 50 || scoring.atlas.framesLikelyVisible !== 207) {
  fail("3I/ATLAS score should be 50 of 207 visible photos.");
}
if (
  scoring.atlas.falseTargetPoints !== 0 ||
  scoring.atlas.medianPositionErrorArcsec !== 2.8
) {
  fail("3I/ATLAS should have 0 false points and a 2.8 arcsec error.");
}
if (scoring.ceres?.framesFound !== 134 || scoring.ceres.framesLikelyVisible !== 273) {
  fail("Ceres score should be 134 of 273 photos.");
}
if (scoring.tracks?.known !== 8 || scoring.tracks.candidates !== 0) {
  fail("scoring.json should report 8 known tracks and 0 candidates.");
}

const copy = pipelineCopy(scoring, factsFromTracks(tracks));
const text = [
  copy.recoveredAtlas,
  copy.recoveredKnown,
  copy.noNewObjects,
  copy.validation,
  copy.claim,
  copy.nep,
  ...copy.stats.flatMap((stat) => [stat.label, stat.value]),
].join("\n");
if (
  !copy.recoveredAtlas?.includes("recovered 3I/ATLAS") ||
  !copy.recoveredAtlas.includes("zero false alarms")
) {
  fail(`unexpected 3I/ATLAS sentence: ${copy.recoveredAtlas}`);
}
if (
  !copy.recoveredKnown?.includes("recovered Ceres and three known main-belt asteroids")
) {
  fail(`unexpected known-object sentence: ${copy.recoveredKnown}`);
}
if (
  copy.noNewObjects !==
  "No new objects: every moving thing we found is already known to NASA."
) {
  fail(`unexpected empty-candidate sentence: ${copy.noNewObjects}`);
}
if (
  !copy.validation?.includes("validation run") ||
  !copy.validation.includes("scrambled-data")
) {
  fail("the validation note should explain the locked settings and scrambled-data rule.");
}
if (/\bdiscover/i.test(text) || /\bblind\b/i.test(text)) {
  fail(`pipeline copy uses a forbidden word:\n${text}`);
}

const candidate = parseTracks([
  {
    track_id: "cand-ecliptic-virgo-001",
    patch: "ecliptic-virgo",
    status: "candidate",
    object_id: "cand-ecliptic-virgo-001",
    match_sep_arcsec: null,
    motion_arcsec_per_hr: 40,
    direction_deg: 90,
    score: 0.4,
    first_seen_utc: "2026-06-01T00:00:00Z",
    size_min_km: null,
    size_max_km: null,
    distance_min_au: null,
    distance_max_au: null,
    n_points: 1,
    is_target_claimed: false,
    comet_check: "no known comet",
    linked_tracks: ["cand-a"],
    arc_hours: 0.1,
    v_mag_est: 18.2,
    H_range: [14.1, 16.4],
    position_error_px: 0.5,
    note: "only 6 min of motion",
    points: [
      {
        frame_id: "0001_2026W23_1A_0001_1_D1",
        x: 10,
        y: 12,
        ra: 180,
        dec: 0,
        mag: null,
        is_target: false,
      },
    ],
  },
])[0];
if (!candidate) fail("candidate fixture did not parse.");
if (candidate.distance_min_au !== null || candidate.note !== "only 6 min of motion") {
  fail("a candidate with null distance should keep its note.");
}
if (candidate.H_range?.[0] !== 14.1 || candidate.linked_tracks?.[0] !== "cand-a") {
  fail("candidate-only fields were dropped.");
}
if (candidate.points[0]?.mag !== null) fail("null magnitude must stay null.");

const mock = parseTracks(
  JSON.parse(readFileSync(resolve(dataDir, "detections_mock.json"), "utf8")),
);
if (!mock.some((track) => track.status === "candidate")) {
  fail("the mock file should still parse a candidate track.");
}
if (liveTracks(mock).length !== 0) fail("MOCK- tracks must be filtered out of the demo.");

console.log(
  "v0.3: 8 known tracks, 0 candidates, 3I/ATLAS burst 37, validation copy has no forbidden wording.",
);
