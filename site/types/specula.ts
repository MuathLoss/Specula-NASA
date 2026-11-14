export type PatchKind = "fixed" | "moving";
export type FrameQuality = "ok" | "warn_transients";
export type ObjectKind = "asteroid" | "dwarf_planet" | "interstellar" | "candidate";
export type ObjectStatus = "known" | "candidate";
export type DetectionStatus = "known" | "candidate";
export type OrbitType = "elliptic" | "hyperbolic";

export type Vec3 = [number, number, number];
export type Vec3Tuple = Vec3;

export type ManifestPatch = {
  patch_id: string;
  name: string;
  kind: PatchKind;
  n_frames: number;
  n_bursts: number;
  date_start: string;
  date_end: string;
  folder: string;
};

export type ManifestFileEntry = {
  path: string;
  bytes: number;
};

export type Manifest = {
  version: string;
  generated_utc: string;
  data_through_utc: string;
  latest_ingest_utc: string;
  new_badge_days: number;
  new_badge_rule: string;
  patches: ManifestPatch[];
  files: ManifestFileEntry[];
};

/** UI patch: contract fields plus aliases and flags derived at load time. */
export type Patch = ManifestPatch & {
  id: string;
  has_candidates?: boolean;
  is_placeholder?: boolean;
};

export type AppManifest = Omit<Manifest, "patches"> & {
  patches: Patch[];
};

/**
 * Delivered history.json uses a string for the baseline `frames_added`
 * note; later packs may use a number.
 */
export type HistoryUpdate = {
  update_id: string;
  ingested_utc: string;
  baseline: boolean;
  data_through_utc: string;
  n_frames: number;
  frames_added: string | number;
  note: string;
};

export type History = HistoryUpdate[];
export type DataUpdate = HistoryUpdate;

export type PatchHeader = {
  patch_id: string;
  name: string;
  kind: PatchKind;
  followed_object?: string | null;
  size_px: number;
  pixel_scale_arcsec: number;
  north_up: boolean;
  projection: string;
  date_start: string;
  date_end: string;
  n_frames: number;
  n_bursts: number;
};

export type TimelineFrame = {
  frame_id: string;
  burst_id: string;
  time_utc: string;
  mjd: number;
  detector: string;
  wavelength_um: number;
  image: string;
  thumb: string;
  ra_center: number;
  dec_center: number;
  coverage: number;
  quality: FrameQuality;
  update_id: string;
  added_utc: string;
  diff?: string;
};

export type Frame = TimelineFrame;

export type TimelineBurst = {
  burst_id: string;
  time_utc: string;
  frame_ids: string[];
  detectors: string[];
  ra_center: number;
  dec_center: number;
  composite: string;
  composite_thumb: string;
  representative: string;
};

export type Timeline = {
  patch: PatchHeader;
  frames: TimelineFrame[];
  bursts: TimelineBurst[];
};

export type PatchTimeline = Timeline;

export type Marker = {
  frame_id: string;
  object_id: string;
  name: string;
  x: number;
  y: number;
  v_mag: number;
  likely_visible: boolean;
};

export type AtlasMarker = {
  frame_id: string;
  object_id: "3I";
  name: string;
  x: number;
  y: number;
  in_data: boolean;
  snr_peak: number;
  likely_visible: boolean;
};

export type DetectionPoint = {
  frame_id: string;
  x: number;
  y: number;
  ra: number;
  dec: number;
  /** Null when the pipeline did not measure a magnitude for this point. */
  mag: number | null;
  /** The detector marked this point as Ceres or 3I/ATLAS. */
  is_target: boolean;
};

export type TrackPoint = DetectionPoint;

export type DetectionTrack = {
  track_id: string;
  patch: string;
  status: DetectionStatus;
  object_id: string | null;
  match_sep_arcsec: number | null;
  motion_arcsec_per_hr: number | null;
  direction_deg: number | null;
  score: number | null;
  first_seen_utc: string;
  size_min_km: number | null;
  size_max_km: number | null;
  /** Null for known objects: use the published orbit, not a line-of-sight range. */
  distance_min_au: number | null;
  distance_max_au: number | null;
  /** Detections in the track. Falls back to points.length when the file omits it. */
  n_points: number;
  /** The detector named this track as Ceres or 3I/ATLAS. False in the v0.3 pack. */
  is_target_claimed: boolean;
  /** Known-comet check. Null when the track was not checked or did not match. */
  comet_check: string | null;
  /** Candidate tracks joined across bursts. Absent on known tracks. */
  linked_tracks?: string[];
  arc_hours?: number | null;
  v_mag_est?: number | null;
  H_range?: [number, number] | null;
  position_error_px?: number | null;
  /** Why a candidate distance or size is missing, in plain words. */
  note?: string | null;
  points: DetectionPoint[];
};

export type Track = DetectionTrack;

export type CatalogObject = {
  object_id: string;
  name: string;
  kind: ObjectKind;
  status: ObjectStatus;
  H_mag: number | null;
  size_min_km: number | null;
  size_max_km: number | null;
  size_source: string;
  distance_min_au: number | null;
  distance_max_au: number | null;
  show_in_3d: boolean;
  patches: string[];
  n_frames: number;
  first_utc: string | null;
  last_utc: string | null;
  orbit?: OrbitEntry;
};

