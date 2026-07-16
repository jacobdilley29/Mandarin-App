import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Curriculum } from "../api";
import { ToneMark } from "../components/ToneMark";

function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  );
}

function ScoreDots({ score }: { score: number | null }) {
  // Map a best-score into a small three-dot mastery indicator.
  const filled = score == null ? 0 : score >= 0.95 ? 3 : score >= 0.8 ? 2 : 1;
  return (
    <span className="flex gap-1" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className={["h-1.5 w-1.5 rounded-full", i < filled ? "bg-good" : "bg-border"].join(" ")}
        />
      ))}
    </span>
  );
}

export default function Learn() {
  const [data, setData] = useState<Curriculum | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.curriculum().then(setData).catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="mx-auto max-w-xl px-4 py-6">
      <header className="mb-6 flex items-center gap-3">
        <span className="text-primary">
          <ToneMark tone={1} size={30} strokeWidth={7} />
        </span>
        <div>
          <h1 lang="zh-Hant" className="font-serifhan text-3xl leading-none text-ink">
            學
          </h1>
          <p className="text-sm text-ink-soft">Learn · Taiwan daily life</p>
        </div>
      </header>

      {error && (
        <div className="mb-4 rounded-md border border-bad/40 bg-accent-soft px-4 py-3 text-sm text-bad">
          {error}
        </div>
      )}

      {!data ? (
        <div className="card text-sm text-ink-soft">Loading curriculum…</div>
      ) : (
        <div className="space-y-6">
          {data.units.map((unit) => (
            <section key={unit.id}>
              <div className="mb-2 flex items-baseline gap-2">
                <h2 lang="zh-Hant" className="font-han text-lg font-medium text-ink">
                  {unit.title}
                </h2>
                {unit.hsk_level != null && (
                  <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[0.65rem] font-medium text-ink-soft">
                    HSK {unit.hsk_level}
                  </span>
                )}
              </div>
              {unit.subtitle && <p className="mb-2 text-xs text-ink-soft">{unit.subtitle}</p>}

              <ul className="space-y-2">
                {unit.lessons.map((lesson) => {
                  const body = (
                    <div
                      className={[
                        "card flex items-center justify-between gap-3 transition-colors",
                        lesson.unlocked ? "hover:border-primary" : "opacity-60",
                      ].join(" ")}
                    >
                      <div className="min-w-0">
                        <div lang="zh-Hant" className="font-han text-base text-ink">
                          {lesson.title}
                        </div>
                        <div className="mt-1 flex items-center gap-2 text-xs text-ink-soft">
                          <span>{lesson.vocab_count} words</span>
                          {lesson.completed && <span className="text-good">✓ done</span>}
                        </div>
                      </div>
                      {lesson.unlocked ? (
                        <ScoreDots score={lesson.best_score} />
                      ) : (
                        <span className="text-ink-faint">
                          <LockIcon />
                        </span>
                      )}
                    </div>
                  );
                  return (
                    <li key={lesson.id}>
                      {lesson.unlocked ? (
                        <Link to={`/learn/${lesson.id}`} className="block">
                          {body}
                        </Link>
                      ) : (
                        <div aria-disabled className="cursor-not-allowed">
                          {body}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
