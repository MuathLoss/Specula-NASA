import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { isValidOrbit, orbitPath, orbitPathAround, orbitPosition } from "../lib/orbit";
import type { OrbitEntry, OrbitsFile, ReferencePositions } from "../types/specula";

const dataDir = resolve(process.cwd(), "public/data");
const orbitsPath = resolve(dataDir, "orbits.json");
const refPath = resolve(dataDir, "reference_positions.json");

if (!existsSync(orbitsPath) || !existsSync(refPath)) {
  console.log(
    "Skipping orbit test: public/data/orbits.json or reference_positions.json is missing.",
  );
  process.exit(0);
}

const orbits = JSON.parse(readFileSync(orbitsPath, "utf8")) as OrbitsFile;
const refs = JSON.parse(readFileSync(refPath, "utf8")) as ReferencePositions;

const byId = new Map<string, OrbitEntry>();
for (const entry of orbits.objects) byId.set(entry.object_id, entry);
for (const entry of orbits.planets) byId.set(entry.object_id, entry);

let worst = 0;
let failed = 0;
let checked = 0;

for (const obj of refs.objects) {
  const entry = byId.get(obj.object_id);
  if (!entry) {
    console.error(`No orbit for object_id ${obj.object_id}`);
    failed += 1;
    continue;
  }
  for (const sample of obj.positions) {
    const [x, y, z] = orbitPosition(entry, sample.jd_tdb);
    const err = Math.hypot(
      x - sample.two_body_x_au,
      y - sample.two_body_y_au,
      z - sample.two_body_z_au,
    );
    checked += 1;
    worst = Math.max(worst, err);
    if (err > 1e-6) {
      failed += 1;
      console.error(
        `${obj.name} @ ${sample.date_tdb}: two-body error ${err.toExponential(3)} AU (limit 1e-6)`,
      );
    }
  }
}

if (failed > 0) {
  console.error(
    `Failed ${failed} of ${checked} samples. Worst error ${worst.toExponential(3)} AU.`,
  );
  process.exit(1);
}

function fail(message: string): never {
  console.error(message);
  process.exit(1);
}

const atlas = byId.get("3I");
if (!atlas || atlas.orbit_type !== "hyperbolic") {
  fail("3I/ATLAS is missing from orbits.json or is not hyperbolic.");
}
if (!(atlas.e > 1) || !isValidOrbit(atlas)) {
  fail("3I/ATLAS hyperbolic elements were rejected by isValidOrbit.");
}

const atlasPath = orbitPath(atlas, 160, 50);
if (atlasPath.length < 100) {
  fail(`orbitPath dropped the 3I/ATLAS hyperbola (${atlasPath.length} points).`);
}
const radii = atlasPath.map((p) => Math.hypot(p[0], p[1], p[2]));
const minR = Math.min(...radii);
const maxR = Math.max(...radii);
if (Math.abs(minR - atlas.q_au) > 1e-6) {
  fail(`3I/ATLAS perihelion radius ${minR} AU does not match q ${atlas.q_au} AU.`);
}
if (maxR < 40) {
  fail(`3I/ATLAS hyperbola is clipped too early (max r ${maxR} AU).`);
}

const peri = orbitPosition(atlas, atlas.tp_jd_tdb);
const periR = Math.hypot(peri[0], peri[1], peri[2]);
if (Math.abs(periR - atlas.q_au) > 1e-9) {
  fail(`Position at tp is ${periR} AU, expected q ${atlas.q_au} AU.`);
}

const around = orbitPathAround(atlas, atlas.tp_jd_tdb, 200, 35, 800);
if (around.length < 50) {
  fail(`orbitPathAround returned too few 3I/ATLAS points (${around.length}).`);
}
const aroundR = around.map((p) => Math.hypot(p[0], p[1], p[2]));
if (Math.min(...aroundR) > atlas.q_au + 0.05) {
  fail("orbitPathAround around perihelion missed the perihelion segment.");
}

const ceres = byId.get("1");
if (!ceres || ceres.orbit_type !== "elliptic" || orbitPath(ceres).length < 50) {
  fail("Ceres elliptic orbit path was not generated.");
}

console.log(
  `Orbit solver matched two_body_* on ${checked} samples. Worst error ${worst.toExponential(3)} AU.`,
);
console.log(
  `Hyperbolic 3I/ATLAS path: ${atlasPath.length} points, r ${minR.toFixed(4)}–${maxR.toFixed(4)} AU.`,
);
