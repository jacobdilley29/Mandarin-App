import { useEffect, useRef, useState } from "react";
import { api, type NewWord, type RecapWord, type Scenario, type TeacherNote } from "../../api";
import { useRecorder } from "../../audio_record";
import { useSpeak } from "../../audio";
import { useSettings } from "../../SettingsContext";

interface Msg {
  role: "user" | "assistant";
  text: string;
  pinyin?: string;
  note?: TeacherNote | null;
}

function TeacherNoteBox({ note }: { note: TeacherNote }) {
  const [open, setOpen] = useState(false);
  const has = note.corrections.length > 0 || note.better;
  if (!has) return null;
  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs font-medium text-primary"
      >
        <span>📝 Teacher note</span>
        <span className="text-ink-faint">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="mt-1 rounded-md border border-border bg-surface-2 p-2 text-xs text-ink-soft">
          {note.corrections.map((c, i) => (
            <div key={i}>• {c}</div>
          ))}
          {note.better && (
            <div className="mt-1">
              More natural: <span lang="zh-Hant" className="font-han text-ink">{note.better}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Chat({ scenario, onExit }: { scenario: Scenario; onExit: () => void }) {
  const { settings } = useSettings();
  const { play } = useSpeak();
  const { state: recState, start, stop, supported } = useRecorder();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recap, setRecap] = useState<RecapWord[] | null>(null);
  const [added, setAdded] = useState<number | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .talkStart(scenario.id)
      .then((r) => {
        setSessionId(r.session_id);
        setMessages([{ role: "assistant", text: r.opening.hanzi, pinyin: r.opening.pinyin }]);
      })
      .catch((e) => setError(String(e)));
  }, [scenario.id]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send() {
    if (!sessionId || !input.trim() || busy) return;
    const text = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      const turn = await api.talkMessage(sessionId, text);
      setMessages((m) => [
        ...m,
        { role: "assistant", text: turn.reply, pinyin: turn.reply_pinyin, note: turn.teacher_note },
      ]);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function micInput() {
    const wav = await start(); // resolves on stop
    if (!wav) return;
    try {
      const form = new FormData();
      form.append("audio", wav, "rec.wav");
      const res = await fetch("/api/talk/transcribe", { method: "POST", body: form });
      if (!res.ok) throw new Error("transcription unavailable");
      const { text } = await res.json();
      setInput(text || ""); // show for confirmation before sending (spec §3.5)
    } catch {
      setError("Speech input needs faster-whisper installed. Type instead.");
    }
  }

  async function endConversation() {
    if (!sessionId) return;
    try {
      const r = await api.talkRecap(sessionId);
      setRecap(r.words);
    } catch (e) {
      setError(String(e));
    }
  }

  async function addWords(words: NewWord[]) {
    try {
      const r = await api.talkRecapAdd(words);
      setAdded(r.added);
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-4rem)] max-w-xl flex-col">
      <header className="flex items-center gap-2 border-b border-border px-4 py-3">
        <button type="button" onClick={onExit} className="tap text-ink-faint" aria-label="Back">
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M15 18l-6-6 6-6" />
          </svg>
        </button>
        <span className="text-2xl">{scenario.emoji}</span>
        <div className="flex-1">
          <div lang="zh-Hant" className="font-han text-sm text-ink">{scenario.title}</div>
          <div className="text-xs text-ink-soft">{scenario.en}</div>
        </div>
        <button type="button" onClick={endConversation} className="rounded-full border border-border px-3 py-1 text-xs text-ink-soft">
          End
        </button>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={["max-w-[80%]", m.role === "user" ? "text-right" : ""].join(" ")}>
              <div
                className={[
                  "rounded-2xl px-3 py-2",
                  m.role === "user" ? "bg-primary text-primary-ink" : "border border-border bg-surface",
                ].join(" ")}
              >
                {m.role === "assistant" ? (
                  <button
                    type="button"
                    lang="zh-Hant"
                    onClick={() => play(m.text, { voice: settings?.tts_voice, rate: settings?.playback_rate })}
                    className="text-left font-han text-base text-ink"
                  >
                    {m.text} <span className="text-xs text-ink-faint">🔊</span>
                  </button>
                ) : (
                  <span lang="zh-Hant" className="font-han text-base">{m.text}</span>
                )}
                {m.role === "assistant" && settings?.show_pinyin && m.pinyin && (
                  <div className="text-xs text-ink-soft">{m.pinyin}</div>
                )}
              </div>
              {m.role === "assistant" && m.note && <TeacherNoteBox note={m.note} />}
            </div>
          </div>
        ))}
        {busy && <div className="text-center text-xs text-ink-faint">…</div>}
        <div ref={endRef} />
      </div>

      {error && <div className="px-4 pb-2 text-xs text-warn">{error}</div>}

      <div className="flex items-center gap-2 border-t border-border px-3 py-3" style={{ paddingBottom: "calc(0.75rem + env(safe-area-inset-bottom))" }}>
        {supported && (
          <button
            type="button"
            onClick={recState === "recording" ? stop : micInput}
            className={[
              "tap flex h-11 w-11 shrink-0 items-center justify-center rounded-full",
              recState === "recording" ? "bg-bad text-primary-ink" : "border border-border text-ink-soft",
            ].join(" ")}
            aria-label="Speak"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
              <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3z" />
            </svg>
          </button>
        )}
        <input
          lang="zh-Hant"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="用中文回覆…"
          className="tap flex-1 rounded-full border border-border bg-surface px-4 font-han text-base text-ink"
        />
        <button
          type="button"
          onClick={send}
          disabled={!input.trim() || busy}
          className="tap flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-primary text-primary-ink disabled:opacity-40"
          aria-label="Send"
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor"><path d="M2 21l21-9L2 3v7l15 2-15 2z" /></svg>
        </button>
      </div>

      {recap && (
        <div className="fixed inset-0 z-30 flex items-end justify-center bg-black/40 p-4" onClick={() => setRecap(null)}>
          <div className="w-full max-w-xl rounded-lg bg-surface p-5" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-ink">Recap</h3>
            {added != null ? (
              <p className="mt-2 text-sm text-good">✓ Added {added} words to your review deck.</p>
            ) : recap.length === 0 ? (
              <p className="mt-2 text-sm text-ink-soft">No new words this time. Nicely done!</p>
            ) : (
              <>
                <p className="mt-1 text-sm text-ink-soft">New words you met — add them to your review deck?</p>
                <ul className="mt-3 max-h-60 space-y-2 overflow-y-auto">
                  {recap.map((w) => (
                    <li key={w.hanzi} className="flex items-center justify-between rounded-md border border-border p-2">
                      <div>
                        <span lang="zh-Hant" className="font-han text-lg text-ink">{w.hanzi}</span>
                        <span className="ml-2 text-sm text-ink-soft">{w.pinyin}</span>
                        <div className="text-xs text-ink-soft">{w.gloss}</div>
                      </div>
                      {w.in_deck && <span className="text-xs text-ink-faint">in deck</span>}
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  onClick={() => addWords(recap.filter((w) => !w.in_deck))}
                  className="mt-4 w-full rounded-md bg-primary py-3 font-medium text-primary-ink"
                >
                  Add {recap.filter((w) => !w.in_deck).length} to review deck
                </button>
              </>
            )}
            <button type="button" onClick={onExit} className="mt-2 w-full rounded-md border border-border py-2 text-sm text-ink-soft">
              Back to scenes
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
