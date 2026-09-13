import { useSettings } from "../SettingsContext";

// One reading, shown in whichever script the learner asked for (spec §3.1).
//
// The Me tab offers pinyin, 注音, or both, and that choice has to mean the same
// thing everywhere a reading appears — the vocabulary card, the tap-to-define
// popover, the passage. Three copies of this rule is how one of them ends up
// still showing pinyin after the toggle gains a mode.
//
// Zhuyin is transcribed from our own pinyin, so the two lines always agree; see
// backend/app/zhuyin.py for why that matters.
export function Phonetic({
  pinyin,
  zhuyin,
  className,
}: {
  pinyin?: string | null;
  zhuyin?: string | null;
  className?: string;
}) {
  const { settings } = useSettings();
  const script = settings?.script ?? "pinyin";
  const zh = script !== "pinyin" ? zhuyin : null;
  const py = script === "zhuyin" && zh ? null : pinyin;
  if (!zh && !py) return null;

  return (
    <span className={className}>
      {zh && (
        <span lang="zh-Hant" className="font-han">
          {zh}
        </span>
      )}
      {zh && py && <span className="mx-1.5 text-ink-faint">·</span>}
      {py}
    </span>
  );
}
