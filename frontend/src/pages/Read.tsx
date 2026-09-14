import { useEffect, useState } from "react";
import { api, type ReadingLibrary } from "../api";
import { LevelBadge } from "../components/LevelBadge";
import PassageReader from "./read/PassageReader";

// Read tab (spec §3.2, §3.6): the passages, and which ones are due.
//
// The drills teach words one at a time; a passage is where they come back as a
// paragraph, which is a different skill and the one that eventually turns into
// reading Chinese. Each passage is written to exactly its lesson's level, so it
// can be read rather than decoded.
//
// A passage opens when its lesson is finished. Earlier it would be full of words
// the lesson hasn't taught yet — precisely the out-of-scope reading the content
// pipeline exists to prevent.

function Empty({ total }: { total: number }) {
  return (
    <p className="rounded-md border border-dashed border-border px-4 py-8 text-center text-sm text-ink-soft">
      {total === 0
        ? "No passages yet — they arrive with the lessons."
        : "Finish a lesson and its passage opens here."}
    </p>
  );
}

export default function Read() {
  const [lib, setLib] = useState<ReadingLibrary | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api
      .reading()
      .then((r) => {
        setLib(r);
        setError(null);
      })
      .catch((e: Error) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  if (open) {
    return (
      <PassageReader
        lessonId={open}
        onExit={() => {
          setOpen(null);
          load();
        }}
      />
    );
  }

  if (error) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-sm text-bad">{error}</div>;
  }
  if (!lib) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Loading…</div>;
  }

  const unlocked = lib.passages.filter((p) => p.unlocked);
  const due = unlocked.filter((p) => p.due);
  const fresh = unlocked.filter((p) => !p.read);
  const rest = unlocked.filter((p) => p.read && !p.due);
  const locked = lib.passages.filter((p) => !p.unlocked);

  const Row = ({ id, title, unit, chars, level, note }: {
    id: string;
    title: string;
    unit: string;
    chars: number;
    level: ReadingLibrary["passages"][number]["level"];
    note?: string;
  }) => (
    <button
      type="button"
      onClick={() => setOpen(id)}
      className="tap w-full rounded-md border border-border bg-surface px-4 py-3 text-left hover:border-primary"
    >
      <div className="flex items-baseline justify-between gap-2">
        <span lang="zh-Hant" className="font-han text-base text-ink">
          {title}
        </span>
        <LevelBadge level={level} showHsk={false} />
      </div>
      <div className="mt-0.5 text-xs text-ink-soft">
        {unit} · {chars} characters
        {note ? ` · ${note}` : ""}
      </div>
    </button>
  );

  const Section = ({ heading, blurb, items }: {
    heading: string;
    blurb: string;
    items: typeof lib.passages;
  }) =>
    items.length === 0 ? null : (
      <section className="mb-6">
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-ink-soft">
          {heading}
        </h2>
        <p className="mb-2 text-xs text-ink-faint">{blurb}</p>
        <div className="grid gap-2">
          {items.map((p) => (
            <Row
              key={p.lesson_id}
              id={p.lesson_id}
              title={p.title}
              unit={p.unit_title}
              chars={p.chars}
              level={p.level}
              note={p.reps > 0 ? `read ${p.reps}×` : undefined}
            />
          ))}
        </div>
      </section>
    );

  return (
    <div className="mx-auto max-w-xl px-4 py-6">
      <header className="mb-5">
        <h1 lang="zh-Hant" className="font-han text-2xl text-ink">
          閱讀
        </h1>
        <p className="text-sm text-ink-soft">
          Short passages at your level. Tap any word you don't know.
        </p>
      </header>

      <Section
        heading="Due to reread"
        blurb="Scheduled the same way your cards are — a passage you found hard comes back sooner."
        items={due}
      />
      <Section heading="New" blurb="Passages you haven't read yet." items={fresh} />
      <Section heading="Read" blurb="Reread any of these whenever you like." items={rest} />

      {unlocked.length === 0 && <Empty total={lib.total} />}

      {locked.length > 0 && (
        <section className="mt-6">
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-ink-soft">
            Locked
          </h2>
          <p className="mb-2 text-xs text-ink-faint">
            {locked.length} more open as you finish their lessons.
          </p>
        </section>
      )}
    </div>
  );
}
