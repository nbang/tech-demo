# Vietnamese subtitle style guide

Read this before translating the first batch. Subtitle translation is constrained
writing — the reader gets one pass at reading speed, so a shorter natural line
beats a complete accurate one.

## Register and pronouns

Vietnamese forces a relationship choice on almost every line, and the source
language rarely encodes it. Decide once per speaker pair, then hold it:

| Situation | Speaker → listener |
|---|---|
| Strangers, neutral/polite | tôi → anh / chị |
| Close friends, peers | tớ/mình → cậu, or tao → mày when clearly crude |
| Older to younger (family, mentor) | anh/chị/chú/cô → em |
| Younger to older | em/con → anh/chị/bố/mẹ/thầy |
| Formal, workplace, official | tôi → ông/bà/quý vị |
| Superior to subordinate, military | ta/tôi → cậu/các anh |

Notes:
- Getting the pair wrong is more jarring to a viewer than an imprecise noun. If
  the relationship is genuinely unclear early on, start neutral (tôi/anh) and
  keep it — do not drift mid-file.
- English "you" plural → các anh / các chị / mọi người, not a bare anh.
- Vietnamese drops pronouns freely. When the referent is obvious, omit them: it
  buys characters and reads more naturally.
- Chinese 您 signals deference — reach for ông/bà/quý vị, not anh.

## Length and line breaks

- ≤ 42 characters per line, ≤ 2 lines, ≤ ~21 characters/second. `srt_kit.py check`
  reports violations; each cue's `max_chars` in the batch file is the budget.
- Break at clause boundaries, never inside a phrase:
  - good: `Nếu cậu đi bây giờ,` / `sẽ không ai biết đâu.`
  - bad: `Nếu cậu đi bây giờ, sẽ không` / `ai biết đâu.`
- Keep a noun with its classifier (`một chiếc` / `xe`, never split) and a name
  with its title (`bác sĩ Lâm`).
- Cutting is the main skill. Fillers (`you know`, `I mean`, `那个`, `就是`),
  repeated vocatives and redundant subjects go first.

## English → Vietnamese traps

- Tense lives in adverbs, not verbs: đã / đang / sẽ / rồi / vừa. Use them only
  where the timeline is genuinely unclear — over-marking bloats the line.
- Passive voice usually flips to active. `He was arrested` → `Họ đã bắt anh ta`,
  or `bị bắt` when the agent truly is unknown (bị = adverse, được = favourable).
- Politeness particles carry tone better than adverbs: nhé, đấy, mà, thôi, ạ.
  `Come on, let's go` → `Đi thôi.`
- Profanity: match intensity, not vocabulary. Vietnamese swearing escalates
  through pronouns (tao/mày) and mẹ-/đồ- constructions; a literal rendering
  usually lands far stronger or far weaker than the original.
- Idioms get a Vietnamese equivalent or a plain paraphrase — never a literal one.

## Chinese → Vietnamese traps

- **Names.** Use the customary Sino-Vietnamese reading for Chinese personal and
  place names (李伟 → Lý Vĩ, 北京 → Bắc Kinh), not pinyin. Modern pop-culture
  names sometimes circulate in pinyin — follow the source's own convention if one
  is already established in the file or a supplied glossary, and stay consistent.
- **Kinship terms are plot-relevant.** 哥/姐/叔/伯/舅 map onto anh/chị/chú/bác/cậu
  and carry which side of the family and relative age. Get these right; viewers
  notice immediately.
- **Titles.** 师父 → thầy/sư phụ, 掌门 → chưởng môn, 皇上 → hoàng thượng,
  大人 → đại nhân. Wuxia and period drama have settled Vietnamese conventions;
  use them rather than inventing.
- Chinese is compact — expect the Vietnamese to run 40–70% longer in characters.
  This is where `max_chars` bites hardest; compress aggressively.
- Measure words and 了/过/着 aspect markers usually vanish into adverbs or nothing.
- 你/我 in argument scenes often warrants mày/tao once hostility is established.

## Formatting conventions

- Keep markup byte-identical: `<i>…</i>` (thoughts, off-screen voices, song
  titles), `{\an8}` (top placement, used when on-screen text sits at the bottom).
- Speaker dashes stay dashes: `- Cậu đến rồi à?` / `- Vâng.`
- Numbers: Vietnamese uses `.` for thousands and `,` for decimals (1.000 / 3,5).
  Convert units when the exact figure is not the point.
- Sound cues in brackets get translated: `[laughter]` → `[tiếng cười]`.
  `♪` lines stay untouched.
- On-screen text (signs, letters, chyrons) is conventionally set in caps or
  italics — follow whatever the source file already does.
- Don't add a translator credit, and don't leave romanisation in parentheses.
