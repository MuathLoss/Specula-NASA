import type { DetectionPoint, DetectionTrack } from "@/types/specula";

const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

const num = (v: unknown): number | undefined =>
  typeof v === "number" && Number.isFinite(v)
    ? v
    : typeof v === "string" && v.trim() !== "" && Number.isFinite(+v)
      ? +v
      : undefined;

const str = (v: unknown): string | undefined =>
  typeof v === "string" && v.trim() !== "" ? v.trim() : undefined;

function listFrom(raw: unknown): unknown[] {
  if (Array.isArray(raw)) return raw;
  if (isObj(raw) && Array.isArray(raw.tracks)) return raw.tracks;
  throw new Error("expected a track array or { tracks: [...] }");
}

function magnitudeRange(v: unknown): [number, number] | null {
  if (Array.isArray(v) && v.length >= 2) {
    const lo = num(v[0]);
    const hi = num(v[1]);
    if (lo !== undefined && hi !== undefined) return [lo, hi];
  }
  if (isObj(v)) {
    const lo = num(v.min ?? v.lo ?? v.min_mag);
    const hi = num(v.max ?? v.hi ?? v.max_mag);
    if (lo !== undefined && hi !== undefined) return [lo, hi];
  }
  return null;
}

function linkedTracks(v: unknown): string[] | undefined {
  if (!Array.isArray(v)) return undefined;
  const ids = v.flatMap((item) => {
    if (typeof item === "string" && item.trim() !== "") return [item.trim()];
    if (typeof item === "number" && Number.isFinite(item)) return [String(item)];
    return [];
  });
  return ids;
}

function cometCheck(v: unknown): string | null {
  if (v == null) return null;
  const text = str(v);
  if (text) return text;
  if (!isObj(v)) return null;
  return str(v.result) ?? str(v.note) ?? str(v.status) ?? str(v.match) ?? null;
}

function point(raw: unknown): DetectionPoint | null {
  if (!isObj(raw)) return null;
  const frame_id = str(raw.frame_id);
  const x = num(raw.x);
  const y = num(raw.y);
  const ra = num(raw.ra);
  const dec = num(raw.dec);
  if (
    !frame_id ||
    x === undefined ||
    y === undefined ||
    ra === undefined ||
    dec === undefined
  ) {
    return null;
  }
  return {
    frame_id,
    x,
    y,
    ra,
    dec,
    mag: num(raw.mag) ?? null,
    is_target: raw.is_target === true,
  };
}

function optionalPresent<T>(
  row: Record<string, unknown>,
  key: string,
  value: T | null,
): T | null | undefined {
  return key in row ? value : undefined;
}

/** Parse detections.json or detections_mock.json. Invalid rows are dropped. */
export function parseTracks(raw: unknown): DetectionTrack[] {
  return listFrom(raw).flatMap((row): DetectionTrack[] => {
    if (!isObj(row)) return [];
    const track_id = str(row.track_id);
    const patch = str(row.patch ?? row.patch_id);
    if (!track_id || !patch || (row.status !== "known" && row.status !== "candidate")) {
      return [];
    }
    const points = (Array.isArray(row.points) ? row.points : []).flatMap((item) => {
      const parsed = point(item);
      return parsed ? [parsed] : [];
    });
    if (points.length === 0) return [];
    const linked = linkedTracks(row.linked_tracks);
    const track: DetectionTrack = {
      track_id,
      patch,
      status: row.status,
      object_id: str(row.object_id) ?? null,
      match_sep_arcsec: num(row.match_sep_arcsec) ?? null,
      motion_arcsec_per_hr: num(row.motion_arcsec_per_hr) ?? null,
      direction_deg: num(row.direction_deg) ?? null,
      score: num(row.score) ?? null,
      first_seen_utc: str(row.first_seen_utc) ?? "",
      size_min_km: num(row.size_min_km) ?? null,
      size_max_km: num(row.size_max_km) ?? null,
      distance_min_au: num(row.distance_min_au) ?? null,
      distance_max_au: num(row.distance_max_au) ?? null,
      n_points: num(row.n_points) ?? points.length,
      is_target_claimed: row.is_target_claimed === true,
      comet_check: cometCheck(row.comet_check),
      points,
    };
    const arc = optionalPresent(row, "arc_hours", num(row.arc_hours) ?? null);
    const vMag = optionalPresent(row, "v_mag_est", num(row.v_mag_est) ?? null);
    const hRange = optionalPresent(row, "H_range", magnitudeRange(row.H_range));
    const positionError = optionalPresent(
      row,
      "position_error_px",
      num(row.position_error_px) ?? null,
    );
    const note = optionalPresent(row, "note", str(row.note) ?? null);
    if (linked) track.linked_tracks = linked;
    if (arc !== undefined) track.arc_hours = arc;
    if (vMag !== undefined) track.v_mag_est = vMag;
    if (hRange !== undefined) track.H_range = hRange;
    if (positionError !== undefined) track.position_error_px = positionError;
    if (note !== undefined) track.note = note;
    return [track];
  });
}
