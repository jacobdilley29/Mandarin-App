import { useEffect, useMemo, useState } from "react";
import {
  api,
  type PlacementItem,
  type PlacementRound,
  type PlacementSummary,
} from "../../api";
import { ToneMark } from "../../components/ToneMark";
import { PlayButton } from "../../components/PlayButton";

// Adaptive placement check (spec §3.1). Walks TOCFL bands rather than sampling
// one: a short round per band, stepping up or down until it finds the boundary
// between what Jacob knows and what he doesn't. Three item kinds per the spec —
// recognition, listening, and sentence building.
//
// The client plays one round at a time and posts it back; the server decides
// where to go next and records the verdict, so dropping out mid-quiz keeps
// whatever was already answered.

type Answer = { vocab_id: string | null; correct: boolean };

function Progress({ round, index }: { round: PlacementRound; index: number }) {
  const pct = Math.round((index / round.items.length) * 100);
  return (
    <>
      <div className="mb-1 flex items-center justify-between text-xs text-ink-soft">
        <span>
          {round.level.label}
          <span className="ml-1.5 text-ink-faint">{round.level.sublabel}</span>
        </span>
        <span>
          {index + 1} / {round.items.length}
        </span>
      </div>
      <div className="mb-5 h-2 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
      </div>
    </>
  );
}

/** Tap the words into the right order. */
function SentenceBuild({
  item,
  locked,
  onAnswer,
}: {
  item: PlacementItem;
  locked: boolean;
  onAnswer: (correct: boolean) => void;
}) {
  const [picked, setPicked] = useState<number[]>([]);
  const tokens = item.tokens ?? [];

  useEffect(() => {
    setPicked([]);
  }, [item]);

  const done = picked.length === tokens.length;
  const built = picked.map((i) => tokens[i]);
  const correct = done && built.join("") === (item.answer ?? []).join("");

  return (
    <div>
      <div className="mb-3 text-sm text-ink-soft">Put the words in order</div>
      <p className="mb-4 text-base text-ink">{item.gloss}</p>

      <div className="mb-4 min-h-[3.5rem] rounded-md border border-dashed border-border bg-surface-2 px-3 py-3">
        <span lang="zh-Hant" className="font-serifhan text-2xl text-ink">
          {built.join("") || <span className="text-ink-faint">…</span>}
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        {tokens.map((t, i) => (
          <button
            key={`${t}-${i}`}
            type="button"
            disabled={locked || picked.includes(i)}
            onClick={() => setPicked([...picked, i])}
            className={[
              "tap rounded-md border px-3 py-2 font-serifhan text-lg transition-colors",
              picked.includes(i)
                ? "border-border bg-surface-2 text-ink-faint"
                : "border-border bg-surface text-ink hover:border-primary",
            ].join(" ")}
            lang="zh-Hant"
          >
            {t}
          </button>
        ))}
      </div>

      <div className="mt-5 flex gap-2">
        <button
          type="button"
          disabled={locked || picked.length === 0}
          onClick={() => setPicked(picked.slice(0, -1))}
          className="tap rounded-md border border-border px-4 py-2 text-sm text-ink-soft disabled:opacity-40"
        >
          Undo
        </button>
        <button
          type="button"
          disabled={locked || !done}
          onClick={() => onAnswer(correct)}
          className="tap flex-1 rounded-md bg-primary py-2 font-medium text-primary-ink disabled:opacity-40"
        >
          Check
        </button>
        <button
          type="button"
          disabled={locked}
          onClick={() => onAnswer(false)}
          className="tap rounded-md border border-dashed border-border px-4 py-2 text-sm text-ink-soft"
        >
          Skip
        </button>
      </div>
    </div>
  );
}

function Choice({
  item,
  picked,
  onAnswer,
}: {
  item: PlacementItem;
  picked: string | null;
  onAnswer: (correct: boolean) => void;
}) {
  const listening = item.kind === "listening";
  return (
    <div>
      <div className="mb-2 text-sm text-ink-soft">
        {listening ? "Listen — what does it mean?" : "Do you know this word?"}
      </div>

      <div className="py-4 text-center">
        {listening ? (
          // No characters and no pinyin: the question is whether he knows it by ear.
          <PlayButton text={item.audio_text ?? ""} big />
        ) : (
          <span lang="zh-Hant" className="font-serifhan text-hero text-ink">
            {item.char}
          </span>
        )}
      </div>

      <div className="mt-2 grid gap-2">
        {(item.options ?? []).map((o) => {
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
              onClick={() => onAnswer(o.correct)}
              className={["tap rounded-md border px-4 py-3 text-left text-base transition-colors", cls].join(" ")}
            >
              {o.text}
            </button>
          );
        })}
        <button
          type="button"
          disabled={!!picked}
          onClick={() => onAnswer(false)}
          className="tap mt-1 rounded-md border border-dashed border-border px-4 py-2 text-sm text-ink-soft hover:text-ink"
        >
          I don't know this yet
        </button>
      </div>
    </div>
  );
}

