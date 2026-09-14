import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  api,
  type Tile,
  type ZhuyinExercise,
  type ZhuyinLesson as Lesson,
  type ZhuyinResult,
} from "../../api";
import { useSettings } from "../../SettingsContext";
import { useSpeak } from "../../audio";
import { gradeTiles, TileRack, TileTray, tilesMatch } from "../../components/Tiles";

interface Option {
  text: string;
  correct: boolean;
}

// Audio always plays a Han character, never the symbol itself: text-to-speech
// reads Han, and asking it for ㄅ gets you silence. The character carrying each
// symbol's teaching sound is in content/zhuyin.json.
function PlayButton({ text, big }: { text: string; big?: boolean }) {
  const { play, state } = useSpeak();
  const { settings } = useSettings();
  return (
    <button
      type="button"
      onClick={() => play(text, { voice: settings?.tts_voice, rate: settings?.playback_rate })}
      className={[
        "tap flex items-center justify-center rounded-full bg-primary text-primary-ink shadow-card transition-transform active:scale-95",
        big ? "h-20 w-20" : "h-12 w-12",
      ].join(" ")}
      aria-label="Play sound"
    >
      {state === "loading" ? (
        <span className="h-5 w-5 animate-spin rounded-full border-2 border-primary-ink border-t-transparent" />
      ) : (
        <svg viewBox="0 0 24 24" className={big ? "h-9 w-9" : "h-6 w-6"} fill="currentColor">
          <path d="M8 5v14l11-7z" />
        </svg>
      )}
    </button>
  );
}

function Glyph({ symbol, size = "text-6xl" }: { symbol: string; size?: string }) {
  return (
    <span lang="zh-Hant" className={`font-han ${size} leading-none text-ink`}>
      {symbol}
    </span>
  );
}

function Choices({
  options,
  chosen,
  onChoose,
  glyph,
}: {
  options: Option[];
  chosen: string | null;
  onChoose: (o: Option) => void;
  glyph?: boolean;
}) {
  return (
    <div className={["mt-5 grid gap-2", glyph ? "grid-cols-2" : ""].join(" ")}>
      {options.map((o) => {
        let cls = "border-border bg-surface hover:border-primary";
        if (chosen != null) {
          if (o.correct) cls = "border-good bg-good/10 text-good";
          else if (chosen === o.text) cls = "border-bad bg-accent-soft text-bad";
          else cls = "border-border bg-surface opacity-60";
        }
        return (
          <button
            key={o.text}
            type="button"
            disabled={chosen != null}
            onClick={() => onChoose(o)}
            lang={glyph ? "zh-Hant" : undefined}
            className={[
              "tap rounded-md border px-4 py-3 transition-colors",
              glyph ? "text-center font-han text-3xl" : "text-left text-base",
              cls,
            ].join(" ")}
          >
            {o.text}
          </button>
        );
      })}
    </div>
  );
}

function Continue({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="mt-6 w-full rounded-md bg-primary py-3 font-medium text-primary-ink"
    >
      Continue
    </button>
  );
}

interface DrillProps {
  ex: ZhuyinExercise;
  onDone: (correct: boolean) => void;
}

function Intro({ ex, onDone }: DrillProps) {
  const p = ex.payload as {
    symbol: string;
    pinyin: string;
    order: number;
    note: string;
    audio_text: string;
    voice: string;
    voice_pinyin: string;
    example: { traditional: string; pinyin: string; gloss: string };
  };
  return (
    <div className="text-center">
      <div className="text-xs uppercase tracking-wide text-ink-faint">
        #{p.order} in the order
      </div>
      <div className="mt-3">
        <Glyph symbol={p.symbol} />
      </div>
      <div className="mt-2 font-mono text-lg text-primary">{p.pinyin}</div>

      <div className="mt-5 flex justify-center">
        <PlayButton text={p.audio_text} big />
      </div>
      <div className="mt-2 text-sm text-ink-soft">
        said as{" "}
        <span lang="zh-Hant" className="font-han text-ink">
          {p.voice}
        </span>{" "}
        {p.voice_pinyin}
      </div>

      <p className="mt-5 text-left text-sm leading-relaxed text-ink-soft">{p.note}</p>

      <div className="mt-4 rounded-md bg-surface-2 p-3 text-left">
        <div className="text-xs uppercase tracking-wide text-ink-faint">in a word</div>
        <div className="mt-1 flex items-baseline gap-2">
          <span lang="zh-Hant" className="font-han text-xl text-ink">
            {p.example.traditional}
          </span>
          <span className="text-sm text-ink-soft">{p.example.pinyin}</span>
        </div>
        <div className="text-sm text-ink-soft">{p.example.gloss}</div>
      </div>

      <Continue onClick={() => onDone(true)} />
    </div>
  );
}

