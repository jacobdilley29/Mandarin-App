// The signature element: the four Mandarin tone shapes as an SVG motif, reused
// as section markers, feedback marks, and progress indicators. See DESIGN.md.

export type Tone = 1 | 2 | 3 | 4 | 5; // 5 = neutral

// Schematic contours on a 0..100 x 0..100 grid (y inverted: 0 = top/high).
const CONTOURS: Record<Tone, string> = {
  1: "M8,26 L92,26", // high flat
  2: "M10,80 L90,20", // rising
  3: "M10,45 C30,90 70,90 90,40", // dip (low-falling-rising)
  4: "M10,18 L90,82", // falling
  5: "M50,50 L50,50", // neutral — a dot (rendered as a circle below)
};

interface Props {
  tone: Tone;
  size?: number;
  color?: string;
  strokeWidth?: number;
  className?: string;
  title?: string;
}

export function ToneMark({
  tone,
  size = 24,
  color = "currentColor",
  strokeWidth = 8,
  className,
  title,
}: Props) {
  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      className={className}
      role="img"
      aria-label={title ?? `tone ${tone}`}
      fill="none"
    >
      {tone === 5 ? (
        <circle cx="50" cy="50" r={strokeWidth * 0.9} fill={color} />
      ) : (
        <path
          d={CONTOURS[tone]}
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
    </svg>
  );
}

/** A row of all four tone shapes — used as a calm brand motif / divider. */
export function ToneRow({ size = 20, color }: { size?: number; color?: string }) {
  return (
    <div className="flex items-center gap-2" aria-hidden="true">
      {([1, 2, 3, 4] as Tone[]).map((t) => (
        <ToneMark key={t} tone={t} size={size} color={color} />
      ))}
    </div>
  );
}
