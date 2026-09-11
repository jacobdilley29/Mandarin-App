import { useSettings } from "../SettingsContext";

/**
 * The phonetic line that sits under a Chinese string.
 *
 * Which notation appears is a user setting (pinyin / zhuyin / both / off) rather
 * than a per-call decision, so every call site renders this instead of reaching
 * for `pinyin` directly. `show` stays a prop because Review deliberately hides
 * the annotation to force recall, whatever the setting says.
 *
 * Zhuyin is derived from pinyin server-side and may be absent for a string that
 * could not be converted safely — in that case we fall back to pinyin rather
 * than show nothing.
 */
export default function Phonetic({
  pinyin,
  zhuyin,
  show = true,
  className = "",
}: {
  pinyin?: string | null;
  zhuyin?: string | null;
  show?: boolean;
  className?: string;
}) {
  const { settings } = useSettings();
  const mode = settings?.phonetic ?? "pinyin";

  if (!show || mode === "off") return null;

  const wantsZhuyin = mode === "zhuyin" || mode === "both";
  const wantsPinyin = mode === "pinyin" || mode === "both" || (wantsZhuyin && !zhuyin);

  const lines: React.ReactNode[] = [];
  if (wantsZhuyin && zhuyin) {
    lines.push(
      <div key="z" lang="zh-TW" className="font-zhuyin">
        {zhuyin}
      </div>,
    );
  }
  if (wantsPinyin && pinyin) {
    lines.push(
      <div key="p" className="font-sans">
        {pinyin}
      </div>,
    );
  }
  if (lines.length === 0) return null;

  return <div className={`text-sm text-ink-soft ${className}`.trim()}>{lines}</div>;
}

/**
 * The same choice as `Phonetic`, but as a plain string — for the handful of
 * places that need the notation inline inside other text rather than as its own
 * block. Returns null when the user has annotations switched off.
 */
export function usePhoneticText(
  pinyin?: string | null,
  zhuyin?: string | null,
): string | null {
  const { settings } = useSettings();
  const mode = settings?.phonetic ?? "pinyin";

  if (mode === "off") return null;
  if (mode === "zhuyin") return zhuyin || pinyin || null;
  if (mode === "both") return [zhuyin, pinyin].filter(Boolean).join("  ") || null;
  return pinyin || null;
}