// Hear it, pick the symbol. The direction that reading zhuyin actually needs.
function SoundDrill({ ex, onDone }: DrillProps) {
  const p = ex.payload as { symbol: string; audio_text: string; options: Option[] };
  const [chosen, setChosen] = useState<string | null>(null);
  return (
    <div className="text-center">
      <div className="mb-4 text-sm text-ink-soft">Which symbol makes this sound?</div>
      <div className="flex justify-center">
        <PlayButton text={p.audio_text} big />
      </div>
      <Choices options={p.options} chosen={chosen} onChoose={(o) => setChosen(o.text)} glyph />
      {chosen != null && (
        <Continue onClick={() => onDone(p.options.find((o) => o.text === chosen)!.correct)} />
      )}
    </div>
  );
}

// See it, name it in pinyin — the bridge from the script he already reads.
function SymbolDrill({ ex, onDone }: DrillProps) {
  const p = ex.payload as { symbol: string; audio_text: string; options: Option[] };
  const [chosen, setChosen] = useState<string | null>(null);
  return (
    <div className="text-center">
      <div className="mb-4 text-sm text-ink-soft">What sound is this?</div>
      <Glyph symbol={p.symbol} />
      {chosen != null && (
        <div className="mt-4 flex justify-center">
          <PlayButton text={p.audio_text} />
        </div>
      )}
      <Choices options={p.options} chosen={chosen} onChoose={(o) => setChosen(o.text)} />
      {chosen != null && (
        <Continue onClick={() => onDone(p.options.find((o) => o.text === chosen)!.correct)} />
      )}
    </div>
  );
}

// The symbol doing its job in a real word, rather than reciting.
function WordDrill({ ex, onDone }: DrillProps) {
  const p = ex.payload as {
    symbol: string;
    traditional: string;
    pinyin: string;
    audio_text: string;
    options: Option[];
  };
  const [chosen, setChosen] = useState<string | null>(null);
  return (
    <div className="text-center">
      <div className="mb-3 text-sm text-ink-soft">
        A word with{" "}
        <span lang="zh-Hant" className="font-han text-base text-ink">
          {p.symbol}
        </span>{" "}
        in it — what does it mean?
      </div>
      <div lang="zh-Hant" className="font-han text-4xl text-ink">
        {p.traditional}
      </div>
      <div className="mt-1 text-sm text-ink-soft">{p.pinyin}</div>
      <div className="mt-3 flex justify-center">
        <PlayButton text={p.audio_text} />
      </div>
      <Choices options={p.options} chosen={chosen} onChoose={(o) => setChosen(o.text)} />
      {chosen != null && (
        <Continue onClick={() => onDone(p.options.find((o) => o.text === chosen)!.correct)} />
      )}
    </div>
  );
}

// Put the lesson back in recitation order — the half of the alphabet that
// symbol-by-symbol drilling never teaches.
function OrderDrill({ ex, onDone }: DrillProps) {
  const p = ex.payload as { symbol: string; tiles: Tile[]; answer: string[]; prompt: string };
  const [rack, setRack] = useState<Tile[]>(p.tiles);
  const [built, setBuilt] = useState<Tile[]>([]);
  const [checked, setChecked] = useState<null | boolean>(null);

  return (
    <div>
      <div className="mb-3 text-sm text-ink-soft">
        Put them back in order — the order you recite them in.
      </div>
      <TileTray
        tiles={built}
        states={checked == null ? undefined : gradeTiles(built, p.answer)}
        showReading
        onRemove={
          checked == null
            ? (i) => {
                setRack([...rack, built[i]]);
                setBuilt(built.filter((_, j) => j !== i));
              }
            : undefined
        }
        frame={checked == null ? "neutral" : checked ? "correct" : "wrong"}
      />
      {checked === false && (
        <div lang="zh-Hant" className="mt-2 font-han text-lg tracking-widest text-bad">
          {p.answer.join("")}
        </div>
      )}
      {checked == null && (
        <TileRack
          tiles={rack}
          showReading
          onPlace={(i) => {
            setBuilt([...built, rack[i]]);
            setRack(rack.filter((_, j) => j !== i));
          }}
        />
      )}
      {checked == null ? (
        <button
          type="button"
          disabled={built.length === 0}
          onClick={() => setChecked(tilesMatch(built, p.answer))}
          className="mt-6 w-full rounded-md bg-primary py-3 font-medium text-primary-ink disabled:opacity-40"
        >
          Check
        </button>
      ) : (
        <Continue onClick={() => onDone(checked)} />
      )}
    </div>
  );
}

