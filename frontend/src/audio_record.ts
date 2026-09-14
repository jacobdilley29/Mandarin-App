import { useCallback, useRef, useState } from "react";

// Records mic audio (MediaRecorder → webm/opus) and decodes it to a 16-kHz mono
// 16-bit PCM WAV in the browser, so the backend needs no ffmpeg/decoder.

export type RecState = "idle" | "recording" | "processing" | "denied" | "unsupported";

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeStr = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, samples.length * 2, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

function resample(input: Float32Array, inRate: number, outRate: number): Float32Array {
  if (inRate === outRate) return input;
  const ratio = inRate / outRate;
  const outLen = Math.round(input.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio;
    const i0 = Math.floor(pos);
    const frac = pos - i0;
    out[i] = (input[i0] ?? 0) * (1 - frac) + (input[i0 + 1] ?? input[i0] ?? 0) * frac;
  }
  return out;
}

async function blobToWav16k(blob: Blob): Promise<Blob> {
  const arrayBuffer = await blob.arrayBuffer();
  const AudioCtx: typeof AudioContext =
    window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  const ctx = new AudioCtx();
  try {
    const decoded = await ctx.decodeAudioData(arrayBuffer);
    const mono = decoded.getChannelData(0); // channel 0 is fine for a single mic
    const resampled = resample(mono, decoded.sampleRate, 16000);
    return encodeWav(resampled, 16000);
  } finally {
    ctx.close();
  }
}

export function useRecorder(maxMs = 6000) {
  const [state, setState] = useState<RecState>("idle");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const resolveRef = useRef<((wav: Blob | null) => void) | null>(null);

  const supported =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined";

  const stop = useCallback(() => {
    if (timerRef.current) window.clearTimeout(timerRef.current);
    recorderRef.current?.state !== "inactive" && recorderRef.current?.stop();
  }, []);

  const start = useCallback(async (): Promise<Blob | null> => {
    if (!supported) {
      setState("unsupported");
      return null;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const rec = new MediaRecorder(stream);
      recorderRef.current = rec;
      chunksRef.current = [];
      rec.ondataavailable = (e) => e.data.size > 0 && chunksRef.current.push(e.data);
      const done = new Promise<Blob | null>((resolve) => (resolveRef.current = resolve));
      rec.onstop = async () => {
        setState("processing");
        stream.getTracks().forEach((t) => t.stop());
        try {
          const webm = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
          const wav = await blobToWav16k(webm);
          setState("idle");
          resolveRef.current?.(wav);
        } catch {
          setState("idle");
          resolveRef.current?.(null);
        }
      };
      rec.start();
      setState("recording");
      timerRef.current = window.setTimeout(stop, maxMs);
      return done;
    } catch {
      setState("denied");
      return null;
    }
  }, [maxMs, stop, supported]);

  return { state, start, stop, supported };
}
