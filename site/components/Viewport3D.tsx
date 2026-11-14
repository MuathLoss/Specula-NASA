// components/Viewport3D.tsx
// Heliocentric ecliptic J2000 view: Sun, 8 planets, all catalog objects from
// orbits.json (primary ones with orbit lines), stars from cosmos.json, SPHEREx
// pointing cones from pointings.json, and approximate distance-from-Earth ranges for Candidates.
// Import this through next/dynamic with { ssr: false } (WebGL is client-only).

import { useEffect, useMemo, useState, type ComponentProps } from "react";
import { Canvas, useThree, type ThreeEvent } from "@react-three/fiber";
import { Line, OrbitControls, useCursor } from "@react-three/drei";
import * as THREE from "three";
import type {
  CatalogObject,
  CosmosData,
  CosmosLabel,
  CosmosStar,
  Detection,
  OrbitEntry,
  Patch,
  Pointing,
} from "@/types/specula";
import {
  DEG,
  PLANETS,
  finitePoints,
  hasCompleteElements,
  isFiniteVec,
  lineOfSightSegment,
  type ScaleMode,
  type Vec3,
  julianDate,
  julianDateTdb,
  orbitPath,
  orbitPosition,
  planetOrbit,
  planetPosition,
  radecToEcliptic,
  rayPoints,
  tiltedDirection,
  toScene,
} from "@/lib/astro";
import { orbitPathAround } from "@/lib/orbit";
import { objectKey, selectionKey, type SelectionKey } from "@/lib/selection";
import { burstIdFromFrameId, nearestPointing } from "@/lib/timeline";
import { FocusControl } from "@/components/FocusControl";
import { LayerPanel } from "@/components/LayerPanel";
import { Tooltip } from "@/components/Tooltip";
import { bvToRgb } from "@/lib/star-color";
import { galacticLatitudePoints, skyPathPoints, toStarSphere } from "@/lib/sky-paths";
import { useSession, type SceneLayers } from "@/store/session";

export const COLORS = {
  known: "#00F0FF",
  candidate: "#FF8C00",
  cone: "#8B7FD6",
  coneActive: "#C4B5FD",
  sun: "#FFD27A",
  planetOrbit: "#9a9a9a",
  catalogOrbit: "#2EC8D6",
  comet: "#D7F08A",
  cometTail: "#E8D4A0",
  cometNucleus: "#F3F0D8",
} as const;

const PLANET_STYLE: Record<string, { color: string; radius: number }> = {
  mercury: { color: "#B1ADA7", radius: 0.25 },
  venus: { color: "#E8CDA0", radius: 0.35 },
  earth: { color: "#4F8CFF", radius: 0.38 },
  mars: { color: "#D9643A", radius: 0.3 },
  jupiter: { color: "#D8B38A", radius: 0.8 },
  saturn: { color: "#E3CF9A", radius: 0.7 },
  uranus: { color: "#9BD8E0", radius: 0.5 },
  neptune: { color: "#4A6BFF", radius: 0.5 },
};

/** How far the pointing cones extend from Earth (AU). */
const CONE_LENGTH_AU = 5;
/** Real fields are ~1°; widen cones to at least this half-angle so they're visible. */
const MIN_CONE_HALF_ANGLE_DEG = 1.5;
const EMPTY_FOCUS_IDS: readonly string[] = [];
const RAYCASTER_PARAMS = {
  Mesh: {},
  Line: { threshold: 1 },
  LOD: {},
  Points: { threshold: 0.35 },
  Sprite: {},
};

export interface Viewport3DProps {
  cosmos?: CosmosData | null;
  /** orbits.json planets by id ("earth", …); replace the built-in JPL elements. */
  planetOrbits?: Record<string, OrbitEntry>;
  patches?: Patch[];
  pointings?: Pointing[];
  activePatchId?: string | null;
  /** Pointing of the current burst: exact cone and Earth position. */
  activePointing?: Pointing;
  /** Detections at the current burst; candidates with distance ranges are drawn. */
  detections?: Detection[];
  /** Epoch for positions (UTC). Defaults to the time the view mounted. */
  date?: Date;
  selectedId?: SelectionKey | null;
  onSelect?: (id: SelectionKey | null) => void;
  /** Known-object ids in the current photo or burst. Null while that patch is loading. */
  photoFocusIds?: readonly string[] | null;
  className?: string;
}

