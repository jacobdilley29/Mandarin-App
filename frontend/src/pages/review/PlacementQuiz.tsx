import { useEffect, useMemo, useState } from "react";
import { api, type PlacementItem } from "../../api";
import { ToneMark } from "../../components/ToneMark";

// First-run placement check (spec §3.2): a quick recognition quiz over HSK 1–2.
// Correct answers seed the SRS deck as mature; misses enter as new.
export default function PlacementQuiz({ onDone }: { onDone: () => void }) {
  const [items, setItems] = useState<PlacementItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [index, setIndex] = useState(0);
  const [results, setResults] = useState<{ vocab_id: string; correct: boolean }[]>([]);
  const [picked, setPicked] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.placement().then((p) => setItems(p.items)).catch((e) => setError(String(e)));
  }, []);

  const correctCount = useMemo(() => results.filter((r) => r.correct).length, [results]);

  async function choose(item: PlacementItem, isCorrect: boolean) {
    if (picked) return;
    setPicked(isCorrect ? "correct" : "wrong");
    const next = [...results, { vocab_id: item.vocab_id, correct: isCorrect }];
    setTimeout(async () => {
      setPicked(null);
      if (items && index + 1 < items.length) {
        setResults(next);
        setIndex(index + 1);
      } else {
        setResults(next);
        setSubmitting(true);
        try {
          await api.placementResult(next);
          onDone();
        } catch (e) {
          setError(String(e));
          setSubmitting(false);
        }
      }
    }, 220);
  }

  if (error) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-bad">{error}</div>;
  }
  if (!items) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Loading placement…</div>;
  }

  if (!started) {
    return (
      <div className="mx-auto flex min-h-[70vh] max-w-xl flex-col items-center justify-center px-6 text-center">
        <div className="text-primary">
          <ToneMark tone={3} size={52} strokeWidth={7} />
        </div>
        <h1 lang="zh-Hant" className="mt-4 font-serifhan text-4xl text-ink">
          程度測驗
        </h1>
        <p className="mt-2 text-lg font-semibold text-ink">Quick placement check</p>
        <p className="mt-3 max-w-sm text-sm leading-relaxed text-ink-soft">
          {items.length} words over HSK 1–2. Tap the meaning you know. Words you get right are added
          to your review deck as already-learned; the rest start fresh. No pressure — it just tunes
          where you begin.
        </p>
        <button
          type="button"
          onClick={() => setStarted(true)}
          className="mt-8 w-full max-w-xs rounded-md bg-primary py-3 font-medium text-primary-ink"
        >
          Start
        </button>
      </div>
    );
  }

  if (submitting) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Setting up your deck…</div>;
  }

  const item = items[index];
  const progress = Math.round((index / items.length) * 100);

  return (
    <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-xl flex-col px-4 py-4">
      <div className="mb-1 flex items-center justify-between text-xs text-ink-soft">
        <span>
          {index + 1} / {items.length}
        </span>
        <span className="text-good">{correctCount} known</span>
      </div>
      <div className="mb-5 h-2 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} />
      </div>

      <div className="card flex-1">
        <div className="mb-2 text-sm text-ink-soft">Do you know this word?</div>
        <div className="py-4 text-center">
          <span lang="zh-Hant" className="font-serifhan text-hero text-ink">
            {item.char}
          </span>
        </div>
        <div className="mt-2 grid gap-2">
          {item.options.map((o) => {
            let cls = "border-border bg-surface hover:border-primary";
            if (picked) {
              if (o.correct) cls = "border-good bg-good/10 text-good";
              else cls = "border-border bg-surface opacity-50";
            }
            return (
              <button
                key={o.text}
                type="button"
                disabled={!!picked}
                onClick={() => choose(item, o.correct)}
                className={["tap rounded-md border px-4 py-3 text-left text-base transition-colors", cls].join(" ")}
              >
                {o.text}
              </button>
            );
          })}
          <button
            type="button"
            disabled={!!picked}
            onClick={() => choose(item, false)}
            className="tap mt-1 rounded-md border border-dashed border-border px-4 py-2 text-sm text-ink-soft hover:text-ink"
          >
            I don't know this yet
          </button>
        </div>
      </div>
    </div>
  );
}
