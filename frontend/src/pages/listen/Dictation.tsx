import { useCallback, useEffect, useState } from "react";
import { api, type DictationItem, type DiffResult, type DiffSegment } from "../../api";
import { useSpeak } from "../../audio";
import { useSettings } from "../../SettingsContext";

const SPEEDS = [
  { value: 0.75, label: "0.75×" },
  { value: 1.0, label: "1×" },
  { value: 1.25, label: "1.25×" },
];

function Segment({ seg }: { seg: DiffSegment }) {
  switch (seg.type) {
    case "equal":
      return <span className="text-ink">{seg.text}</span>;
    case "missing":
      return (
        <span className="rounded bg-accent-soft px-0.5 text-bad underline decoration-dotted">
          {seg.text}
        </span>
      );
    case "extra":
      return <span className="text-ink-faint line-through">{seg.text}</span>;
    case "wrong":
      return (
        <span>
          <span className="text-ink-faint line-through">{seg.got}</span>
          <span className="rounded bg-accent-soft px-0.5 text-bad">{seg.expected}</span>
        </span>
      );
  }
}

export default function Dictation() {
  const { settings } = useSettings();
  const { play } = useSpeak();
  const [item, setItem] = useState<DictationItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rate, setRate] = useState(1.0);
  const [answer, setAnswer] = useState("");
  const [toneSensitive, setToneSensitive] = useState(true);
  const [result, setResult] = useState<DiffResult | null>(null);

  const load = useCallback(() => {
    setResult(null);
    setAnswer("");
    api.listenDictation().then(setItem).catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);

  function playClip(r = rate) {
    if (item) play(item.audio_text, { voice: item.voice, rate: r });
  }

  async function check() {
    if (!item || !answer.trim()) return;
    try {
      const r = await api.listenCheck({
        expected_hanzi: item.hanzi,
        expected_pinyin: item.pinyin,
        answer,
        tone_sensitive: toneSensitive,
      });
      setResult(r);
    } catch (e) {
      setError(String(e));
    }
  }

  if (error) return <div className="text-bad">{error}</div>;
  if (!item) return <div className="text-ink-soft">Loading…</div>;

  return (
    <div className="card">
      <p className="text-sm text-ink-soft">Listen and type what you hear — characters or pinyin.</p>

      <div className="mt-4 flex flex-col items-center gap-3">
        <button
          type="button"
          onClick={() => playClip()}
          className="tap flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-ink shadow-card active:scale-95"
          aria-label="Play sentence"
        >
          <svg viewBox="0 0 24 24" className="h-7 w-7" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
        </button>
        <div className="inline-flex rounded-md border border-border bg-surface-2 p-1">
          {SPEEDS.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => {
                setRate(s.value);
                playClip(s.value);
              }}
              className={[
                "tap rounded px-3 text-sm font-medium transition-colors",
                s.value === rate ? "bg-primary text-primary-ink" : "text-ink-soft",
              ].join(" ")}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <input
        lang="zh-Hant"
        value={answer}
        disabled={!!result}
        onChange={(e) => setAnswer(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && check()}
        placeholder="輸入 / type here…"
        className="mt-5 w-full rounded-md border border-border bg-surface px-4 py-3 text-center font-han text-xl text-ink"
      />

      <label className="mt-2 flex items-center justify-end gap-2 text-xs text-ink-soft">
        <input
          type="checkbox"
          checked={toneSensitive}
          onChange={(e) => setToneSensitive(e.target.checked)}
          className="accent-[color:var(--primary)]"
        />
        match tones (pinyin)
      </label>

      {result ? (
        <div className="mt-5">
          <div
            className={[
              "rounded-md border p-4 text-center",
              result.correct ? "border-good bg-good/10" : "border-border bg-surface-2",
            ].join(" ")}
          >
            <div lang="zh-Hant" className="font-han text-xl leading-relaxed">
              {result.segments.map((s, i) => (
                <Segment key={i} seg={s} />
              ))}
            </div>
            <div className={["mt-1 text-sm font-medium", result.correct ? "text-good" : "text-warn"].join(" ")}>
              {result.correct ? "✓ Correct" : "Not quite — corrected above"}
            </div>
          </div>
          <div className="mt-3 rounded-md bg-surface-2 p-3 text-center">
            <button
              type="button"
              onClick={() => playClip()}
              lang="zh-Hant"
              className="font-han text-lg text-ink underline decoration-ink-faint"
            >
              {item.hanzi}
            </button>
            {settings?.show_pinyin && <div className="text-sm text-ink-soft">{item.pinyin}</div>}
            <div className="text-sm text-ink-soft">{item.gloss}</div>
          </div>
          <button
            type="button"
            onClick={load}
            className="mt-4 w-full rounded-md bg-primary py-3 font-medium text-primary-ink"
          >
            Next ▸
          </button>
        </div>
      ) : (
        <button
          type="button"
          disabled={!answer.trim()}
          onClick={check}
          className="mt-4 w-full rounded-md bg-primary py-3 font-medium text-primary-ink disabled:opacity-40"
        >
          Check
        </button>
      )}
    </div>
  );
}
