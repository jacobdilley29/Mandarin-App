# HSK word lists

Vendored reference data: the HSK 2.0 vocabulary lists for levels 1–4, used by
`backend/scripts/build_skeleton.py` to build the curriculum skeleton.

| File | Level | Words |
|---|---|---|
| `hsk1.json` | HSK 1 | 150 |
| `hsk2.json` | HSK 2 | 147 |
| `hsk3.json` | HSK 3 | 298 |
| `hsk4.json` | HSK 4 | 598 |
| | **total** | **1,193** |

These are committed rather than downloaded so the app never needs network access
to rebuild its curriculum. (The CC-CEDICT importer in
`backend/scripts/import_cedict.py` does still download at setup, but nothing in
this pipeline depends on it.)

## Source and licence

Derived from [`drkameleon/complete-hsk-vocabulary`](https://github.com/drkameleon/complete-hsk-vocabulary),
`wordlists/exclusive/old/` — the HSK 2.0 (pre-2021) lists.

- The dataset is **MIT licensed**, © Yanis Zafirópulos.
- Its English definitions derive from [CC-CEDICT](https://www.mdbg.net/chinese/dictionary),
  licensed **CC BY-SA 4.0**. The `gloss` field in these files is therefore
  CC BY-SA 4.0 and carries that licence onward.
- The upstream old-HSK lists originate from
  [`clem109/hsk-vocabulary`](https://github.com/clem109/hsk-vocabulary).

## Shape

Each file is `{ meta, words: [...] }`; `words` is sorted by descending frequency
(most common first), which is the order `build_skeleton.py` bins them in.

```json
{
  "traditional": "愛",
  "simplified": "爱",
  "pinyin": "ài",
  "bopomofo": "ㄞˋ",
  "gloss": "to love; to be fond of; to like",
  "pos": ["v", "vn", "b"],
  "frequency": 130,
  "hsk_level": 1,
  "readings": ["ài", "ài"]
}
```

`readings` is present only on polyphonic entries (多音字) — it lists every
reading the source carried, so a wrong pick is recoverable. See "Readings" below.

`bopomofo` is not used to render the app's zhuyin (that is derived from pinyin by
`backend/app/zhuyin.py`); it is kept as an independent cross-check. Validating the
converter against all 1,193 entries found **zero genuine mismatches** — the only
differences were neutral-tone dot placement, where this app follows the Taiwan MOE
convention (`˙ㄒㄧㄝ`) and the dataset does not (`ㄒㄧㄝ˙`).

## These lists are mainland-standard — read `taiwan_overrides.json`

They carry **traditional characters but PRC vocabulary and PRC readings**. Two
systematic divergences matter for a Taiwan-focused app, and both are handled by
`content/taiwan_overrides.json`, applied by `build_skeleton.py`:

1. **Vocabulary.** 11 entries are PRC words with different Taiwan equivalents —
   自行車→腳踏車, 出租車→計程車, 地鐵→捷運, 公共汽車→公車, and so on.
2. **Readings.** Besides the readings spec §6 names (垃圾 lèsè, 星期 xīngqí,
   和 hàn), the mainland standard **neutralises a second syllable that Taiwan keeps
   fully toned** — 朋友 is péngyǒu in Taiwan, not péngyou; likewise 學生 xuéshēng,
   喜歡 xǐhuān, 衣服 yīfú. 83 list entries fall in this class.

Never edit these files to fix a Taiwan difference — put it in
`taiwan_overrides.json`, so refreshing a list from upstream cannot clobber it.

## Readings

The source lists every reading of a polyphonic character in its `forms` array, and
the first one is frequently *not* the one a learner wants: 都 leads with `Dū` (the
surname) rather than `dōu`, 讀 with `dòu` rather than `dú`, 個 with `gě` rather
than `gè`. The slimming pass picks a reading by dropping proper-noun (capitalised)
readings and preferring the one with the most senses.

Checked against the 88 words that also appear in the hand-authored curriculum, that
heuristic agrees on 78. The disagreements were all the Taiwan/mainland tone
difference above — plus one genuine error in the hand-authored content (好吃 was
transcribed `hào chī` but means `hǎochī`), now corrected in `taiwan_overrides.json`.

Words the heuristic cannot resolve confidently are listed under `needs_review` in
that file and are settled per word by the Claude theming pass.
