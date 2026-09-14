import { Phonetic } from "./Phonetic";

// A tile: one word, with its reading printed underneath.
//
// The reading is attached to the tile server-side, because it has to be split
// out of the sentence's own pinyin (see backend/app/zhuyin.py `for_tokens`) —
// the browser is handed one pinyin string for a whole sentence and cannot tell
// which syllables belong to which word. A tile whose reading could not be
// derived carries nulls and renders as bare hanzi; the drill still works.
export interface Tile {
  text: string;
  pinyin?: string | null;
  zhuyin?: string | null;
}

export type TileState = "rack" | "placed" | "correct" | "wrong";

const STATE_CLASS: Record<TileState, string> = {
  rack: "border-border bg-surface text-ink hover:border-primary",
  placed: "border-primary bg-primary text-primary-ink",
  correct: "border-good bg-good/10 text-good",
  wrong: "border-bad bg-accent-soft text-bad",
};

export function TileButton({
  tile,
  state = "rack",
  showReading,
  onClick,
  disabled,
}: {
  tile: Tile;
  state?: TileState;
  showReading: boolean;
  onClick?: () => void;
  disabled?: boolean;
}) {
  const reading = showReading && (tile.pinyin || tile.zhuyin);
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      lang="zh-Hant"
      className={[
        "tap flex min-w-[3rem] flex-col items-center justify-center rounded-md border px-3 py-1.5 transition-colors disabled:cursor-default",
        STATE_CLASS[state],
      ].join(" ")}
    >
      {/* The reading sits above the characters, as it does on a Taiwanese
          textbook page and in the vocabulary card. */}
      {reading && (
        <Phonetic
          pinyin={tile.pinyin}
          zhuyin={tile.zhuyin}
          className="mb-0.5 text-[0.65rem] leading-tight opacity-80"
        />
      )}
      <span className="font-han text-lg leading-tight">{tile.text}</span>
    </button>
  );
}

// The answer area: tiles placed so far, tapped to take one back.
export function TileTray({
  tiles,
  states,
  showReading,
  onRemove,
  frame,
}: {
  tiles: Tile[];
  states?: TileState[];
  showReading: boolean;
  onRemove?: (i: number) => void;
  frame: "neutral" | "correct" | "wrong";
}) {
  const border =
    frame === "correct"
      ? "border-good bg-good/10"
      : frame === "wrong"
        ? "border-bad bg-accent-soft"
        : "border-border";
  return (
    <div className={["min-h-[4.25rem] rounded-md border-2 border-dashed p-2", border].join(" ")}>
      <div className="flex flex-wrap gap-2">
        {tiles.map((t, i) => (
          <TileButton
            key={`${t.text}-${i}`}
            tile={t}
            state={states?.[i] ?? "placed"}
            showReading={showReading}
            onClick={onRemove ? () => onRemove(i) : undefined}
            disabled={!onRemove}
          />
        ))}
      </div>
    </div>
  );
}

// The rack: tiles still available to place.
export function TileRack({
  tiles,
  showReading,
  onPlace,
  disabled,
}: {
  tiles: Tile[];
  showReading: boolean;
  onPlace: (i: number) => void;
  disabled?: boolean;
}) {
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {tiles.map((t, i) => (
        <TileButton
          key={`${t.text}-${i}`}
          tile={t}
          showReading={showReading}
          onClick={() => onPlace(i)}
          disabled={disabled}
        />
      ))}
    </div>
  );
}

// Mark each placed tile against the answer, so a wrong build says *where* it
// went wrong rather than only that it did.
export function gradeTiles(built: Tile[], answer: string[]): TileState[] {
  return built.map((t, i) => (t.text === answer[i] ? "correct" : "wrong"));
}

export function tilesMatch(built: Tile[], answer: string[]): boolean {
  return built.length === answer.length && built.every((t, i) => t.text === answer[i]);
}
