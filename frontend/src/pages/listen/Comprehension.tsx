import { useCallback, useEffect, useState } from "react";
import { api, type ComprehensionSet, type Option } from "../../api";
import { useSpeak } from "../../audio";
import { useSettings } from "../../SettingsContext";

export default function Comprehension() {
  const { settings } = useSettings();
  const { play } = useSpeak();
  const [set, setSet] = useState<ComprehensionSet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showEn, setShowEn] = useState(false);
  const [answers, setAnswers] = useState<Record<number, Option>>({});

  const load = useCallback(() => {
    setAnswers({});
    setShowEn(false);
    api.listenSet().then(setSet).catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);

  if (error) return <div className="text-bad">{error}</div>;
  if (!set) return <div className="text-ink-soft">Loading…</div>;

  const allAnswered = Object.keys(answers).length === set.questions.length;
  const correctCount = Object.values(answers).filter((a) => a.correct).length;

  return (
    <div>
      {/* Dialogue */}
      <div className="card">
        <div className="mb-3 flex items-center justify-between">
          <h2 lang="zh-Hant" className="font-han text-base text-ink">
            {set.title}
          </h2>
          <button
            type="button"
            onClick={() => setShowEn((v) => !v)}
            className="rounded-full border border-border px-3 py-1 text-xs text-ink-soft"
          >
            {showEn ? "Hide English" : "Show English"}
          </button>
        </div>
        <div className="space-y-2">
          {set.dialogue.map((line, i) => (
            <div key={i} className="rounded-md border border-border p-3">
              <div className="text-xs font-medium text-primary">{line.speaker}</div>
              <button
                type="button"
                lang="zh-Hant"
                onClick={() => play(line.audio_text, { voice: line.voice, rate: settings?.playback_rate })}
                className="mt-0.5 text-left font-han text-lg text-ink"
              >
                {line.hanzi}
                <span className="ml-1 text-xs text-ink-faint">🔊</span>
              </button>
              {settings?.show_pinyin && <div className="text-sm text-ink-soft">{line.pinyin}</div>}
              {showEn && <div className="mt-0.5 text-sm text-ink-soft">{line.gloss}</div>}
            </div>
          ))}
        </div>
      </div>

      {/* Questions */}
      <div className="mt-4 space-y-4">
        {set.questions.map((q, qi) => {
          const chosen = answers[qi];
          return (
            <div key={qi} className="card">
              <div className="mb-3 text-sm font-medium text-ink">
                {qi + 1}. {q.prompt}
              </div>
              <div className="grid gap-2">
                {q.options.map((o) => {
                  let cls = "border-border bg-surface hover:border-primary";
                  if (chosen) {
                    if (o.correct) cls = "border-good bg-good/10 text-good";
                    else if (o.text === chosen.text) cls = "border-bad bg-accent-soft text-bad";
                    else cls = "border-border bg-surface opacity-50";
                  }
                  return (
                    <button
                      key={o.text}
                      type="button"
                      disabled={!!chosen}
                      onClick={() => setAnswers((a) => ({ ...a, [qi]: o }))}
                      className={["tap rounded-md border px-4 py-3 text-left text-sm transition-colors", cls].join(" ")}
                    >
                      {o.text}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {allAnswered && (
        <div className="mt-4 text-center">
          <div className="text-sm text-ink-soft">
            {correctCount} / {set.questions.length} correct
          </div>
          <button
            type="button"
            onClick={load}
            className="mt-2 w-full rounded-md bg-primary py-3 font-medium text-primary-ink"
          >
            Next dialogue ▸
          </button>
        </div>
      )}
    </div>
  );
}
