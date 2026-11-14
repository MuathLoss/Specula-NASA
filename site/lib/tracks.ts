// lib/tracks.ts
// Unroll detection tracks into per-frame detections.

import type { Burst, CatalogObject, Detection, Frame, Track } from "@/types/specula";
import { sizeRangeKm } from "@/types/specula";
import { burstIdFromFrameId } from "@/lib/timeline";

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Fake pack rows. They stay available for tests and must not reach the demo. */
export function isMockTrackId(trackId: string): boolean {
  return trackId.startsWith("MOCK-");
}

export function liveTracks<T extends { track_id: string }>(tracks: readonly T[]): T[] {
  return tracks.filter((track) => !isMockTrackId(track.track_id));
}

export function unrollTracks(
  tracks: Track[],
  catalogById: Map<string, CatalogObject>,
  framesById: Map<string, Frame>,
): Detection[] {
  const out: Detection[] = [];
  for (const t of tracks) {
    const obj = t.object_id ? catalogById.get(t.object_id) : undefined;
    const trackSize: [number, number] | undefined =
      finite(t.size_min_km) && finite(t.size_max_km)
        ? [t.size_min_km, t.size_max_km]
        : obj
          ? sizeRangeKm(obj)
          : undefined;
    for (const p of t.points) {
      out.push({
        id: `${t.track_id}:${p.frame_id}`,
        track_id: t.track_id,
        frame_id: p.frame_id,
        patch_id: t.patch,
        type: t.status,
        x: p.x,
        y: p.y,
        ra_deg: p.ra,
        dec_deg: p.dec,
        mag: finite(p.mag) ? p.mag : undefined,
        object_id: t.object_id ?? undefined,
        designation: obj?.name,
        wavelength_um: framesById.get(p.frame_id)?.wavelength_um,
        score: finite(t.score) ? t.score : undefined,
        motion_arcsec_per_hr: finite(t.motion_arcsec_per_hr)
          ? t.motion_arcsec_per_hr
          : undefined,
        size_est_km: trackSize,
        distance_min_au: finite(t.distance_min_au) ? t.distance_min_au : undefined,
        distance_max_au: finite(t.distance_max_au) ? t.distance_max_au : undefined,
        is_target: p.is_target === true,
        is_target_claimed: t.is_target_claimed === true,
        n_points: finite(t.n_points) ? t.n_points : t.points.length,
        match_sep_arcsec: finite(t.match_sep_arcsec) ? t.match_sep_arcsec : undefined,
        comet_check: t.comet_check ?? undefined,
        note: t.note ?? undefined,
        v_mag_est: finite(t.v_mag_est) ? t.v_mag_est : undefined,
        h_range:
          t.H_range && finite(t.H_range[0]) && finite(t.H_range[1])
            ? t.H_range
            : undefined,
        position_error_px: finite(t.position_error_px) ? t.position_error_px : undefined,
        arc_hours: finite(t.arc_hours) ? t.arc_hours : undefined,
        linked_tracks: t.linked_tracks?.length ? [...t.linked_tracks] : undefined,
      });
    }
  }
  return out;
}

/**
 * One detection per track for the burst on screen, at the mean of all its
 * points in the burst. This stays one circle across all days of a burst.
 */
export function detectionsAtBurst(
  detections: Detection[],
  burst: Burst | undefined,
): Detection[] {
  if (!burst) return [];
  const frames = new Set(burst.frame_ids);
  const inBurst = (d: Detection) => {
    for (const frameId of frames) {
      // A composite expands one exposure per detector suffix (D1–D6).
      if (d.frame_id.startsWith(frameId)) return true;
    }
    return frames.size === 0 && burstIdFromFrameId(d.frame_id) === burst.burst_id;
  };

  const byTrack = new Map<string, Detection[]>();
  for (const d of detections) {
    if (!inBurst(d)) continue;
    const points = byTrack.get(d.track_id) ?? [];
    points.push(d);
    byTrack.set(d.track_id, points);
  }
  return [...byTrack.values()].flatMap((points) => {
    const first = points[0];
    if (!first) return [];
    return [
      {
        ...first,
        id: `${first.track_id}:${burst.burst_id}`,
        x: points.reduce((sum, point) => sum + point.x, 0) / points.length,
        y: points.reduce((sum, point) => sum + point.y, 0) / points.length,
      },
    ];
  });
}

/** Merge track lists, later lists winning on duplicate track_id. */
export function mergeTracks(...lists: Track[][]): Track[] {
  const map = new Map<string, Track>();
  for (const list of lists) for (const t of list) map.set(t.track_id, t);
  return [...map.values()];
}

/**
 * Tracks with at least one point on the current burst (composite) or the
 * current frame (full). Markers are not detections.
 */
export function countDetectionsInView(
  tracks: ReadonlyArray<{ points: ReadonlyArray<{ frame_id: string }> }>,
  scope:
    | { mode: "composite"; frameIds: readonly string[] }
    | { mode: "full"; frameId: string | undefined },
): number {
  const ids = new Set(
    scope.mode === "full" ? (scope.frameId ? [scope.frameId] : []) : scope.frameIds,
  );
  if (ids.size === 0) return 0;
  let count = 0;
  for (const track of tracks) {
    if (track.points.some((point) => ids.has(point.frame_id))) count += 1;
  }
  return count;
}

/** Detections that fall on a single photo. */
export function detectionsAtFrame(
  detections: Detection[],
  frameId: string | undefined,
): Detection[] {
  if (!frameId) return [];
  return detections.filter((d) => d.frame_id === frameId);
}
