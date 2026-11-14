import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { isFiniteVec, lineOfSightSegment, type Vec3 } from "../lib/astro";
import { radecToEcliptic } from "../lib/orbit";
import type { Pointing } from "../types/specula";

const dataDir = resolve(process.cwd(), "public/data");

function fail(message: string): never {
  console.error(message);
  process.exit(1);
}

function almostEqual(a: number, b: number, eps = 1e-9): boolean {
  return Math.abs(a - b) <= eps;
}

const detections = JSON.parse(
  readFileSync(resolve(dataDir, "detections_mock.json"), "utf8"),
) as Array<{
  track_id: string;
  distance_min_au: number | null;
  distance_max_au: number | null;
  points: Array<{ frame_id: string; ra: number; dec: number }>;
}>;

const candidate = detections.find((t) => t.track_id === "MOCK-cand-001");
if (!candidate) fail("MOCK-cand-001 is missing from detections_mock.json.");
if (candidate.distance_min_au !== 1.9 || candidate.distance_max_au !== 3.2) {
  fail(
    `MOCK-cand-001 distances should be 1.9-3.2 AU, got ${candidate.distance_min_au}-${candidate.distance_max_au}.`,
  );
}

const point = candidate.points[0];
if (!point) fail("MOCK-cand-001 has no points.");

const pointings = JSON.parse(readFileSync(resolve(dataDir, "pointings.json"), "utf8")) as
  Pointing[] | { pointings: Pointing[] };
const pointingList = Array.isArray(pointings) ? pointings : pointings.pointings;
const pointing = pointingList.find((p) => p.burst_id === "2025W51_2A_0242");
if (!pointing) fail("Pointing 2025W51_2A_0242 is missing.");

const earth = pointing.earth_au;
const u = radecToEcliptic(point.ra, point.dec);
if (!isFiniteVec(earth) || !isFiniteVec(u)) {
  fail("Earth position or line-of-sight direction is not finite.");
}

const segment = lineOfSightSegment(
  earth,
  u,
  candidate.distance_min_au,
  candidate.distance_max_au,
);
if (!segment || segment.length < 2) {
  fail("lineOfSightSegment returned no segment for MOCK-cand-001.");
}

const start = segment[0];
const end = segment[segment.length - 1];
const distFromEarth = (p: Vec3) =>
  Math.hypot(p[0] - earth[0], p[1] - earth[1], p[2] - earth[2]);

const startDist = distFromEarth(start);
const endDist = distFromEarth(end);
if (!almostEqual(startDist, 1.9, 1e-9)) {
  fail(`Segment should start 1.9 AU from Earth, got ${startDist} AU.`);
}
if (!almostEqual(endDist, 3.2, 1e-9)) {
  fail(`Segment should end 3.2 AU from Earth, got ${endDist} AU.`);
}

const lo = 1.9;
const expectedStart: Vec3 = [
  earth[0] + u[0] * lo,
  earth[1] + u[1] * lo,
  earth[2] + u[2] * lo,
];
if (
  !almostEqual(start[0], expectedStart[0]) ||
  !almostEqual(start[1], expectedStart[1]) ||
  !almostEqual(start[2], expectedStart[2])
) {
  fail("Segment start is not E + 1.9 * u along the detection line of sight.");
}

const unknown = lineOfSightSegment(earth, u, Number.NaN, 3.2);
if (unknown !== null) fail("Null distances must not produce a 3D segment.");

console.log(
  `MOCK-cand-001 segment starts ${startDist.toFixed(3)} AU from Earth and ends ${endDist.toFixed(3)} AU along its line of sight.`,
);
