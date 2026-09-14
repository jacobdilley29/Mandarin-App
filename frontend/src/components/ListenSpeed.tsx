// Playback speed for listening exercises (spec §3.4: "slow / normal / native pace").
//
// Native is 1.0 because edge-tts already speaks at native pace — the useful
// range for a learner is slower than that, not faster. The app-wide
// playback_rate in Settings is separate and unchanged; this is the per-exercise
// control, so slowing one hard clip down doesn't slow everything else.
export const LISTEN_SPEEDS = [
  { value: 0.7, label: "Slow" },
  { value: 0.85, label: "Normal" },
  { value: 1.0, label: "Native" },
] as const;

export const DEFAULT_LISTEN_SPEED = 0.85;

export function ListenSpeed({
  rate,
  onChange,
}: {
  rate: number;
  onChange: (r: number) => void;
}) {
  return (
    <div className="inline-flex rounded-md border border-border bg-surface-2 p-1">
      {LISTEN_SPEEDS.map((s) => (
        <button
          key={s.value}
          type="button"
          onClick={() => onChange(s.value)}
          aria-pressed={s.value === rate}
          className={[
            "tap rounded px-3 py-1 text-sm font-medium transition-colors",
            s.value === rate ? "bg-primary text-primary-ink" : "text-ink-soft hover:text-ink",
          ].join(" ")}
        >
          {s.label}
        </button>
      ))}
    </div>
  );
}
