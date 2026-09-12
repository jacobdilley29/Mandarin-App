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

    // --- Grammar (spec §3.3) ---
    case "pattern_recall":
      return (
        <div className="py-4">
          <GrammarTag title={item.title} />
          <div className="mb-2 text-sm text-ink-soft">Which pattern is this?</div>
          <p className="text-base leading-relaxed text-ink">{item.explanation}</p>
        </div>
      );
    case "particle_cloze":
      return (
        <div className="py-4 text-center">
          <GrammarTag title={item.title} />
          <div className="mb-3 text-sm text-ink-soft">Which word belongs here?</div>
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

function GrammarTag({ title }: { title?: string }) {
  if (!title) return null;
  return (
    <div className="mb-3 flex items-baseline gap-2">
      <span className="rounded-full bg-primary-soft/40 px-2 py-0.5 text-[0.65rem] font-medium uppercase tracking-wide text-primary">
        Grammar
      </span>
      <span lang="zh-Hant" className="font-han text-sm text-ink-soft">
        {title}
      </span>
    </div>
  );
}

/**
 * Reorder the words to make the pattern (spec §3.3).
 *
 * Grammar's version of the tile drill: the tiles are chunked so the particle is
 * its own tile, which makes "where does 的 go" the actual question rather than a
 * general word-order puzzle.
 */
function PatternBuild({
  item,
  onAnswer,
}: {
  item: ReviewItem;
  onAnswer: (correct: boolean) => void;
}) {
  const [picked, setPicked] = useState<number[]>([]);
  const tokens = item.tokens ?? [];
  const answer = Array.isArray(item.answer) ? item.answer : [];

  useEffect(() => {
    setPicked([]);
  }, [item.card_id]);

  const built = picked.map((i) => tokens[i]);
  const done = picked.length === tokens.length;

  return (
    <div className="py-4">
      <GrammarTag title={item.title} />
      <div className="mb-2 text-sm text-ink-soft">Put the words in order</div>
      {item.gloss && <p className="mb-3 text-base text-ink">{item.gloss}</p>}

      <div className="mb-4 min-h-[3.5rem] rounded-md border border-dashed border-border bg-surface-2 px-3 py-3 text-center">
        <span lang="zh-Hant" className="font-serifhan text-2xl text-ink">
          {built.join("") || <span className="text-ink-faint">…</span>}
        </span>
      </div>

      <div className="flex flex-wrap justify-center gap-2">
        {tokens.map((t, i) => (
          <button
            key={`${t}-${i}`}
            type="button"
            lang="zh-Hant"
            disabled={picked.includes(i)}
            onClick={() => setPicked([...picked, i])}
            className={[
              "tap rounded-md border px-3 py-2 font-serifhan text-lg transition-colors",
              picked.includes(i)
                ? "border-border bg-surface-2 text-ink-faint"
                : "border-border bg-surface text-ink hover:border-primary",
            ].join(" ")}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="mt-5 flex gap-2">
        <button
          type="button"
          disabled={!picked.length}
          onClick={() => setPicked(picked.slice(0, -1))}
          className="tap rounded-md border border-border px-4 py-2 text-sm text-ink-soft disabled:opacity-40"
        >
          Undo
        </button>
        <button
          type="button"
          disabled={!done}
          onClick={() => onAnswer(built.join("") === answer.join(""))}
          className="tap flex-1 rounded-md bg-primary py-2 font-medium text-primary-ink disabled:opacity-40"
        >
          Check
        </button>
      </div>
    </div>
  );
}

export default function ReviewSession() {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [chosen, setChosen] = useState<Option | null>(null);
  // pattern_build answers by reordering tiles, not by picking an option, so its
  // correctness is tracked separately — it still gates the rating buttons.
  const [built, setBuilt] = useState<boolean | null>(null);
  const [reviewed, setReviewed] = useState(0);

  function load() {
    Promise.all([api.reviewQueue(), api.reviewStats()])
      .then(([q, s]) => {
        setItems(q.items);
        setStats(s);
        setIndex(0);
        setChosen(null);
        setBuilt(null);
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
    setBuilt(null);
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
  const answered = chosen != null || built != null;

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
        {item.kind === "pattern_build" ? (
          <PatternBuild item={item} onAnswer={setBuilt} />
        ) : (
          <Prompt item={item} />
        )}

        {/* Answer choices */}
        <div className="mt-3 grid gap-2">
          {(item.options ?? []).map((o) => {
            const isHan =
              item.kind === "recall" ||
              item.kind === "cloze" ||
              item.kind === "particle_cloze";
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
