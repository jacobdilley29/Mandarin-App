import { useCallback, useEffect, useState } from "react";
import { api, type Option, type PracticeItem, type PracticeSet } from "../../api";
import { PlayButton } from "../../components/PlayButton";
import { ToneMark } from "../../components/ToneMark";

// Extra practice (spec §3.6 "needs practice", §3.1 "review known material").
//
// Deliberately NOT the daily queue: there are no Again/Hard/Good/Easy buttons
// here, because nothing you do in this session changes your FSRS schedule. You
// can drill a word you keep forgetting ten times without moving a single due
// date or recording a lapse. §3.1 asks for review to stop blocking progress;
// a practice mode that charged you for using it would defeat that.

type Mode = "needs" | "known";

const COPY: Record<Mode, { title: string; han: string; blurb: string }> = {
  needs: {
    title: "Needs practice",
    han: "加強",
    blurb:
      "The words and patterns giving you the most trouble — repeated lapses, wrong answers, and shaky tones. Drilling here doesn't affect your review schedule.",
  },
  known: {
    title: "Known material",
    han: "複習舊的",
    blurb:
      "Things you've already mastered, for a confidence pass. Nothing here changes your schedule either.",
  },
};

function Prompt({ item }: { item: PracticeItem }) {
  switch (item.kind) {
    case "recognition":
      return (
        <div className="py-4 text-center">
          <div className="mb-3 text-sm text-ink-soft">What does this mean?</div>
          <span lang="zh-Hant" className="font-serifhan text-hero text-ink">
            {item.char}
          </span>
        </div>
      );
    case "recall":
      return (
        <div className="py-4 text-center">
          <div className="mb-3 text-sm text-ink-soft">Which word means…</div>
          <div className="text-2xl font-semibold text-ink">{item.prompt_gloss}</div>
        </div>
      );
    case "audio_meaning":
      return (
        <div className="py-4 text-center">
          <div className="mb-3 text-sm text-ink-soft">Listen — what does it mean?</div>
          <div className="flex justify-center">
            <PlayButton text={item.audio_text ?? ""} big />
          </div>
        </div>
      );
    case "pattern_recall":
      return (
        <div className="py-4">
          <div className="mb-2 text-sm text-ink-soft">Which pattern is this?</div>
          <p className="text-base leading-relaxed text-ink">{item.explanation}</p>
        </div>
      );
    default:
      // cloze / particle_cloze and anything else with a masked sentence.
      return (
        <div className="py-4 text-center">
          <div className="mb-3 text-sm text-ink-soft">Fill in the blank</div>
          {item.audio_text && (
            <div className="flex justify-center">
              <PlayButton text={item.audio_text} />
            </div>
          )}
          <div lang="zh-Hant" className="mt-3 font-han text-2xl text-ink">
            {item.masked}
          </div>
          {item.gloss && <div className="mt-1 text-sm text-ink-soft">{item.gloss}</div>}
        </div>
      );
  }
}

