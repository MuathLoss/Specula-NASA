import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  atlasMarkersAsMarkers,
  collapseMarkers,
  markersForFrames,
  parseAtlasMarkers,
} from "../lib/markers";
import type { Burst, Detection, Track } from "../types/specula";
import { countDetectionsInView, detectionsAtBurst, unrollTracks } from "../lib/tracks";

const dataDir = resolve(process.cwd(), "public/data");

function fail(message: string): never {
  console.error(message);
  process.exit(1);
}

type TrackFile = Track[];

type TimelineFile = {
  bursts: Array<
    Burst & {
      burst_id: string;
      frame_ids: string[];
      frames: Array<{ frame_id: string; time_utc: string }>;
    }
  >;
};

const tracks = JSON.parse(
  readFileSync(resolve(dataDir, "detections_mock.json"), "utf8"),
) as TrackFile;
const timeline = JSON.parse(
  readFileSync(resolve(dataDir, "ecliptic-virgo/timeline.json"), "utf8"),
) as TimelineFile;

function burst(id: string): Burst {
  const found = timeline.bursts.find((item) => item.burst_id === id);
  if (!found) fail(`Burst ${id} is missing from the ecliptic-virgo timeline.`);
  return found;
}

function count(id: string, mode: "composite" | "full", frameId?: string): number {
  const item = burst(id);
  return countDetectionsInView(
    tracks.filter((track) => track.patch === "ecliptic-virgo"),
    mode === "full"
      ? { mode: "full", frameId }
      : { mode: "composite", frameIds: item.frame_ids },
  );
}

const first = burst("2025W20_2D_0234");
if (count("2025W20_2D_0234", "composite") !== 0) {
  fail("2025W20_2D_0234 should have 0 detections in composite view.");
}
if (count("2025W20_2D_0234", "full", first.frame_ids[0]) !== 0) {
  fail("The first frame of 2025W20_2D_0234 should have 0 detections.");
}

const known = tracks.find((track) => track.track_id === "MOCK-trk-001");
if (!known || known.points.length < 2) {
  fail("MOCK-trk-001 should have more than one point.");
}
if (count("2025W51_2A_0398", "composite") !== 1) {
  fail("2025W51_2A_0398 should count MOCK-trk-001 once, not once per point.");
}
if (count("2025W51_2A_0398", "full", known.points[0]?.frame_id) !== 1) {
  fail("A frame that contains MOCK-trk-001 should count 1 detection.");
}
if (count("2025W51_2A_0242", "composite") !== 1) {
  fail("2025W51_2A_0242 should count the candidate track once.");
}

const expandedTracks = unrollTracks(tracks, new Map(), new Map());
const emptyOffDate = detectionsAtBurst(expandedTracks, first);
if (emptyOffDate.length !== 0) {
  fail("Fixed-patch points must not be drawn on 2025W20_2D_0234.");
}
const positions = expandedTracks
  .filter((detection) => detection.track_id === "MOCK-trk-001")
  .map((detection, index) => ({
    ...detection,
    x: 10 * (index + 1),
    y: 20 * (index + 1),
  })) as Detection[];
const compositeBurst = burst("2025W51_2A_0398");
const inComposite = positions.filter((point) =>
  compositeBurst.frame_ids.some((id) => point.frame_id.startsWith(id)),
);
const composite = detectionsAtBurst(positions, compositeBurst);
if (
  composite.length !== 1 ||
  composite[0].x !==
    inComposite.reduce((sum, point) => sum + point.x, 0) / inComposite.length ||
  composite[0].y !==
    inComposite.reduce((sum, point) => sum + point.y, 0) / inComposite.length
) {
  fail("A composite must show one mean x/y position per track across its dates.");
}

const russia = unrollTracks(
  tracks.filter(
    (track) => track.patch === "ecliptic-virgo" && track.track_id === "MOCK-trk-001",
  ),
  new Map(),
  new Map(),
);
const russiaDays = [
  ...new Set(
    russia
      .filter((point) =>
        compositeBurst.frame_ids.some((id) => point.frame_id.startsWith(id)),
      )
      .map((point) => point.frame_id.match(/\d{4}_\d{4}W\d{2}_/)?.[0]),
  ),
];
if (russiaDays.length > 1 && detectionsAtBurst(russia, compositeBurst).length !== 1) {
  fail("Multiple days in one burst must still produce exactly one track circle.");
}

const atlas = parseAtlasMarkers(
  JSON.parse(readFileSync(resolve(dataDir, "addons/3i-atlas_markers.json"), "utf8")),
);
if (
  atlas.length !== 259 ||
  atlas.some((marker) => !marker.in_data && marker.likely_visible)
) {
  fail("The original 3I/ATLAS addon must keep null-SNR and in_data rows.");
}
const predicted = collapseMarkers(
  markersForFrames(atlasMarkersAsMarkers(atlas.filter((m) => m.in_data)), [
    "0001_2025W31_2A_0156_1_D3",
    "0002_2025W31_2A_0156_1_D6",
  ]),
);
if (predicted.length !== 1) fail("One JPL ring should be drawn per 3I/ATLAS burst.");

const outside = countDetectionsInView(tracks, {
  mode: "composite",
  frameIds: first.frame_ids,
});
if (outside !== 0) {
  fail("Tracks from other patches must not count on 2025W20_2D_0234.");
}

console.log(
  "2025W20_2D_0234 has 0 detections in view. Tracks with points in view count once.",
);
