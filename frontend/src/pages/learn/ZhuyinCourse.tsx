import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ZhuyinCourse as Course } from "../../api";
import { ToneMark } from "../../components/ToneMark";

function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  );
}

// The 注音 course index.
//
// Lessons unlock in order rather than all at once, because the order *is* the
// syllabus: ㄅㄆㄇㄈ is how a Taiwanese dictionary, a phone keyboard and a class
// register are all sorted, and learning the symbols out of sequence teaches the
// sounds without the thing they are indexed by.
export default function ZhuyinCourse() {
  const [course, setCourse] = useState<Course | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.zhuyinCourse().then(setCourse).catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="mx-auto max-w-xl px-4 py-6">
      <header className="mb-5 flex items-center gap-3">
        <span className="text-primary">
          <ToneMark tone={3} size={30} strokeWidth={7} />
        </span>
        <div>
          <h1 lang="zh-Hant" className="font-serifhan text-3xl leading-none text-ink">
            注音
          </h1>
          <p className="text-sm text-ink-soft">Bopomofo · Taiwan's own alphabet</p>
        </div>
      </header>

      <div className="card mb-5">
        <p className="text-sm leading-relaxed text-ink-soft">
          Thirty-seven symbols and four tone marks, learned in the order Taiwan recites
          them. Once you know these you can read a Taiwanese dictionary entry, type on a
          Taiwanese keyboard, and follow the readings this app has been showing you all
          along.
        </p>
        {course && (
          <p className="mt-3 text-xs text-ink-faint">
            <span className="font-medium text-ink-soft">
              {course.learned_symbols} of {course.total_symbols}
            </span>{" "}
            symbols in your review queue
          </p>
        )}
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-bad/40 bg-accent-soft px-4 py-3 text-sm text-bad">
          {error}
        </div>
      )}

      {!course ? (
        <div className="card text-sm text-ink-soft">Loading…</div>
      ) : (
        <ul className="space-y-2">
          {course.lessons.map((l, i) => {
            const body = (
              <>
                <div className="flex items-baseline justify-between gap-3">
                  <span lang="zh-Hant" className="font-han text-xl tracking-wide text-ink">
                    {l.title}
                  </span>
                  {l.completed ? (
                    <span className="text-xs font-medium text-good">✓ done</span>
                  ) : l.unlocked ? (
                    <span className="text-xs text-primary">start ▸</span>
                  ) : (
                    <span className="text-ink-faint">
                      <LockIcon />
                    </span>
                  )}
                </div>
                <div className="mt-0.5 text-sm text-ink-soft">{l.subtitle}</div>
              </>
            );
            const shell =
              "block w-full rounded-md border px-4 py-3 text-left transition-colors";
            return (
              <li key={l.id}>
                {l.unlocked ? (
                  <Link
                    to={`/learn/zhuyin/${l.id}`}
                    className={`${shell} border-border bg-surface hover:border-primary`}
                  >
                    {body}
                  </Link>
                ) : (
                  <div
                    className={`${shell} border-border bg-surface-2 opacity-60`}
                    aria-disabled="true"
                    title={`Finish ${course.lessons[i - 1]?.title ?? "the previous lesson"} first`}
                  >
                    {body}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <Link
        to="/learn"
        className="mt-6 block text-center text-sm text-ink-soft underline decoration-ink-faint"
      >
        ← back to the curriculum
      </Link>
    </div>
  );
}
