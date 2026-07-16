import { ToneMark, type Tone } from "./ToneMark";

// Honest placeholder for tabs whose features land in later phases. Uses a tone
// shape as the section marker so the brand motif is present from Phase 0.
export function ComingSoon({
  han,
  title,
  phase,
  blurb,
  tone = 2,
}: {
  han: string;
  title: string;
  phase: number;
  blurb: string;
  tone?: Tone;
}) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 text-primary">
        <ToneMark tone={tone} size={48} strokeWidth={7} />
      </div>
      <h1 lang="zh-Hant" className="font-serifhan text-hero text-ink">
        {han}
      </h1>
      <p className="mt-2 text-lg font-semibold text-ink">{title}</p>
      <p className="mt-3 max-w-sm text-sm leading-relaxed text-ink-soft">{blurb}</p>
      <span className="mt-6 rounded-full border border-border bg-surface-2 px-3 py-1 text-xs font-medium text-ink-faint">
        Phase {phase} · coming soon
      </span>
    </div>
  );
}
