import { useStatus } from "../StatusContext";
import { ComingSoon } from "../components/ComingSoon";
import { ToneMark } from "../components/ToneMark";

export default function Talk() {
  const status = useStatus();

  // Degrade gracefully: without an Anthropic key the conversation tab explains
  // itself rather than pretending to work.
  if (status && !status.features.conversation) {
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
          <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">ANTHROPIC_API_KEY</code>{" "}
          to your <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">.env</code> and
          restart. Everything else in the app works without it.
        </p>
        <span className="mt-6 rounded-full border border-border bg-surface-2 px-3 py-1 text-xs font-medium text-ink-faint">
          Phase 5 · needs API key
        </span>
      </div>
    );
  }

  return (
    <ComingSoon
      han="聊"
      title="Talk"
      phase={5}
      tone={2}
      blurb="AI roleplay conversations set in Taiwan — in Traditional characters, at your level, with a teacher note on every turn. Arrives in Phase 5."
    />
  );
}
