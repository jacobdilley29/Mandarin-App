import { useEffect, useState } from "react";
import { api, type Scenario, type TutorFocus } from "../api";
import { ToneMark } from "../components/ToneMark";
import ApiKeyForm from "../components/ApiKeyForm";
import Chat from "./talk/Chat";
import Tutor from "./talk/Tutor";

function NoKey({ onConfigured }: { onConfigured: () => void }) {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-sm flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 text-ink-faint">
        <ToneMark tone={5} size={40} strokeWidth={9} />
      </div>
      <h1 lang="zh-Hant" className="font-serifhan text-hero text-ink">
        聊
      </h1>
      <p className="mt-2 text-lg font-semibold text-ink">Talk</p>
      <p className="mt-3 text-sm leading-relaxed text-ink-soft">
        Conversation practice needs an Anthropic API key. Enter one below to enable it — you can also
        set it later under <span className="text-ink">我 · Settings</span>.
      </p>
      <div className="mt-5 w-full text-left">
        <ApiKeyForm onSaved={onConfigured} />
      </div>
    </div>
  );
}

type Mode = "roleplay" | "ask";

export default function Talk() {
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [chosen, setChosen] = useState<Scenario | null>(null);
  // Two Claude-powered modes share this tab rather than taking a seventh slot in
  // the bar — six tabs is already a lot on a phone, and spec §6 is mobile-first.
  const [mode, setMode] = useState<Mode>("roleplay");
  // Set when the learner arrived here via "ask about this" from a lesson or
  // review card (spec §3.7's curriculum context).
  const [focus, setFocus] = useState<TutorFocus | undefined>(() => {
    try {
      const raw = sessionStorage.getItem("tutor:focus");
      if (raw) {
        sessionStorage.removeItem("tutor:focus");
        return JSON.parse(raw) as TutorFocus;
      }
    } catch {
      // sessionStorage can throw in private windows; the tutor works without it.
    }
    return undefined;
  });

  // Arriving with a focus item means a question is already in mind.
  useEffect(() => {
    if (focus) setMode("ask");
  }, [focus]);

  function load() {
    api
      .talkScenarios()
      .then((r) => {
        setAvailable(r.available);
        setScenarios(r.scenarios);
      })
      .catch(() => setAvailable(false));
  }

  useEffect(() => {
    load();
  }, []);

  if (available === null) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Loading…</div>;
  }
  if (!available) return <NoKey onConfigured={load} />;
  if (chosen) return <Chat scenario={chosen} onExit={() => setChosen(null)} />;

  const modeSwitch = (
    <div className="mb-5 inline-flex rounded-md border border-border bg-surface-2 p-1">
      {([
        ["roleplay", "Roleplay"],
        ["ask", "Ask"],
      ] as const).map(([value, label]) => (
        <button
          key={value}
          type="button"
          onClick={() => setMode(value)}
          aria-pressed={mode === value}
          className={[
            "tap rounded px-4 py-1.5 text-sm font-medium transition-colors",
            mode === value ? "bg-primary text-primary-ink" : "text-ink-soft hover:text-ink",
          ].join(" ")}
        >
          {label}
        </button>
      ))}
    </div>
  );

  if (mode === "ask") {
    return (
      <div className="mx-auto max-w-xl px-4 pt-6">
        {modeSwitch}
        <Tutor focus={focus} onClearFocus={() => setFocus(undefined)} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-6">
      <header className="mb-5 flex items-center gap-3">
        <span className="text-primary">
          <ToneMark tone={2} size={30} strokeWidth={7} />
        </span>
        <div>
          <h1 lang="zh-Hant" className="font-serifhan text-3xl leading-none text-ink">
            聊
          </h1>
          <p className="text-sm text-ink-soft">Talk · roleplay and questions</p>
        </div>
      </header>
      {modeSwitch}
      <p className="mb-4 text-sm text-ink-soft">Pick a scene. The character stays in Traditional characters at your level.</p>
      <div className="grid gap-3">
        {scenarios?.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setChosen(s)}
            className="card flex items-center gap-3 text-left transition-colors hover:border-primary"
          >
            <span className="text-3xl">{s.emoji}</span>
            <div>
              <div lang="zh-Hant" className="font-han text-lg text-ink">
                {s.title}
              </div>
              <div className="text-xs text-ink-soft">{s.en}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
