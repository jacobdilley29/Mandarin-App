// --- Text-to-speech -------------------------------------------------

const RATE_KEY = "mandarin_speech_rate_v1";
function getSpeechRate() {
  const v = parseFloat(localStorage.getItem(RATE_KEY));
  return isNaN(v) ? 0.85 : v;
}
function setSpeechRate(rate) {
  localStorage.setItem(RATE_KEY, String(rate));
}

let cachedVoices = [];
function refreshVoices() {
  cachedVoices = window.speechSynthesis ? window.speechSynthesis.getVoices() : [];
  document.dispatchEvent(new Event("mandarin-voices-ready"));
}
if (window.speechSynthesis) {
  refreshVoices();
  window.speechSynthesis.onvoiceschanged = refreshVoices;
}

function pickChineseVoice() {
  if (!cachedVoices.length) refreshVoices();
  const byLang = (prefix) => cachedVoices.find((v) => v.lang && v.lang.toLowerCase().startsWith(prefix));
  return byLang("zh-tw") || byLang("zh-hk") || byLang("zh-cn") || byLang("zh") || null;
}

function speak(text, { rate } = {}) {
  if (!window.speechSynthesis) return false;
  window.speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(text);
  const voice = pickChineseVoice();
  if (voice) utter.voice = voice;
  utter.lang = voice ? voice.lang : "zh-TW";
  utter.rate = rate !== undefined ? rate : getSpeechRate();
  window.speechSynthesis.speak(utter);
  return true;
}

function hasChineseVoice() {
  return !!pickChineseVoice();
}

// --- Microphone pitch contour ----------------------------------------
// Records ~1.6s of audio and returns a normalized pitch contour:
// an array of 0..1 values (silence => null) sampled at a fixed rate.

let micStream = null;

async function ensureMic() {
  if (micStream) return micStream;
  micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  return micStream;
}

// Autocorrelation-based pitch detection on a Float32 time-domain buffer.
function detectPitch(buf, sampleRate) {
  const SIZE = buf.length;
  let rms = 0;
  for (let i = 0; i < SIZE; i++) rms += buf[i] * buf[i];
  rms = Math.sqrt(rms / SIZE);
  if (rms < 0.01) return -1; // too quiet, treat as silence

  // trim leading/trailing near-silence for a cleaner autocorrelation window
  let start = 0, end = SIZE - 1;
  const thresh = 0.2;
  while (start < SIZE && Math.abs(buf[start]) < thresh * rms) start++;
  while (end > start && Math.abs(buf[end]) < thresh * rms) end--;
  const trimmed = buf.slice(start, end);
  const n = trimmed.length;
  if (n < 512) return -1;

  const minLag = Math.floor(sampleRate / 500); // ~500 Hz upper bound
  const maxLag = Math.floor(sampleRate / 70);  // ~70 Hz lower bound
  let bestLag = -1;
  let bestCorr = 0;

  for (let lag = minLag; lag <= maxLag && lag < n; lag++) {
    let corr = 0;
    for (let i = 0; i < n - lag; i++) corr += trimmed[i] * trimmed[i + lag];
    corr = corr / (n - lag);
    if (corr > bestCorr) {
      bestCorr = corr;
      bestLag = lag;
    }
  }
  if (bestLag <= 0) return -1;
  return sampleRate / bestLag;
}

// Records for `durationMs`, returns { freqs: number[]|-1, times: number[] }
async function recordPitchContour(durationMs = 1600, onFrame) {
  const stream = await ensureMic();
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 2048;
  source.connect(analyser);
  const buf = new Float32Array(analyser.fftSize);

  const freqs = [];
  const start = performance.now();

  return new Promise((resolve) => {
    function tick() {
      analyser.getFloatTimeDomainData(buf);
      const f = detectPitch(buf, ctx.sampleRate);
      freqs.push(f);
      if (onFrame) onFrame(freqs.slice());
      if (performance.now() - start < durationMs) {
        requestAnimationFrame(tick);
      } else {
        source.disconnect();
        ctx.close();
        resolve(freqs);
      }
    }
    tick();
  });
}

