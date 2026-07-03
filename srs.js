// Simplified SM-2 spaced repetition, persisted to localStorage.
// Each reviewable item (vocab or grammar) gets a state record:
// { interval (days), ease, reps, due (ISO date string) }

const SRS_KEY = "mandarin_srs_v1";
const NEW_PER_DAY_KEY = "mandarin_new_today_v1";
const DAY_MS = 24 * 60 * 60 * 1000;

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function loadState() {
  try {
    const raw = localStorage.getItem(SRS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (e) {
    return {};
  }
}

function saveState(state) {
  localStorage.setItem(SRS_KEY, JSON.stringify(state));
}

function getNewTodayCount() {
  try {
    const raw = JSON.parse(localStorage.getItem(NEW_PER_DAY_KEY) || "{}");
    return raw.date === todayStr() ? raw.count : 0;
  } catch (e) {
    return 0;
  }
}

function bumpNewTodayCount() {
  const count = getNewTodayCount() + 1;
  localStorage.setItem(NEW_PER_DAY_KEY, JSON.stringify({ date: todayStr(), count }));
}

const NEW_CARD_LIMIT = 12;

// Returns { due: [...ids due now], fresh: [...ids never studied] }
function getQueue(allIds) {
  const state = loadState();
  const now = Date.now();
  const due = [];
  const fresh = [];
  for (const id of allIds) {
    const rec = state[id];
    if (!rec) {
      fresh.push(id);
    } else if (new Date(rec.due).getTime() <= now) {
      due.push(id);
    }
  }
  return { due, fresh, state };
}

// Build today's review session: all due items + a capped number of new items.
function buildSession(allIds) {
  const { due, fresh } = getQueue(allIds);
  const newBudget = Math.max(0, NEW_CARD_LIMIT - getNewTodayCount());
  const newOnes = fresh.slice(0, newBudget);
  // interleave: due items first, then new items mixed in every third slot
  const session = [...due];
  newOnes.forEach((id, i) => {
    const pos = Math.min(session.length, i * 3 + 1);
    session.splice(pos, 0, id);
  });
  return session;
}

// grade: 0 = again, 1 = hard, 2 = good, 3 = easy
function gradeItem(id, grade) {
  const state = loadState();
  const isNew = !state[id];
  let rec = state[id] || { interval: 0, ease: 2.5, reps: 0, due: new Date().toISOString() };

  if (grade === 0) {
    rec.reps = 0;
    rec.interval = 0;
    rec.ease = Math.max(1.3, rec.ease - 0.2);
    rec.due = new Date(Date.now() + 5 * 60 * 1000).toISOString(); // due again in 5 min (same session)
  } else {
    if (grade === 1) rec.ease = Math.max(1.3, rec.ease - 0.15);
    if (grade === 3) rec.ease = rec.ease + 0.15;

    if (rec.reps === 0) rec.interval = grade === 1 ? 1 : grade === 2 ? 1 : 2;
    else if (rec.reps === 1) rec.interval = grade === 1 ? 2 : grade === 2 ? 6 : 8;
    else rec.interval = Math.round(rec.interval * rec.ease * (grade === 1 ? 0.8 : grade === 3 ? 1.3 : 1));

    rec.reps += 1;
    rec.due = new Date(Date.now() + rec.interval * DAY_MS).toISOString();
  }

  state[id] = rec;
  saveState(state);
  if (isNew) bumpNewTodayCount();
  return rec;
}

function getStats(allIds) {
  const state = loadState();
  const { due, fresh } = getQueue(allIds);
  const learned = allIds.length - fresh.length;
  return { dueCount: due.length, newRemaining: Math.max(0, NEW_CARD_LIMIT - getNewTodayCount()), learned, total: allIds.length };
}

function resetProgress() {
  localStorage.removeItem(SRS_KEY);
  localStorage.removeItem(NEW_PER_DAY_KEY);
}
