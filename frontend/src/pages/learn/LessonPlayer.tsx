import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type DrillResult, type Exercise, type Lesson, type LessonResult, type Option } from "../../api";
import { useSettings } from "../../SettingsContext";
import { useSpeak } from "../../audio";
import { Speakable } from "../../components/Speakable";
import { ToneMark } from "../../components/ToneMark";

// Compare two Han strings ignoring spaces/punctuation (for listen-and-type).
function normalize(s: string): string {
  return s.replace(/[\s，。？！、,.?!]/g, "");
}

function PlayButton({ text, big }: { text: string; big?: boolean }) {
  const { play, state } = useSpeak();
  const { settings } = useSettings();
  return (
    <button
      type="button"
      onClick={() => play(text, { voice: settings?.tts_voice, rate: settings?.playback_rate })}
      className={[
        "tap flex items-center justify-center rounded-full bg-primary text-primary-ink shadow-card transition-transform active:scale-95",
        big ? "h-16 w-16" : "h-12 w-12",
      ].join(" ")}
      aria-label="Play audio"
    >
      {state === "loading" ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary-ink border-t-transparent" />
      ) : (
        <svg viewBox="0 0 24 24" className={big ? "h-7 w-7" : "h-6 w-6"} fill="currentColor">
          <path d="M8 5v14l11-7z" />
        </svg>
      )}
    </button>
  );
}

function Pinyin({ text, show }: { text?: string; show: boolean }) {
  if (!text || !show) return null;
  return <div className="font-sans text-sm text-ink-soft">{text}</div>;
}

// --- Multiple-choice drill (shared by audio_meaning / cloze / translate) ---
function ChoiceGrid({
  options,
  chosen,
  onChoose,
}: {
  options: Option[];
  chosen: string | null;
  onChoose: (o: Option) => void;
}) {
  return (
    <div className="mt-5 grid gap-2">
      {options.map((o) => {
        const isChosen = chosen === o.text;
        let cls = "border-border bg-surface hover:border-primary";
        if (chosen != null) {
          if (o.correct) cls = "border-good bg-good/10 text-good";
          else if (isChosen) cls = "border-bad bg-accent-soft text-bad";
          else cls = "border-border bg-surface opacity-60";
        }
        return (
          <button
            key={o.text}
            type="button"
            disabled={chosen != null}
            onClick={() => onChoose(o)}
            className={["tap rounded-md border px-4 py-3 text-left text-base transition-colors", cls].join(" ")}
          >
            {o.text}
          </button>
        );
      })}
    </div>
  );
}

interface DrillProps {
  ex: Exercise;
  showPinyin: boolean;
  onDone: (correct: boolean) => void;
}

function VocabIntro({ ex, showPinyin, onDone }: DrillProps) {
  const p = ex.payload;
  return (
    <div className="text-center">
      <Pinyin text={p.pinyin} show={showPinyin} />
      <Speakable text={p.traditional} showIcon={false} className="mx-auto mt-1 justify-center">
        <span lang="zh-Hant" className="font-serifhan text-hero-lg text-ink">
          {p.traditional}
        </span>
      </Speakable>
      <div className="mt-3">
        <PlayButtonInline text={p.traditional} />
      </div>
      <p className="mt-4 text-lg text-ink">{p.gloss}</p>
      {p.taiwan_note && (
        <p lang="zh-Hant" className="mx-auto mt-2 max-w-sm rounded-md bg-accent-soft px-3 py-2 text-sm text-ink-soft">
          🇹🇼 {p.taiwan_note}
        </p>
      )}
      {p.example && (
        <div className="mx-auto mt-5 max-w-sm rounded-md border border-border bg-surface-2 p-3 text-left">
          <Speakable text={p.example.hanzi} className="font-han text-base text-ink">
            {p.example.hanzi}
          </Speakable>
          <Pinyin text={p.example.pinyin} show={showPinyin} />
          <div className="mt-1 text-sm text-ink-soft">{p.example.gloss}</div>
        </div>
      )}
      <ContinueButton onClick={() => onDone(true)} />
    </div>
  );
}

