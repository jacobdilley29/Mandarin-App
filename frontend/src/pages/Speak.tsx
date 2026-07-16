import { ComingSoon } from "../components/ComingSoon";

export default function Speak() {
  return (
    <ComingSoon
      han="說"
      title="Speak"
      phase={4}
      tone={2}
      blurb="Shadowing with local Whisper transcription and per-syllable tone feedback — your pitch contour overlaid on the target shape. Arrives in Phase 4."
    />
  );
}
