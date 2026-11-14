import type { CatalogObject, ObjectKind, ObjectStatus } from "@/types/specula";
import { optionalNumber, optionalString, parseBool, parseCsv } from "@/lib/parse-csv";

const KINDS = new Set<ObjectKind>([
  "asteroid",
  "dwarf_planet",
  "interstellar",
  "candidate",
]);

function asKind(value: string): ObjectKind {
  return KINDS.has(value as ObjectKind) ? (value as ObjectKind) : "asteroid";
}

function asStatus(value: string): ObjectStatus {
  return value === "candidate" ? "candidate" : "known";
}

export function parseObjectsCsv(text: string): CatalogObject[] {
  return parseCsv(text).map((row) => ({
    object_id: row.object_id ?? "",
    name: row.name ?? "",
    kind: asKind(row.kind ?? ""),
    status: asStatus(row.status ?? ""),
    H_mag: optionalNumber(row.H_mag),
    size_min_km: optionalNumber(row.size_min_km),
    size_max_km: optionalNumber(row.size_max_km),
    size_source: row.size_source ?? "",
    distance_min_au: optionalNumber(row.distance_min_au),
    distance_max_au: optionalNumber(row.distance_max_au),
    show_in_3d: parseBool(row.show_in_3d),
    patches: (row.patches ?? "")
      .split(";")
      .map((p) => p.trim())
      .filter(Boolean),
    n_frames: optionalNumber(row.n_frames) ?? 0,
    first_utc: optionalString(row.first_utc),
    last_utc: optionalString(row.last_utc),
  }));
}
