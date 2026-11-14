"use client";

// Patch image at native resolution, scaled with nearest-neighbour sampling,
// with an SVG overlay in the image's own pixel coordinates so markers line up
// exactly with pixels at any display size.

import React, { useEffect, useRef, useState } from "react";
import type { Detection, Marker } from "@/types/specula";
import { formatVMagnitude } from "@/lib/markers";
import { objectKey, selectionKey, type SelectionKey } from "@/lib/selection";
import { isMockTrackId } from "@/lib/tracks";

const KNOWN = "#00F0FF";
const CANDIDATE = "#FF8C00";
/** Detection/marker x/y refer to pixel centres (0-based); SVG pixel centres sit at +0.5. */
const PIXEL_CENTER_OFFSET = 0.5;

type OverlayItem =
  | { kind: "marker"; marker: Marker; key: SelectionKey }
  | { kind: "prediction"; marker: Marker; key: SelectionKey }
  | { kind: "known"; detection: Detection; key: SelectionKey }
  | { kind: "candidate"; detection: Detection; key: SelectionKey };

export type ViewportImageStatus = {
  key: string;
  index: number;
  ready: boolean;
  allFailed: boolean;
};

interface Viewport2DProps {
  /** Image URLs tried in order until one loads (see burstImageUrls). */
  imageUrls?: string[];
  /** Native image size in pixels (overlay coordinate space). */
  width?: number;
  height?: number;
  /** Largest on-screen width in CSS px; the view shrinks to fit narrower containers. */
  displayWidth?: number;
  /**
   * Known tracks are circles along their path. Candidates stay orange diamonds.
   * Detections are restricted to the current frame or burst.
   */
  detections?: Detection[];
  /** Frames of the photo on screen. Known points outside this set stay dimmed. */
  activeFrameIds?: readonly string[];
  /** Known-asteroid markers for the frame or burst on screen. */
  markers?: Marker[];
  /** JPL predictions with in_data=true, always distinguishable from recovered tracks. */
  predictedMarkers?: Marker[];
  selectedId?: SelectionKey | null;
  onSelect?: (id: SelectionKey | null) => void;
  onHoverChange?: (id: SelectionKey | null) => void;
  /** Compact label for the image, e.g. the composite's detector pair. */
  imageLabel?: string | null;
  /** Shown when every candidate URL has failed. */
  missingLabel?: string;
  onImageStatus?: (status: ViewportImageStatus) => void;
  /** Per-patch data still loading: dim the view, hide overlays, show a spinner. */
  loading?: boolean;
}

