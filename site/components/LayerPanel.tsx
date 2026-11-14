"use client";

import { Tooltip } from "@/components/Tooltip";
import { useSession, type SceneLayers } from "@/store/session";

const ITEMS: { key: keyof SceneLayers; label: string; hint: string }[] = [
  {
    key: "stars",
    label: "Stars",
    hint: "Background stars from cosmos.json, placed on the celestial sphere",
  },
  {
    key: "milkyWay",
    label: "Milky Way / lines",
    hint: "Galactic band plus the ecliptic and galactic-equator reference lines",
  },
  {
    key: "planets",
    label: "Planets",
    hint: "The Sun and the eight planets at the current burst's time",
  },
  {
    key: "orbits",
    label: "Orbits",
    hint: "Orbit paths for planets and the primary catalog objects",
  },
  {
    key: "objects",
    label: "Objects",
    hint: "Known asteroids, Ceres and 3I/ATLAS from orbits.json",
  },
  {
    key: "pointings",
    label: "SPHEREx pointings",
    hint: "Where SPHEREx looked from Earth for each patch",
  },
  {
    key: "labels",
    label: "Labels",
    hint: "Name labels for planets, bright stars, pointings and the selected object",
  },
];

export function LayerPanel({
  collapsedDefault = false,
  idPrefix = "layer",
}: {
  collapsedDefault?: boolean;
  idPrefix?: string;
}) {
  const layers = useSession((s) => s.layers);
  const setLayer = useSession((s) => s.setLayer);

  const controls = (
    <div className="flex flex-col gap-0.5">
      {ITEMS.map((item) => {
        const id = `${idPrefix}-${item.key}`;
        return (
          <Tooltip key={item.key} content={item.hint} side="left">
            <div className="flex items-center gap-1.5">
              <input
                id={id}
                type="checkbox"
                checked={layers[item.key]}
                onChange={(event) => setLayer(item.key, event.target.checked)}
                className="cursor-pointer accent-neutral-300"
              />
              <label htmlFor={id} className="cursor-pointer">
                {item.label}
              </label>
            </div>
          </Tooltip>
        );
      })}
    </div>
  );

  if (collapsedDefault) {
    return (
      <details className="border-line bg-raised text-muted rounded border px-2 py-1.5 text-[11px]">
        <summary className="text-muted cursor-pointer text-[10px] tracking-wide uppercase">
          Layers
        </summary>
        <div className="mt-1">{controls}</div>
      </details>
    );
  }

  return (
    <fieldset className="border-line bg-raised text-muted rounded border px-2 py-1.5 text-[11px]">
      <legend className="text-muted px-1 text-[10px] tracking-wide uppercase">
        Layers
      </legend>
      {controls}
    </fieldset>
  );
}
