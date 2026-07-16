import type { ContourPoint } from "../../api";

// Pitch-contour overlay (spec §3.4): the learner's normalised f0 (green) over an
// idealised expected contour (faint), rendered as SVG. y is semitones relative
// to the speaker's median; x spans the utterance.
const W = 320;
const H = 150;
const PAD = 12;
const Y_MIN = -9;
const Y_MAX = 7;

function toXY(p: ContourPoint): [number, number] {
  const x = PAD + p.x * (W - 2 * PAD);
  const y = PAD + ((Y_MAX - p.y) / (Y_MAX - Y_MIN)) * (H - 2 * PAD);
  return [x, Math.max(PAD, Math.min(H - PAD, y))];
}

function polyline(points: ContourPoint[]): string {
  return points.map((p) => toXY(p).join(",")).join(" ");
}

export function ContourPlot({
  user,
  expected,
  bounds,
}: {
  user: ContourPoint[];
  expected: ContourPoint[];
  bounds: number[];
}) {
  // The user contour can have gaps (unvoiced); split into runs of consecutive
  // points so the polyline doesn't draw across silences.
  const runs: ContourPoint[][] = [];
  let cur: ContourPoint[] = [];
  for (let i = 0; i < user.length; i++) {
    if (cur.length && user[i].x - cur[cur.length - 1].x > 0.06) {
      runs.push(cur);
      cur = [];
    }
    cur.push(user[i]);
  }
  if (cur.length) runs.push(cur);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Pitch contour">
      {/* midline (median) */}
      <line
        x1={PAD}
        x2={W - PAD}
        y1={toXY({ x: 0, y: 0 })[1]}
        y2={toXY({ x: 0, y: 0 })[1]}
        stroke="var(--border)"
        strokeDasharray="3 3"
      />
      {/* syllable boundaries */}
      {bounds.slice(1, -1).map((b, i) => {
        const x = PAD + b * (W - 2 * PAD);
        return <line key={i} x1={x} x2={x} y1={PAD} y2={H - PAD} stroke="var(--border)" strokeDasharray="2 4" />;
      })}
      {/* idealised expected contour */}
      {expected.length > 1 && (
        <polyline
          points={polyline(expected)}
          fill="none"
          stroke="var(--ink-faint)"
          strokeWidth={2}
          strokeDasharray="4 3"
          opacity={0.7}
        />
      )}
      {/* learner contour */}
      {runs.map((run, i) => (
        <polyline
          key={i}
          points={polyline(run)}
          fill="none"
          stroke="var(--primary)"
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
    </svg>
  );
}
