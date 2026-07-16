import { useState } from "react";
import { ToneMark } from "../components/ToneMark";
import Dictation from "./listen/Dictation";
import Comprehension from "./listen/Comprehension";
import ToneTrainer from "./listen/ToneTrainer";

type Mode = "dictation" | "comprehension" | "tones";

const MODES: { id: Mode; han: string; en: string }[] = [
  { id: "dictation", han: "聽寫", en: "Dictation" },
  { id: "comprehension", han: "對話", en: "Dialogue" },
  { id: "tones", han: "聲調", en: "Tones" },
];

export default function Listen() {
  const [mode, setMode] = useState<Mode>("dictation");

  return (
    <div className="mx-auto max-w-xl px-4 py-6">
      <header className="mb-4 flex items-center gap-3">
        <span className="text-primary">
          <ToneMark tone={4} size={30} strokeWidth={7} />
        </span>
        <div>
          <h1 lang="zh-Hant" className="font-serifhan text-3xl leading-none text-ink">
            聽
          </h1>
          <p className="text-sm text-ink-soft">Listen · comprehension trainer</p>
        </div>
      </header>

      <div className="mb-5 inline-flex w-full rounded-md border border-border bg-surface-2 p-1">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => setMode(m.id)}
            className={[
              "tap flex-1 rounded px-2 py-2 text-center transition-colors",
              m.id === mode ? "bg-primary text-primary-ink" : "text-ink-soft hover:text-ink",
            ].join(" ")}
          >
            <span lang="zh-Hant" className="font-han text-sm">
              {m.han}
            </span>
            <span className="ml-1 text-xs">{m.en}</span>
          </button>
        ))}
      </div>

      {mode === "dictation" && <Dictation />}
      {mode === "comprehension" && <Comprehension />}
      {mode === "tones" && <ToneTrainer />}
    </div>
  );
}
