// ---------- Build the reviewable pool (vocab + grammar share one SRS pool) ----------
const REVIEWABLE = {};
VOCAB.forEach((v) => (REVIEWABLE[v.id] = { type: "vocab", ...v }));
GRAMMAR.forEach((g) => (REVIEWABLE[g.id] = { type: "grammar", ...g }));
const ALL_IDS = Object.keys(REVIEWABLE);

// ---------- Tabs ----------
function switchTab(name) {
  document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
  document.getElementById("tab-" + name).classList.add("active");
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  if (name === "home") refreshHomeStats();
  if (name === "listen" && !currentListenItem) nextListenRound();
  if (name === "speak" && !currentSpeakItem) nextSpeakWord();
}
document.querySelectorAll(".tab-btn").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

// ---------- Settings (persisted view state) ----------
function getListenMode() { return localStorage.getItem("mandarin_listen_mode_v1") || "word"; }
function setListenMode(m) { localStorage.setItem("mandarin_listen_mode_v1", m); }
function getSpeakMode() { return localStorage.getItem("mandarin_speak_mode_v1") || "word"; }
function setSpeakMode(m) { localStorage.setItem("mandarin_speak_mode_v1", m); }

function wireSegmented(containerId, onChange, isActive) {
  const buttons = document.querySelectorAll(`#${containerId} button`);
  buttons.forEach((btn) => {
    btn.classList.toggle("active", isActive(btn));
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      onChange(btn);
    });
  });
}

wireSegmented("rate-toggle", (btn) => setSpeechRate(parseFloat(btn.dataset.rate)), (btn) => parseFloat(btn.dataset.rate) === getSpeechRate());

function refreshStruggleList() {
  const list = getStruggleList(5);
  const card = document.getElementById("struggle-card");
  const wrap = document.getElementById("struggle-list");
  if (!list.length) {
    card.style.display = "none";
    return;
  }
  card.style.display = "block";
  wrap.innerHTML = list
    .map((r) => {
      const item = REVIEWABLE[r.id];
      if (!item || item.type !== "vocab") return "";
      const pct = Math.round(r.ratio * 100);
      return `<div class="struggle-row">
          <div><span class="hanzi">${item.hanzi}</span><span class="pinyin">${item.pinyin}</span></div>
          <span class="miss-badge">${pct}% missed</span>
        </div>`;
    })
    .join("");
}

// ---------- Home ----------
function refreshHomeStats() {
  const stats = getStats(ALL_IDS);
  document.getElementById("stat-due").textContent = stats.dueCount;
  document.getElementById("stat-new").textContent = stats.newRemaining;
  document.getElementById("stat-learned").textContent = stats.learned;
}

function renderGrammarList() {
  const wrap = document.getElementById("grammar-list");
  wrap.innerHTML = "";
  GRAMMAR.forEach((g) => {
    const details = document.createElement("details");
    details.className = "grammar-item";
    const examplesHtml = g.examples
      .map(
        (ex) => `<div class="example-line">
            <span class="hanzi">${ex.hanzi}</span>
            <span class="pinyin">${ex.pinyin}</span>
            <span class="en">${ex.en}</span>
          </div>`
      )
      .join("");
    details.innerHTML = `<summary>${g.title}</summary>
      <div class="body">
        <p class="explain">${g.explain}</p>
        ${examplesHtml}
      </div>`;
    wrap.appendChild(details);
  });
}

function updateVoiceHint() {
  document.getElementById("voice-hint").style.display = hasChineseVoice() ? "none" : "block";
}
document.addEventListener("mandarin-voices-ready", updateVoiceHint);

document.getElementById("btn-start-review").addEventListener("click", startReviewSession);
document.getElementById("btn-go-listen").addEventListener("click", () => switchTab("listen"));
document.getElementById("btn-go-speak").addEventListener("click", () => switchTab("speak"));

// ---------- Review ----------
let sessionQueue = [];
let sessionCompleted = 0;
let currentReviewId = null;
let reviewFlipped = false;

function startReviewSession() {
  sessionQueue = buildSession(ALL_IDS);
  sessionCompleted = 0;
  switchTab("review");
  nextReviewCard();
}

