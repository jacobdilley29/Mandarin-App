import { useCallback, useEffect, useState } from "react";
import { api, type DictationItem, type Tile } from "../../api";
import { useSpeak } from "../../audio";
import { useSettings } from "../../SettingsContext";
import { DEFAULT_LISTEN_SPEED, ListenSpeed } from "../../components/ListenSpeed";
import { Phonetic } from "../../components/Phonetic";
import { gradeTiles, TileRack, TileTray, tilesMatch } from "../../components/Tiles";

// Dictation, built from tiles rather than typed.
//
// It used to be a text box that accepted characters or pinyin. On a phone that
// means an IME standing between the learner and the answer, and in pinyin mode
// it quietly asked a different question — spell the sound — than the one the
// drill is for. Tiles ask only "which words did you hear", which is the whole
// point, and the reading rides along on each tile per the Me-tab setting.
export default function Dictation() {
  const { settings } = useSettings();
  const showReading = settings?.show_pinyin ?? true;
  const { play } = useSpeak();

  const [item, setItem] = useState<DictationItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rate, setRate] = useState(DEFAULT_LISTEN_SPEED);
  const [rack, setRack] = useState<Tile[]>([]);
  const [built, setBuilt] = useState<Tile[]>([]);
  const [checked, setChecked] = useState<null | boolean>(null);

  const load = useCallback(() => {
    setChecked(null);
    setBuilt([]);
    setRack([]);
    api
      .listenDictation()
      .then((next) => {
        setItem(next);
        setRack(next.tiles);
      })
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(load, [load]);

  function playClip(r = rate) {
    if (item) play(item.audio_text, { voice: item.voice, rate: r });
  }

  function place(i: number) {
    if (checked != null) return;
    setBuilt([...built, rack[i]]);
    setRack(rack.filter((_, j) => j !== i));
  }
  function remove(i: number) {
    if (checked != null) return;
    setRack([...rack, built[i]]);
    setBuilt(built.filter((_, j) => j !== i));
  }

  if (error) return <div className="text-bad">{error}</div>;
  if (!item) return <div className="text-ink-soft">Loading…</div>;

  return (
    <div className="card">
      <p className="text-sm text-ink-soft">Listen, then build what you hear from the tiles.</p>

      <div className="mt-4 flex flex-col items-center gap-3">
        <button
          type="button"
          onClick={() => playClip()}
          className="tap flex h-16 w-16 items-center justify-center rounded-full bg-primary text-primary-ink shadow-card active:scale-95"
          aria-label="Play sentence"
        >
          <svg viewBox="0 0 24 24" className="h-7 w-7" fill="currentColor">
            <path d="M8 5v14l11-7z" />
          </svg>
        </button>
        <ListenSpeed
          rate={rate}
          onChange={(r) => {
            setRate(r);
            playClip(r);
          }}
        />
      </div>

      <div className="mt-5">
        <TileTray
          tiles={built}
          states={checked == null ? undefined : gradeTiles(built, item.answer)}
          showReading={showReading}
          onRemove={checked == null ? remove : undefined}
          frame={checked == null ? "neutral" : checked ? "correct" : "wrong"}
        />
      </div>

      {checked == null ? (
        <>
          <TileRack tiles={rack} showReading={showReading} onPlace={place} />
          <button
            type="button"
            disabled={built.length === 0}
            onClick={() => setChecked(tilesMatch(built, item.answer))}
            className="mt-6 w-full rounded-md bg-primary py-3 font-medium text-primary-ink disabled:opacity-40"
          >
            Check
          </button>
        </>
      ) : (
        <div className="mt-4">
          <div
            className={["text-center text-sm font-medium", checked ? "text-good" : "text-warn"].join(
              " ",
            )}
          >
            {checked ? "✓ Correct" : "Not quite — the sentence was:"}
          </div>
          <div className="mt-3 rounded-md bg-surface-2 p-3 text-center">
            <button
              type="button"
              onClick={() => playClip()}
              lang="zh-Hant"
              className="font-han text-lg text-ink underline decoration-ink-faint"
            >
              {item.hanzi}
            </button>
            {showReading && (
              <Phonetic
                pinyin={item.pinyin}
                className="mt-0.5 block text-sm text-ink-soft"
              />
            )}
            <div className="text-sm text-ink-soft">{item.gloss}</div>
          </div>
          <button
            type="button"
            onClick={load}
            className="mt-4 w-full rounded-md bg-primary py-3 font-medium text-primary-ink"
          >
            Next ▸
          </button>
        </div>
      )}
    </div>
  );
}
