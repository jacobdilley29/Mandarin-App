import { type LevelBand } from "../api";

// Level labelling, in one place (spec §3.1).
//
// TOCFL is the exam track Jacob cares about, so it leads; HSK is how the content
// happens to be sourced and graded, so it trails as the smaller line. The strings
// come from the backend (app/levels.py reading content/tocfl_mapping.json) rather
// than being built here, so a correction to the mapping reaches every surface.
export function LevelBadge({ level, showHsk = true }: { level: LevelBand | null; showHsk?: boolean }) {
  if (!level || !level.tocfl_level) return null;
  return (
    <span className="inline-flex items-baseline gap-1.5 rounded-full bg-surface-2 px-2 py-0.5">
      <span className="text-[0.65rem] font-medium text-ink-soft">{level.label}</span>
      {showHsk && <span className="text-[0.6rem] text-ink-faint">{level.sublabel}</span>}
    </span>
  );
}

/** The Chinese name of the band, for headings. */
export function LevelName({ level }: { level: LevelBand | null }) {
  if (!level?.tocfl_level_zh) return null;
  return (
    <span lang="zh-Hant" className="font-han">
      {level.label_zh}
    </span>
  );
}
