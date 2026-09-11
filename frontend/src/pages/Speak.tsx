import { useCallback, useEffect, useState } from "react";
import { api, type SpeakItem, type SpeakScore, type SyllableVerdict } from "../api";
import { useRecorder } from "../audio_record";
import { useSpeak } from "../audio";
import { useSettings } from "../SettingsContext";
import { ToneMark, type Tone } from "../components/ToneMark";
import { ContourPlot } from "./speak/ContourPlot";

const TONE_LABEL: Record<number, string> = { 1: "flat", 2: "rising", 3: "dipping", 4: "falling", 5: "neutral" };

function SyllableRow({ s, whisper }: { s: SyllableVerdict; whisper: boolean }) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-border p-3">
      {s.char && (
        <span lang="zh-Hant" className="font-serifhan text-2xl text-ink">
          {s.char}
        </span>
      )}
      <div className="flex items-center gap-1 text-ink-soft">
        <ToneMark tone={s.expected as Tone} size={22} strokeWidth={9} color="var(--ink-faint)" />
        <span className="text-xs">→</span>
        <ToneMark
          tone={s.detected as Tone}
          size={22}
          strokeWidth={9}
          color={s.ok ? "var(--good)" : "var(--warn)"}
        />
      </div>
      <div className="ml-auto text-right">
        {s.ok ? (
          <span className="text-sm font-medium text-good">✓ {TONE_LABEL[s.expected]}</span>
        ) : (
          <span className="text-sm font-medium text-warn">
            heard {TONE_LABEL[s.detected]}, want {TONE_LABEL[s.expected]}
          </span>
        )}
        {whisper && s.heard != null && (
          <div className={["text-xs", s.char_ok ? "text-good" : "text-bad"].join(" ")}>
            heard「{s.heard}」
          </div>
        )}
      </div>
    </div>
  );
}

