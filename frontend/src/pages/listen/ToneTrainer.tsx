import { useCallback, useEffect, useState } from "react";
import { api, type ToneItem, type ToneOption } from "../../api";
import { useSpeak } from "../../audio";
import { useSettings } from "../../SettingsContext";
import { ToneMark, type Tone } from "../../components/ToneMark";

type ToneMode = "single" | "pair";

const TONE_LABEL: Record<number, string> = {
  1: "1 高平",
  2: "2 上升",
  3: "3 低降升",
  4: "4 下降",
};

function sameOption(a: ToneOption, b: ToneOption): boolean {
  if (a.tone != null && b.tone != null) return a.tone === b.tone;
  if (a.tones && b.tones) return a.tones.join(",") === b.tones.join(",");
  return false;
}

export default function ToneTrainer() {
  const { settings } = useSettings();
  const { play } = useSpeak();
  const [mode, setMode] = useState<ToneMode>("single");
  const [item, setItem] = useState<ToneItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [chosen, setChosen] = useState<ToneOption | null>(null);

  const load = useCallback((m: ToneMode) => {
    setChosen(null);
    setItem(null);
    api.listenTones(m).then(setItem).catch((e) => setError(String(e)));
  }, []);
  useEffect(() => load(mode), [mode, load]);

  function playClip() {
    if (item) play(item.audio_text, { voice: item.voice, rate: settings?.playback_rate });
  }

  if (error) return <div className="text-bad">{error}</div>;

  return (
    <div>
      <div className="mb-4 inline-flex rounded-md border border-border bg-surface-2 p-1">
        {(["single", "pair"] as ToneMode[]).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={[
              "tap rounded px-4 py-1.5 text-sm font-medium transition-colors",
              m === mode ? "bg-primary text-primary-ink" : "text-ink-soft",
            ].join(" ")}
          >
            {m === "single" ? "Single tone" : "Tone pair"}
          </button>
        ))}
      </div>

      <div className="card">
        <p className="text-sm text-ink-soft">
          {mode === "single" ? "Hear the word — which tone is it?" : "Hear the word — which tone pair?"}
        </p>

        <div className="mt-4 flex justify-center">
          <button
            type="button"
            onClick={playClip}
            className="tap flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-ink shadow-card active:scale-95"
            aria-label="Play word"
          >
            <svg viewBox="0 0 24 24" className="h-7 w-7" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
          </button>
        </div>

        {!item ? (
          <div className="mt-6 text-center text-ink-soft">Loading…</div>
        ) : (
          <>
            <div className="mt-5 grid grid-cols-2 gap-3">
              {item.options.map((o, i) => {
                const isChosen = chosen && sameOption(o, chosen);
                let cls = "border-border bg-surface hover:border-primary";
                if (chosen) {
                  if (o.correct) cls = "border-good bg-good/10";
                  else if (isChosen) cls = "border-bad bg-accent-soft";
                  else cls = "border-border bg-surface opacity-50";
                }
                return (
                  <button
                    key={i}
                    type="button"
                    disabled={!!chosen}
                    onClick={() => setChosen(o)}
                    className={["tap flex items-center justify-center gap-2 rounded-md border py-4 transition-colors", cls].join(" ")}
                  >
                    {o.tone != null ? (
                      <span className="flex items-center gap-2 text-ink">
                        <ToneMark tone={o.tone as Tone} size={30} strokeWidth={8} />
                        <span className="text-sm">{TONE_LABEL[o.tone]}</span>
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-ink">
                        {o.tones!.map((t, j) => (
                          <ToneMark key={j} tone={t as Tone} size={26} strokeWidth={8} />
                        ))}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            {chosen && (
              <div className="mt-5 text-center">
                <button
                  type="button"
                  onClick={playClip}
                  lang="zh-Hant"
                  className="font-serifhan text-4xl text-ink"
                >
                  {item.traditional}
                </button>
                <div className="mt-1 text-sm text-ink-soft">
                  {item.pinyin} · {item.tones.join("–")}
                </div>
                <div className={["mt-1 text-sm font-medium", chosen.correct ? "text-good" : "text-warn"].join(" ")}>
                  {chosen.correct ? "✓ Correct" : "Listen again — the shape shows the answer"}
                </div>
                <button
                  type="button"
                  onClick={() => load(mode)}
                  className="mt-4 w-full rounded-md bg-primary py-3 font-medium text-primary-ink"
                >
                  Next ▸
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