function Result({ summary, onDone }: { summary: PlacementSummary; onDone: () => void }) {
  const start = summary.start_at;
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-xl flex-col justify-center px-6 py-8">
      <div className="text-center">
        <div className="mx-auto w-fit text-primary">
          <ToneMark tone={2} size={48} strokeWidth={7} />
        </div>
        <h1 lang="zh-Hant" className="mt-4 font-serifhan text-3xl text-ink">
          {start?.label_zh ?? "完成"}
        </h1>
        {start && (
          <p className="mt-2 text-lg font-semibold text-ink">
            Starting you at {start.label}
            <span className="ml-2 text-sm font-normal text-ink-soft">{start.sublabel}</span>
          </p>
        )}
      </div>

      <div className="card mt-6">
        <h2 className="mb-3 text-sm font-semibold text-ink">Where you landed</h2>
        <div className="space-y-2">
          {summary.bands.map((b) => (
            <div key={b.hsk_level} className="flex items-center justify-between text-sm">
              <span className="text-ink">
                {b.label}
                <span className="ml-2 text-xs text-ink-faint">{b.sublabel}</span>
              </span>
              <span
                className={
                  b.status === "known"
                    ? "text-good"
                    : b.status === "partial"
                      ? "text-primary"
                      : b.status === "to_learn"
                        ? "text-ink-soft"
                        : "text-ink-faint"
                }
              >
                {b.status === "known"
                  ? "known"
                  : b.status === "partial"
                    ? "partly known"
                    : b.status === "to_learn"
                      ? "to learn"
                      : "not tested"}
                {b.assessed && b.score !== null && (
                  <span className="ml-2 text-xs text-ink-faint">{Math.round(b.score * 100)}%</span>
                )}
              </span>
            </div>
          ))}
        </div>
        <p className="mt-4 text-xs leading-relaxed text-ink-soft">
          {summary.known_cards} word{summary.known_cards === 1 ? "" : "s"} went into your deck as
          already-learned, {summary.new_cards} as new. Only the words you were actually asked —
          a short check can't judge the ones it never showed you.
        </p>
      </div>

      {summary.caveat && (
        <p className="mt-4 px-1 text-xs leading-relaxed text-ink-faint">{summary.caveat}</p>
      )}

      <button
        type="button"
        onClick={onDone}
        className="tap mt-6 w-full rounded-md bg-primary py-3 font-medium text-primary-ink"
      >
        Start learning
      </button>
    </div>
  );
}

export default function PlacementQuiz({ onDone }: { onDone: () => void }) {
  const [round, setRound] = useState<PlacementRound | null>(null);
  const [summary, setSummary] = useState<PlacementSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [started, setStarted] = useState(false);
  const [index, setIndex] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [answers, setAnswers] = useState<Answer[]>([]);
  const [visited, setVisited] = useState<number[]>([]);
  const [seen, setSeen] = useState<string[]>([]);

  useEffect(() => {
    api
      .placement()
      .then((p) => setRound(p.round))
      .catch((e) => setError(String(e.message ?? e)));
  }, []);

  const totalAsked = useMemo(() => answers.length + seen.length, [answers, seen]);

  async function submitRound(all: Answer[]) {
    if (!round) return;
    setBusy(true);
    try {
      const res = await api.placementRound({
        band: round.band,
        results: all,
        visited,
        seen,
      });
      if (res.done && res.summary) {
        setSummary(res.summary);
      } else if (res.round) {
        setVisited(res.visited ?? [...visited, round.band]);
        setSeen([...seen, ...all.map((a) => a.vocab_id).filter((v): v is string => !!v)]);
        setRound(res.round);
        setAnswers([]);
        setIndex(0);
      }
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
      setPicked(null);
    }
  }

  function answer(item: PlacementItem, correct: boolean) {
    if (picked || busy) return;
    setPicked(correct ? "correct" : "wrong");
    const next = [...answers, { vocab_id: item.vocab_id, correct }];

    setTimeout(() => {
      setPicked(null);
      if (round && index + 1 < round.items.length) {
        setAnswers(next);
        setIndex(index + 1);
      } else {
        setAnswers(next);
        void submitRound(next);
      }
    }, 220);
  }

  if (error) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-bad">{error}</div>;
  }
  if (summary) {
    return <Result summary={summary} onDone={onDone} />;
  }
  if (!round) {
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
          A few short rounds — reading, listening, and putting sentences together. It gets harder or
          easier depending on how you do, so it finds your level in three or four rounds rather than
          asking you everything. Words you know go into your deck as already-learned.
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

  if (busy) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Working out your level…</div>;
  }

  const item = round.items[index];

  return (
    <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-xl flex-col px-4 py-4">
      <Progress round={round} index={index} />
      {totalAsked > 0 && (
        <div className="mb-2 text-right text-xs text-ink-faint">{totalAsked} asked so far</div>
      )}

      <div className="card flex-1">
        {item.kind === "sentence_build" ? (
          <SentenceBuild item={item} locked={!!picked} onAnswer={(c) => answer(item, c)} />
        ) : (
          <Choice item={item} picked={picked} onAnswer={(c) => answer(item, c)} />
        )}
      </div>
    </div>
  );
}