export default function PracticeSession({ mode, onExit }: { mode: Mode; onExit: () => void }) {
  const [set, setSet] = useState<PracticeSet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [chosen, setChosen] = useState<Option | null>(null);
  const [correct, setCorrect] = useState(0);
  const copy = COPY[mode];

  const load = useCallback(() => {
    const fetcher = mode === "needs" ? api.practiceNeeds : api.practiceKnown;
    fetcher()
      .then((s) => {
        setSet(s);
        setIndex(0);
        setChosen(null);
        setCorrect(0);
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, [mode]);
  useEffect(load, [load]);

  function next() {
    if (!set) return;
    const done = index + 1 >= set.items.length;
    setChosen(null);
    setIndex((i) => i + 1);
    if (done) {
      void api.practiceResult(set.items.length, correct).catch(() => {
        // Logging the session is a nicety; failing it shouldn't eat the practice.
      });
    }
  }

  if (error) return <div className="mx-auto max-w-xl px-4 py-10 text-center text-bad">{error}</div>;
  if (!set) return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Loading…</div>;

  if (set.items.length === 0) {
    return (
      <div className="mx-auto flex min-h-[60vh] max-w-xl flex-col items-center justify-center px-6 text-center">
        <div className="text-ink-faint">
          <ToneMark tone={1} size={44} strokeWidth={7} />
        </div>
        <h2 className="mt-4 text-lg font-semibold text-ink">{copy.title}</h2>
        <p className="mt-2 max-w-sm text-sm text-ink-soft">{set.empty_reason}</p>
        <button
          type="button"
          onClick={onExit}
          className="tap mt-6 w-full max-w-xs rounded-md border border-border py-3 font-medium text-ink"
        >
          Back
        </button>
      </div>
    );
  }

  if (index >= set.items.length) {
    return (
      <div className="mx-auto flex min-h-[60vh] max-w-xl flex-col items-center justify-center px-6 text-center">
        <div className="text-good">
          <ToneMark tone={1} size={52} strokeWidth={7} />
        </div>
        <h1 lang="zh-Hant" className="mt-4 font-serifhan text-4xl text-ink">
          練習完成
        </h1>
        <p className="mt-2 text-lg text-ink">
          {correct} / {set.items.length} correct
        </p>
        <p className="mt-2 max-w-sm text-sm text-ink-soft">
          Your review schedule is untouched — practice never costs you a due date.
        </p>
        <div className="mt-8 flex w-full max-w-xs flex-col gap-2">
          <button
            type="button"
            onClick={load}
            className="tap rounded-md bg-primary py-3 font-medium text-primary-ink"
          >
            Again
          </button>
          <button type="button" onClick={onExit} className="tap rounded-md border border-border py-3 text-ink">
            Done
          </button>
        </div>
      </div>
    );
  }

  const item = set.items[index];
  const answered = chosen != null;

  return (
    <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-xl flex-col px-4 py-4">
      <div className="mb-1 flex items-center justify-between text-xs text-ink-soft">
        <button type="button" onClick={onExit} className="tap text-ink-faint hover:text-ink">
          ✕ {copy.title}
        </button>
        <span>
          {index + 1} / {set.items.length}
        </span>
      </div>
      <div className="mb-5 h-2 overflow-hidden rounded-full bg-surface-2">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${Math.round((index / set.items.length) * 100)}%` }}
        />
      </div>

      <div className="card flex-1">
        {item.why && (
          <div className="mb-3 inline-flex rounded-full bg-accent-soft px-2.5 py-0.5 text-xs text-ink-soft">
            {item.why}
          </div>
        )}
        <Prompt item={item} />

        <div className="mt-3 grid gap-2">
          {(item.options ?? []).map((o) => {
            const isHan = item.kind !== "recognition" && item.kind !== "audio_meaning";
            let cls = "border-border bg-surface hover:border-primary";
            if (answered) {
              if (o.correct) cls = "border-good bg-good/10 text-good";
              else if (o.text === chosen?.text) cls = "border-bad bg-accent-soft text-bad";
              else cls = "border-border bg-surface opacity-50";
            }
            return (
              <button
                key={o.text}
                type="button"
                lang={isHan ? "zh-Hant" : undefined}
                disabled={answered}
                onClick={() => {
                  setChosen(o);
                  if (o.correct) setCorrect((n) => n + 1);
                }}
                className={[
                  "tap rounded-md border px-4 py-3 text-left transition-colors",
                  isHan ? "font-han text-lg" : "text-base",
                  cls,
                ].join(" ")}
              >
                {o.text}
              </button>
            );
          })}
        </div>

        {answered && (
          <button
            type="button"
            onClick={next}
            className="tap mt-5 w-full rounded-md bg-primary py-3 font-medium text-primary-ink"
          >
            Continue
          </button>
        )}
      </div>
    </div>
  );
}