function updateReviewProgress() {
  const denom = sessionCompleted + sessionQueue.length;
  const pct = denom === 0 ? 100 : Math.round((sessionCompleted / denom) * 100);
  document.getElementById("review-progress").style.width = pct + "%";
}

function nextReviewCard() {
  reviewFlipped = false;
  updateReviewProgress();
  const body = document.getElementById("review-body");
  if (sessionQueue.length === 0) {
    body.innerHTML = `<div class="card empty-state">
        <svg class="brush-mark" viewBox="0 0 100 60" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M10 46 Q40 40 60 22 T90 10" stroke="#3B7A5E" stroke-width="7" stroke-linecap="round"/>
        </svg>
        <p>All caught up for now.</p>
        <button class="btn btn-ghost" id="btn-study-ahead">Study ahead anyway</button>
      </div>`;
    document.getElementById("btn-study-ahead").addEventListener("click", () => {
      sessionQueue = [...ALL_IDS].sort(() => Math.random() - 0.5).slice(0, 20);
      sessionCompleted = 0;
      nextReviewCard();
    });
    refreshHomeStats();
    return;
  }
  currentReviewId = sessionQueue[0];
  renderReviewFront(REVIEWABLE[currentReviewId]);
}

function renderReviewFront(item) {
  const body = document.getElementById("review-body");
  if (item.type === "vocab") {
    body.innerHTML = `<div class="card flashcard" id="flip-target">
        <div class="hanzi">${item.hanzi}</div>
        <div class="tap-hint">Tap the card to reveal</div>
      </div>`;
  } else {
    body.innerHTML = `<div class="card flashcard" id="flip-target">
        <div class="hanzi" style="font-size:1.6rem;">${item.title}</div>
        <div class="tap-hint">Tap the card to reveal</div>
      </div>`;
  }
  document.getElementById("flip-target").addEventListener("click", () => renderReviewBack(item));
}

function renderReviewBack(item) {
  reviewFlipped = true;
  const body = document.getElementById("review-body");
  let inner;
  if (item.type === "vocab") {
    inner = `<div class="hanzi">${item.hanzi}</div>
      <div class="pinyin">${item.pinyin}</div>
      <div class="en">${item.en}</div>
      <div class="example">
        <div>${item.ex.hanzi}</div>
        <div class="pinyin" style="font-size:0.85rem;">${item.ex.pinyin}</div>
        <div>${item.ex.en}</div>
      </div>`;
  } else {
    const examplesHtml = item.examples
      .map((ex) => `<div class="example-line"><span class="hanzi">${ex.hanzi}</span><span class="pinyin">${ex.pinyin}</span><span class="en">${ex.en}</span></div>`)
      .join("");
    inner = `<div class="hanzi" style="font-size:1.4rem;">${item.title}</div>
      <div class="example" style="text-align:left;">${item.explain}<br><br>${examplesHtml}</div>`;
  }
  body.innerHTML = `<div class="card flashcard">${inner}</div>
    <div class="btn-row">
      <button class="btn btn-again" data-grade="0">Again</button>
      <button class="btn btn-hard" data-grade="1">Hard</button>
      <button class="btn btn-good" data-grade="2">Good</button>
      <button class="btn btn-easy" data-grade="3">Easy</button>
    </div>`;
  body.querySelectorAll("[data-grade]").forEach((btn) =>
    btn.addEventListener("click", () => gradeCurrentCard(parseInt(btn.dataset.grade, 10)))
  );
  if (item.type === "vocab") speak(item.hanzi);
}

function gradeCurrentCard(grade) {
  gradeItem(currentReviewId, grade);
  sessionQueue.shift();
  sessionCompleted++;
  if (grade === 0) {
    sessionQueue.splice(Math.min(3, sessionQueue.length), 0, currentReviewId);
  }
  nextReviewCard();
}

// ---------- Listen ----------
let currentListenItem = null;

