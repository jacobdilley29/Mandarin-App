import { useEffect, useState } from "react";
import { useSettings } from "../SettingsContext";
import PlacementQuiz from "./review/PlacementQuiz";
import ReviewSession from "./review/ReviewSession";

// Review tab: on first run, a placement check seeds the deck; afterwards it's
// the daily FSRS review session. `placement_done` in settings gates which.
export default function Review() {
  const { settings } = useSettings();
  // Local override so finishing placement transitions without a settings refetch.
  const [placed, setPlaced] = useState<boolean | null>(null);

  useEffect(() => {
    if (settings) setPlaced(settings.placement_done);
  }, [settings]);

  if (placed == null) {
    return <div className="mx-auto max-w-xl px-4 py-10 text-center text-ink-soft">Loading…</div>;
  }
  if (!placed) {
    return <PlacementQuiz onDone={() => setPlaced(true)} />;
  }
  return <ReviewSession />;
}
