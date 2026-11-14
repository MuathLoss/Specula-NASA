"use client";

import dynamic from "next/dynamic";
import { useCallback, useMemo, useState } from "react";
import type { CatalogObject, Detection, Frame, Track } from "@/types/specula";
import { FrameCaption } from "@/components/FrameCaption";
import { Header } from "@/components/Header";
import { IntroOverlay, useIntroOverlay } from "@/components/IntroOverlay";
import { PipelineStatus } from "@/components/PipelineStatus";
import { SidePanel } from "@/components/SidePanel";
import { TimelineScrubber } from "@/components/TimelineScrubber";
import { Viewport2D, type ViewportImageStatus } from "@/components/Viewport2D";
import {
  DATA_BASE_URL,
  loadPatchData,
  usePatchData,
  useSpeculaData,
} from "@/hooks/useSpeculaData";
import {
  buildFrameCaption,
  compositeImageLabel,
  fullFrameImageLabel,
  singlePhotoImageLabel,
} from "@/lib/frame-caption";
import {
  atlasFocusMarkers as emptyAtlasFocusMarkers,
  focusFrameIds,
  objectIdsForFrames,
} from "@/lib/focus";
import {
  atlasMarkersAsMarkers,
  collapseMarkers,
  markersForFrames,
  visibleMarkers,
} from "@/lib/markers";
import { factsFromTracks, pipelineCopy } from "@/lib/scoring";
import { objectKey, resolveSelection, trackKey } from "@/lib/selection";
import {
  DEFAULT_NEW_BADGE_DAYS,
  buildBursts,
  burstIdFromFrameId,
  burstImages,
  burstIndexForPatch,
  newBurstIds,
  newFrameIds,
} from "@/lib/timeline";
import {
  countDetectionsInView,
  detectionsAtBurst,
  detectionsAtFrame,
  isMockTrackId,
  unrollTracks,
} from "@/lib/tracks";
import { useSession } from "@/store/session";

const Viewport3D = dynamic(() => import("@/components/Viewport3D"), {
  ssr: false,
  loading: () => (
    <div className="text-muted flex h-full items-center justify-center text-sm">
      Loading 3D view…
    </div>
  ),
});

const EMPTY_FRAMES = new Map<string, Frame>();

export type AppVariant = "overview" | "viewer" | "cosmos";

/** Without timeline.json the field size is unknown: fit the overlay to the detections. */
function inferFieldSize(
  detections: Detection[],
  xs: number[],
  ys: number[],
): number | null {
  const values = [...detections.map((d) => Math.max(d.x, d.y)), ...xs, ...ys];
  if (values.length === 0) return null;
  const max = Math.max(...values);
  return Math.ceil((max * 1.1) / 50) * 50;
}

function detectionsInViewLabel(count: number): string {
  return count === 1 ? "1 detection in view" : `${count} detections in view`;
}

function frameTime(frame: Frame): number {
  const t = Date.parse(frame.time_utc);
  return Number.isNaN(t) ? 0 : t;
}