function listenPool() {
  return getListenMode() === "word" ? VOCAB : SENTENCES;
}
function listenPlayText(item) {
  return getListenMode() === "word" ? item.ex.hanzi : item.hanzi;
}
function listenAnswerText(item) {
  return getListenMode() === "word" ? item.ex.en : item.en;
}

function nextListenRound() {
  document.getElementById("btn-listen-next").style.display = "none";
  const pool = listenPool().filter((v) => v.id !== (currentListenItem && currentListenItem.id));
  currentListenItem = pool[Math.floor(Math.random() * pool.length)];
  speak(listenPlayText(currentListenItem));

  const answer = listenAnswerText(currentListenItem);
  const distractors = listenPool()
    .filter((v) => v.id !== currentListenItem.id)
    .sort(() => Math.random() - 0.5)
    .slice(0, 3)
    .map(listenAnswerText);
  const options = [...distractors, answer].sort(() => Math.random() - 0.5);

  const wrap = document.getElementById("listen-options");
  wrap.innerHTML = "";
  options.forEach((opt) => {
    const btn = document.createElement("button");
    btn.className = "quiz-option";
    btn.textContent = opt;
    btn.addEventListener("click", () => onListenAnswer(btn, opt));
    wrap.appendChild(btn);
  });
}

function onListenAnswer(btn, opt) {
  const answer = listenAnswerText(currentListenItem);
  const correct = opt === answer;
  document.querySelectorAll(".quiz-option").forEach((b) => {
    b.disabled = true;
    if (b.textContent === answer) b.classList.add("correct");
  });
  if (!correct) btn.classList.add("incorrect");
  document.getElementById("btn-listen-next").style.display = "inline-block";
}

document.getElementById("btn-play-listen").addEventListener("click", () => currentListenItem && speak(listenPlayText(currentListenItem)));
document.getElementById("btn-listen-next").addEventListener("click", nextListenRound);
wireSegmented(
  "listen-mode-toggle",
  (btn) => {
    setListenMode(btn.dataset.mode);
    currentListenItem = null;
    nextListenRound();
  },
  (btn) => btn.dataset.mode === getListenMode()
);

// ---------- Speak / Pronunciation practice ----------
let currentSpeakItem = null;

function speakPool() {
  return getSpeakMode() === "word" ? VOCAB : SENTENCES;
}

function nextSpeakWord() {
  const mode = getSpeakMode();
  const pool = speakPool().filter((v) => v.id !== (currentSpeakItem && currentSpeakItem.id));
  currentSpeakItem = pool[Math.floor(Math.random() * pool.length)];
  document.getElementById("speak-hanzi").textContent = currentSpeakItem.hanzi;
  document.getElementById("speak-pinyin").textContent = currentSpeakItem.pinyin;
  document.getElementById("mic-status").textContent = "";
  document.getElementById("speak-feedback").innerHTML = "";

  const badge = document.getElementById("speak-tone-badge");
  const canvas = document.getElementById("contourCanvas");
  const legend = document.getElementById("contour-legend");

  if (mode === "word") {
    const tone = firstToneOfPinyin(currentSpeakItem.pinyin);
    badge.style.display = "inline-block";
    badge.textContent = tone === 5 ? "Neutral tone" : "Tone " + tone;
    canvas.style.display = "block";
    legend.style.display = "flex";
    drawContour([], referenceContour(tone));
  } else {
    badge.style.display = "none";
    canvas.style.display = "none";
    legend.style.display = "none";
  }

  if (!speechRecognitionSupported()) {
    document.getElementById("speak-feedback").innerHTML =
      `<div class="feedback-tip">Speech-to-text isn't available in this browser${mode === "word" ? " — you'll still get the pitch-shape comparison." : ". Try Chrome on Android or desktop for spoken feedback."}</div>`;
  }
}

