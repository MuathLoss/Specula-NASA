import type { AtlasMarker, Marker } from "@/types/specula";

const isObj = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

const num = (v: unknown): number | undefined =>
  typeof v === "number" && Number.isFinite(v)
    ? v
    : typeof v === "string" && v.trim() !== "" && Number.isFinite(+v)
      ? +v
      : undefined;

const str = (v: unknown): string | undefined =>
  typeof v === "string" && v !== "" ? v : undefined;

function markerList(raw: unknown): unknown[] {
  if (Array.isArray(raw)) return raw;
  if (isObj(raw) && Array.isArray(raw.markers)) return raw.markers;
  throw new Error("expected a marker array");
}

/** Parse a patch markers.json file (flat array, not detection tracks). */
export function parseMarkers(raw: unknown): Marker[] {
  return markerList(raw).flatMap((row): Marker[] => {
    if (!isObj(row)) return [];
    const frame_id = str(row.frame_id);
    const object_id = str(row.object_id);
    const name = str(row.name);
    const x = num(row.x);
    const y = num(row.y);
    const v_mag = num(row.v_mag);
    if (
      !frame_id ||
      !object_id ||
      !name ||
      x === undefined ||
      y === undefined ||
      v_mag === undefined
    ) {
      return [];
    }
    return [
      {
        frame_id,
        object_id,
        name,
        x,
        y,
        v_mag,
        likely_visible: row.likely_visible === true,
      },
    ];
  });
}

export function atlasMarkersAsMarkers(atlas: AtlasMarker[]): Marker[] {
  return atlas.map((marker) => ({
    frame_id: marker.frame_id,
    object_id: marker.object_id,
    name: marker.name,
    x: marker.x,
    y: marker.y,
    v_mag: 0,
    likely_visible: false,
  }));
}

export function parseAtlasMarkers(raw: unknown): AtlasMarker[] {
  let rows: unknown[];
  try {
    rows = markerList(raw);
  } catch {
    return [];
  }
  return rows.flatMap((row): AtlasMarker[] => {
    if (!isObj(row)) return [];
    const frame_id = str(row.frame_id);
    const name = str(row.name);
    const x = num(row.x);
    const y = num(row.y);
    if (
      !frame_id ||
      !name ||
      x === undefined ||
      y === undefined ||
      row.object_id !== "3I"
    ) {
      return [];
    }
    return [
      {
        frame_id,
        object_id: "3I",
        name,
        x,
        y,
        in_data: row.in_data === true,
        snr_peak: num(row.snr_peak) ?? 0,
        likely_visible: row.likely_visible === true,
      },
    ];
  });
}

export function markersForFrames(
  markers: Marker[],
  frameIds: Iterable<string>,
): Marker[] {
  const ids = frameIds instanceof Set ? frameIds : new Set(frameIds);
  if (ids.size === 0) return [];
  return markers.filter((m) => ids.has(m.frame_id));
}

export function visibleMarkers(markers: Marker[], showFaint: boolean): Marker[] {
  return showFaint ? markers : markers.filter((m) => m.likely_visible);
}

export function collapseMarkers(markers: Marker[]): Marker[] {
  const groups = new Map<string, Marker[]>();
  for (const marker of markers) {
    const group = groups.get(marker.object_id);
    if (group) group.push(marker);
    else groups.set(marker.object_id, [marker]);
  }

  const collapsed: Marker[] = [];
  for (const group of groups.values()) {
    const head = group[0];
    if (!head || group.length === 1) {
      if (head) collapsed.push(head);
      continue;
    }
    let x = 0;
    let y = 0;
    let vMag = 0;
    let likelyVisible = false;
    for (const marker of group) {
      x += marker.x;
      y += marker.y;
      vMag += marker.v_mag;
      if (marker.likely_visible) likelyVisible = true;
    }
    const n = group.length;
    collapsed.push({
      frame_id: head.frame_id,
      object_id: head.object_id,
      name: head.name,
      x: x / n,
      y: y / n,
      v_mag: vMag / n,
      likely_visible: likelyVisible,
    });
  }
  return collapsed;
}

export function formatVMagnitude(vMag: number): string {
  const text = vMag
    .toFixed(1)
    .replace(/(\.\d*?)0+$/, "$1")
    .replace(/\.$/, "");
  return `V ${text}`;
}