export function SpeculaApp({ variant = "overview" }: { variant?: AppVariant }) {
  const data = useSpeculaData();
  const patches = useMemo(() => data.manifest?.patches ?? [], [data.manifest]);
  const { open: introOpen, openIntro, closeIntro } = useIntroOverlay();

  const chosenPatchId = useSession((s) => s.patchId);
  const burstIndex = useSession((s) => s.burstIndex);
  const frameIndex = useSession((s) => s.frameIndex);
  const selectedId = useSession((s) => s.selectedId);
  const imageMode = useSession((s) => s.imageMode);
  const showFaintMarkers = useSession((s) => s.showFaintMarkers);
  const setPatchId = useSession((s) => s.setPatchId);
  const setBurstIndex = useSession((s) => s.setBurstIndex);
  const setFrameIndex = useSession((s) => s.setFrameIndex);
  const setSelectedId = useSession((s) => s.setSelectedId);
  const setImageMode = useSession((s) => s.setImageMode);
  const setShowFaintMarkers = useSession((s) => s.setShowFaintMarkers);

  const patch = patches.find((p) => p.id === chosenPatchId) ?? patches[0] ?? null;
  const patchId = patch?.id ?? null;
  const { status: patchStatus, data: patchData } = usePatchData(patch);
  const timeline = patchData?.timeline ?? null;
  const patchLoading = patchStatus === "loading";

  // Warm a patch's timeline/markers on hover or focus so switching is instant.
  const prefetchPatch = useCallback(
    (id: string) => {
      const target = patches.find((p) => p.id === id);
      if (target) void loadPatchData(target);
    },
    [patches],
  );

  const catalogById = useMemo(
    () =>
      new Map<string, CatalogObject>(
        (data.cosmos?.objects_3d ?? []).map((o) => [o.object_id, o]),
      ),
    [data.cosmos],
  );
  const framesById = useMemo(
    () =>
      timeline ? new Map(timeline.frames.map((f) => [f.frame_id, f])) : EMPTY_FRAMES,
    [timeline],
  );

  const bursts = useMemo(
    () => (patchId ? buildBursts(patchId, data.pointings ?? [], timeline) : []),
    [patchId, data.pointings, timeline],
  );
  const safeBurst = Math.min(burstIndex, Math.max(bursts.length - 1, 0));
  const burst = bursts[safeBurst];
  const burstFrames = useMemo(() => {
    const frames = (burst?.frame_ids ?? [])
      .map((id) => framesById.get(id))
      .filter((f): f is Frame => f !== undefined);
    return [...frames].sort(
      (a, b) => frameTime(a) - frameTime(b) || a.frame_id.localeCompare(b.frame_id),
    );
  }, [burst, framesById]);
  const safeFrame = Math.min(frameIndex, Math.max(burstFrames.length - 1, 0));
  const frame =
    imageMode === "full" ? burstFrames[safeFrame] : (burstFrames[0] ?? undefined);
  const newBursts = useMemo(
    () =>
      newBurstIds(
        bursts,
        newFrameIds(timeline?.frames, data.updates ?? [], data.manifest),
      ),
    [bursts, timeline, data.updates, data.manifest],
  );

  const patchDetections = useMemo(() => {
    const tracks = (data.tracks ?? []).filter(
      (t) => t.patch === patchId && !isMockTrackId(t.track_id),
    );
    return unrollTracks(tracks, catalogById, framesById);
  }, [data.tracks, patchId, catalogById, framesById]);

  const pipeline = useMemo(
    () => pipelineCopy(data.scoring ?? null, factsFromTracks(data.tracks ?? [])),
    [data.scoring, data.tracks],
  );

  const overlayMarkers = useMemo(() => {
    const ids =
      imageMode === "full" ? (frame ? [frame.frame_id] : []) : (burst?.frame_ids ?? []);
    const visible = visibleMarkers(
      markersForFrames(patchData?.markers ?? [], ids),
      showFaintMarkers,
    );
    return imageMode === "composite" ? collapseMarkers(visible) : visible;
  }, [imageMode, frame, burst, patchData, showFaintMarkers]);

  const visibleDetections = useMemo(
    () =>
      imageMode === "full"
        ? detectionsAtFrame(patchDetections, frame?.frame_id)
        : detectionsAtBurst(patchDetections, burst),
    [patchDetections, imageMode, frame, burst],
  );

  const overlayDetections = useMemo(() => {
    return imageMode === "full"
      ? detectionsAtFrame(patchDetections, frame?.frame_id)
      : detectionsAtBurst(patchDetections, burst);
  }, [patchDetections, burst, imageMode, frame]);

  const activeFrameIds = useMemo(
    () =>
      imageMode === "full"
        ? frame?.frame_id
          ? [frame.frame_id]
          : []
        : (burst?.frame_ids ?? []),
    [imageMode, frame, burst],
  );

  const predictedMarkers = useMemo(() => {
    const inData = (data.atlasFocusMarkers ?? []).filter((marker) => marker.in_data);
    const current = markersForFrames(atlasMarkersAsMarkers(inData), activeFrameIds);
    return imageMode === "composite" ? collapseMarkers(current) : current;
  }, [data.atlasFocusMarkers, activeFrameIds, imageMode]);

  const burstCandidates = useMemo(
    () =>
      imageMode === "full"
        ? []
        : detectionsAtBurst(
            patchDetections.filter((d) => d.type === "candidate"),
            burst,
          ),
    [patchDetections, burst, imageMode],
  );

  const openTrack = useCallback(
    (track: Track) => {
      const burstId = track.points[0]
        ? burstIdFromFrameId(track.points[0].frame_id)
        : null;
      const index =
        burstId === null
          ? -1
          : burstIndexForPatch(track.patch, burstId, data.pointings ?? []);
      setPatchId(track.patch);
      if (index >= 0) setBurstIndex(index);
      setSelectedId(
        track.status === "known" && track.object_id
          ? objectKey(track.object_id)
          : trackKey(track.track_id),
      );
    },
    [data.pointings, setBurstIndex, setPatchId, setSelectedId],
  );

  const selectionMarkers = useMemo(() => {
    const ids = burst?.frame_ids ?? (frame ? [frame.frame_id] : []);
    const all = markersForFrames(patchData?.markers ?? [], ids);
    if (!frame) return all;
    return [
      ...all.filter((m) => m.frame_id === frame.frame_id),
      ...all.filter((m) => m.frame_id !== frame.frame_id),
    ];
  }, [burst, frame, patchData]);

  const selection = useMemo(
    () =>
      resolveSelection(
        selectedId,
        [...visibleDetections, ...patchDetections],
        catalogById,
        selectionMarkers,
      ),
    [selectedId, visibleDetections, patchDetections, catalogById, selectionMarkers],
  );

  const fieldSize =
    timeline?.patch.size_px ??
    inferFieldSize(
      patchDetections,
      overlayMarkers.map((m) => m.x),
      overlayMarkers.map((m) => m.y),
    ) ??
    351;
  const imageSources = useMemo(
    () => (patch ? burstImages(DATA_BASE_URL, patch, burst, frame, imageMode) : []),
    [patch, burst, frame, imageMode],
  );
  const imageUrls = useMemo(() => imageSources.map((image) => image.url), [imageSources]);
  const imageKey = imageUrls.join("|");
  const [imageStatus, setImageStatus] = useState<ViewportImageStatus | null>(null);
  const loadedImage =
    imageStatus?.key === imageKey && imageStatus.ready
      ? imageSources[imageStatus.index]
      : null;
  const imageFailed = imageStatus?.key === imageKey && imageStatus.allFailed;
  const date = useMemo(() => {
    const iso = frame?.time_utc ?? burst?.time_utc;
    const d = iso ? new Date(iso) : null;
    return d && !Number.isNaN(d.getTime()) ? d : undefined;
  }, [frame, burst]);

  const timelineBurst = useMemo(
    () => timeline?.bursts.find((b) => b.burst_id === burst?.burst_id) ?? null,
    [timeline, burst],
  );
  const compositeDetectors =
    timelineBurst?.detectors ?? burstFrames.map((item) => item.detector);
  const compositeShown = loadedImage?.kind ?? (imageFailed ? "missing" : "pending");
  const displayedImageLine =
    imageMode !== "composite"
      ? undefined
      : compositeShown === "full"
        ? singlePhotoImageLabel(frame?.detector)
        : compositeShown === "missing"
          ? "composite missing"
          : compositeShown === "pending"
            ? null
            : undefined;
  const captionLines = useMemo(() => {
    const wavelengthFrames =
      imageMode !== "composite" || compositeShown === "composite"
        ? undefined
        : compositeShown === "full" && frame
          ? [frame]
          : [];
    return buildFrameCaption({
      mode: imageMode,
      patch: timeline?.patch,
      frame: frame ?? null,
      burst: timelineBurst,
      framesInBurst: burstFrames,
      pointing: burst?.pointing,
      imageLine: displayedImageLine,
      wavelengthFrames,
    });
  }, [
    imageMode,
    timeline,
    frame,
    timelineBurst,
    burstFrames,
    burst,
    displayedImageLine,
    compositeShown,
  ]);
  const photoFocusIds = useMemo(() => {
    if (patchStatus !== "ready") return null;
    const frameIds = focusFrameIds(
      imageMode,
      burst?.burst_id,
      timeline?.frames ?? [],
      frame?.frame_id,
      burst?.frame_ids ?? [],
    );
    const ids = new Set(
      objectIdsForFrames(
        patchData?.markers ?? [],
        frameIds,
        (data.atlasFocusMarkers ?? emptyAtlasFocusMarkers).filter(
          (marker) => marker.in_data,
        ),
      ),
    );
    const frames = new Set(frameIds);
    for (const detection of patchDetections) {
      if (
        detection.type === "known" &&
        detection.object_id &&
        frames.has(detection.frame_id)
      ) {
        ids.add(detection.object_id);
      }
    }
    return [...ids];
  }, [
    patchStatus,
    imageMode,
    burst,
    timeline,
    frame,
    patchData,
    data.atlasFocusMarkers,
    patchDetections,
  ]);

  const imageLabel =
    imageMode === "composite"
      ? compositeShown === "composite"
        ? compositeImageLabel(compositeDetectors)
        : compositeShown === "full"
          ? singlePhotoImageLabel(frame?.detector)
          : null
      : loadedImage?.kind === "composite"
        ? compositeImageLabel(compositeDetectors)
        : imageFailed
          ? null
          : fullFrameImageLabel(frame?.detector, frame?.wavelength_um);
  const detectionCount = useMemo(
    () =>
      countDetectionsInView(
        (data.tracks ?? []).filter((track) => track.patch === patchId),
        imageMode === "full"
          ? { mode: "full", frameId: frame?.frame_id }
          : { mode: "composite", frameIds: burst?.frame_ids ?? [] },
      ),
    [data.tracks, patchId, imageMode, frame, burst],
  );

  const show2d = variant !== "cosmos";
  const show3d = variant !== "viewer";
  const gridClass =
    variant === "overview"
      ? "grid flex-1 gap-4 xl:grid-cols-[minmax(0,560px)_minmax(0,1fr)_300px]"
      : "grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(0,1fr)_300px]";

  return (
    <main className="bg-void text-ink flex min-h-dvh flex-col gap-4 p-4 sm:p-6">
      <Header
        patches={patches}
        activePatchId={patchId}
        onPatchChange={setPatchId}
        packVersion={data.manifest?.version}
        onOpenAbout={openIntro}
        onPatchPrefetch={prefetchPatch}
        patchLoading={patchLoading}
        status={
          data.status === "loading"
            ? "Loading data…"
            : detectionsInViewLabel(detectionCount)
        }
      />

      {data.status === "ready" && data.sources.detections === "remote" && (
        <PipelineStatus
          copy={pipeline}
          tracks={data.tracks ?? []}
          catalogById={catalogById}
          patches={patches}
          selectedId={selectedId}
          onOpenTrack={openTrack}
          detail={variant === "overview"}
        />
      )}

      {data.usingFallback && (
        <div className="rounded border border-amber-700/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-200">
          Some data files could not be loaded, so placeholder data is shown:{" "}
          {Object.values(data.errors).join(" · ")}
          <button type="button" onClick={data.reload} className="ml-2 underline">
            Retry
          </button>
        </div>
      )}

      <div className={gridClass}>
        {show2d && (
          <div className="flex min-w-0 flex-col gap-2">
            <div className="text-muted flex flex-wrap items-center justify-end gap-2 text-[11px]">
              <div className="flex items-center gap-1.5">
                <input
                  id="show-faint-markers"
                  type="checkbox"
                  checked={showFaintMarkers}
                  onChange={(event) => setShowFaintMarkers(event.target.checked)}
                  className="accent-neutral-300"
                />
                <label htmlFor="show-faint-markers" className="cursor-pointer">
                  Show faint (predicted)
                </label>
              </div>
              <div className="flex shrink-0 gap-1" role="group" aria-label="Image type">
                {(["composite", "full"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setImageMode(m)}
                    aria-pressed={imageMode === m}
                    className={`rounded px-2 py-0.5 ${imageMode === m ? "bg-hover text-ink ring-line ring-1" : "text-muted hover:text-ink"}`}
                  >
                    {m === "composite" ? "Composite" : "Full frame"}
                  </button>
                ))}
              </div>
            </div>
            <figure className="flex flex-col gap-2">
              <Viewport2D
                imageUrls={imageUrls}
                width={fieldSize}
                height={fieldSize}
                detections={overlayDetections}
                activeFrameIds={activeFrameIds}
                markers={overlayMarkers}
                predictedMarkers={predictedMarkers}
                selectedId={selectedId}
                onSelect={setSelectedId}
                imageLabel={imageLabel}
                missingLabel={
                  imageMode === "composite"
                    ? "composite missing"
                    : "Patch image not found"
                }
                onImageStatus={setImageStatus}
                loading={patchLoading}
              />
              {captionLines.length > 0 && (
                <figcaption>
                  <FrameCaption lines={captionLines} />
                </figcaption>
              )}
            </figure>
            {patchStatus === "ready" && !timeline && (
              <p className="text-muted text-[11px]">
                No timeline.json for this patch: bursts come from pointings.json, images
                and wavelengths are unavailable, and the overlay is scaled to the
                detections.
              </p>
            )}
          </div>
        )}
        {show3d && (
          <div
            className={
              variant === "overview"
                ? "h-[520px] min-w-0 xl:h-auto xl:min-h-[520px]"
                : "min-h-[520px] min-w-0"
            }
          >
            <Viewport3D
              className="h-full"
              cosmos={data.cosmos}
              planetOrbits={data.planetOrbits}
              patches={patches}
              pointings={data.pointings}
              activePatchId={patchId}
              activePointing={burst?.pointing}
              detections={burstCandidates}
              date={date}
              selectedId={selectedId}
              onSelect={setSelectedId}
              photoFocusIds={photoFocusIds}
            />
          </div>
        )}
        <SidePanel selection={selection} onClear={() => setSelectedId(null)} />
      </div>

      <TimelineScrubber
        bursts={bursts}
        index={safeBurst}
        onIndexChange={setBurstIndex}
        newBurstIds={newBursts}
        newBadgeDays={data.manifest?.new_badge_days ?? DEFAULT_NEW_BADGE_DAYS}
        imageMode={imageMode}
        frameIndex={safeFrame}
        frameCount={burstFrames.length}
        onFrameIndexChange={setFrameIndex}
      />

      <IntroOverlay
        open={introOpen}
        onClose={closeIntro}
        manifest={data.manifest}
        pipeline={data.status === "ready" ? pipeline : null}
      />
    </main>
  );
}