export type EllipticOrbit = {
  object_id: string;
  name: string;
  orbit_type: "elliptic";
  a_au: number;
  e: number;
  i_deg: number;
  node_deg: number;
  peri_deg: number;
  M_deg: number;
  n_deg_day: number;
  epoch_jd_tdb: number;
};

export type HyperbolicOrbit = {
  object_id: string;
  name: string;
  orbit_type: "hyperbolic";
  q_au: number;
  a_au: number;
  e: number;
  i_deg: number;
  node_deg: number;
  peri_deg: number;
  tp_jd_tdb: number;
  n_deg_day: number;
  elements_epoch_jd_tdb?: number;
  source?: string;
};

export type OrbitEntry = EllipticOrbit | HyperbolicOrbit;

export type OrbitsFile = {
  frame: string;
  how_to: string;
  source: {
    objects: string;
    planets: string;
  };
  objects: OrbitEntry[];
  planets: EllipticOrbit[];
};

export type ReferenceSample = {
  jd_tdb: number;
  date_tdb: string;
  x_au: number;
  y_au: number;
  z_au: number;
  two_body_x_au: number;
  two_body_y_au: number;
  two_body_z_au: number;
  two_body_error_au: number;
};

export type ReferenceObject = {
  object_id: string;
  name: string;
  positions: ReferenceSample[];
};

export type ReferencePositions = {
  frame: string;
  time_scale: string;
  source: string;
  note: string;
  objects: ReferenceObject[];
  two_body_max_error_au: number;
};

export type Pointing = {
  burst_id: string;
  patch_id: string;
  time_utc: string;
  jd: number;
  ra_deg: number;
  dec_deg: number;
  fov_deg: number;
  dir_ecl: Vec3;
  earth_au: Vec3;
};

export type StarRow = [ra_deg: number, dec_deg: number, vmag: number, bv: number | null];

export type GalacticBand = {
  half_width_deg: number;
  note: string;
  columns: string[];
  points: [ra_deg: number, dec_deg: number, l_deg: number][];
};

export type SkyPath = [ra_deg: number, dec_deg: number][];

export type StarLabel = {
  text: string;
  kind: "star";
  ra_deg: number;
  dec_deg: number;
  vmag: number;
};

export type PatchLabel = {
  text: string;
  kind: "patch";
  patch_id: string;
  moving: boolean;
  ra_deg: number;
  dec_deg: number;
};

export type PoleLabel = {
  text: string;
  kind: "pole" | "galaxy";
  ra_deg: number;
  dec_deg: number;
};

export type CosmosLabel = StarLabel | PatchLabel | PoleLabel;

export type CosmosFile = {
  frame_note: string;
  obliquity_deg: number;
  source: {
    stars: string;
  };
  star_columns: string[];
  stars: StarRow[];
  galactic_band: GalacticBand;
  lines: {
    ecliptic: SkyPath;
    galactic_equator: SkyPath;
  };
  labels: CosmosLabel[];
};

export type CosmosStar = {
  ra: number;
  dec: number;
  mag: number;
  bv?: number | null;
};

/** Loaded cosmos.json plus catalog objects with orbits, for the 3D view. */
export type CosmosData = {
  stars: CosmosStar[];
  objects_3d: CatalogObject[];
  obliquity_deg?: number;
  galactic_band?: GalacticBand;
  lines?: CosmosFile["lines"];
  labels?: CosmosLabel[];
};

export type ThreeDObject = {
  catalog: CatalogObject;
  orbit: OrbitEntry | null;
};

/** One step on the scrubber: a burst of the active patch. */
export type Burst = {
  index: number;
  burst_id: string;
  patch_id: string;
  time_utc: string;
  frame_ids: string[];
  composite?: string;
  pointing?: Pointing;
};

/** A track point unrolled to one frame, as drawn on the 2D overlay. */
export type Detection = {
  id: string;
  track_id: string;
  frame_id: string;
  patch_id: string;
  type: DetectionStatus;
  x: number;
  y: number;
  ra_deg: number;
  dec_deg: number;
  mag?: number;
  object_id?: string;
  designation?: string;
  wavelength_um?: number;
  score?: number;
  motion_arcsec_per_hr?: number;
  size_est_km?: [number, number];
  distance_min_au?: number;
  distance_max_au?: number;
  is_target?: boolean;
  is_target_claimed?: boolean;
  n_points?: number;
  match_sep_arcsec?: number;
  comet_check?: string;
  note?: string;
  v_mag_est?: number;
  h_range?: [number, number];
  position_error_px?: number;
  arc_hours?: number;
  linked_tracks?: string[];
};

export function sizeRangeKm(o: {
  size_min_km: number | null;
  size_max_km: number | null;
}): [number, number] | undefined {
  const lo = o.size_min_km;
  const hi = o.size_max_km;
  if (lo === null || hi === null || !Number.isFinite(lo) || !Number.isFinite(hi)) {
    return undefined;
  }
  return [lo, hi];
}
