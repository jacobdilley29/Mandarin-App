import { useEffect, useState } from "react";
import { api, type Option, type ReviewItem, type ReviewStats } from "../../api";
import { PlayButton } from "../../components/PlayButton";
import { ToneMark } from "../../components/ToneMark";

// Anki-style rating buttons drive FSRS. Colours cue difficulty.
const RATINGS = [
  { rating: 1, label: "Again", cls: "bg-bad text-primary-ink" },
  { rating: 2, label: "Hard", cls: "bg-warn text-primary-ink" },
  { rating: 3, label: "Good", cls: "bg-primary text-primary-ink" },
  { rating: 4, label: "Easy", cls: "bg-good text-primary-ink" },
];

function Prompt({ item }: { item: ReviewItem }) {
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
    case "cloze":
      return (
        <div className="py-4 text-center">
          <div className="mb-3 text-sm text-ink-soft">Fill in the blank</div>
          <div className="flex justify-center">
            <PlayButton text={item.audio_text ?? ""} />
          </div>
          <div lang="zh-Hant" className="mt-3 font-han text-2xl text-ink">
            {item.masked}
          </div>
          {item.gloss && <div className="mt-1 text-sm text-ink-soft">{item.gloss}</div>}
        </div>
      );
  }
}

export default function ReviewSession() {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [chosen, setChosen] = useState<Option | null>(null);
  const [reviewed, setReviewed] = useState(0);

  function load() {
    Promise.all([api.reviewQueue(), api.reviewStats()])
      .then(([q, s]) => {
        setItems(q.items);
        setStats(s);
        setIndex(0);
        setChosen(null);
        setReviewed(0);
      })
      .catch((e) => setError(String(e)));
  }
  useEffect(load, []);

  async function rate(rating: number) {
    if (!items) return;
    const item = items[index];
    try {
      await api.reviewAnswer(item.card_id, rating);
    } catch (e) {
      setError(String(e));
      return;
    }
    setReviewed((n) => n + 1);
    setChosen(null);
    setIndex((i) => i + 1);
  }

  if (error) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-bad">{error}</div>;
  }
  if (!items) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Loading review…</div>;
  }

  // Empty queue or finished.
  if (items.length === 0 || index >= items.length) {
    return (
      <div className="mx-auto flex min-h-[70vh] max-w-xl flex-col items-center justify-center px-6 text-center">
        <div className="text-good">
          <ToneMark tone={1} size={52} strokeWidth={7} />
        </div>
        <h1 lang="zh-Hant" className="mt-4 font-serifhan text-4xl text-ink">
          {reviewed > 0 ? "複習完成" : "沒有到期"}
        </h1>
        <p className="mt-2 text-lg text-ink">
          {reviewed > 0 ? `${reviewed} cards reviewed` : "Nothing due right now"}
        </p>
        {stats && (
          <p className="mt-2 text-sm text-ink-soft">
            {stats.new} new · {stats.total} in deck
            {stats.mature > 0 && ` · ${stats.mature} mature`}
          </p>
        )}
        <button
          type="button"
          onClick={load}
          className="mt-8 w-full max-w-xs rounded-md border border-border py-3 font-medium text-ink"
        >
          Refresh queue
        </button>
      </div>
    );
  }

  const item = items[index];
  const progress = Math.round((index / items.length) * 100);
  const answered = chosen != null;

  return (
    <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-xl flex-col px-4 py-4">
      <div className="mb-1 flex items-center justify-between text-xs text-ink-soft">
        <span>
          {index + 1} / {items.length}
        </span>
        <span className="capitalize">{item.state}</span>
      </div>
      <div className="mb-5 h-2 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} />
      </div>

      <div className="card flex-1">
        <Prompt item={item} />

        {/* Answer choices */}
        <div className="mt-3 grid gap-2">
          {item.options.map((o) => {
            const isHan = item.kind === "recall" || item.kind === "cloze";
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
                onClick={() => setChosen(o)}
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

        {/* Reveal + FSRS rating */}
        {answered && (
          <div className="mt-5">
            <div className="rounded-md bg-surface-2 p-3 text-center">
              <span lang="zh-Hant" className="font-han text-lg text-ink">
                {item.char ?? item.audio_text ?? item.answer}
              </span>
              {item.pinyin && <span className="ml-2 text-sm text-ink-soft">{item.pinyin}</span>}
            </div>
            <div className="mt-2 text-center text-xs text-ink-soft">How well did you recall it?</div>
            <div className="mt-2 grid grid-cols-4 gap-2">
              {RATINGS.map((r) => (
                <button
                  key={r.rating}
                  type="button"
                  onClick={() => rate(r.rating)}
                  className={["tap rounded-md py-3 text-sm font-medium", r.cls].join(" ")}
                >
                  {r.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
