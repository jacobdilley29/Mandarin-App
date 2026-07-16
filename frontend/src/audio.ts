import { useCallback, useRef, useState } from "react";
import { audioUrl } from "./api";

export type PlayState = "idle" | "loading" | "playing" | "error";

// Reuse one Audio element per (text, voice) so repeated taps don't refetch.
const cache = new Map<string, HTMLAudioElement>();

function elementFor(text: string, voice?: string): HTMLAudioElement {
  const key = `${voice ?? ""}::${text}`;
  let el = cache.get(key);
  if (!el) {
    el = new Audio(audioUrl(text, voice));
    el.preload = "none";
    cache.set(key, el);
  }
  return el;
}

/**
 * Hook to play a Chinese string as audio. Degrades gracefully: if the backend
 * can't synthesise the clip (e.g. offline / TTS unavailable), state becomes
 * "error" and the UI can show a muted affordance instead of breaking.
 */
export function useSpeak() {
  const [state, setState] = useState<PlayState>("idle");
  const currentRef = useRef<HTMLAudioElement | null>(null);

  const play = useCallback((text: string, opts?: { voice?: string; rate?: number }) => {
    if (!text) return;
    // Stop anything already playing.
    if (currentRef.current) {
      currentRef.current.pause();
      currentRef.current.currentTime = 0;
    }
    const el = elementFor(text, opts?.voice);
    el.playbackRate = opts?.rate ?? 1;
    currentRef.current = el;
    setState("loading");

    const onPlaying = () => setState("playing");
    const onEnded = () => setState("idle");
    const onError = () => setState("error");
    el.addEventListener("playing", onPlaying, { once: true });
    el.addEventListener("ended", onEnded, { once: true });
    el.addEventListener("error", onError, { once: true });

    el.play().catch(() => setState("error"));
  }, []);

  return { play, state };
}
