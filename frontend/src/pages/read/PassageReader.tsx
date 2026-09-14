import { useEffect, useState } from "react";
import { api, type Passage } from "../../api";
import { Glossable } from "../../components/Glossable";
import { Phonetic } from "../../components/Phonetic";
import { PlayButton } from "../../components/PlayButton";

// One passage, then rate it (spec §3.2, §3.6).
//
// The English is hidden behind a tap on purpose. With the translation on screen
// the eye reads it first and the Chinese becomes decoration — the passage has to
// be attempted before it can be checked.
//
// The four buttons are the same Again/Hard/Good/Easy that drive the review deck,
// because a passage is scheduled by the same engine. Rating one moves that
// passage and nothing else: an extra reading session must never cost the learner
// a pile of vocabulary reviews the next morning.
const RATINGS = [
  { rating: 1, label: "Again", hint: "Lost me", cls: "bg-bad text-primary-ink" },
  { rating: 2, label: "Hard", hint: "Slow going", cls: "bg-warn text-primary-ink" },
  { rating: 3, label: "Good", hint: "Followed it", cls: "bg-primary text-primary-ink" },
  { rating: 4, label: "Easy", hint: "Read it straight", cls: "bg-good text-primary-ink" },
];

export default function PassageReader({
  lessonId,
  onExit,
}: {
  lessonId: string;
  onExit: () => void;
}) {
  const [passage, setPassage] = useState<Passage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [rating, setRating] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setRevealed(false);
    setRating(null);
    api
      .passage(lessonId)
      .then(setPassage)
      .catch((e: Error) => setError(e.message));
  }, [lessonId]);

  const rate = (value: number) => {
    setSaving(true);
    api
      .readingAnswer(lessonId, value)
      .then(() => setRating(value))
      .catch((e: Error) => setError(e.message))
      .finally(() => setSaving(false));
  };

  if (error) {
    return (
      <div className="mx-auto max-w-xl px-4 py-10 text-center">
        <p className="text-sm text-bad">{error}</p>
        <button type="button" onClick={onExit} className="tap mt-4 text-sm text-primary underline">
          Back to reading
        </button>
      </div>
    );
  }
  if (!passage) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Loading…</div>;
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-6">
      <button type="button" onClick={onExit} className="tap mb-4 text-sm text-ink-soft">
        ← Reading
      </button>

      <header className="mb-4 flex items-baseline justify-between gap-3">
        <h1 lang="zh-Hant" className="font-han text-xl text-ink">
          {passage.title}
        </h1>
        <PlayButton text={passage.hanzi} />
      </header>

      <article
        lang="zh-Hant"
        className="rounded-md border border-border bg-surface px-4 py-5 font-serifhan text-2xl
                   leading-loose tracking-wide text-ink"
      >
        <Glossable text={passage.hanzi} />
      </article>

      <div className="mt-4">
        {revealed ? (
          <p className="rounded-md bg-surface-2 px-4 py-3 text-sm leading-relaxed text-ink-soft">
            {passage.gloss}
          </p>
        ) : (
          <button
            type="button"
            onClick={() => setRevealed(true)}
            className="tap w-full rounded-md border border-dashed border-border px-4 py-3
                       text-sm text-ink-soft hover:border-primary"
          >
            Show the English
          </button>
        )}
      </div>

      {passage.vocab.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-soft">
            From this lesson
          </h2>
          <ul className="grid gap-1 text-sm">
            {passage.vocab.map((v) => (
              <li key={v.id} className="flex items-baseline gap-2">
                <span lang="zh-Hant" className="font-han text-ink">
                  {v.traditional}
                </span>
                <Phonetic pinyin={v.pinyin} zhuyin={v.zhuyin} className="text-xs text-ink-faint" />
                <span className="text-ink-soft">{v.gloss}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-8">
        {rating ? (
          <div className="text-center">
            <p className="text-sm text-ink-soft">
              Scheduled. It'll come back when it's due.
            </p>
            <button
              type="button"
              onClick={onExit}
              className="tap mt-3 rounded-md bg-primary px-5 py-2 text-primary-ink"
            >
              Done
            </button>
          </div>
        ) : (
          <>
            <p className="mb-2 text-center text-xs text-ink-faint">
              How did that go? This only schedules the passage — your word cards don't move.
            </p>
            <div className="grid grid-cols-4 gap-2">
              {RATINGS.map((r) => (
                <button
                  key={r.rating}
                  type="button"
                  disabled={saving}
                  onClick={() => rate(r.rating)}
                  className={`tap rounded-md px-2 py-3 text-center disabled:opacity-50 ${r.cls}`}
                >
                  <span className="block text-sm font-medium">{r.label}</span>
                  <span className="block text-[0.62rem] opacity-80">{r.hint}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
