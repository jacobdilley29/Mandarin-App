// Thin API client. In dev, Vite proxies /api to the backend; in production the
// backend serves this bundle so same-origin requests just work.

export interface AppStatus {
  version: string;
  phase: number;
  features: {
    conversation: boolean;
    learn: boolean;
    review: boolean;
    listen: boolean;
    speak: boolean;
    progress: boolean;
  };
  whisper_model: string;
}

export interface Settings {
  show_pinyin: boolean;
  playback_rate: number;
  tts_voice: string;
  theme: "system" | "light" | "dark";
  daily_new_limit: number;
  reduced_motion: boolean;
  placement_done: boolean;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  status: () => fetch("/api/status").then(json<AppStatus>),
  health: () => fetch("/api/health").then(json<{ status: string; version: string }>),
  getSettings: () => fetch("/api/settings").then(json<Settings>),
  updateSettings: (patch: Partial<Settings>) =>
    fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }).then(json<Settings>),
};
