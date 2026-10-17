# Feedback loop

How a player's attempt gets back into the content. Two early observations drove the
design: some drills rejected correct solutions (copy_line was ex-kind, so `yyjp` failed),
and practice turned up pars that could be shorter. The oracle cannot catch either,
because it only verifies the solutions someone already thought of. Players are the
search engine the par search is missing (ADR 0009).

## What is recorded

Every attempt logs `keys` (a count). Three optional fields on `AttemptRecord`
(`app/src/model/model.ts`) carry what the loop needs:

```json
{ "t": ..., "ex": "py/x.copymove/03ed26c61c", "ok": true, "ms": 2100, "keys": 4, "par": 4,
  "seq": "yyjp", "beatPar": false }
```

- `seq`: the normalised keystrokes in angle-bracket notation, the string the result
  strip shows, except that a `jk` escape is logged as `<Esc>` so Neovim can replay it
  (`replayKeys(tokens)` in `grading.ts`). Set on practice and placement records.
- `beatPar`: true when `ok && keys < par`. The result strip says so plainly ("you beat
  par: 3 vs 4"), using the `beat` band in grading.md.
- `flag`: absent until the player flags the attempt. Shape
  `{reason: "wrong-par" | "wording" | "emulator" | "other", note?: string}`.

Both model mirrors pass the fields through untouched; the Python model reads records as
dicts and ignores extra keys, and the vector digest ignores record contents. One test per
suite checks that a record with `seq` survives `applyAttempt` unchanged.

Nothing is sent anywhere automatically. The log stays in localStorage and in the
export file.

## The `!` flag

On the result strip, `!` opens a small picker in the footer:

| key | reason | meaning |
|---|---|---|
| `1` | `wrong-par` | a shorter solution, or a correct one that was rejected |
| `2` | `wording` | the task text was unclear or wrong |
| `3` | `emulator` | the editor behaved differently from real Vim |
| `4` | `other` | anything else |

An optional one-line note goes in a text field; `Enter` confirms and `Esc` cancels. On
confirm the app sets `flag` on that attempt's record in `saved.model.log`, saves, and
opens the prefilled issue below. A flag during placement lands on the placement record
and reaches the log with it. Warm-ups and placement retries are not logged, so flagging
one only opens the issue. The result-strip legend shows `[!] flag`.
`app/README.md` has a reading note on this code path for the TypeScript reader.

## How it gets back (no backend)

1. **Prefilled GitHub issue.** Confirming a flag opens a new tab on
   `https://github.com/daniel-m-campos/vim-trainer/issues/new` with the `feedback`
   label and a prefilled title and body: exercise id, language, kind, task text, the
   player's `seq`, the par keys, the flag reason, the note, the editor profile and the
   app version. The task, `seq` and note are clipped to 400 characters each, and the
   body is cut until it is at most 6000 characters once URL-encoded, which keeps the
   URL under GitHub's limit of about 8k characters. If a popup blocker stops the new
   tab, the strip says so and links the form. The player can edit and submit, or close
   the tab. The issue tracker is the review queue.
2. **Export file.** Settings -> export produces the full state. A "Share your log"
   paragraph next to it says what the file contains and links the issues page, for
   people who prefer a bulk hand-off.

There is no third channel. The site has no server (ADR 0012), so nothing is collected
unless a player files an issue or attaches an export. The repo URL is one constant
(`REPO` in `app/src/feedback.ts`), so moving the tracker is a one-line change.

## Error ring buffer

The app keeps the last 20 uncaught errors and unhandled rejections (`ERRORS_MAX` in
`app/src/storage.ts`) in `saved.errors`: timestamp, app version, route, message and the
first 5 stack lines, nothing typed by the player. The footer then says "something broke —
export your data and flag it with !" until the next exercise opens. The export includes
the buffer, and the prefilled issue body appends the newest 3 entries after the flag
fields, one line at a time and only while the body stays under the 6000-character
encoded limit, so the par and version lines are never pushed out. The version field is
a real version string, `package.json` version plus the short commit (`0.4.0+5b58f38`,
`__APP_VERSION__` in `vite.config.ts`), so a report can be matched to the code that
produced it.

## What the pipeline does with it

`uv run vimtrainer-content ingest <path>` takes an exported `Saved` JSON or a GitHub
issue body saved to a file.

- It collects records with `beatPar` or a `wrong-par` or `emulator` flag and replays
  every `seq` in one Neovim batch against the exercise in `build/exercises/`
  (`oracle.verify_many`).
- **Passes and shorter than par:** `seq` becomes the canonical in the exercise JSON and
  the old canonical moves to `alternates`. The sequence is generalised (digit runs to
  `{{k}}`, which expands to 1-9; typed insert text to `{{text}}`), deduplicated, and
  appended to `content/idioms_learned.toml` under its skill with `status = "new"`.
  `par_search.IDIOMS` merges that file at import, so the next `make content` re-pars
  every sibling exercise with the new idiom, and `build.evaluate` lets a learned idiom
  compete as a canonical variant, so the player's par survives the rebuild.
- **Passes at equal length or longer:** `seq` is added to `alternates`, and its
  generalised idiom is appended to `idioms_learned.toml` as well, so the rebuild ships it
  as an alternate (a learned variant that ties or loses never becomes the canonical).
  Only an idiom already in `idioms_learned.toml` counts as known: built-in idioms are
  build candidates, not variants, so a player's built-in idiom is written too.
- **Fails in Neovim but the app said correct:** the emulator accepted something real
  Vim does not. The exercise id, `seq`, the Neovim verdict and the first differing line
  go to `content/review/emulator-divergences.md`. A seq that both reject is only logged.
- **Passes in Neovim but the app said wrong:** also a divergence entry (the `yyjp`
  bug class).
- `wording` flags go to `content/review/wording-queue.md`, grouped by template.
- Every run appends date, source and outcome per record to
  `content/review/ingest-log.md`.

`ingest` creates each of these review files the first time it writes to it; a fresh
checkout has none of them.

The oracle stays the arbiter. A player report never changes a par without passing
through real Neovim.

## Human review

Ingest writes; a human decides what ships. Before committing an ingest run, a
maintainer:

- reads the diff of `content/idioms_learned.toml`, since one bad generalisation re-pars
  a whole template (`vimtrainer-content review --idioms` lists the entries), and sets
  each new entry's `status` to `ok` or `rejected`;
- works through `wording-queue.md` and fixes the template text, not single exercises;
- reproduces each entry in `emulator-divergences.md` as an editor case
  (`app/e2e/cases/*.json`), then fixes it in `vimfixes.ts` or records it in
  `build/supported_commands.md` (the differential fuzzer in differential-testing.md
  finds most of these first);
- runs `make content` and `make content-check`, and closes the GitHub issue with a
  link to the commit.

## Why pars can be wrong, and the structural fix

The par search tries a fixed idiom list per skill plus the template's own variants.
That finds shorter *known* idioms, never unknown ones. Three changes narrow the gap:

1. **Kind by intent, not by skill.** `ex` kind only for drills where normal mode would
   be a repetition drill rather than the skill (`:g`, `:v`, `:normal`, `:s` over many
   lines). Copy, move and duplicate are `edit` (content-pipeline.md, Template kind rule).
2. **Cross-skill idiom search.** When searching a par, try every skill's idioms, not
   only the drilled skill's, so a `t.paren` drill learns that `ct)` or `f)` can beat
   `ci(` in a given buffer. Cost is oracle time, which is cheap in batches. Not built.
3. **Player-sourced idioms** via the loop above. Built.

## Quality signal

The flag rate (flagged attempts per attempt, by reason) and the error-buffer count are
the trainer's quality signal. A rising `wrong-par` rate points at the par search, a
rising `emulator` rate at `vimfixes.ts`, and a rising `wording` rate at the templates.
They are read from filed issues and shared exports; nothing is measured centrally.

## Scope and what it is not

- No leaderboards, no social. The log is yours; sharing is a deliberate act.
- No LLM involvement: reports are verified by Neovim and read by a human.
- Not a replacement for the issue tracker; GitHub issues are the tracker.
