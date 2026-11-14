"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { Burst } from "@/types/specula";
import { Kbd, Tooltip } from "@/components/Tooltip";
import {
  hasModifier,
  isTypingTarget,
  modalOpen,
  spaceActivatesTarget,
} from "@/lib/keyboard";
import type { ImageMode } from "@/lib/timeline";

const FRAMES_PER_SECOND = 6;
const NEW_COLOR = "#34D399";

interface TimelineScrubberProps {
  bursts: Burst[];
  index: number;
  onIndexChange: (index: number) => void;
  /** burst_ids that are NEW under the manifest rule (see lib/timeline.ts newFrameIds). */
  newBurstIds: Set<string>;
  /** manifest new_badge_days, for the badge tooltip. */
  newBadgeDays: number;
  imageMode?: ImageMode;
  frameIndex?: number;
  frameCount?: number;
  onFrameIndexChange?: (index: number) => void;
}

export function TimelineScrubber({
  bursts,
  index,
  onIndexChange,
  newBurstIds,
  newBadgeDays,
  imageMode = "composite",
  frameIndex = 0,
  frameCount = 0,
  onFrameIndexChange,
}: TimelineScrubberProps) {
  const [playing, setPlaying] = useState(false);
  const count = bursts.length;
  const last = Math.max(count - 1, 0);
  const current = bursts[index];
  const currentIsNew = !!current && newBurstIds.has(current.burst_id);
  const photos = imageMode === "full" && frameCount > 0 && !!onFrameIndexChange;
  const safeFrame = photos ? Math.min(Math.max(frameIndex, 0), frameCount - 1) : 0;
  const lastFrame = Math.max(frameCount - 1, 0);

  const newMarks = useMemo(
    () => bursts.flatMap((b, i) => (newBurstIds.has(b.burst_id) ? [i] : [])),
    [bursts, newBurstIds],
  );

  useEffect(() => {
    if (!playing) return;
    if (photos) {
      const atLastPhoto = safeFrame >= lastFrame;
      const atLastBurst = index >= last;
      if (atLastPhoto && atLastBurst) return;
      const t = setTimeout(() => {
        if (!atLastPhoto) {
          onFrameIndexChange?.(safeFrame + 1);
        } else {
          onIndexChange(index + 1);
        }
        if (atLastPhoto && index + 1 >= last) setPlaying(false);
      }, 1000 / FRAMES_PER_SECOND);
      return () => clearTimeout(t);
    }
    if (index >= last) return;
    const t = setTimeout(() => {
      onIndexChange(index + 1);
      if (index + 1 >= last) setPlaying(false);
    }, 1000 / FRAMES_PER_SECOND);
    return () => clearTimeout(t);
  }, [
    playing,
    photos,
    safeFrame,
    lastFrame,
    index,
    last,
    onIndexChange,
    onFrameIndexChange,
  ]);

  const togglePlay = useCallback(() => {
    if (!playing) {
      if (photos) {
        if (index >= last && safeFrame >= lastFrame) {
          onIndexChange(0);
          onFrameIndexChange?.(0);
        }
      } else if (index >= last) {
        onIndexChange(0);
      }
    }
    setPlaying((p) => !p);
  }, [
    playing,
    photos,
    index,
    last,
    safeFrame,
    lastFrame,
    onIndexChange,
    onFrameIndexChange,
  ]);

  const step = useCallback(
    (delta: -1 | 1) => {
      setPlaying(false);
      onIndexChange(Math.min(Math.max(index + delta, 0), last));
    },
    [index, last, onIndexChange],
  );

  // Global shortcuts: Space = play/pause, ←/→ = previous/next burst.
  useEffect(() => {
    if (count === 0) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || hasModifier(e) || isTypingTarget(e.target) || modalOpen())
        return;
      if (e.key === " ") {
        if (spaceActivatesTarget(e.target)) return; // Space clicks the focused control instead
        e.preventDefault();
        if (!e.repeat) togglePlay();
      } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
        // A focused slider already moves with the arrows.
        if (e.target instanceof HTMLInputElement && e.target.type === "range") return;
        e.preventDefault();
        step(e.key === "ArrowLeft" ? -1 : 1);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [count, togglePlay, step]);

  if (count === 0) {
    return (
      <div className="border-line text-muted rounded-lg border p-3 text-sm">
        No bursts in history.
      </div>
    );
  }

  const timestamp = current?.time_utc ? new Date(current.time_utc) : null;

  return (
    <div className="border-line bg-panel flex flex-col gap-3 rounded-lg border px-4 py-3 sm:flex-row sm:items-center sm:gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <Tooltip
            content={
              <>
                Previous burst <Kbd>←</Kbd>
              </>
            }
            align="start"
          >
            <button
              type="button"
              onClick={() => step(-1)}
              disabled={index === 0}
              aria-label="Previous burst"
              className="text-ink hover:bg-hover rounded px-2 py-1 transition-colors disabled:cursor-not-allowed disabled:opacity-30"
            >
              ‹
            </button>
          </Tooltip>
          <Tooltip
            align="start"
            content={
              <>
                {playing
                  ? "Pause playback"
                  : `Play through the bursts (${photos ? "every photo" : "one burst per step"})`}{" "}
                <Kbd>Space</Kbd>
              </>
            }
          >
            <button
              type="button"
              onClick={togglePlay}
              aria-label={playing ? "Pause" : "Play"}
              aria-keyshortcuts="Space"
              className="bg-raised text-ink ring-line hover:bg-hover w-16 rounded px-3 py-1 text-sm ring-1 transition-colors"
            >
              {playing ? "Pause" : "Play"}
            </button>
          </Tooltip>
          <Tooltip
            content={
              <>
                Next burst <Kbd>→</Kbd>
              </>
            }
          >
            <button
              type="button"
              onClick={() => step(1)}
              disabled={index >= last}
              aria-label="Next burst"
              className="text-ink hover:bg-hover rounded px-2 py-1 transition-colors disabled:cursor-not-allowed disabled:opacity-30"
            >
              ›
            </button>
          </Tooltip>
        </div>
        {photos && (
          <div className="flex items-center gap-1">
            <Tooltip content="Previous photo in this burst (other detector)">
              <button
                type="button"
                onClick={() => onFrameIndexChange(Math.max(safeFrame - 1, 0))}
                disabled={safeFrame === 0}
                aria-label="Previous photo"
                className="text-ink hover:bg-hover rounded px-2 py-1 transition-colors disabled:cursor-not-allowed disabled:opacity-30"
              >
                ‹
              </button>
            </Tooltip>
            <span className="text-muted font-mono text-xs">
              photo {safeFrame + 1} / {frameCount} of this burst
            </span>
            <Tooltip content="Next photo in this burst (other detector)">
              <button
                type="button"
                onClick={() => onFrameIndexChange(Math.min(safeFrame + 1, lastFrame))}
                disabled={safeFrame >= lastFrame}
                aria-label="Next photo"
                className="text-ink hover:bg-hover rounded px-2 py-1 transition-colors disabled:cursor-not-allowed disabled:opacity-30"
              >
                ›
              </button>
            </Tooltip>
          </div>
        )}
      </div>

      <div className="relative min-w-0 flex-1">
        <input
          type="range"
          min={0}
          max={last}
          step={1}
          value={index}
          onChange={(e) => {
            setPlaying(false);
            onIndexChange(Number(e.target.value));
          }}
          aria-label="Burst"
          title="Drag to scrub through the bursts"
          aria-valuetext={`Burst ${index + 1} of ${count}${currentIsNew ? ", new" : ""}`}
          className="w-full min-w-0 cursor-pointer accent-neutral-300"
        />
        <div className="pointer-events-none absolute inset-x-0 -bottom-1 h-1" aria-hidden>
          {newMarks.map((i) => (
            <span
              key={i}
              className="absolute h-1 w-px"
              style={{ left: `${last ? (i / last) * 100 : 0}%`, background: NEW_COLOR }}
            />
          ))}
        </div>
      </div>

      <div className="text-muted flex min-w-0 shrink-0 items-center justify-end gap-2 font-mono text-xs sm:min-w-[11rem]">
        {currentIsNew && (
          <span
            className="text-void rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wider"
            style={{ background: NEW_COLOR }}
            title={`Ingested in a non-baseline update within ${newBadgeDays} days of the latest ingest`}
          >
            NEW
          </span>
        )}
        <span>
          {index + 1} / {count}
        </span>
        {timestamp && !Number.isNaN(timestamp.getTime()) && (
          <span className="text-muted">
            {timestamp.toISOString().slice(0, 16).replace("T", " ")}
          </span>
        )}
      </div>
    </div>
  );
}
