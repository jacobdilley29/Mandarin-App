import { useEffect, useRef, useState } from "react";
import { api, type GlossSpan } from "../api";
import { useSettings } from "../SettingsContext";

// Tap a word to see what it means, without leaving the sentence (spec §5).
//
// Reading a dialogue or a passage, you hit a word you don't know, and the choice
// is to guess or to go and look it up. Going is how reading practice turns into
// dictionary practice, so the answer arrives in place instead.
//
// The whole string is segmented server-side in one request, so a tap opens
// instantly rather than putting a spinner between the learner and the word they
// are stuck on. 我要喝水 is four characters and four words; 便利商店 is four
// characters and one — the split follows what the curriculum teaches, so the
// boundaries match the lessons.
//
// Degrades to plain text: if the request fails, or nothing can define a word,
// the sentence still reads exactly the same.

function Popover({ span, onClose }: { span: GlossSpan; onClose: () => void }) {
  const { settings } = useSettings();
  const script = settings?.script ?? "pinyin";
  const entry = span.entry!;
  const zh = script !== "pinyin" ? entry.zhuyin : null;
  const py = script === "zhuyin" && zh ? null : entry.pinyin;

  return (
    <span
      role="dialog"
      className="absolute bottom-full left-1/2 z-20 mb-1 w-max max-w-[16rem] -translate-x-1/2
                 rounded-md border border-border bg-surface px-3 py-2 text-left shadow-lg"
      onClick={(e) => {
        e.stopPropagation();
        onClose();
      }}
    >
      <span lang="zh-Hant" className="block font-han text-lg text-ink">
        {entry.text}
      </span>
      <span className="block text-sm text-ink-soft">
        {zh && (
          <span lang="zh-Hant" className="font-han">
            {zh}
          </span>
        )}
        {zh && py && <span className="mx-1.5 text-ink-faint">·</span>}
        {py}
      </span>
      <span className="mt-0.5 block text-sm text-ink">{entry.gloss}</span>
    </span>
  );
}

export function Glossable({
  text,
  className,
}: {
  text: string;
  className?: string;
}) {
  const [spans, setSpans] = useState<GlossSpan[] | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const box = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    let live = true;
    setOpen(null);
    api
      .annotate(text)
      .then((r) => live && setSpans(r.spans))
      // Plain text is a perfectly good sentence; only the tapping is lost.
      .catch(() => live && setSpans(null));
    return () => {
      live = false;
    };
  }, [text]);

  useEffect(() => {
    if (open === null) return;
    const close = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(null);
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [open]);

  if (!spans) return <span className={className}>{text}</span>;

  return (
    <span ref={box} className={className}>
      {spans.map((s, i) =>
        s.entry ? (
          <span key={i} className="relative inline-block">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setOpen(open === i ? null : i);
              }}
              className={[
                "tap -mx-0.5 rounded px-0.5 transition-colors",
                "underline decoration-border decoration-dotted underline-offset-4",
                open === i ? "bg-primary-soft/40 decoration-primary" : "hover:bg-surface-2",
              ].join(" ")}
            >
              {s.text}
            </button>
            {open === i && <Popover span={s} onClose={() => setOpen(null)} />}
          </span>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </span>
  );
}