function PlayButtonInline({ text }: { text: string }) {
  return (
    <div className="flex justify-center">
      <PlayButton text={text} />
    </div>
  );
}

function GrammarCard({ ex, showPinyin, onDone }: DrillProps) {
  const p = ex.payload;
  return (
    <div>
      <div className="mb-1 text-xs font-medium uppercase tracking-wide text-primary">Grammar</div>
      <h3 lang="zh-Hant" className="font-han text-xl text-ink">
        {p.title}
      </h3>
      <div className="mt-3 rounded-md bg-surface-2 px-3 py-2 font-mono text-sm text-ink">{p.pattern}</div>
      <p className="mt-3 text-sm leading-relaxed text-ink-soft">{p.explanation}</p>
      <div className="mt-4 space-y-2">
        {p.examples.map((ex2: { hanzi: string; pinyin: string; gloss: string }, i: number) => (
          <div key={i} className="rounded-md border border-border p-3">
            <Speakable text={ex2.hanzi} className="font-han text-base text-ink">
              {ex2.hanzi}
            </Speakable>
            <Pinyin text={ex2.pinyin} show={showPinyin} />
            <div className="mt-1 text-sm text-ink-soft">{ex2.gloss}</div>
          </div>
        ))}
      </div>
      <ContinueButton onClick={() => onDone(true)} />
    </div>
  );
}

