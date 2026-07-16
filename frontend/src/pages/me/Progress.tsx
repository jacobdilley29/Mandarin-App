import { useEffect, useState } from "react";
import { api, type Progress as ProgressData } from "../../api";

function StatTile({ value, label, accent }: { value: string; label: string; accent?: boolean }) {
  return (
    <div className="rounded-md border border-border bg-surface p-3 text-center">
      <div className={["text-2xl font-semibold", accent ? "text-primary" : "text-ink"].join(" ")}>{value}</div>
      <div className="mt-0.5 text-xs text-ink-soft">{label}</div>
    </div>
  );
}

// 14-day activity — single-series magnitude over time (sessions per day).
function ActivityChart({ data }: { data: ProgressData["activity"] }) {
  const max = Math.max(1, ...data.map((d) => d.reviews + d.lessons));
  return (
    <div className="flex h-16 items-end gap-1">
      {data.map((d) => {
        const total = d.reviews + d.lessons;
        const h = (total / max) * 100;
        return (
          <div key={d.day} className="flex-1" title={`${d.day}: ${total} sessions`}>
            <div
              className="mx-auto w-full rounded-[3px]"
              style={{
                height: `${Math.max(total ? 8 : 2, h)}%`,
                background: total ? "var(--primary)" : "var(--border)",
                minHeight: 2,
              }}
            />
          </div>
        );
      })}
    </div>
  );
}

// Words known by HSK level, stacked by mastery band. Mastery is ordinal
// magnitude → one hue, light→dark (sequential), from the brand green.
const BANDS: { key: "learning" | "young" | "mature"; label: string; color: string }[] = [
  { key: "learning", label: "Learning", color: "var(--primary-soft)" },
  { key: "young", label: "Familiar", color: "var(--good)" },
  { key: "mature", label: "Mastered", color: "var(--primary)" },
];

function WordsByHsk({ data }: { data: ProgressData["words_by_hsk"] }) {
  const max = Math.max(1, ...data.map((d) => d.learning + d.young + d.mature));
  return (
    <div>
      <div className="space-y-2">
        {data.map((row) => (
          <div key={row.hsk_level} className="flex items-center gap-2">
            <span className="w-12 shrink-0 text-xs text-ink-soft">HSK {row.hsk_level}</span>
            <div className="flex h-5 flex-1 gap-[2px] overflow-hidden rounded">
              {BANDS.map((b) => {
                const v = row[b.key];
                if (!v) return null;
                return (
                  <div
                    key={b.key}
                    style={{ width: `${(v / max) * 100}%`, background: b.color }}
                    title={`HSK ${row.hsk_level} · ${b.label}: ${v}`}
                  />
                );
              })}
            </div>
            <span className="w-6 shrink-0 text-right text-xs text-ink-soft">
              {row.learning + row.young + row.mature}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-3">
        {BANDS.map((b) => (
          <span key={b.key} className="flex items-center gap-1 text-xs text-ink-soft">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: b.color }} />
            {b.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const W = 120;
  const H = 28;
  const pts = values
    .map((v, i) => `${(i / (values.length - 1)) * W},${H - v * H}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-7 w-24" aria-hidden="true">
      <polyline points={pts} fill="none" stroke="var(--primary)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Progress() {
  const [data, setData] = useState<ProgressData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.progress().then(setData).catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="card text-sm text-bad">{error}</div>;
  if (!data) return <div className="card text-sm text-ink-soft">Loading progress…</div>;

  const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

  return (
    <section className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        <StatTile value={`${data.streak}🔥`} label="day streak" accent />
        <StatTile value={String(data.total_known)} label="words known" />
        <StatTile value={String(data.total_mature)} label="mastered" />
      </div>

      <div className="card">
        <h3 className="mb-2 text-sm font-semibold text-ink">Last 14 days</h3>
        <ActivityChart data={data.activity} />
      </div>

      {data.words_by_hsk.length > 0 && (
        <div className="card">
          <h3 className="mb-3 text-sm font-semibold text-ink">Words by level</h3>
          <WordsByHsk data={data.words_by_hsk} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-2xl font-semibold text-ink">{pct(data.tone_accuracy)}</div>
              <div className="text-xs text-ink-soft">tone accuracy</div>
            </div>
            <Sparkline values={data.tone_trend} />
          </div>
        </div>
        <div className="card">
          <div className="text-2xl font-semibold text-ink">{pct(data.retention)}</div>
          <div className="text-xs text-ink-soft">review retention</div>
        </div>
      </div>

      {data.weakest_grammar.length > 0 && (
        <div className="card">
          <h3 className="mb-2 text-sm font-semibold text-ink">Weakest grammar</h3>
          <ul className="space-y-1">
            {data.weakest_grammar.map((g) => (
              <li key={g.id} className="flex items-center justify-between text-sm">
                <span lang="zh-Hant" className="font-han text-ink">
                  {g.title}
                </span>
                <span className="text-xs text-warn">{g.errors} slips</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