export const Viewport2D: React.FC<Viewport2DProps> = ({
  imageUrls = [],
  width = 351,
  height = 351,
  displayWidth = 528,
  detections = [],
  activeFrameIds,
  markers = [],
  predictedMarkers = [],
  selectedId = null,
  onSelect,
  onHoverChange,
  imageLabel = null,
  missingLabel = "Patch image not found",
  onImageStatus,
  loading = false,
}) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const urlsKey = imageUrls.join("|");
  const [attempt, setAttempt] = useState<{ key: string; index: number }>({
    key: urlsKey,
    index: 0,
  });
  const index = attempt.key === urlsKey ? attempt.index : 0;
  const imageUrl = imageUrls[index];
  const allFailed = imageUrls.length > 0 && index >= imageUrls.length;
  // Last URL that finished loading. It stays on screen until the next image is
  // ready, so stepping bursts or switching patches never flashes an empty frame.
  const [shownUrl, setShownUrl] = useState<string | null>(null);
  const ready = !!imageUrl && shownUrl === imageUrl;
  const holdPrevious = !!shownUrl && !!imageUrl && shownUrl !== imageUrl;
  const showImage = !!imageUrl || (loading && !!shownUrl);
  const imageRef = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const img = imageRef.current;
    if (!img || !imageUrl || img.getAttribute("src") !== imageUrl) return;
    if (img.complete && img.naturalWidth > 0) setShownUrl(imageUrl);
  }, [imageUrl, urlsKey, index]);

  useEffect(() => {
    onImageStatus?.({ key: urlsKey, index, ready, allFailed });
  }, [onImageStatus, urlsKey, index, ready, allFailed]);

  const activeFrames = activeFrameIds ? new Set(activeFrameIds) : null;
  const pointActive = (frameId: string) => !activeFrames || activeFrames.has(frameId);
  const items: OverlayItem[] = [
    ...predictedMarkers.map((marker) => ({
      kind: "prediction" as const,
      marker,
      key: objectKey(marker.object_id),
    })),
    ...markers.map((marker) => ({
      kind: "marker" as const,
      marker,
      key: objectKey(marker.object_id),
    })),
    ...detections.flatMap((detection): OverlayItem[] => {
      if (isMockTrackId(detection.track_id)) return [];
      if (detection.type === "known") {
        return [{ kind: "known", detection, key: selectionKey(detection) }];
      }
      if (detection.type === "candidate") {
        return [{ kind: "candidate", detection, key: selectionKey(detection) }];
      }
      return [];
    }),
  ];
  const knownPaths = (() => {
    const groups = new Map<string, { x: number; y: number }[]>();
    for (const item of items) {
      if (item.kind !== "known") continue;
      const points = groups.get(item.detection.track_id) ?? [];
      points.push({ x: item.detection.x, y: item.detection.y });
      groups.set(item.detection.track_id, points);
    }
    return [...groups.entries()].map(([trackId, points]) => ({ trackId, points }));
  })();

  const hovered = hoveredId
    ? (items.find((item) => overlayHoverId(item) === hoveredId) ?? null)
    : null;

  const unit = Math.max(width, height) / 351;
  const r = 5 * unit;

  const hover = (item: OverlayItem | null) => {
    setHoveredId(item ? overlayHoverId(item) : null);
    onHoverChange?.(item?.key ?? null);
  };

  return (
    <div className="border-line bg-void flex items-center justify-center rounded-lg border p-4">
      <div
        className="relative w-full"
        style={{ maxWidth: displayWidth, aspectRatio: `${width} / ${height}` }}
      >
        {showImage ? (
          <div
            className={`absolute inset-0 transition-opacity duration-200 motion-reduce:transition-none ${loading ? "opacity-40" : "opacity-100"}`}
          >
            {(holdPrevious || (loading && !imageUrl)) && shownUrl && (
              // eslint-disable-next-line @next/next/no-img-element -- previous frame, held until the next loads
              <img
                src={shownUrl}
                alt=""
                aria-hidden
                draggable={false}
                className="absolute inset-0 h-full w-full select-none"
                style={{ imageRendering: "pixelated" }}
              />
            )}
            {imageUrl && (
              // eslint-disable-next-line @next/next/no-img-element -- raw pixels; next/image would resample
              <img
                key={imageUrl}
                ref={imageRef}
                src={imageUrl}
                alt="SPHEREx patch field"
                draggable={false}
                onLoad={(event) => {
                  if (event.currentTarget.getAttribute("src") !== imageUrl) return;
                  setShownUrl(imageUrl);
                }}
                onError={(event) => {
                  if (event.currentTarget.getAttribute("src") !== imageUrl) return;
                  setAttempt({ key: urlsKey, index: index + 1 });
                }}
                className={`absolute inset-0 h-full w-full select-none ${holdPrevious ? "opacity-0" : ""}`}
                style={{ imageRendering: "pixelated" }}
              />
            )}
          </div>
        ) : loading ? null : (
          <div className="animate-fade-in border-line text-muted absolute inset-0 flex items-center justify-center rounded border border-dashed text-sm">
            {allFailed ? missingLabel : "No patch image"}
          </div>
        )}

        {loading && (
          <div
            className="animate-fade-in bg-raised/90 text-ink ring-line pointer-events-none absolute top-2 right-2 z-20 flex items-center gap-2 rounded px-2 py-1 text-[11px] ring-1"
            role="status"
          >
            <span className="border-muted border-t-ink h-3 w-3 animate-spin rounded-full border motion-reduce:animate-none" />
            Loading patch…
          </div>
        )}

        <svg
          className={`absolute inset-0 h-full w-full transition-opacity duration-200 motion-reduce:transition-none ${loading ? "pointer-events-none opacity-0" : "opacity-100"}`}
          aria-busy={loading || undefined}
          viewBox={`0 0 ${width} ${height}`}
          onClick={() => onSelect?.(null)}
          role="group"
          aria-label="Detections"
        >
          {knownPaths.map((path) =>
            path.points.length < 2 ? null : (
              <polyline
                key={path.trackId}
                points={path.points
                  .map((p) => `${p.x + PIXEL_CENTER_OFFSET},${p.y + PIXEL_CENTER_OFFSET}`)
                  .join(" ")}
                fill="none"
                stroke={KNOWN}
                strokeWidth={1.25}
                strokeOpacity={0.8}
                strokeLinejoin="round"
                strokeLinecap="round"
                vectorEffect="non-scaling-stroke"
                pointerEvents="none"
              />
            ),
          )}
          {items.map((item) => {
            const selected = item.key === selectedId;
            const isHovered = overlayHoverId(item) === hoveredId;
            const s = selected || isHovered ? 1.35 : 1;
            if (item.kind === "marker" || item.kind === "prediction") {
              const prediction = item.kind === "prediction";
              const m = item.marker;
              const cx = m.x + PIXEL_CENTER_OFFSET;
              const cy = m.y + PIXEL_CENTER_OFFSET;
              const faint = !prediction && !m.likely_visible;
              const label = prediction
                ? `Predicted by NASA JPL: ${m.name}`
                : `${m.name}, ${formatVMagnitude(m.v_mag)}`;
              return (
                <g
                  key={`${item.kind}:${m.frame_id}:${m.object_id}`}
                  role="button"
                  tabIndex={0}
                  aria-label={label}
                  aria-pressed={selected}
                  data-kind={item.kind}
                  data-visible={faint ? "faint" : "solid"}
                  data-source={prediction ? "NASA JPL" : undefined}
                  data-object-id={m.object_id}
                  className="cursor-pointer outline-none"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect?.(item.key);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect?.(item.key);
                    }
                  }}
                  onMouseEnter={() => hover(item)}
                  onMouseLeave={() => hover(null)}
                  onFocus={() => hover(item)}
                  onBlur={() => hover(null)}
                >
                  <circle cx={cx} cy={cy} r={r * 1.8} fill="transparent" />
                  <circle
                    cx={cx}
                    cy={cy}
                    r={r * s}
                    fill="none"
                    stroke={KNOWN}
                    strokeWidth={selected ? 2 : prediction ? 1.5 : faint ? 1 : 1.25}
                    strokeOpacity={prediction ? 0.7 : faint ? 0.45 : 1}
                    strokeDasharray={prediction ? "4 3" : faint ? "2 2" : undefined}
                    vectorEffect="non-scaling-stroke"
                  />
                  {selected && (
                    <circle
                      cx={cx}
                      cy={cy}
                      r={r * 2.2}
                      fill="none"
                      stroke={KNOWN}
                      strokeOpacity={0.5}
                      strokeDasharray="2 2"
                      vectorEffect="non-scaling-stroke"
                    />
                  )}
                </g>
              );
            }

            if (item.kind === "known") {
              const d = item.detection;
              const cx = d.x + PIXEL_CENTER_OFFSET;
              const cy = d.y + PIXEL_CENTER_OFFSET;
              const active = pointActive(d.frame_id);
              const name = d.designation ?? d.object_id ?? d.track_id;
              const label = `Recovered by our pipeline: ${name}`;
              return (
                <g
                  key={d.id}
                  role="button"
                  tabIndex={active ? 0 : -1}
                  aria-label={label}
                  aria-pressed={selected}
                  data-kind="known"
                  data-active={active ? "true" : "false"}
                  data-object-id={d.object_id}
                  className="cursor-pointer outline-none"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect?.(item.key);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect?.(item.key);
                    }
                  }}
                  onMouseEnter={() => hover(item)}
                  onMouseLeave={() => hover(null)}
                  onFocus={() => hover(item)}
                  onBlur={() => hover(null)}
                >
                  <circle cx={cx} cy={cy} r={r * 1.8} fill="transparent" />
                  <circle
                    cx={cx}
                    cy={cy}
                    r={Math.max(1.6, r * 0.38) * s}
                    fill={KNOWN}
                    fillOpacity={active ? 0.95 : 0.4}
                    stroke="none"
                  />
                  <circle
                    cx={cx}
                    cy={cy}
                    r={r * s}
                    fill="none"
                    stroke={KNOWN}
                    strokeWidth={selected ? 2 : 1.25}
                    strokeOpacity={active ? 1 : 0.45}
                    vectorEffect="non-scaling-stroke"
                  />
                  {selected && (
                    <circle
                      cx={cx}
                      cy={cy}
                      r={r * 2.2}
                      fill="none"
                      stroke={KNOWN}
                      strokeOpacity={0.5}
                      strokeDasharray="2 2"
                      vectorEffect="non-scaling-stroke"
                    />
                  )}
                </g>
              );
            }

            const d = item.detection;
            const cx = d.x + PIXEL_CENTER_OFFSET;
            const cy = d.y + PIXEL_CENTER_OFFSET;
            const name = d.designation ?? d.track_id;
            const unknown =
              !Number.isFinite(d.distance_min_au) || !Number.isFinite(d.distance_max_au);
            const label = unknown
              ? `Candidate ${name}, distance unknown`
              : `Candidate ${name}`;
            return (
              <g
                key={d.id}
                role="button"
                tabIndex={0}
                aria-label={label}
                aria-pressed={selected}
                data-kind="candidate"
                className="cursor-pointer outline-none"
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect?.(item.key);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect?.(item.key);
                  }
                }}
                onMouseEnter={() => hover(item)}
                onMouseLeave={() => hover(null)}
                onFocus={() => hover(item)}
                onBlur={() => hover(null)}
              >
                <circle cx={cx} cy={cy} r={r * 1.8} fill="transparent" />
                <polygon
                  points={`${cx},${cy - r * s} ${cx + r * s},${cy} ${cx},${cy + r * s} ${cx - r * s},${cy}`}
                  fill={selected ? "rgba(255,140,0,0.25)" : "none"}
                  stroke={CANDIDATE}
                  strokeWidth={selected ? 2 : 1.5}
                  vectorEffect="non-scaling-stroke"
                  style={{
                    filter: `drop-shadow(0 0 ${selected ? 4 : 2.5}px ${CANDIDATE})`,
                  }}
                />
                {selected && (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={r * 2.2}
                    fill="none"
                    stroke={CANDIDATE}
                    strokeOpacity={0.5}
                    strokeDasharray="2 2"
                    vectorEffect="non-scaling-stroke"
                  />
                )}
              </g>
            );
          })}
        </svg>

        {imageLabel && (
          <div className="bg-raised/90 text-ink ring-line pointer-events-none absolute bottom-2 left-2 rounded px-2 py-0.5 font-mono text-[10px] ring-1">
            {imageLabel}
          </div>
        )}

        {hovered && (
          <div
            className="bg-raised/95 text-ink ring-line pointer-events-none absolute z-10 rounded px-2 py-1 text-[11px] whitespace-nowrap ring-1"
            style={{
              left: `${((itemX(hovered) + PIXEL_CENTER_OFFSET) / width) * 100}%`,
              top: `${((itemY(hovered) + PIXEL_CENTER_OFFSET) / height) * 100}%`,
              transform: "translate(12px, -50%)",
            }}
          >
            {hovered.kind === "marker" || hovered.kind === "prediction" ? (
              <>
                <span style={{ color: KNOWN }}>
                  {hovered.kind === "prediction" ? "Predicted by NASA JPL" : "Known"}
                </span>{" "}
                {hovered.marker.name}
                {hovered.kind === "marker" && (
                  <span className="text-muted ml-1.5">
                    {formatVMagnitude(hovered.marker.v_mag)}
                  </span>
                )}
              </>
            ) : hovered.kind === "known" ? (
              <>
                <span style={{ color: KNOWN }}>Recovered by our pipeline</span>{" "}
                {hovered.detection.designation ??
                  hovered.detection.object_id ??
                  hovered.detection.track_id}
              </>
            ) : (
              <>
                <span style={{ color: CANDIDATE }}>Candidate</span>{" "}
                {hovered.detection.designation ?? hovered.detection.track_id}
                {(!Number.isFinite(hovered.detection.distance_min_au) ||
                  !Number.isFinite(hovered.detection.distance_max_au)) && (
                  <span className="text-muted ml-1.5">distance unknown</span>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

function overlayHoverId(item: OverlayItem): string {
  if (item.kind === "marker" || item.kind === "prediction") {
    return `${item.kind}:${item.marker.frame_id}:${item.marker.object_id}`;
  }
  return item.detection.id;
}

function itemX(item: OverlayItem): number {
  return item.kind === "marker" || item.kind === "prediction"
    ? item.marker.x
    : item.detection.x;
}

function itemY(item: OverlayItem): number {
  return item.kind === "marker" || item.kind === "prediction"
    ? item.marker.y
    : item.detection.y;
}
