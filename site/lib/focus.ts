import type { ImageMode } from "@/lib/timeline";

export type FocusMode = "photo" | "big" | "all";

/** A 3I/ATLAS predicted-position row. `object_id` is fixed so only "3I" can join. */
export type AtlasFocusMarker = {
  frame_id: string;
  object_id: "3I";
  in_data?: boolean;
};

/** The loader supplies the restored 3I/ATLAS addon; empty is its loading fallback. */
export const atlasFocusMarkers: readonly AtlasFocusMarker[] = [];

export function focusFrameIds(
  imageMode: ImageMode,
  burstId: string | undefined,
  frames: readonly { frame_id: string; burst_id: string }[],
  selectedFrameId: string | undefined,
  burstFrameIds: readonly string[] = [],
): string[] {
  if (imageMode === "full") return selectedFrameId ? [selectedFrameId] : [];
  if (!burstId) return [];
  const matched = frames
    .filter((frame) => frame.burst_id === burstId)
    .map((frame) => frame.frame_id);
  return matched.length > 0 ? matched : [...burstFrameIds];
}

export function atlasObjectIds(
  frameIds: ReadonlySet<string>,
  markers: readonly AtlasFocusMarker[] = atlasFocusMarkers,
): string[] {
  const ids = new Set<string>();
  for (const marker of markers) {
    if (frameIds.has(marker.frame_id)) ids.add(marker.object_id);
  }
  return [...ids];
}

export function objectIdsForFrames(
  markers: readonly { frame_id: string; object_id: string }[],
  frameIds: readonly string[],
  atlasMarkers: readonly AtlasFocusMarker[] = atlasFocusMarkers,
): string[] {
  if (frameIds.length === 0) return [];
  const frames = new Set(frameIds);
  const ids = new Set<string>();
  for (const marker of markers) {
    if (frames.has(marker.frame_id)) ids.add(marker.object_id);
  }
  for (const objectId of atlasObjectIds(frames, atlasMarkers)) ids.add(objectId);
  return [...ids];
}