function renderDrill(ex: ZhuyinExercise, onDone: (c: boolean) => void) {
  const props = { ex, onDone };
  switch (ex.kind) {
    case "zhuyin_intro":
      return <Intro {...props} />;
    case "zhuyin_sound":
      return <SoundDrill {...props} />;
    case "zhuyin_symbol":
      return <SymbolDrill {...props} />;
    case "zhuyin_word":
      return <WordDrill {...props} />;
    case "zhuyin_order":
      return <OrderDrill {...props} />;
    default:
      return null;
  }
}

function Complete({
  lesson,
  outcome,
  onExit,
}: {
  lesson: Lesson;
  outcome: ZhuyinResult;
  onExit: () => void;
}) {
  return (
    <div className="mx-auto max-w-xl px-4 py-10 text-center">
      <div lang="zh-Hant" className="font-han text-4xl tracking-widest text-ink">
        {lesson.symbols.join("")}
      </div>
      <div className="mt-4 text-2xl font-medium text-ink">
        {Math.round(outcome.score * 100)}%
      </div>
      <p className="mt-2 text-sm text-ink-soft">
        {outcome.passed
          ? outcome.new_srs_cards > 0
            ? `${outcome.new_srs_cards} symbols added to your reviews.`
            : "Passed — these are already in your reviews."
          : "Not quite yet. Run it again — nothing is lost."}
      </p>
      <button
        type="button"
        onClick={onExit}
        className="mt-6 w-full rounded-md bg-primary py-3 font-medium text-primary-ink"
      >
        Done
      </button>
    </div>
  );
}

export default function ZhuyinLesson() {
  const { lessonId } = useParams();
  const navigate = useNavigate();

  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [results, setResults] = useState<{ symbol: string; correct: boolean }[]>([]);
  const [outcome, setOutcome] = useState<ZhuyinResult | null>(null);

  useEffect(() => {
    if (!lessonId) return;
    api.zhuyinLesson(lessonId).then(setLesson).catch((e) => setError(String(e)));
  }, [lessonId]);

  async function handleDone(correct: boolean) {
    if (!lesson || !lessonId) return;
    const ex = lesson.exercises[index];
    const next = ex.gradable
      ? [...results, { symbol: ex.payload.symbol, correct }]
      : results;
    setResults(next);

    if (index + 1 < lesson.exercises.length) {
      setIndex(index + 1);
      return;
    }
    try {
      setOutcome(await api.zhuyinResult(lessonId, next));
    } catch (e) {
      setError(String(e));
    }
  }

  if (error) {
    return (
      <div className="mx-auto max-w-xl px-4 py-10 text-center">
        <p className="text-bad">{error}</p>
        <Link to="/learn/zhuyin" className="mt-4 inline-block text-primary underline">
          Back to the 注音 course
        </Link>
      </div>
    );
  }
  if (!lesson) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Loading…</div>;
  }
  if (outcome) {
    return <Complete lesson={lesson} outcome={outcome} onExit={() => navigate("/learn/zhuyin")} />;
  }

  const ex = lesson.exercises[index];
  const progress = Math.round((index / lesson.exercises.length) * 100);

  return (
    <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-xl flex-col px-4 py-4">
      <div className="mb-4 flex items-center gap-3">
        <button
          type="button"
          onClick={() => navigate("/learn/zhuyin")}
          className="tap text-ink-faint hover:text-ink"
          aria-label="Exit lesson"
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
      <div className="flex-1">
        <div key={ex.id} className="card">
          {renderDrill(ex, handleDone)}
        </div>
      </div>
    </div>
  );
}
