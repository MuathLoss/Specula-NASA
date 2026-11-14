"use client";

import { create } from "zustand";
import type { ScaleMode } from "@/lib/astro";
import type { FocusMode } from "@/lib/focus";
import type { SelectionKey } from "@/lib/selection";
import type { ImageMode } from "@/lib/timeline";

export type SceneLayers = {
  planets: boolean;
  orbits: boolean;
  objects: boolean;
  stars: boolean;
  milkyWay: boolean;
  pointings: boolean;
  labels: boolean;
};

const defaultLayers: SceneLayers = {
  planets: true,
  orbits: true,
  objects: true,
  stars: true,
  milkyWay: true,
  pointings: true,
  labels: true,
};

type SessionState = {
  patchId: string | null;
  burstIndex: number;
  frameIndex: number;
  selectedId: SelectionKey | null;
  imageMode: ImageMode;
  scale: ScaleMode;
  layers: SceneLayers;
  showFaintMarkers: boolean;
  focus: FocusMode;
  setPatchId: (patchId: string) => void;
  setBurstIndex: (index: number) => void;
  setFrameIndex: (index: number) => void;
  setSelectedId: (id: SelectionKey | null) => void;
  setImageMode: (mode: ImageMode) => void;
  setScale: (scale: ScaleMode) => void;
  toggleScale: () => void;
  setLayer: (key: keyof SceneLayers, value: boolean) => void;
  setShowFaintMarkers: (value: boolean) => void;
  setFocus: (focus: FocusMode) => void;
};

export const useSession = create<SessionState>((set) => ({
  patchId: null,
  burstIndex: 0,
  frameIndex: 0,
  selectedId: null,
  imageMode: "composite",
  scale: "compressed",
  layers: defaultLayers,
  showFaintMarkers: false,
  focus: "photo",
  setPatchId: (patchId) =>
    set({ patchId, burstIndex: 0, frameIndex: 0, selectedId: null }),
  setBurstIndex: (burstIndex) => set({ burstIndex, frameIndex: 0 }),
  setFrameIndex: (frameIndex) => set({ frameIndex }),
  setSelectedId: (selectedId) => set({ selectedId }),
  setImageMode: (imageMode) => set({ imageMode }),
  setScale: (scale) => set({ scale }),
  toggleScale: () =>
    set((state) => ({ scale: state.scale === "compressed" ? "linear" : "compressed" })),
  setLayer: (key, value) =>
    set((state) => ({ layers: { ...state.layers, [key]: value } })),
  setShowFaintMarkers: (showFaintMarkers) => set({ showFaintMarkers }),
  setFocus: (focus) => set({ focus }),
}));
