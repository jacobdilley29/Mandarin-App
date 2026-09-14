import { useSpeak } from "../audio";
import { useSettings } from "../SettingsContext";

// Round audio-play button used by drills and review cards.
export function PlayButton({ text, big }: { text: string; big?: boolean }) {
  const { play, state } = useSpeak();
  const { settings } = useSettings();
  return (
    <button
      type="button"
      onClick={() => play(text, { voice: settings?.tts_voice, rate: settings?.playback_rate })}
      className={[
        "tap flex items-center justify-center rounded-full bg-primary text-primary-ink shadow-card transition-transform active:scale-95",
        big ? "h-16 w-16" : "h-12 w-12",
      ].join(" ")}
      aria-label="Play audio"
    >
      {state === "loading" ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary-ink border-t-transparent" />
      ) : (
        <svg viewBox="0 0 24 24" className={big ? "h-7 w-7" : "h-6 w-6"} fill="currentColor">
          <path d="M8 5v14l11-7z" />
        </svg>
      )}
    </button>
  );
}
