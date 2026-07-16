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

// --- Learn / curriculum types (mirror backend shapes) ---
export interface CurriculumLesson {
  id: string;
  title: string;
  vocab_count: number;
  completed: boolean;
  best_score: number | null;
  unlocked: boolean;
}
export interface CurriculumUnit {
  id: string;
  title: string;
  subtitle: string | null;
  hsk_level: number | null;
  lessons: CurriculumLesson[];
}
export interface Curriculum {
  units: CurriculumUnit[];
}

export interface Example {
  hanzi: string;
  pinyin: string;
  gloss: string;
}
export interface Option {
  text: string;
  correct: boolean;
}
// Payload shapes vary by kind; consumers narrow on `kind`.
export interface Exercise {
  id: string;
  kind:
    | "vocab_intro"
    | "grammar"
    | "match"
    | "audio_meaning"
    | "cloze"
    | "tile_build"
    | "translate"
    | "listen_type"
    | "dialogue";
  gradable: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload: any;
}
export interface Lesson {
  id: string;
  title: string;
  unit_id: string;
  unlocked: boolean;
  gradable_count: number;
  exercises: Exercise[];
}

export interface DrillResult {
  id: string;
  kind: string;
  correct: boolean;
  vocab_id?: string | null;
  grammar_id?: string | null;
}
export interface LessonResult {
  score: number;
  correct: number;
  total: number;
  passed: boolean;
  completed: boolean;
  best_score: number;
  unlocked_next: string | null;
  new_srs_cards: number;
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
  curriculum: () => fetch("/api/curriculum").then(json<Curriculum>),
  lesson: (id: string) => fetch(`/api/lesson/${id}`).then(json<Lesson>),
  lessonResult: (id: string, results: DrillResult[]) =>
    fetch(`/api/lesson/${id}/result`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ results }),
    }).then(json<LessonResult>),
};

/** URL for a cached TTS clip. */
export function audioUrl(text: string, voice?: string): string {
  const params = new URLSearchParams({ text });
  if (voice) params.set("voice", voice);
  return `/api/audio?${params.toString()}`;
}
