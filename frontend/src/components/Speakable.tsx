import { useSpeak } from "../audio";
import { useSettings } from "../SettingsContext";

// A tappable Chinese string that plays its audio (design brief: every Chinese
// string is tappable to hear it). Shows a subtle speaker cue; on TTS failure it
// simply stops reacting rather than breaking the exercise.
export function Speakable({
  text,
  children,
  className,
  lang = "zh-Hant",
  showIcon = true,
}: {
  text: string;
  children: React.ReactNode;
  className?: string;
  lang?: string;
  showIcon?: boolean;
}) {
  const { play, state } = useSpeak();
  const { settings } = useSettings();

  return (
    <button
      type="button"
      lang={lang}
      onClick={() => play(text, { voice: settings?.tts_voice, rate: settings?.playback_rate })}
      className={[
        "group inline-flex items-center gap-1 text-left transition-colors",
        state === "error" ? "cursor-default" : "",
        className ?? "",
      ].join(" ")}
      aria-label={`Play audio: ${text}`}
    >
      <span>{children}</span>
      {showIcon && (
        <svg
          viewBox="0 0 24 24"
          className={[
            "h-[0.7em] w-[0.7em] shrink-0 transition-opacity",
            state === "playing" ? "text-primary" : "text-ink-faint opacity-50 group-hover:opacity-90",
          ].join(" ")}
          fill="currentColor"
          aria-hidden="true"
        >
          <path d="M3 9v6h4l5 5V4L7 9H3z" />
          {state !== "error" && <path d="M16 8a5 5 0 010 8" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />}
        </svg>
      )}
    </button>
  );
}