function MatchDrill({ ex, onDone }: DrillProps) {
  const p = ex.payload;
  type Pair = { vocab_id: string; traditional: string; gloss: string };
  const pairs: Pair[] = p.pairs;
  const glosses = useMemo(() => [...pairs].sort(() => Math.random() - 0.5), [pairs]);
  const [pickedChar, setPickedChar] = useState<string | null>(null);
  const [matched, setMatched] = useState<Set<string>>(new Set());
  const [mistakes, setMistakes] = useState(0);
  const [wrongFlash, setWrongFlash] = useState<string | null>(null);

  function tryMatch(gloss: Pair) {
    if (!pickedChar) return;
    const pair = pairs.find((x) => x.traditional === pickedChar)!;
    if (pair.gloss === gloss.gloss) {
      const next = new Set(matched).add(pair.traditional);
      setMatched(next);
      setPickedChar(null);
      if (next.size === pairs.length) {
        setTimeout(() => onDone(mistakes === 0), 350);
      }
    } else {
      setMistakes((m) => m + 1);
      setWrongFlash(gloss.gloss);
      setTimeout(() => setWrongFlash(null), 350);
      setPickedChar(null);
    }
  }

  return (
    <div>
      <div className="mb-4 text-sm text-ink-soft">Match each word to its meaning.</div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          {pairs.map((pr) => (
            <button
              key={pr.traditional}
              type="button"
              disabled={matched.has(pr.traditional)}
              onClick={() => setPickedChar(pr.traditional)}
              lang="zh-Hant"
              className={[
                "tap w-full rounded-md border px-3 py-3 font-han text-lg transition-colors",
                matched.has(pr.traditional)
                  ? "border-good bg-good/10 text-good"
                  : pickedChar === pr.traditional
                    ? "border-primary bg-primary-soft"
                    : "border-border bg-surface hover:border-primary",
              ].join(" ")}
            >
              {pr.traditional}
            </button>
          ))}
        </div>
        <div className="space-y-2">
          {glosses.map((pr) => {
            const done = matched.has(pr.traditional);
            return (
              <button
                key={pr.gloss}
                type="button"
                disabled={done}
                onClick={() => tryMatch(pr)}
                className={[
                  "tap w-full rounded-md border px-3 py-3 text-sm transition-colors",
                  done
                    ? "border-good bg-good/10 text-good"
                    : wrongFlash === pr.gloss
                      ? "border-bad bg-accent-soft text-bad"
                      : "border-border bg-surface hover:border-primary",
                ].join(" ")}
              >
                {pr.gloss}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function AudioMeaning({ ex, showPinyin, onDone }: DrillProps) {
  const p = ex.payload;
  const [chosen, setChosen] = useState<string | null>(null);
  return (
    <div className="text-center">
      <div className="mb-2 text-sm text-ink-soft">What does this mean?</div>
      <div className="flex justify-center">
        <PlayButton text={p.audio_text} big />
      </div>
      <Pinyin text={showPinyin ? p.pinyin : undefined} show={showPinyin} />
      <ChoiceGrid options={p.options} chosen={chosen} onChoose={(o) => setChosen(o.text)} />
      {chosen != null && <ContinueButton onClick={() => onDone(p.options.find((o: Option) => o.text === chosen)!.correct)} />}
    </div>
  );
}

function ClozeDrill({ ex, showPinyin, onDone }: DrillProps) {
  const p = ex.payload;
  const [chosen, setChosen] = useState<string | null>(null);
  return (
    <div>
      <div className="mb-3 text-sm text-ink-soft">Fill in the blank.</div>
      <div className="rounded-md border border-border bg-surface-2 p-4 text-center">
        <Speakable text={p.audio_text} showIcon lang="zh-Hant" className="justify-center font-han text-2xl text-ink">
          <span lang="zh-Hant" className="font-han text-2xl text-ink">
            {p.tokens.join(" ")}
          </span>
        </Speakable>
        <Pinyin text={p.pinyin} show={showPinyin} />
        {p.gloss && <div className="mt-1 text-sm text-ink-soft">{p.gloss}</div>}
      </div>
      <ChoiceGrid options={p.options} chosen={chosen} onChoose={(o) => setChosen(o.text)} />
      {chosen != null && <ContinueButton onClick={() => onDone(p.options.find((o: Option) => o.text === chosen)!.correct)} />}
    </div>
  );
}

function TranslateDrill({ ex, showPinyin, onDone }: DrillProps) {
  const p = ex.payload;
  const [chosen, setChosen] = useState<string | null>(null);
  return (
    <div>
      <div className="mb-3 text-sm text-ink-soft">Choose the translation.</div>
      <div className="rounded-md border border-border bg-surface-2 p-4 text-center">
        <Speakable text={p.audio_text} lang="zh-Hant" className="justify-center font-han text-2xl text-ink">
          <span lang="zh-Hant" className="font-han text-2xl text-ink">
            {p.prompt_hanzi}
          </span>
        </Speakable>
        <Pinyin text={p.pinyin} show={showPinyin} />
      </div>
      <ChoiceGrid options={p.options} chosen={chosen} onChoose={(o) => setChosen(o.text)} />
      {chosen != null && <ContinueButton onClick={() => onDone(p.options.find((o: Option) => o.text === chosen)!.correct)} />}
    </div>
  );
}

function TileBuild({ ex, showPinyin, onDone }: DrillProps) {
  const p = ex.payload;
  const answer: string[] = p.answer;
  const [tiles, setTiles] = useState<string[]>(p.tiles);
  const [built, setBuilt] = useState<string[]>([]);
  const [checked, setChecked] = useState<null | boolean>(null);

  function place(i: number) {
    if (checked != null) return;
    setBuilt([...built, tiles[i]]);
    setTiles(tiles.filter((_, j) => j !== i));
  }
  function remove(i: number) {
    if (checked != null) return;
    setTiles([...tiles, built[i]]);
    setBuilt(built.filter((_, j) => j !== i));
  }
  function check() {
    const ok = built.join("") === answer.join("");
    setChecked(ok);
  }

  return (
    <div>
      <div className="mb-3 text-sm text-ink-soft">Build the sentence: “{p.gloss}”.</div>
      <div
        className={[
          "min-h-[3.5rem] rounded-md border-2 border-dashed p-3",
          checked === true ? "border-good bg-good/10" : checked === false ? "border-bad bg-accent-soft" : "border-border",
        ].join(" ")}
      >
        <div className="flex flex-wrap gap-2">
          {built.map((t, i) => (
            <button
              key={i}
              type="button"
              onClick={() => remove(i)}
              lang="zh-Hant"
              className="tap rounded bg-primary px-3 py-2 font-han text-lg text-primary-ink"
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      {checked === false && (
        <div lang="zh-Hant" className="mt-2 text-sm text-bad">
          Correct: {answer.join(" ")}
        </div>
      )}
      <Pinyin text={showPinyin ? p.pinyin : undefined} show={showPinyin && checked != null} />
      <div className="mt-4 flex flex-wrap gap-2">
        {tiles.map((t, i) => (
          <button
            key={i}
            type="button"
            onClick={() => place(i)}
            lang="zh-Hant"
            className="tap rounded border border-border bg-surface px-3 py-2 font-han text-lg text-ink hover:border-primary"
          >
            {t}
          </button>
        ))}
      </div>
      {checked == null ? (
        <button
          type="button"
          disabled={built.length === 0}
          onClick={check}
          className="btn-continue mt-6 w-full rounded-md bg-primary py-3 font-medium text-primary-ink disabled:opacity-40"
        >
          Check
        </button>
      ) : (
        <ContinueButton onClick={() => onDone(checked)} />
      )}
    </div>
  );
}

function ListenType({ ex, showPinyin, onDone }: DrillProps) {
  const p = ex.payload;
  const [value, setValue] = useState("");
  const [checked, setChecked] = useState<null | boolean>(null);
  function check() {
    setChecked(normalize(value) === normalize(p.answer));
  }
  return (
    <div className="text-center">
      <div className="mb-2 text-sm text-ink-soft">Type what you hear.</div>
      <div className="flex justify-center">
        <PlayButton text={p.audio_text} big />
      </div>
      <input
        lang="zh-Hant"
        value={value}
        disabled={checked != null}
        onChange={(e) => setValue(e.target.value)}
        placeholder="輸入你聽到的…"
        className="mt-5 w-full rounded-md border border-border bg-surface px-4 py-3 text-center font-han text-xl text-ink"
      />
      {checked != null && (
        <div className="mt-3">
          <div lang="zh-Hant" className={["font-han text-lg", checked ? "text-good" : "text-bad"].join(" ")}>
            {checked ? "✓ " : ""}
            {p.answer}
          </div>
          <Pinyin text={showPinyin ? p.pinyin : undefined} show={showPinyin} />
          <div className="text-sm text-ink-soft">{p.gloss}</div>
        </div>
      )}
      {checked == null ? (
        <button
          type="button"
          disabled={!value}
          onClick={check}
          className="mt-6 w-full rounded-md bg-primary py-3 font-medium text-primary-ink disabled:opacity-40"
        >
          Check
        </button>
      ) : (
        <ContinueButton onClick={() => onDone(checked)} />
      )}
    </div>
  );
}

function DialogueDrill({ ex, showPinyin: initialShow, onDone }: DrillProps) {
  const p = ex.payload;
  const [showEn, setShowEn] = useState(false);
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm text-ink-soft">Dialogue · tap a line to hear it</div>
        <button
          type="button"
          onClick={() => setShowEn((v) => !v)}
          className="rounded-full border border-border px-3 py-1 text-xs text-ink-soft"
        >
          {showEn ? "Hide English" : "Show English"}
        </button>
      </div>
      <div className="space-y-3">
        {p.lines.map((line: { speaker: string; hanzi: string; pinyin: string; gloss: string }, i: number) => (
          <div key={i} className="rounded-md border border-border p-3">
            <div className="text-xs font-medium text-primary">{line.speaker}</div>
            <Speakable text={line.hanzi} className="mt-0.5 font-han text-lg text-ink">
              {line.hanzi}
            </Speakable>
            <Pinyin text={line.pinyin} show={initialShow} />
            {showEn && <div className="mt-0.5 text-sm text-ink-soft">{line.gloss}</div>}
          </div>
        ))}
      </div>
      <ContinueButton onClick={() => onDone(true)} />
    </div>
  );
}

function ContinueButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-6 w-full rounded-md bg-primary py-3 font-medium text-primary-ink transition-transform active:scale-[0.99]"
    >
      Continue
    </button>
  );
}

function renderDrill(ex: Exercise, showPinyin: boolean, onDone: (c: boolean) => void) {
  const props = { ex, showPinyin, onDone };
  switch (ex.kind) {
    case "vocab_intro":
      return <VocabIntro {...props} />;
    case "grammar":
      return <GrammarCard {...props} />;
    case "match":
      return <MatchDrill {...props} />;
    case "audio_meaning":
      return <AudioMeaning {...props} />;
    case "cloze":
      return <ClozeDrill {...props} />;
    case "translate":
      return <TranslateDrill {...props} />;
    case "tile_build":
      return <TileBuild {...props} />;
    case "listen_type":
      return <ListenType {...props} />;
    case "dialogue":
      return <DialogueDrill {...props} />;
    default:
      return null;
  }
}

export default function LessonPlayer() {
  const { lessonId } = useParams();
  const navigate = useNavigate();
  const { settings } = useSettings();
  const showPinyin = settings?.show_pinyin ?? true;

  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [results, setResults] = useState<DrillResult[]>([]);
  const [outcome, setOutcome] = useState<LessonResult | null>(null);

  useEffect(() => {
    if (!lessonId) return;
    api.lesson(lessonId).then(setLesson).catch((e) => setError(String(e)));
  }, [lessonId]);

  async function handleDone(correct: boolean) {
    if (!lesson) return;
    const ex = lesson.exercises[index];
    const nextResults = ex.gradable
      ? [
          ...results,
          {
            id: ex.id,
            kind: ex.kind,
            correct,
            vocab_id: ex.payload.vocab_id ?? null,
            grammar_id: ex.payload.grammar_id ?? null,
          },
        ]
      : results;
    setResults(nextResults);

    if (index + 1 < lesson.exercises.length) {
      setIndex(index + 1);
    } else if (lessonId) {
      try {
        const res = await api.lessonResult(lessonId, nextResults);
        setOutcome(res);
      } catch (e) {
        setError(String(e));
      }
    }
  }

  if (error) {
    return (
      <div className="mx-auto max-w-xl px-4 py-10 text-center">
        <p className="text-bad">{error}</p>
        <Link to="/learn" className="mt-4 inline-block text-primary underline">
          Back to Learn
        </Link>
      </div>
    );
  }
  if (!lesson) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Loading lesson…</div>;
  }

  if (outcome) {
    return <LessonComplete lesson={lesson} outcome={outcome} onExit={() => navigate("/learn")} />;
  }

  const ex = lesson.exercises[index];
  const progress = Math.round((index / lesson.exercises.length) * 100);

  return (
    <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-xl flex-col px-4 py-4">
      <div className="mb-4 flex items-center gap-3">
        <button
          type="button"
          onClick={() => navigate("/learn")}
          className="tap text-ink-faint hover:text-ink"
          aria-label="Exit lesson"
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
          <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} />
        </div>
      </div>
      <div className="flex-1">
        <div key={ex.id} className="card">
          {renderDrill(ex, showPinyin, handleDone)}
        </div>
      </div>
    </div>
  );
}

function LessonComplete({
  lesson,
  outcome,
  onExit,
}: {
  lesson: Lesson;
  outcome: LessonResult;
  onExit: () => void;
}) {
  const pct = Math.round(outcome.score * 100);
  const tone = outcome.passed ? 2 : 3;
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-xl flex-col items-center justify-center px-6 text-center">
      <div className={outcome.passed ? "text-good" : "text-warn"}>
        <ToneMark tone={tone} size={56} strokeWidth={7} />
      </div>
      <h1 lang="zh-Hant" className="mt-4 font-serifhan text-4xl text-ink">
        {outcome.passed ? "過關！" : "再試一次"}
      </h1>
      <p className="mt-2 text-lg text-ink">
        {outcome.correct} / {outcome.total} correct · {pct}%
      </p>
      {outcome.passed ? (
        <p className="mt-2 text-sm text-ink-soft">
          {lesson.title} complete.
          {outcome.new_srs_cards > 0 && ` ${outcome.new_srs_cards} words added to your review deck.`}
          {outcome.unlocked_next && " Next lesson unlocked."}
        </p>
      ) : (
        <p className="mt-2 text-sm text-ink-soft">Score ≥ 80% to complete the lesson. Give it another go.</p>
      )}
      <button
        type="button"
        onClick={onExit}
        className="mt-8 w-full max-w-xs rounded-md bg-primary py-3 font-medium text-primary-ink"
      >
        Back to Learn
      </button>
    </div>
  );
}
