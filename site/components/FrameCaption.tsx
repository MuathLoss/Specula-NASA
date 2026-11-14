import type { CaptionLine } from "@/lib/frame-caption";

export function FrameCaption({ lines }: { lines: CaptionLine[] }) {
  if (lines.length === 0) return null;
  return (
    <dl className="text-muted grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-[11px]">
      {lines.map((line) => (
        <div key={line.key} className="contents">
          <dt className="text-muted">{line.label}</dt>
          <dd className="text-ink min-w-0 font-mono break-words">{line.value}</dd>
        </div>
      ))}
    </dl>
  );
}
