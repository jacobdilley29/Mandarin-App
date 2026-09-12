import { useEffect, useState } from "react";
import { api, type BackupStatus, type Settings } from "../api";
import { useSettings } from "../SettingsContext";
import { useStatus } from "../StatusContext";
import { ToneRow } from "../components/ToneMark";
import ApiKeyForm from "../components/ApiKeyForm";
import Progress from "./me/Progress";

const VOICES = [
  { value: "zh-TW-HsiaoChenNeural", label: "曉臻 (female)" },
  { value: "zh-TW-YunJheNeural", label: "雲哲 (male)" },
];
const RATES = [
  { value: 0.75, label: "0.75×" },
  { value: 1.0, label: "1×" },
  { value: 1.25, label: "1.25×" },
];
const THEMES = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const;

function Segmented<T extends string | number>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-md border border-border bg-surface-2 p-1">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          onClick={() => onChange(o.value)}
          className={[
            "tap rounded px-3 text-sm font-medium transition-colors",
            o.value === value
              ? "bg-primary text-primary-ink"
              : "text-ink-soft hover:text-ink",
          ].join(" ")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={[
        "tap relative w-12 rounded-full transition-colors",
        on ? "bg-primary" : "border border-border bg-surface-2",
      ].join(" ")}
    >
      <span
        className={[
          "absolute top-1 h-4 w-4 rounded-full bg-surface shadow transition-all",
          on ? "left-7" : "left-1",
        ].join(" ")}
      />
    </button>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div>
        <div className="text-sm font-medium text-ink">{label}</div>
        {hint && <div className="text-xs text-ink-soft">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

/** How long ago, in words. Precision beyond "days" doesn't help here. */
function ago(iso: string): string {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 2) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs === 1 ? "" : "s"} ago`;
  const days = Math.floor(hrs / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Backup health.
 *
 * This app was lost once already because backups were never set up. A backup
 * job that silently stopped running is the same failure wearing a disguise, so
 * the state of it is shown here rather than left to be discovered too late.
 */
function BackupPanel() {
  const [info, setInfo] = useState<BackupStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    api
      .backupStatus()
      .then((b) => {
        setInfo(b);
        setErr(null);
      })
      .catch((e) => setErr(String(e.message ?? e)));

  useEffect(() => {
    refresh();
  }, []);

  const runNow = async () => {
    setBusy(true);
    try {
      await api.runBackup();
      await refresh();
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  // Nightly job: anything past ~36h means it isn't running.
  const stale =
    !info?.last_backup_at ||
    Date.now() - new Date(info.last_backup_at).getTime() > 36 * 3600 * 1000;

  return (
    <section className="card mt-6">
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Backups</h2>
        <button
          type="button"
          onClick={runNow}
          disabled={busy}
          className="tap rounded-md border border-border px-3 py-1 text-xs font-medium text-ink-soft hover:text-ink disabled:opacity-50"
        >
          {busy ? "Backing up…" : "Back up now"}
        </button>
      </div>

      {err ? (
        <p className="text-sm text-bad">Couldn't read backup status: {err}</p>
      ) : !info ? (
        <p className="text-sm text-ink-soft">Checking…</p>
      ) : (
        <dl className="space-y-1 text-sm text-ink-soft">
          <div className="flex justify-between">
            <dt>Last backup</dt>
            <dd className={stale ? "text-bad" : "text-good"}>
              {info.last_backup_at ? ago(info.last_backup_at) : "never"}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt>Kept</dt>
            <dd className="text-ink">
              {info.snapshot_count} snapshot{info.snapshot_count === 1 ? "" : "s"}
              {info.total_bytes > 0 ? ` · ${bytes(info.total_bytes)}` : ""}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt>Schedule</dt>
            <dd className="text-ink">
              daily at {info.scheduled_at}, {info.retention_days}-day window
            </dd>
          </div>
        </dl>
      )}

      {info && stale && !err && (
        <p className="mt-3 rounded-md border border-bad/40 bg-accent-soft px-3 py-2 text-xs text-bad">
          No recent backup. If you're running under Docker, check the backup
          container: <code>docker compose ps</code>. See the README's
          "Backups &amp; restore" section.
        </p>
      )}
    </section>
  );
}

export default function Me() {
  const status = useStatus();
  const { settings, error, saving, update } = useSettings();

  return (
    <div className="mx-auto max-w-xl px-4 py-6">
      <header className="mb-6">
        <h1 lang="zh-Hant" className="font-serifhan text-3xl text-ink">
          我
        </h1>
        <p className="text-sm text-ink-soft">Progress &amp; settings</p>
      </header>

      <div className="mb-8">
        <Progress />
      </div>

      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-soft">Settings</h2>

      {error && (
        <div className="mb-4 rounded-md border border-bad/40 bg-accent-soft px-4 py-3 text-sm text-bad">
          {error}
        </div>
      )}

      {!settings ? (
        <div className="card text-sm text-ink-soft">Loading settings…</div>
      ) : (
        <>
          <section className="card divide-y divide-border">
            <Row label="Show pinyin" hint="Global default; hidden in review to force recall">
              <Toggle on={settings.show_pinyin} onClick={() => update({ show_pinyin: !settings.show_pinyin })} />
            </Row>

            <Row label="Playback speed" hint="Used across Learn, Listen, and audio playback">
              <Segmented
                value={settings.playback_rate}
                options={RATES}
                onChange={(v) => update({ playback_rate: v })}
              />
            </Row>

            <Row label="Voice" hint="zh-TW edge-tts voice">
              <select
                value={settings.tts_voice}
                onChange={(e) => update({ tts_voice: e.target.value })}
                className="tap rounded-md border border-border bg-surface px-3 text-sm text-ink"
              >
                {VOICES.map((v) => (
                  <option key={v.value} value={v.value}>
                    {v.label}
                  </option>
                ))}
              </select>
            </Row>

            <Row label="Theme">
              <Segmented
                value={settings.theme}
                options={THEMES as unknown as { value: string; label: string }[]}
                onChange={(v) => update({ theme: v as Settings["theme"] })}
              />
            </Row>

            <Row label="New words per day" hint="Daily SRS intake cap">
              <input
                type="number"
                min={0}
                max={100}
                value={settings.daily_new_limit}
                onChange={(e) =>
                  update({ daily_new_limit: Math.max(0, Math.min(100, Number(e.target.value) || 0)) })
                }
                className="tap w-20 rounded-md border border-border bg-surface px-3 text-sm text-ink"
              />
            </Row>

            <Row label="Reduce motion" hint="Minimise feedback animations">
              <Toggle on={settings.reduced_motion} onClick={() => update({ reduced_motion: !settings.reduced_motion })} />
            </Row>
          </section>

          <p className="mt-3 text-right text-xs text-ink-faint">{saving ? "Saving…" : "Saved"}</p>
        </>
      )}

      <h2 className="mb-3 mt-8 text-sm font-semibold uppercase tracking-wide text-ink-soft">
        Talk (AI conversation)
      </h2>
      <section className="card">
        <ApiKeyForm />
      </section>

      <BackupPanel />

      <section className="card mt-6">
        <h2 className="mb-2 text-sm font-semibold text-ink">About</h2>
        <dl className="space-y-1 text-sm text-ink-soft">
          <div className="flex justify-between">
            <dt>App</dt>
            <dd className="text-ink">台灣華語老師</dd>
          </div>
          <div className="flex justify-between">
            <dt>Version</dt>
            <dd className="text-ink">{status?.version ?? "—"}</dd>
          </div>
          <div className="flex justify-between">
            <dt>Build phase</dt>
            <dd className="text-ink">Phase {status?.phase ?? 0}</dd>
          </div>
          <div className="flex justify-between">
            <dt>Conversation (Talk)</dt>
            <dd className={status?.features.conversation ? "text-good" : "text-ink-faint"}>
              {status?.features.conversation ? "enabled" : "no API key"}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt>Whisper model</dt>
            <dd className="text-ink">{status?.whisper_model ?? "—"}</dd>
          </div>
        </dl>
        <div className="mt-4 flex justify-center opacity-70">
          <ToneRow size={16} />
        </div>
      </section>
    </div>
  );
}
