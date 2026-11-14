// lib/selection.ts
// One selection key is shared by the 2D viewport, the 3D viewport and the side
// panel, so selecting something in one place highlights it everywhere.
//
//   known track / catalog object -> "obj:<object_id>"   (2D track <-> 3D orbit)
//   candidate (or unmatched) track -> "track:<track_id>"
//   planet -> "planet:<id>"

import type { CatalogObject, Detection, Marker } from "@/types/specula";
import { PLANETS, type PlanetDef } from "@/lib/astro";

export type SelectionKey = string;

export const objectKey = (objectId: string): SelectionKey => `obj:${objectId}`;
export const trackKey = (trackId: string): SelectionKey => `track:${trackId}`;

export function selectionKey(d: Detection): SelectionKey {
  return d.type === "known" && d.object_id
    ? objectKey(d.object_id)
    : trackKey(d.track_id);
}

export type ResolvedSelection =
  | {
      kind: "detection";
      key: SelectionKey;
      detection: Detection;
      catalog?: CatalogObject;
    }
  | {
      kind: "marker";
      key: SelectionKey;
      marker: Marker;
      catalog?: CatalogObject;
    }
  | { kind: "catalog"; key: SelectionKey; catalog: CatalogObject }
  | { kind: "planet"; key: SelectionKey; planet: PlanetDef };

/**
 * @param detections search order matters: pass the detections visible at the
 *   current burst first so the inspector shows the current frame's values.
 */
export function resolveSelection(
  key: SelectionKey | null,
  detections: Detection[],
  catalogById: Map<string, CatalogObject>,
  markers: Marker[] = [],
): ResolvedSelection | null {
  if (!key) return null;
  if (key.startsWith("planet:")) {
    const planet = PLANETS.find((p) => `planet:${p.id}` === key);
    return planet ? { kind: "planet", key, planet } : null;
  }
  const detection = detections.find((d) => selectionKey(d) === key);
  const catalog = key.startsWith("obj:") ? catalogById.get(key.slice(4)) : undefined;
  const marker = key.startsWith("obj:")
    ? markers.find((m) => objectKey(m.object_id) === key)
    : undefined;
  if (detection) return { kind: "detection", key, detection, catalog };
  if (marker) return { kind: "marker", key, marker, catalog };
  if (catalog) return { kind: "catalog", key, catalog };
  return null;
}
