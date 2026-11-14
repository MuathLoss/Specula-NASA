-- Optional Neon / Postgres schema. The app does not need a database;
-- static files in public/data/ are the source of truth for the UI.
-- Apply with the Neon SQL editor, or: npm run db:push (requires DATABASE_URL).

CREATE TABLE IF NOT EXISTS catalog_objects (
  object_id text PRIMARY KEY,
  name text NOT NULL,
  kind text NOT NULL,
  status text NOT NULL,
  h_mag double precision,
  size_min_km double precision,
  size_max_km double precision,
  size_source text,
  distance_min_au double precision,
  distance_max_au double precision,
  show_in_3d boolean NOT NULL,
  patches text NOT NULL,
  n_frames integer NOT NULL,
  first_utc timestamptz,
  last_utc timestamptz
);

CREATE TABLE IF NOT EXISTS data_updates (
  update_id text PRIMARY KEY,
  ingested_utc timestamptz NOT NULL,
  baseline boolean NOT NULL,
  data_through_utc timestamptz,
  n_frames integer,
  frames_added text,
  note text
);

CREATE TABLE IF NOT EXISTS detections (
  track_id text PRIMARY KEY,
  patch text NOT NULL,
  status text NOT NULL,
  object_id text,
  match_sep_arcsec double precision,
  motion_arcsec_per_hr double precision,
  direction_deg double precision,
  score double precision,
  first_seen_utc timestamptz,
  size_min_km double precision,
  size_max_km double precision,
  distance_min_au double precision,
  distance_max_au double precision
);

CREATE TABLE IF NOT EXISTS detection_points (
  id integer PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  track_id text NOT NULL REFERENCES detections (track_id) ON DELETE CASCADE,
  frame_id text NOT NULL,
  x double precision NOT NULL,
  y double precision NOT NULL,
  ra double precision NOT NULL,
  dec double precision NOT NULL,
  mag double precision
);

CREATE INDEX IF NOT EXISTS detection_points_track_idx ON detection_points (track_id);
CREATE INDEX IF NOT EXISTS detection_points_frame_idx ON detection_points (frame_id);
CREATE UNIQUE INDEX IF NOT EXISTS detection_points_track_frame_idx
  ON detection_points (track_id, frame_id);
