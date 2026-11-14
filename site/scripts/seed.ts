import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { eq } from "drizzle-orm";
import { parseObjectsCsv } from "../lib/parse-objects";
import { getDb, isDatabaseConfigured } from "../lib/db/client";
import {
  catalogObjects,
  dataUpdates,
  detectionPoints,
  detections,
} from "../lib/db/schema";
import type { DetectionTrack, History } from "../types/specula";

function loadEnvFile(name: string) {
  try {
    process.loadEnvFile(resolve(process.cwd(), name));
  } catch {
    // file is optional
  }
}

loadEnvFile(".env");
loadEnvFile(".env.local");

const dataDir = resolve(process.cwd(), "public/data");

async function main() {
  if (!isDatabaseConfigured()) {
    console.error(
      "DATABASE_URL is not set. The site does not need a database; skip this script or copy .env.example to .env.",
    );
    process.exit(1);
  }

  const db = getDb();
  const objectsPath = resolve(dataDir, "objects.csv");
  if (!existsSync(objectsPath)) {
    console.error("public/data/objects.csv not found.");
    process.exit(1);
  }

  const objects = parseObjectsCsv(readFileSync(objectsPath, "utf8"));
  for (const obj of objects) {
    const row = {
      objectId: obj.object_id,
      name: obj.name,
      kind: obj.kind,
      status: obj.status,
      hMag: obj.H_mag,
      sizeMinKm: obj.size_min_km,
      sizeMaxKm: obj.size_max_km,
      sizeSource: obj.size_source,
      distanceMinAu: obj.distance_min_au,
      distanceMaxAu: obj.distance_max_au,
      showIn3d: obj.show_in_3d,
      patches: obj.patches.join(";"),
      nFrames: obj.n_frames,
      firstUtc: obj.first_utc,
      lastUtc: obj.last_utc,
    };
    await db.insert(catalogObjects).values(row).onConflictDoUpdate({
      target: catalogObjects.objectId,
      set: row,
    });
  }
  console.log(`Upserted ${objects.length} catalog objects.`);

  const historyPath = resolve(dataDir, "history.json");
  if (existsSync(historyPath)) {
    const history = JSON.parse(readFileSync(historyPath, "utf8")) as History;
    for (const entry of history) {
      const row = {
        updateId: entry.update_id,
        ingestedUtc: entry.ingested_utc,
        baseline: entry.baseline,
        dataThroughUtc: entry.data_through_utc || null,
        nFrames: entry.n_frames,
        framesAdded: String(entry.frames_added),
        note: entry.note,
      };
      await db.insert(dataUpdates).values(row).onConflictDoUpdate({
        target: dataUpdates.updateId,
        set: row,
      });
    }
    console.log(`Upserted ${history.length} data updates.`);
  } else {
    console.log("history.json not found; skipped data_updates.");
  }

  const detectionsPath = existsSync(resolve(dataDir, "detections.json"))
    ? resolve(dataDir, "detections.json")
    : resolve(dataDir, "detections_mock.json");

  if (existsSync(detectionsPath)) {
    const tracks = JSON.parse(readFileSync(detectionsPath, "utf8")) as DetectionTrack[];
    for (const track of tracks) {
      const row = {
        trackId: track.track_id,
        patch: track.patch,
        status: track.status,
        objectId: track.object_id,
        matchSepArcsec: track.match_sep_arcsec,
        motionArcsecPerHr: track.motion_arcsec_per_hr,
        directionDeg: track.direction_deg,
        score: track.score,
        firstSeenUtc: track.first_seen_utc || null,
        sizeMinKm: track.size_min_km,
        sizeMaxKm: track.size_max_km,
        distanceMinAu: track.distance_min_au,
        distanceMaxAu: track.distance_max_au,
      };
      await db.insert(detections).values(row).onConflictDoUpdate({
        target: detections.trackId,
        set: row,
      });
      await db.delete(detectionPoints).where(eq(detectionPoints.trackId, track.track_id));
      if (track.points.length > 0) {
        await db.insert(detectionPoints).values(
          track.points.map((point) => ({
            trackId: track.track_id,
            frameId: point.frame_id,
            x: point.x,
            y: point.y,
            ra: point.ra,
            dec: point.dec,
            mag: point.mag,
          })),
        );
      }
    }
    console.log(`Upserted ${tracks.length} detection tracks from ${detectionsPath}.`);
  } else {
    console.log("No detections file found; skipped detections.");
  }
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
