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

// --- Review / placement types ---
export interface PlacementItem {
  vocab_id: string;
  char: string;
  pinyin: string;
  options: Option[];
}
export interface Placement {
  done: boolean;
  items: PlacementItem[];
}
export interface PlacementResult {
  seeded_mature: number;
  seeded_new: number;
}

// One review item; fields present depend on `kind`.
export interface ReviewItem {
  card_id: number;
  item_id: string;
  reps: number;
  state: string;
  kind: "recognition" | "recall" | "audio_meaning" | "cloze";
  answer: string;
  options: Option[];
  char?: string;
  pinyin?: string | null;
  audio_text?: string;
  prompt_gloss?: string;
  masked?: string;
  gloss?: string | null;
}
export interface ReviewQueue {
  items: ReviewItem[];
  count: number;
}
export interface ReviewStats {
  due: number;
  new: number;
  total: number;
  mature: number;
}
export interface ReviewAnswerResult {
  card_id: number;
  state: string;
  due: string | null;
  stability: number | null;
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
  placement: () => fetch("/api/placement").then(json<Placement>),
  placementResult: (results: { vocab_id: string; correct: boolean }[]) =>
    fetch("/api/placement/result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ results }),
    }).then(json<PlacementResult>),
  reviewQueue: () => fetch("/api/review/queue").then(json<ReviewQueue>),
  reviewStats: () => fetch("/api/review/stats").then(json<ReviewStats>),
  reviewAnswer: (card_id: number, rating: number) =>
    fetch("/api/review/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ card_id, rating }),
    }).then(json<ReviewAnswerResult>),
};

/** URL for a cached TTS clip. */
export function audioUrl(text: string, voice?: string): string {
  const params = new URLSearchParams({ text });
  if (voice) params.set("voice", voice);
  return `/api/audio?${params.toString()}`;
}
