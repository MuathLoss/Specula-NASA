import {
  boolean,
  doublePrecision,
  index,
  integer,
  pgTable,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";

/** Seeded from objects.csv. Optional — the UI reads the CSV directly. */
export const catalogObjects = pgTable("catalog_objects", {
  objectId: text("object_id").primaryKey(),
  name: text("name").notNull(),
  kind: text("kind").notNull(),
  status: text("status").notNull(),
  hMag: doublePrecision("h_mag"),
  sizeMinKm: doublePrecision("size_min_km"),
  sizeMaxKm: doublePrecision("size_max_km"),
  sizeSource: text("size_source"),
  distanceMinAu: doublePrecision("distance_min_au"),
  distanceMaxAu: doublePrecision("distance_max_au"),
  showIn3d: boolean("show_in_3d").notNull(),
  patches: text("patches").notNull(),
  nFrames: integer("n_frames").notNull(),
  firstUtc: timestamp("first_utc", { withTimezone: true, mode: "string" }),
  lastUtc: timestamp("last_utc", { withTimezone: true, mode: "string" }),
});

/** Data-pack updates, used by the NEW-badge rule. */
export const dataUpdates = pgTable("data_updates", {
  updateId: text("update_id").primaryKey(),
  ingestedUtc: timestamp("ingested_utc", {
    withTimezone: true,
    mode: "string",
  }).notNull(),
  baseline: boolean("baseline").notNull(),
  dataThroughUtc: timestamp("data_through_utc", {
    withTimezone: true,
    mode: "string",
  }),
  nFrames: integer("n_frames"),
  // Delivered history.json uses a string for the baseline row.
  framesAdded: text("frames_added"),
  note: text("note"),
});

/** Detection tracks from detections.json (v0.3) or the mock file. */
export const detections = pgTable("detections", {
  trackId: text("track_id").primaryKey(),
  patch: text("patch").notNull(),
  status: text("status").notNull(),
  objectId: text("object_id"),
  matchSepArcsec: doublePrecision("match_sep_arcsec"),
  motionArcsecPerHr: doublePrecision("motion_arcsec_per_hr"),
  directionDeg: doublePrecision("direction_deg"),
  score: doublePrecision("score"),
  firstSeenUtc: timestamp("first_seen_utc", { withTimezone: true, mode: "string" }),
  sizeMinKm: doublePrecision("size_min_km"),
  sizeMaxKm: doublePrecision("size_max_km"),
  distanceMinAu: doublePrecision("distance_min_au"),
  distanceMaxAu: doublePrecision("distance_max_au"),
});

export const detectionPoints = pgTable(
  "detection_points",
  {
    id: integer("id").primaryKey().generatedAlwaysAsIdentity(),
    trackId: text("track_id")
      .notNull()
      .references(() => detections.trackId, { onDelete: "cascade" }),
    frameId: text("frame_id").notNull(),
    x: doublePrecision("x").notNull(),
    y: doublePrecision("y").notNull(),
    ra: doublePrecision("ra").notNull(),
    dec: doublePrecision("dec").notNull(),
    mag: doublePrecision("mag"),
  },
  (table) => [
    index("detection_points_track_idx").on(table.trackId),
    index("detection_points_frame_idx").on(table.frameId),
    uniqueIndex("detection_points_track_frame_idx").on(table.trackId, table.frameId),
  ],
);
