import { useState } from "react";
import { useSettings } from "../SettingsContext";

/**
 * Enter / replace / clear the Anthropic API key that enables the Talk tab.
 * The key is stored locally by the backend (settings DB) and is never read
 * back to the browser — we only ever learn whether one is configured.
 */
export default function ApiKeyForm({ onSaved }: { onSaved?: () => void }) {
  const { settings, update, saving } = useSettings();
  const [value, setValue] = useState("");
  const [justSaved, setJustSaved] = useState(false);

  if (!settings) return null;

  const fromEnv = settings.conversation_key_from_env;
  const configured = settings.conversation_configured;

  async function save(next: string) {
    await update({ anthropic_api_key: next });
    setValue("");
    setJustSaved(true);
    onSaved?.();
  }

  if (fromEnv) {
    return (
      <p className="text-sm text-ink-soft">
        A key is configured via <code className="rounded bg-surface-2 px-1 py-0.5 text-xs">.env</code>. To
        change it, edit that file and restart. Talk is <span className="text-good">enabled</span>.
      </p>
    );
  }

  return (
    <div>
      {configured ? (
        <p className="mb-2 text-sm text-good">✓ Talk is enabled — a key is saved.</p>
      ) : (
        <p className="mb-2 text-sm text-ink-soft">
          Paste an Anthropic API key to enable conversation practice. It's stored only on this device.
        </p>
      )}
      <div className="flex gap-2">
        <input
          type="password"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setJustSaved(false);
          }}
          placeholder={configured ? "Enter a new key to replace…" : "sk-ant-…"}
          autoComplete="off"
          spellCheck={false}
          className="tap min-w-0 flex-1 rounded-md border border-border bg-surface px-3 py-2 text-sm text-ink"
        />
        <button
          type="button"
          disabled={!value.trim() || saving}
          onClick={() => save(value.trim())}
          className="tap shrink-0 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-ink disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
      {configured && (
        <button
          type="button"
          disabled={saving}
          onClick={() => save("")}
          className="mt-2 text-xs text-ink-faint underline"
        >
          Remove saved key
        </button>
      )}
      {justSaved && !saving && (
        <p className="mt-2 text-xs text-good">Saved.</p>
      )}
      <p className="mt-2 text-xs text-ink-faint">
        Get a key at console.anthropic.com. Everything else in the app works without it.
      </p>
    </div>
  );
}