export default function Speak() {
  const { settings } = useSettings();
  const { play } = useSpeak();
  const { state, start, stop, supported } = useRecorder();
  const [mode, setMode] = useState<"word" | "sentence">("word");
  const [item, setItem] = useState<SpeakItem | null>(null);
  const [score, setScore] = useState<SpeakScore | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setScore(null);
    setError(null);
    api.speakItem(mode).then(setItem).catch((e) => setError(String(e)));
  }, [mode]);
  useEffect(load, [load]);

  async function record() {
    if (!item) return;
    setError(null);
    const wav = await start(); // resolves when recording stops
    if (!wav) return;
    setBusy(true);
    try {
      setScore(await api.speakScore(wav, item.hanzi, item.pinyin));
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-6">
      <header className="mb-4 flex items-center gap-3">
        <span className="text-primary">
          <ToneMark tone={2} size={30} strokeWidth={7} />
        </span>
        <div>
          <h1 lang="zh-Hant" className="font-serifhan text-3xl leading-none text-ink">
            說
          </h1>
          <p className="text-sm text-ink-soft">Speak · pronunciation &amp; tones</p>
        </div>
      </header>

      <div className="mb-5 inline-flex rounded-md border border-border bg-surface-2 p-1">
        {(["word", "sentence"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => setMode(m)}
            className={[
              "tap rounded px-4 py-1.5 text-sm font-medium transition-colors",
              m === mode ? "bg-primary text-primary-ink" : "text-ink-soft",
            ].join(" ")}
          >
            {m === "word" ? "Word" : "Sentence"}
          </button>
        ))}
      </div>

      {error && <div className="mb-4 rounded-md border border-bad/40 bg-accent-soft px-4 py-3 text-sm text-bad">{error}</div>}
      {!item ? (
        <div className="card text-ink-soft">Loading…</div>
      ) : (
        <div className="card">
          {/* Target */}
          <div className="text-center">
            <button
              type="button"
              lang="zh-Hant"
              onClick={() => play(item.hanzi, { voice: settings?.tts_voice, rate: settings?.playback_rate })}
              className="font-serifhan text-hero text-ink"
            >
              {item.hanzi}
            </button>
            {settings?.show_pinyin && <div className="mt-1 text-lg text-ink-soft">{item.pinyin}</div>}
            <div className="text-sm text-ink-soft">{item.gloss}</div>
            <div className="mt-3 flex justify-center">
              <button
                type="button"
                onClick={() => play(item.hanzi, { voice: settings?.tts_voice, rate: settings?.playback_rate })}
                className="tap flex items-center gap-1 rounded-full border border-border px-3 py-1.5 text-sm text-ink-soft"
              >
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
                Reference
              </button>
            </div>
          </div>

          {/* Record */}
          {!supported ? (
            <p className="mt-6 text-center text-sm text-ink-soft">
              Recording needs microphone access, which this browser doesn't support here.
            </p>
          ) : state === "denied" ? (
            <p className="mt-6 text-center text-sm text-warn">
              Microphone permission was denied. Allow mic access and try again.
            </p>
          ) : (
            <div className="mt-6 flex flex-col items-center">
              {state === "recording" ? (
                <button
                  type="button"
                  onClick={stop}
                  className="tap flex h-20 w-20 items-center justify-center rounded-full bg-bad text-primary-ink shadow-card"
                  aria-label="Stop recording"
                >
                  <span className="h-6 w-6 rounded-sm bg-primary-ink" />
                </button>
              ) : (
                <button
                  type="button"
                  disabled={busy || state === "processing"}
                  onClick={record}
                  className="tap flex h-20 w-20 items-center justify-center rounded-full bg-primary text-primary-ink shadow-card active:scale-95 disabled:opacity-50"
                  aria-label="Record"
                >
                  {busy || state === "processing" ? (
                    <span className="h-6 w-6 animate-spin rounded-full border-2 border-primary-ink border-t-transparent" />
                  ) : (
                    <svg viewBox="0 0 24 24" className="h-8 w-8" fill="currentColor">
                      <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3z" />
                      <path d="M19 11a7 7 0 0 1-14 0M12 18v3" stroke="currentColor" strokeWidth="2" fill="none" />
                    </svg>
                  )}
                </button>
              )}
              <p className="mt-2 text-xs text-ink-soft">
                {state === "recording"
                  ? "Recording… tap to stop"
                  : busy || state === "processing"
                    ? "Analysing…"
                    : "Tap to record yourself"}
              </p>
            </div>
          )}

          {/* Feedback */}
          {score && (
            <div className="mt-6 border-t border-border pt-5">
              <div className="mb-1 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-ink">Tone check</h3>
                <span className="text-xs text-ink-soft">
                  {score.tone_correct}/{score.tone_total} tones
                </span>
              </div>
              <div className="rounded-md border border-border bg-surface-2 p-2">
                <ContourPlot
                  user={score.contour.points}
                  expected={score.expected_contour}
                  bounds={score.contour.syllable_bounds}
                />
                <div className="flex justify-center gap-4 text-xs text-ink-soft">
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-0.5 w-4 bg-primary" /> you
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-ink-faint" /> target
                  </span>
                </div>
              </div>

              <div className="mt-3 space-y-2">
                {score.syllables.map((s) => (
                  <SyllableRow key={s.index} s={s} whisper={score.whisper_available} />
                ))}
              </div>

              {score.whisper_available && score.transcription != null && (
                <div className="mt-3 rounded-md bg-surface-2 p-3 text-sm">
                  <span className="text-ink-soft">Heard: </span>
                  <span lang="zh-Hant" className="font-han text-ink">
                    {score.transcription || "—"}
                  </span>
                </div>
              )}

              <p className="mt-3 text-center text-xs text-ink-faint">
                Tone check is approximate — a guide, not a graded score.
                {!score.whisper_available && " (Transcription off — install faster-whisper to compare characters.)"}
              </p>

              <button
                type="button"
                onClick={load}
                className="mt-4 w-full rounded-md bg-primary py-3 font-medium text-primary-ink"
              >
                Next ▸
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
