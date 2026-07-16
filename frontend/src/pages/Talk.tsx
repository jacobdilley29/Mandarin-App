import { useEffect, useState } from "react";
import { api, type Scenario } from "../api";
import { ToneMark } from "../components/ToneMark";
import Chat from "./talk/Chat";

function NoKey() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 text-ink-faint">
        <ToneMark tone={5} size={40} strokeWidth={9} />
      </div>
      <h1 lang="zh-Hant" className="font-serifhan text-hero text-ink">
        聊
      </h1>
      <p className="mt-2 text-lg font-semibold text-ink">Talk</p>
      <p className="mt-3 max-w-sm text-sm leading-relaxed text-ink-soft">
        Conversation practice needs an Anthropic API key. Add{" "}
        <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">ANTHROPIC_API_KEY</code> to your{" "}
        <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">.env</code> and restart.
        Everything else in the app works without it.
      </p>
    </div>
  );
}

export default function Talk() {
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null);
  const [available, setAvailable] = useState<boolean | null>(null);
  const [chosen, setChosen] = useState<Scenario | null>(null);

  useEffect(() => {
    api
      .talkScenarios()
      .then((r) => {
        setAvailable(r.available);
        setScenarios(r.scenarios);
      })
      .catch(() => setAvailable(false));
  }, []);

  if (available === null) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Loading…</div>;
  }
  if (!available) return <NoKey />;
  if (chosen) return <Chat scenario={chosen} onExit={() => setChosen(null)} />;

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
          <p className="text-sm text-ink-soft">Talk · roleplay in Taiwan</p>
        </div>
      </header>
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
