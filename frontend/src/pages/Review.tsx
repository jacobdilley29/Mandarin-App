import { useEffect, useState } from "react";
import { useSettings } from "../SettingsContext";
import PlacementQuiz from "./review/PlacementQuiz";
import PracticeSession from "./review/PracticeSession";
import ReviewSession from "./review/ReviewSession";

// Review tab: on first run, a placement check seeds the deck; afterwards it's
// the daily FSRS review session, plus two practice modes that sit alongside it.
//
// The practice modes are deliberately separate from the daily queue (spec §3.6:
// "separate from the daily review queue") and change nothing about scheduling —
// see PracticeSession and app/practice.py.
type View = "review" | "needs" | "known";

export default function Review() {
  const { settings } = useSettings();
  // Local override so finishing placement transitions without a settings refetch.
  const [placed, setPlaced] = useState<boolean | null>(null);
  const [view, setView] = useState<View>("review");

  useEffect(() => {
    if (settings) setPlaced(settings.placement_done);
  }, [settings]);

  if (placed == null) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Loading…</div>;
  }
  if (!placed) {
    return <PlacementQuiz onDone={() => setPlaced(true)} />;
  }
  if (view !== "review") {
    return <PracticeSession mode={view} onExit={() => setView("review")} />;
  }

  return (
    <div>
      <ReviewSession />

      <div className="mx-auto max-w-xl px-4 pb-8">
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-ink-soft">Practice</h2>
        <p className="mb-3 text-xs text-ink-faint">
          Extra drilling, outside the daily queue. Neither affects your review schedule.
        </p>
        <div className="grid gap-2">
          <button
            type="button"
            onClick={() => setView("needs")}
            className="tap rounded-md border border-border bg-surface px-4 py-3 text-left hover:border-primary"
          >
            <div lang="zh-Hant" className="font-han text-base text-ink">
              加強
            </div>
            <div className="text-sm font-medium text-ink">Needs practice</div>
            <div className="text-xs text-ink-soft">What you keep forgetting or getting wrong</div>
          </button>
          <button
            type="button"
            onClick={() => setView("known")}
            className="tap rounded-md border border-border bg-surface px-4 py-3 text-left hover:border-primary"
          >
            <div lang="zh-Hant" className="font-han text-base text-ink">
              複習舊的
            </div>
            <div className="text-sm font-medium text-ink">Known material</div>
            <div className="text-xs text-ink-soft">A confidence pass over what you've mastered</div>
          </button>
        </div>
      </div>
    </div>
  );
}
