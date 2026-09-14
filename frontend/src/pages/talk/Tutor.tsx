import { useEffect, useRef, useState } from "react";
import { api, type TutorAnswer, type TutorFocus } from "../../api";
import { Speakable } from "../../components/Speakable";
import { ToneMark } from "../../components/ToneMark";

// Ask-a-question tutor (spec §3.7).
//
// The counterpart to the roleplay in Chat.tsx: there Claude stays in character
// and never explains; here explaining is the entire job, so answers come back in
// English with Traditional-character examples.
//
// `focus` is what the learner was looking at when the question occurred to him —
// a word, a grammar point, a sentence. It's what turns "why is 了 here" from an
// unanswerable question into an answerable one, and it's what §3.7 means by
// giving the tutor context about what he's currently working on.

const SUGGESTIONS = [
  "What's the difference between 才 and 就?",
  "When do I use 的 vs 得 vs 地?",
  "Why does 有 + verb mean past tense in Taiwan?",
  "Is 不好意思 the same as 對不起?",
];

type Turn = { question: string; answer?: TutorAnswer; error?: string };

function Answer({ a }: { a: TutorAnswer }) {
  return (
    <div className="card">
      <p className="whitespace-pre-wrap text-base leading-relaxed text-ink">{a.answer}</p>

      {a.examples.length > 0 && (
        <div className="mt-4 space-y-2">
          {a.examples.map((ex, i) => (
            <div key={i} className="rounded-md border border-border p-3">
              <Speakable text={ex.hanzi} showIcon lang="zh-Hant" className="font-han text-lg text-ink">
                <span lang="zh-Hant" className="font-han text-lg text-ink">
                  {ex.hanzi}
                </span>
              </Speakable>
              <div className="mt-0.5 text-sm text-ink-soft">{ex.pinyin}</div>
              <div className="text-sm text-ink-soft">{ex.gloss}</div>
            </div>
          ))}
        </div>
      )}

      {a.taiwan_note && (
        <p
          lang="zh-Hant"
          className="mt-4 rounded-md border border-primary/30 bg-primary-soft/30 px-3 py-2 font-han text-sm leading-relaxed text-ink"
        >
          🇹🇼 {a.taiwan_note}
        </p>
      )}

      {a.related.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {a.related.map((r) => (
            <span key={r} className="rounded-full bg-surface-2 px-2 py-0.5 text-xs text-ink-soft">
              {r}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Tutor({ focus, onClearFocus }: { focus?: TutorFocus; onClearFocus?: () => void }) {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [threadId, setThreadId] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api
      .tutorStatus()
      .then((s) => setAvailable(s.available))
      .catch(() => setAvailable(false));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setQuestion("");
    setTurns((t) => [...t, { question: q }]);
    setBusy(true);
    try {
      const answer = await api.tutorAsk({ question: q, focus, thread_id: threadId });
      setThreadId(answer.thread_id);
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, answer } : turn)));
    } catch (e) {
      const msg = String((e as Error).message ?? e);
      setTurns((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: msg } : turn)));
    } finally {
      setBusy(false);
    }
  }

  if (available === false) {
    return (
      <div className="mx-auto max-w-xl px-4 py-10 text-center">
        <div className="mx-auto w-fit text-ink-faint">
          <ToneMark tone={3} size={44} strokeWidth={7} />
        </div>
        <h2 className="mt-4 text-lg font-semibold text-ink">Tutor needs an API key</h2>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-ink-soft">
          Asking questions uses the Claude API — one of only two things in this app that
          go online. Add a key on the <strong>Me</strong> tab and it'll work here and in
          Roleplay. Everything else keeps running without it.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-[calc(100vh-8rem)] max-w-xl flex-col px-4 py-4">
      {focus && (
        <div className="mb-3 flex items-center justify-between rounded-md border border-primary/30 bg-primary-soft/20 px-3 py-2">
          <span className="text-xs text-ink-soft">
            Asking about{" "}
            <span lang="zh-Hant" className="font-han text-sm text-ink">
              {focus.text ?? focus.id}
            </span>
          </span>
          {onClearFocus && (
            <button type="button" onClick={onClearFocus} className="tap text-xs text-ink-faint hover:text-ink">
              Clear
            </button>
          )}
        </div>
      )}

      <div className="flex-1 space-y-4">
        {turns.length === 0 && (
          <div className="py-6 text-center">
            <p className="text-sm text-ink-soft">
              Ask anything about the Mandarin you're studying.
            </p>
            <div className="mt-4 grid gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => send(s)}
                  className="tap rounded-md border border-border bg-surface px-3 py-2 text-left text-sm text-ink-soft hover:border-primary hover:text-ink"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) => (
          <div key={i} className="space-y-2">
            <div className="ml-auto w-fit max-w-[85%] rounded-md bg-primary px-3 py-2 text-sm text-primary-ink">
              {t.question}
            </div>
            {t.answer && <Answer a={t.answer} />}
            {t.error && (
              <div className="rounded-md border border-bad/40 bg-accent-soft px-3 py-2 text-sm text-bad">
                {t.error}
              </div>
            )}
          </div>
        ))}

        {busy && <div className="text-sm text-ink-soft">Thinking…</div>}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(question);
        }}
        className="sticky bottom-0 mt-4 flex gap-2 bg-surface/95 py-3 backdrop-blur"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question…"
          disabled={busy}
          className="flex-1 rounded-md border border-border bg-surface px-3 py-2 text-base text-ink outline-none focus:border-primary"
        />
        <button
          type="submit"
          disabled={busy || !question.trim()}
          className="tap rounded-md bg-primary px-4 py-2 font-medium text-primary-ink disabled:opacity-40"
        >
          Ask
        </button>
      </form>
    </div>
  );
}