// Normalize a freq contour (values or -1 for silence) to 0..1 for plotting.
function normalizeContour(freqs) {
  const voiced = freqs.filter((f) => f > 0);
  if (voiced.length < 3) return freqs.map(() => null);
  const min = Math.min(...voiced);
  const max = Math.max(...voiced);
  const range = Math.max(1, max - min);
  return freqs.map((f) => (f > 0 ? (f - min) / range : null));
}

// Idealized reference shapes for the four tones + neutral, as 0..1 curves
// sampled at 20 points, for overlay comparison in the Tone Lab.
function referenceContour(toneNumber) {
  const N = 20;
  const pts = [];
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1);
    let y;
    switch (toneNumber) {
      case 1: y = 0.85; break; // high and flat
      case 2: y = 0.25 + 0.6 * t; break; // rising
      case 3: y = 0.55 - 0.45 * Math.sin(Math.PI * t) ; break; // dip then rise
      case 4: y = 0.9 - 0.75 * t; break; // sharp fall
      default: y = 0.45; break; // neutral, short & flat-ish
    }
    pts.push(Math.max(0.03, Math.min(0.97, y)));
  }
  return pts;
}

// Extract the tone number from a pinyin syllable's diacritic, e.g. "mā" -> 1.
const TONE_MARKS = {
  "ā": 1, "ē": 1, "ī": 1, "ō": 1, "ū": 1, "ǖ": 1,
  "á": 2, "é": 2, "í": 2, "ó": 2, "ú": 2, "ǘ": 2,
  "ǎ": 3, "ě": 3, "ǐ": 3, "ǒ": 3, "ǔ": 3, "ǚ": 3,
  "à": 4, "è": 4, "ì": 4, "ò": 4, "ù": 4, "ǜ": 4,
};
function toneOfSyllable(syllable) {
  for (const ch of syllable) {
    if (TONE_MARKS[ch]) return TONE_MARKS[ch];
  }
  return 5; // neutral tone if no mark found
}
function firstToneOfPinyin(pinyin) {
  const firstSyllable = pinyin.split(/[\s']+/)[0] || pinyin;
  return toneOfSyllable(firstSyllable);
}

// --- Speech recognition (for pronunciation feedback) -----------------
// Uses the browser's built-in recognizer. This sends audio to the
// browser vendor's speech service over the network (unlike the fully
// local pitch-contour analysis above) and isn't available everywhere.

function speechRecognitionSupported() {
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

// Returns a promise resolving to { transcript, confidence } or rejecting
// with an Error describing what went wrong.
function recognizeSpeech(durationMs = 3500) {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return Promise.reject(new Error("unsupported"));

  return new Promise((resolve, reject) => {
    const rec = new Recognition();
    const voice = pickChineseVoice();
    rec.lang = voice ? voice.lang : "zh-TW";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    let settled = false;
    const timeout = setTimeout(() => {
      if (!settled) {
        settled = true;
        rec.stop();
        reject(new Error("timeout"));
      }
    }, durationMs);

    rec.onresult = (event) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      const result = event.results[0][0];
      resolve({ transcript: result.transcript.trim(), confidence: result.confidence });
    };
    rec.onerror = (event) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      reject(new Error(event.error || "recognition-error"));
    };
    rec.onend = () => {
      if (!settled) {
        settled = true;
        clearTimeout(timeout);
        reject(new Error("no-speech"));
      }
    };
    try {
      rec.start();
    } catch (e) {
      clearTimeout(timeout);
      reject(e);
    }
  });
}

// --- Character-level diff (target vs. what was recognized) -----------
// Longest-common-subsequence alignment so we can highlight, character by
// character in the TARGET string, which parts likely came through and
// which didn't — without requiring an exact whole-string match.

function diffTargetAgainstHeard(target, heard) {
  const a = Array.from(target);
  const b = Array.from(heard || "");
  const n = a.length, m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  const matched = new Array(n).fill(false);
  let i = n, j = m;
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) {
      matched[i - 1] = true;
      i--; j--;
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      i--;
    } else {
      j--;
    }
  }
  return a.map((ch, idx) => ({ char: ch, matched: matched[idx] }));
}