function drawContour(yourPts, refPts) {
  const canvas = document.getElementById("contourCanvas");
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  ctx.strokeStyle = "#E6DFCB";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, H - 20);
  ctx.lineTo(W, H - 20);
  ctx.stroke();

  const plot = (pts, color, width) => {
    if (!pts.length) return;
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    let started = false;
    pts.forEach((v, i) => {
      const x = (i / (pts.length - 1 || 1)) * (W - 20) + 10;
      if (v === null || v === undefined) {
        started = false;
        return;
      }
      const y = 20 + (1 - v) * (H - 60);
      if (!started) {
        ctx.moveTo(x, y);
        started = true;
      } else {
        ctx.lineTo(x, y);
      }
    });
    ctx.stroke();
  };

  plot(refPts, "#C9A24B", 4);
  plot(yourPts, "#3B7A5E", 3.5);
}

function renderSpeakFeedback(transcript) {
  const target = currentSpeakItem.hanzi;
  const heard = transcript || "";
  const diff = diffTargetAgainstHeard(target, heard);
  const matchCount = diff.filter((d) => d.matched).length;
  const ratio = target.length ? matchCount / target.length : 0;
  const diffHtml = diff.map((d) => `<span class="diff-char ${d.matched ? "match" : "miss"}">${d.char}</span>`).join("");

  let tip;
  if (ratio === 1) tip = "Recognized perfectly — nice work!";
  else if (ratio >= 0.6) tip = "Close — the underlined character(s) are the ones to work on.";
  else tip = "That didn't come through clearly — try again a little slower and more clearly.";

  document.getElementById("speak-feedback").innerHTML = `
    <div class="diff-line">${diffHtml}</div>
    <div class="heard-line">The recognizer heard: "${heard || "(nothing)"}"</div>
    <div class="feedback-tip">${tip}</div>`;

  if (getSpeakMode() === "word") {
    recordPronunciationAttempt(currentSpeakItem.id, ratio === 1);
    refreshStruggleList();
  }
}

function renderSpeakFeedbackError(err) {
  const code = (err && err.message) || "";
  let msg;
  if (code === "not-allowed") msg = "Microphone permission was blocked — allow microphone access for this site to get pronunciation feedback.";
  else if (code === "no-speech" || code === "timeout") msg = "Didn't catch any speech — try again a bit closer to the mic.";
  else if (code === "network") msg = "Speech recognition needs an internet connection.";
  else if (code === "unsupported") return; // already noted at render time
  else msg = "Couldn't get a pronunciation reading that time — try again.";
  document.getElementById("speak-feedback").innerHTML = `<div class="feedback-tip">${msg}</div>`;
}

document.getElementById("btn-play-speak").addEventListener("click", () => currentSpeakItem && speak(currentSpeakItem.hanzi));
document.getElementById("btn-next-speak").addEventListener("click", nextSpeakWord);
wireSegmented(
  "speak-mode-toggle",
  (btn) => {
    setSpeakMode(btn.dataset.mode);
    currentSpeakItem = null;
    nextSpeakWord();
  },
  (btn) => btn.dataset.mode === getSpeakMode()
);

document.getElementById("btn-record").addEventListener("click", async () => {
  const recordBtn = document.getElementById("btn-record");
  const status = document.getElementById("mic-status");
  const mode = getSpeakMode();
  recordBtn.classList.add("recording");
  status.textContent = "Listening…";

  const tasks = [];

  if (mode === "word") {
    const tone = firstToneOfPinyin(currentSpeakItem.pinyin);
    const ref = referenceContour(tone);
    tasks.push(
      recordPitchContour(1600, (partial) => drawContour(normalizeContour(partial), ref))
        .then((raw) => drawContour(normalizeContour(raw), ref))
        .catch(() => {
          status.textContent = "Microphone unavailable: this page needs to run over HTTPS (like your published site link) with mic permission allowed.";
        })
    );
  }

  if (speechRecognitionSupported()) {
    tasks.push(
      recognizeSpeech(mode === "word" ? 3000 : 5000)
        .then((result) => renderSpeakFeedback(result.transcript))
        .catch((err) => renderSpeakFeedbackError(err))
    );
  }

  await Promise.allSettled(tasks);
  recordBtn.classList.remove("recording");
  if (!status.textContent.startsWith("Microphone unavailable")) status.textContent = "";
});

// ---------- Init ----------
renderGrammarList();
refreshHomeStats();
refreshStruggleList();
updateVoiceHint();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").catch(() => {});
  });
}