export default function Viewport3D({
  cosmos,
  planetOrbits,
  patches = [],
  pointings = [],
  activePatchId,
  activePointing,
  detections = [],
  date: dateProp,
  selectedId = null,
  onSelect,
  photoFocusIds = null,
  className = "",
}: Viewport3DProps) {
  const scale = useSession((s) => s.scale);
  const toggleScale = useSession((s) => s.toggleScale);
  const focus = useSession((s) => s.focus);
  const setFocus = useSession((s) => s.setFocus);
  const layers = useSession((s) => s.layers);
  const [mountedAt] = useState(() => new Date()); // client-only component (ssr: false)
  const date = dateProp ?? mountedAt;
  const focusCounts = useMemo(() => {
    const objects = cosmos?.objects_3d ?? [];
    let big = 0;
    for (const object of objects) if (object.show_in_3d) big += 1;
    return {
      photo: photoFocusIds?.length ?? 0,
      big,
      all: objects.length,
    };
  }, [cosmos, photoFocusIds]);
  const noKnownAsteroids =
    focus === "photo" && photoFocusIds !== null && photoFocusIds.length === 0;

  return (
    <div className={`@container flex h-full min-h-0 flex-col gap-2 ${className}`}>
      <div className="flex min-w-0 shrink-0 items-center gap-1 text-[11px]">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1">
          <Tooltip
            className="shrink-0"
            side="bottom"
            align="start"
            content={
              scale === "compressed"
                ? "Log radial scale: inner planets and Neptune fit in one view; directions from the Sun are kept. Click for true linear distances."
                : "True linear distances in AU; the inner solar system gets small. Click for the compressed (log) view."
            }
          >
            <button
              type="button"
              onClick={toggleScale}
              aria-pressed={scale === "linear"}
              aria-label={
                scale === "compressed" ? "Scale: Compressed (log)" : "Scale: Linear"
              }
              className="border-line bg-raised text-ink hover:bg-hover shrink-0 rounded border px-2 py-1 whitespace-nowrap transition-colors"
            >
              <span className="hidden @[26rem]:inline">
                Scale: {scale === "compressed" ? "Compressed (log)" : "Linear"}
              </span>
              <span className="@[26rem]:hidden">
                {scale === "compressed" ? "Log" : "Linear"}
              </span>
            </button>
          </Tooltip>
          <div className="shrink-0">
            <FocusControl mode={focus} counts={focusCounts} onChange={setFocus} />
          </div>
        </div>
        <details className="relative shrink-0">
          <summary className="border-line bg-raised text-muted hover:bg-hover hover:text-ink cursor-pointer list-none rounded border px-2 py-1 whitespace-nowrap [&::-webkit-details-marker]:hidden">
            Layers
          </summary>
          <div className="absolute top-full right-0 z-20 mt-1">
            <LayerPanel idPrefix="layer-bar" />
          </div>
        </details>
      </div>

      <div className="border-line bg-void relative min-h-[420px] flex-1 overflow-hidden rounded-lg border">
        <Canvas
          className="h-full w-full"
          camera={{ position: [0, 55, 75], fov: 45, near: 0.05, far: 4000 }}
          raycaster={{ params: RAYCASTER_PARAMS }}
          onPointerMissed={() => onSelect?.(null)}
          dpr={[1, 2]}
        >
          <color attach="background" args={["#000000"]} />
          <Scene
            cosmos={cosmos}
            planetOrbits={planetOrbits}
            patches={patches}
            pointings={pointings}
            activePatchId={activePatchId}
            activePointing={activePointing}
            detections={detections}
            jdUtc={julianDate(date)}
            jdTdb={julianDateTdb(date)}
            selectedId={selectedId}
            onSelect={onSelect}
            scale={scale}
            layers={layers}
            photoFocusIds={photoFocusIds ?? EMPTY_FOCUS_IDS}
          />
          <OrbitControls makeDefault enableDamping maxDistance={1500} minDistance={2} />
        </Canvas>

        <div className="text-muted pointer-events-none absolute top-2 right-2 left-2 text-[11px]">
          <div className="truncate font-mono text-[10px] whitespace-nowrap sm:text-[11px]">
            Heliocentric ecliptic J2000 ·{" "}
            {date.toISOString().slice(0, 16).replace("T", " ")} UTC
          </div>
          <div className="mt-1 inline-block max-w-full rounded bg-[rgba(0,0,0,0.6)] px-2 py-1">
            <Legend />
          </div>
          {noKnownAsteroids && (
            <p role="status" className="text-ink mt-1 text-[11px]">
              No known asteroids in this photo
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function Legend() {
  const item = (color: string, label: string, shape: "dot" | "diamond" | "line") => (
    <div className="flex items-center gap-2">
      <span
        className={shape === "line" ? "h-px w-3" : "h-2 w-2"}
        style={{
          background: color,
          borderRadius: shape === "dot" ? "9999px" : 0,
          transform: shape === "diamond" ? "rotate(45deg)" : undefined,
          boxShadow: shape === "diamond" ? `0 0 6px ${color}` : undefined,
        }}
      />
      {label}
    </div>
  );
  return (
    <div className="space-y-0.5">
      {item(COLORS.known, "Known object", "dot")}
      {item(COLORS.comet, "3I/ATLAS (comet)", "dot")}
      {item(COLORS.candidate, "Candidate (approximate distance from Earth)", "diamond")}
      {item(COLORS.planetOrbit, "Orbit", "line")}
      {item(COLORS.cone, "SPHEREx pointing", "line")}
    </div>
  );
}

type ScenePoint = [number, number, number];

/**
 * drei <Line> that drops non-finite points first and renders nothing with
 * fewer than two, so NaN never reaches BufferGeometry (computeBoundingSphere).
 */
function SafeLine({
  points,
  ...props
}: Omit<ComponentProps<typeof Line>, "points"> & { points: ScenePoint[] }) {
  const clean = useMemo(() => finitePoints(points), [points]);
  if (clean.length < 2) return null;
  return <Line points={clean} {...props} />;
}

// ---------------------------------------------------------------------------

interface SceneProps {
  cosmos?: CosmosData | null;
  planetOrbits?: Record<string, OrbitEntry>;
  patches: Patch[];
  pointings: Pointing[];
  activePatchId?: string | null;
  activePointing?: Pointing;
  detections: Detection[];
  /** UTC JD (pointings.json) and TDB JD (orbits.json). */
  jdUtc: number;
  jdTdb: number;
  selectedId: SelectionKey | null;
  onSelect?: (id: SelectionKey | null) => void;
  scale: ScaleMode;
  layers: SceneLayers;
  photoFocusIds: readonly string[];
}

function Scene({
  cosmos,
  planetOrbits,
  patches,
  pointings,
  activePatchId,
  activePointing,
  detections,
  jdUtc,
  jdTdb,
  selectedId,
  onSelect,
  scale,
  layers,
  photoFocusIds,
}: SceneProps) {
  const planets = useMemo(
    () =>
      PLANETS.map((p) => {
        // Prefer the pipeline's own elements (orbits.json) so Earth matches the data's geometry.
        const el = planetOrbits?.[p.id];
        const pos = el ? orbitPosition(el, jdTdb) : null;
        const path = pos && el ? orbitPath(el) : [];
        const usePipeline = pos !== null && path.length > 1;
        return {
          ...p,
          ...PLANET_STYLE[p.id],
          pos: usePipeline ? pos : planetPosition(p, jdTdb),
          orbit: usePipeline ? path : planetOrbit(p, jdTdb),
        };
      }),
    [jdTdb, planetOrbits],
  );
  const select = (id: SelectionKey) => (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    onSelect?.(id);
  };

  const focus = useSession((s) => s.focus);

  const { focused, outside } = useMemo(() => {
    const all = (cosmos?.objects_3d ?? []).filter((object) => object.orbit);
    const photoIds = new Set(photoFocusIds);
    const focusedObjects: CatalogObject[] = [];
    const outsideObjects: CatalogObject[] = [];
    for (const object of all) {
      const inFocus =
        focus === "all" ||
        (focus === "big" && object.show_in_3d) ||
        (focus === "photo" && photoIds.has(object.object_id));
      if (inFocus || objectKey(object.object_id) === selectedId) {
        focusedObjects.push(object);
      } else {
        outsideObjects.push(object);
      }
    }
    return { focused: focusedObjects, outside: outsideObjects };
  }, [cosmos, focus, photoFocusIds, selectedId]);

  const earthByBurst = useMemo(() => {
    const map = new Map<string, Vec3>();
    for (const pointing of pointings) map.set(pointing.burst_id, pointing.earth_au);
    return map;
  }, [pointings]);

  const cones = useMemo(
    () =>
      patches
        .filter((p) => !p.is_placeholder)
        .flatMap((p) => {
          const pointing =
            p.id === activePatchId
              ? (activePointing ?? nearestPointing(pointings, p.id, jdUtc))
              : nearestPointing(pointings, p.id, jdUtc);
          return pointing ? [{ patch: p, pointing }] : [];
        }),
    [patches, pointings, activePatchId, activePointing, jdUtc],
  );

  const candidates = useMemo(
    () =>
      detections.filter(
        (d) =>
          d.type === "candidate" &&
          Number.isFinite(d.distance_min_au) &&
          Number.isFinite(d.distance_max_au),
      ),
    [detections],
  );

  return (
    <>
      <ambientLight intensity={0.15} />
      <pointLight position={[0, 0, 0]} intensity={2.5} decay={0} />

      {layers.stars && <StarField stars={cosmos?.stars ?? []} />}
      {layers.milkyWay && <SkyGuides cosmos={cosmos} />}
      {layers.labels && <SkyLabels labels={cosmos?.labels ?? []} />}

      {/* Sun */}
      <mesh>
        <sphereGeometry args={[0.9, 32, 32]} />
        <meshBasicMaterial color={COLORS.sun} />
      </mesh>

      {layers.planets &&
        planets.map((p) => {
          const id = `planet:${p.id}`;
          return (
            <Body
              key={p.id}
              position={toScene(p.pos, scale)}
              orbit={layers.orbits ? p.orbit.map((v) => toScene(v, scale)) : []}
              color={p.color}
              orbitColor={COLORS.planetOrbit}
              radius={p.radius}
              label={p.name}
              alwaysLabel={layers.labels}
              selected={selectedId === id}
              onClick={select(id)}
            />
          );
        })}

      {layers.objects && (
        <CatalogPoints
          objects={outside}
          jd={jdTdb}
          scale={scale}
          onSelect={(id) => onSelect?.(id)}
        />
      )}

      {layers.objects &&
        focused.map((o) => {
          const key = objectKey(o.object_id);
          return (
            <CatalogBody
              key={key}
              obj={o}
              jd={jdTdb}
              scale={scale}
              selected={selectedId === key}
              onClick={select(key)}
              showOrbit={layers.orbits}
              showLabel={layers.labels}
            />
          );
        })}

      {layers.pointings &&
        cones.map(({ patch, pointing }) => (
          <PointingCone
            key={patch.id}
            pointing={pointing}
            label={patch.name}
            scale={scale}
            active={patch.id === activePatchId}
            showLabel={layers.labels}
          />
        ))}

      {layers.objects &&
        candidates.map((d) => {
          const key = selectionKey(d);
          const burstId = burstIdFromFrameId(d.frame_id);
          const earth = burstId ? earthByBurst.get(burstId) : undefined;
          if (!earth) return null;
          return (
            <CandidateRange
              key={key}
              detection={d}
              earth={earth}
              scale={scale}
              selected={selectedId === key}
              onClick={select(key)}
            />
          );
        })}
    </>
  );
}

// ---------------------------------------------------------------------------

function useHover() {
  const [hovered, setHovered] = useState(false);
  useCursor(hovered);
  return {
    hovered,
    bind: {
      onPointerOver: (e: ThreeEvent<PointerEvent>) => {
        e.stopPropagation();
        setHovered(true);
      },
      onPointerOut: () => setHovered(false),
    },
  };
}

// ---------------------------------------------------------------------------
// Labels: drawn to a canvas texture on a THREE.Sprite. Unlike drei <Html>
// (a separate React DOM root that is unmounted synchronously during R3F
// updates), these are ordinary scene objects and mount/unmount freely.

interface LabelLine {
  text: string;
  color?: string;
  bold?: boolean;
}

const LABEL_FONT = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';
const LABEL_FONT_PX = 10;
const LABEL_LINE_PX = 14;
const LABEL_PAD_X = 6;
const LABEL_PAD_Y = 3;
/** Gap between the anchor point and the label, in CSS px. */
const LABEL_GAP = 10;

function drawLabel(spec: string) {
  const { lines, highlight } = JSON.parse(spec) as {
    lines: LabelLine[];
    highlight: boolean;
  };
  const ratio =
    Math.min(typeof window === "undefined" ? 1 : window.devicePixelRatio || 1, 2) * 2;
  const font = (l: LabelLine) => `${l.bold ? 600 : 400} ${LABEL_FONT_PX}px ${LABEL_FONT}`;

  const ctx = document.createElement("canvas").getContext("2d")!;
  const textW = Math.max(
    ...lines.map((l) => ((ctx.font = font(l)), ctx.measureText(l.text).width)),
  );
  const boxW = Math.ceil(textW + LABEL_PAD_X * 2);
  const w = LABEL_GAP + boxW;
  const h = lines.length * LABEL_LINE_PX + LABEL_PAD_Y * 2;

  const canvas = ctx.canvas;
  canvas.width = Math.ceil(w * ratio);
  canvas.height = Math.ceil(h * ratio);
  const c = canvas.getContext("2d")!;
  c.scale(ratio, ratio);
  if (highlight) {
    c.fillStyle = "rgba(22, 22, 22, 0.94)";
    c.strokeStyle = "#262626";
    c.lineWidth = 1;
    c.beginPath();
    c.roundRect(LABEL_GAP + 0.5, 0.5, boxW - 1, h - 1, 3);
    c.fill();
    c.stroke();
  }
  c.textBaseline = "middle";
  lines.forEach((l, k) => {
    c.font = font(l);
    c.fillStyle = l.color ?? (highlight ? "#e8e8e8" : "#9a9a9a");
    c.fillText(l.text, LABEL_GAP + LABEL_PAD_X, LABEL_PAD_Y + LABEL_LINE_PX * (k + 0.5));
  });

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  return { texture, w, h };
}

/** Screen-space label anchored at its left-middle edge; constant size in CSS px. */
function CanvasLabel({
  position,
  lines,
  highlight = false,
}: {
  position: [number, number, number] | undefined;
  lines: LabelLine[];
  highlight?: boolean;
}) {
  const viewportHeight = useThree((state) => state.size.height);
  const fov = useThree((state) =>
    state.camera instanceof THREE.PerspectiveCamera ? state.camera.fov : 45,
  );
  const spec = JSON.stringify({ lines, highlight });
  const { texture, w, h } = useMemo(() => drawLabel(spec), [spec]);
  useEffect(() => () => texture.dispose(), [texture]);

  if (!position || !isFiniteVec(position) || !(viewportHeight > 0)) return null;
  // With sizeAttenuation off, 1 unit of scale spans 2·tan(fov/2) of the viewport height.
  const k = (2 * Math.tan((fov * DEG) / 2)) / viewportHeight;
  return (
    <sprite
      position={position}
      scale={[w * k, h * k, 1]}
      center={[0, 0.5]}
      renderOrder={10}
      raycast={() => null}
    >
      <spriteMaterial
        map={texture}
        sizeAttenuation={false}
        depthTest={false}
        depthWrite={false}
        transparent
        toneMapped={false}
      />
    </sprite>
  );
}

interface BodyProps {
  position: [number, number, number] | null;
  orbit: [number, number, number][];
  color: string;
  orbitColor: string;
  radius: number;
  label: string;
  alwaysLabel?: boolean;
  selected: boolean;
  dimOrbit?: boolean;
  onClick: (e: ThreeEvent<MouseEvent>) => void;
}

function Body({
  position: rawPosition,
  orbit,
  color,
  orbitColor,
  radius,
  label,
  alwaysLabel,
  selected,
  dimOrbit = false,
  onClick,
}: BodyProps) {
  const { hovered, bind } = useHover();
  const emphasis = selected || hovered;
  const position = isFiniteVec(rawPosition) ? rawPosition : null;
  const labelAt = position ?? orbit.find((p) => isFiniteVec(p));
  return (
    <group>
      {orbit.length > 1 && (
        <SafeLine
          points={orbit}
          color={emphasis ? color : orbitColor}
          lineWidth={emphasis ? 2.4 : dimOrbit ? 1 : 1.7}
          transparent
          opacity={emphasis ? 1 : dimOrbit ? 0.4 : 0.9}
          onClick={onClick}
          {...bind}
        />
      )}
      {position && (
        <mesh position={position} onClick={onClick} {...bind}>
          <sphereGeometry args={[radius * (emphasis ? 1.3 : 1), 24, 24]} />
          <meshStandardMaterial
            color={color}
            emissive={color}
            emissiveIntensity={emphasis ? 0.5 : 0.15}
          />
        </mesh>
      )}
      {(alwaysLabel || emphasis) && (
        <CanvasLabel position={labelAt} lines={[{ text: label }]} highlight={emphasis} />
      )}
    </group>
  );
}

function CatalogBody({
  obj,
  jd,
  scale,
  selected,
  onClick,
  showOrbit = true,
  showLabel = true,
}: {
  obj: CatalogObject;
  jd: number;
  scale: ScaleMode;
  selected: boolean;
  onClick: (e: ThreeEvent<MouseEvent>) => void;
  showOrbit?: boolean;
  showLabel?: boolean;
}) {
  const orbit = obj.orbit!;
  if (isComet(obj)) {
    return (
      <CometBody
        obj={obj}
        orbit={orbit}
        jd={jd}
        scale={scale}
        selected={selected}
        onClick={onClick}
        showOrbit={showOrbit}
        showLabel={showLabel}
      />
    );
  }
  return (
    <CatalogOrbitBody
      obj={obj}
      orbit={orbit}
      jd={jd}
      scale={scale}
      selected={selected}
      onClick={onClick}
      showOrbit={showOrbit}
      showLabel={showLabel}
    />
  );
}

function CatalogOrbitBody({
  obj,
  orbit,
  jd,
  scale,
  selected,
  onClick,
  showOrbit = true,
  showLabel = true,
}: {
  obj: CatalogObject;
  orbit: OrbitEntry;
  jd: number;
  scale: ScaleMode;
  selected: boolean;
  onClick: (e: ThreeEvent<MouseEvent>) => void;
  showOrbit?: boolean;
  showLabel?: boolean;
}) {
  const path = useMemo(
    () => (showOrbit ? orbitPath(orbit).map((v) => toScene(v, scale)) : []),
    [orbit, scale, showOrbit],
  );
  const pos = useMemo(() => {
    const p = orbitPosition(orbit, jd);
    return p ? toScene(p, scale) : null;
  }, [orbit, jd, scale]);
  const label = hasCompleteElements(orbit)
    ? obj.name
    : `${obj.name} (approximate position)`;

  return (
    <Body
      position={pos}
      orbit={path}
      color={COLORS.known}
      orbitColor={COLORS.catalogOrbit}
      radius={obj.kind === "dwarf_planet" ? 0.28 : 0.2}
      label={label}
      alwaysLabel={showLabel && selected}
      selected={selected}
      dimOrbit
      onClick={onClick}
    />
  );
}

function isComet(obj: CatalogObject): boolean {
  return obj.kind === "interstellar" || obj.object_id === "3I";
}

function normalize(v: Vec3): Vec3 | null {
  const r = Math.hypot(v[0], v[1], v[2]);
  if (!(r > 0) || !Number.isFinite(r)) return null;
  return [v[0] / r, v[1] / r, v[2] / r];
}

function CometBody({
  obj,
  orbit,
  jd,
  scale,
  selected,
  onClick,
  showOrbit = true,
  showLabel = true,
}: {
  obj: CatalogObject;
  orbit: OrbitEntry;
  jd: number;
  scale: ScaleMode;
  selected: boolean;
  onClick: (e: ThreeEvent<MouseEvent>) => void;
  showOrbit?: boolean;
  showLabel?: boolean;
}) {
  const { hovered, bind } = useHover();
  const emphasis = selected || hovered;
  const fullPath = useMemo(
    () => (showOrbit ? orbitPath(orbit, 220, 45).map((v) => toScene(v, scale)) : []),
    [orbit, scale, showOrbit],
  );
  const nearPath = useMemo(
    () =>
      showOrbit
        ? orbitPathAround(orbit, jd, 200, 35, 800).map((v) => toScene(v, scale))
        : [],
    [orbit, jd, scale, showOrbit],
  );
  const posAu = useMemo(() => orbitPosition(orbit, jd), [orbit, jd]);
  const position = posAu ? toScene(posAu, scale) : null;
  const tail = useMemo(() => {
    if (!posAu || !isFiniteVec(posAu)) return [];
    const dir = normalize(posAu);
    if (!dir) return [];
    const lengthAu = 2.4;
    const steps = 10;
    const pts: [number, number, number][] = [];
    for (let k = 0; k <= steps; k++) {
      const d = (lengthAu * k) / steps;
      pts.push(
        toScene(
          [posAu[0] + dir[0] * d, posAu[1] + dir[1] * d, posAu[2] + dir[2] * d],
          scale,
        ),
      );
    }
    return finitePoints(pts);
  }, [posAu, scale]);
  const label = obj.name;
  const labelAt =
    position && isFiniteVec(position) ? position : nearPath.find((p) => isFiniteVec(p));

  return (
    <group>
      {fullPath.length > 1 && (
        <SafeLine
          points={fullPath}
          color={COLORS.comet}
          lineWidth={emphasis ? 2.4 : 1}
          transparent
          opacity={emphasis ? 1 : 0.4}
          onClick={onClick}
          {...bind}
        />
      )}
      {nearPath.length > 1 && (
        <SafeLine
          points={nearPath}
          color={COLORS.comet}
          lineWidth={emphasis ? 3 : 1}
          transparent
          opacity={emphasis ? 1 : 0.4}
          onClick={onClick}
          {...bind}
        />
      )}
      {tail.length > 1 && (
        <SafeLine
          points={tail}
          color={COLORS.cometTail}
          lineWidth={emphasis ? 5 : 3.6}
          transparent
          opacity={emphasis ? 0.95 : 0.8}
          onClick={onClick}
          {...bind}
        />
      )}
      {position && isFiniteVec(position) && (
        <group position={position}>
          <mesh renderOrder={1} raycast={() => null}>
            <sphereGeometry args={[emphasis ? 1.05 : 0.85, 24, 24]} />
            <meshBasicMaterial
              color={COLORS.comet}
              transparent
              opacity={0.18}
              depthWrite={false}
              toneMapped={false}
            />
          </mesh>
          <mesh renderOrder={2} raycast={() => null}>
            <sphereGeometry args={[emphasis ? 0.55 : 0.42, 20, 20]} />
            <meshBasicMaterial
              color={COLORS.comet}
              transparent
              opacity={0.35}
              depthWrite={false}
              toneMapped={false}
            />
          </mesh>
          <mesh onClick={onClick} {...bind} renderOrder={3}>
            <sphereGeometry args={[emphasis ? 0.26 : 0.2, 20, 20]} />
            <meshBasicMaterial color={COLORS.cometNucleus} toneMapped={false} />
          </mesh>
        </group>
      )}
      {(selected || (showLabel && hovered)) && labelAt && (
        <CanvasLabel
          position={labelAt}
          highlight={emphasis}
          lines={[
            { text: label, color: COLORS.comet, bold: true },
            { text: "Interstellar comet", color: "#9a9a9a" },
          ]}
        />
      )}
    </group>
  );
}

// ---------------------------------------------------------------------------

/** Catalog objects outside the current focus, as one clickable point cloud. */
function CatalogPoints({
  objects,
  jd,
  scale,
  onSelect,
}: {
  objects: CatalogObject[];
  jd: number;
  scale: ScaleMode;
  onSelect: (id: SelectionKey) => void;
}) {
  const { geometry, items } = useMemo(() => {
    const items: { id: string; name: string; pos: ScenePoint }[] = [];
    for (const o of objects) {
      const p = o.orbit ? orbitPosition(o.orbit, jd) : null;
      const pos = p ? toScene(p, scale) : null;
      if (pos && isFiniteVec(pos)) items.push({ id: o.object_id, name: o.name, pos });
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(items.flatMap((i) => i.pos)), 3),
    );
    return { geometry: g, items };
  }, [objects, jd, scale]);
  useEffect(() => () => geometry.dispose(), [geometry]);

  const [hovered, setHovered] = useState<number | null>(null);
  useCursor(hovered !== null);
  const hoveredItem = hovered !== null ? items[hovered] : undefined;

  if (items.length === 0) return null;
  return (
    <group>
      <points
        geometry={geometry}
        onClick={(e) => {
          e.stopPropagation();
          const item = e.index !== undefined ? items[e.index] : undefined;
          if (item) onSelect(objectKey(item.id));
        }}
        onPointerMove={(e) => {
          e.stopPropagation();
          setHovered(e.index ?? null);
        }}
        onPointerOut={() => setHovered(null)}
      >
        <pointsMaterial
          size={2}
          sizeAttenuation={false}
          color="#9a9a9a"
          transparent
          opacity={0.3}
          depthWrite={false}
        />
      </points>
      {hoveredItem && (
        <CanvasLabel
          position={hoveredItem.pos}
          lines={[{ text: hoveredItem.name }]}
          highlight
        />
      )}
    </group>
  );
}

function StarField({ stars }: { stars: CosmosStar[] }) {
  const geometry = useMemo(() => {
    const valid = stars.filter((s) => Number.isFinite(s.ra) && Number.isFinite(s.dec));
    const positions = new Float32Array(valid.length * 3);
    const colors = new Float32Array(valid.length * 3);
    valid.forEach((s, k) => {
      const [x, y, z] = toStarSphere(s.ra, s.dec);
      positions.set([x, y, z], k * 3);
      const mag = Number.isFinite(s.mag) ? s.mag : 6;
      const fade = THREE.MathUtils.clamp(1 - (mag + 1.5) / 8, 0.15, 1);
      const [r, g, b] = bvToRgb(s.bv);
      colors.set([r * fade, g * fade, b * fade], k * 3);
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    return { g, count: valid.length };
  }, [stars]);

  if (geometry.count === 0) return null;
  return (
    <points geometry={geometry.g}>
      <pointsMaterial size={2} sizeAttenuation={false} vertexColors depthWrite={false} />
    </points>
  );
}

function SkyGuides({ cosmos }: { cosmos?: CosmosData | null }) {
  const lines = cosmos?.lines;
  const band = cosmos?.galactic_band;
  const ecliptic = useMemo(() => (lines ? skyPathPoints(lines.ecliptic) : []), [lines]);
  const galactic = useMemo(
    () => (lines ? skyPathPoints(lines.galactic_equator) : []),
    [lines],
  );
  const equator = useMemo(() => {
    if (lines?.galactic_equator) return lines.galactic_equator;
    return (band?.points ?? []).map(([ra, dec]) => [ra, dec] as [number, number]);
  }, [lines, band]);
  const half = band?.half_width_deg ?? 10;
  const north = useMemo(
    () => (equator.length ? galacticLatitudePoints(equator, half) : []),
    [equator, half],
  );
  const south = useMemo(
    () => (equator.length ? galacticLatitudePoints(equator, -half) : []),
    [equator, half],
  );
  return (
    <group>
      <SafeLine
        points={ecliptic}
        color="#6a6a6a"
        lineWidth={0.6}
        transparent
        opacity={0.45}
      />
      <SafeLine
        points={galactic}
        color="#5a5a5a"
        lineWidth={0.6}
        transparent
        opacity={0.4}
      />
      <SafeLine
        points={north}
        color="#4a4a4a"
        lineWidth={0.4}
        transparent
        opacity={0.25}
      />
      <SafeLine
        points={south}
        color="#4a4a4a"
        lineWidth={0.4}
        transparent
        opacity={0.25}
      />
    </group>
  );
}

function SkyLabels({ labels }: { labels: CosmosLabel[] }) {
  if (labels.length === 0) return null;
  return (
    <group>
      {labels.map((label, i) => {
        const pos = toStarSphere(label.ra_deg, label.dec_deg);
        const key = `${label.kind}-${label.text}-${i}`;
        if (label.kind === "star") {
          return <HoverStarLabel key={key} position={pos} text={label.text} />;
        }
        const color = label.kind === "patch" ? "#C4B5FD" : "#9a9a9a";
        return (
          <CanvasLabel key={key} position={pos} lines={[{ text: label.text, color }]} />
        );
      })}
    </group>
  );
}

function HoverStarLabel({
  position,
  text,
}: {
  position: [number, number, number];
  text: string;
}) {
  const { hovered, bind } = useHover();
  return (
    <group position={position}>
      <mesh {...bind}>
        <sphereGeometry args={[8, 8, 8]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      {hovered && (
        <CanvasLabel position={[0, 0, 0]} lines={[{ text, color: "#e8e8e8" }]} />
      )}
    </group>
  );
}

function PointingCone({
  pointing,
  label,
  scale,
  active,
  showLabel = true,
}: {
  pointing: Pointing;
  label: string;
  scale: ScaleMode;
  active: boolean;
  showLabel?: boolean;
}) {
  const lines = useMemo(() => {
    // pointings.json gives the exact direction and observer position for the burst.
    const u = pointing.dir_ecl;
    const earth = pointing.earth_au;
    if (!isFiniteVec(u) || !isFiniteVec(earth)) return null;
    const fov = Number.isFinite(pointing.fov_deg) ? pointing.fov_deg : 0;
    const half = Math.max(fov / 2, MIN_CONE_HALF_ANGLE_DEG) * DEG;
    const map = (pts: Vec3[]) => pts.map((v) => toScene(v, scale));
    const edges = [0, 1, 2, 3].map((k) =>
      map(
        rayPoints(
          earth,
          tiltedDirection(u, half, (k * Math.PI) / 2),
          0,
          CONE_LENGTH_AU,
          24,
        ),
      ),
    );
    const rim = map(
      Array.from({ length: 33 }, (_, k) => {
        const d = tiltedDirection(u, half, (k / 32) * 2 * Math.PI);
        return [
          earth[0] + d[0] * CONE_LENGTH_AU,
          earth[1] + d[1] * CONE_LENGTH_AU,
          earth[2] + d[2] * CONE_LENGTH_AU,
        ] as Vec3;
      }),
    );
    return { axis: map(rayPoints(earth, u, 0, CONE_LENGTH_AU, 24)), edges, rim };
  }, [pointing, scale]);

  if (!lines) return null;
  const color = active ? COLORS.coneActive : COLORS.cone;
  const opacity = active ? 0.85 : 0.3;
  return (
    <group>
      <SafeLine
        points={lines.axis}
        color={color}
        lineWidth={active ? 1.2 : 0.6}
        transparent
        opacity={opacity}
        dashed
        dashSize={0.6}
        gapSize={0.4}
      />
      {lines.edges.map((pts, k) => (
        <SafeLine
          key={k}
          points={pts}
          color={color}
          lineWidth={0.6}
          transparent
          opacity={opacity * 0.7}
        />
      ))}
      <SafeLine
        points={lines.rim}
        color={color}
        lineWidth={0.6}
        transparent
        opacity={opacity * 0.7}
      />
      {active && showLabel && (
        <CanvasLabel
          position={lines.axis.findLast((p) => isFiniteVec(p))}
          lines={[{ text: label }]}
        />
      )}
    </group>
  );
}

const fmt = (n: number) => (n >= 10 ? n.toFixed(0) : n.toFixed(2));

function CandidateRange({
  detection: d,
  earth,
  scale,
  selected,
  onClick,
}: {
  detection: Detection;
  earth: Vec3;
  scale: ScaleMode;
  selected: boolean;
  onClick: (e: ThreeEvent<MouseEvent>) => void;
}) {
  const { hovered, bind } = useHover();
  const emphasis = selected || hovered;
  // distance_min_au / distance_max_au are measured from Earth along the line of sight.
  const { segment, mid, ends } = useMemo(() => {
    const u = radecToEcliptic(d.ra_deg, d.dec_deg);
    const lo = d.distance_min_au;
    const hi = d.distance_max_au;
    if (
      !isFiniteVec(u) ||
      !isFiniteVec(earth) ||
      lo === undefined ||
      hi === undefined ||
      !Number.isFinite(lo) ||
      !Number.isFinite(hi)
    ) {
      return { segment: [], mid: null, ends: [] };
    }
    const pts = lineOfSightSegment(earth, u, lo, hi);
    const mapped = pts ? finitePoints(pts.map((v) => toScene(v, scale))) : [];
    if (mapped.length < 2) return { segment: [], mid: null, ends: [] };
    return {
      segment: mapped,
      mid: mapped[Math.floor(mapped.length / 2)],
      ends: [mapped[0], mapped[mapped.length - 1]],
    };
  }, [d, earth, scale]);

  if (!mid) return null;

  return (
    <group>
      <SafeLine
        points={segment}
        color={COLORS.candidate}
        lineWidth={emphasis ? 4 : 2.5}
        transparent
        opacity={emphasis ? 1 : 0.75}
        onClick={onClick}
        {...bind}
      />
      {ends.map((p, k) => (
        <mesh key={k} position={p}>
          <sphereGeometry args={[0.08, 12, 12]} />
          <meshBasicMaterial color={COLORS.candidate} />
        </mesh>
      ))}
      {/* Glowing orange diamond at the middle of the range */}
      <mesh position={mid} onClick={onClick} {...bind}>
        <octahedronGeometry args={[emphasis ? 0.4 : 0.3]} />
        <meshStandardMaterial
          color={COLORS.candidate}
          emissive={COLORS.candidate}
          emissiveIntensity={emphasis ? 1.6 : 0.9}
          toneMapped={false}
        />
      </mesh>
      {emphasis && (
        <CanvasLabel
          position={mid}
          highlight
          lines={[
            {
              text: `Candidate ${d.designation ?? d.track_id}`,
              color: COLORS.candidate,
              bold: true,
            },
            {
              text: `Approximate distance from Earth: ${fmt(Math.min(d.distance_min_au!, d.distance_max_au!))}–${fmt(Math.max(d.distance_min_au!, d.distance_max_au!))} AU`,
            },
            ...(d.size_est_km
              ? [
                  {
                    text: `Approximate size: ${fmt(d.size_est_km[0])}–${fmt(d.size_est_km[1])} km`,
                  },
                ]
              : []),
          ]}
        />
      )}
    </group>
  );
}
