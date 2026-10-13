# Feedback loop

Added 2026-10-13 after the author's first practice sessions. Two observations drove it:
some drills rejected correct solutions (copy_line was ex-kind, so `yyjp` failed), and
the author found pars that could be shorter. Neither can be caught by the oracle alone,
because the oracle only verifies the solutions we already thought of. Players are the
search engine we are missing (ADR 0009).

Status: built in round 3a (2026-10-13). The sections below describe what shipped.

## What we record

Every attempt already logged `keys` (a count). Round 3a adds three optional fields to
`AttemptRecord` (`app/src/model/model.ts`):

```json
{ "t": ..., "ex": "py/x.copymove/03ed26c61c", "ok": true, "ms": 2100, "keys": 4, "par": 4,
  "seq": "yyjp", "beatPar": false }
```

- `seq`: the normalised keystrokes in angle-bracket notation, the string the result
  strip shows, except that a `jk` escape is logged as `<Esc>` so Neovim can replay it
  (`replayKeys(tokens)` in `grading.ts`). Set on practice and placement records.
- `beatPar`: true when `ok && keys < par`. The result strip says so plainly ("you beat
  par: 3 vs 4"), using the `beat` band in 05.
- `flag`: absent until the player flags the attempt. Shape
  `{reason: "wrong-par" | "wording" | "emulator" | "other", note?: string}`.

Both model mirrors pass the fields through untouched; the Python model reads records as
dicts and ignores extra keys, and the vector digest ignores record contents, so no
vectors changed. One test per suite checks that a record with `seq` survives
`applyAttempt` unchanged.

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

## How it gets back to us (no backend in v1)

1. **Prefilled GitHub issue.** Confirming a flag opens a new tab on
   `https://github.com/daniel-m-campos/vim-trainer/issues/new` with the `feedback`
   label and a prefilled title and body: exercise id, language, kind, task text, the
   player's `seq`, the par keys, the flag reason, the note, the editor profile and the
   app version. The task, `seq` and note are clipped to 400 characters each, and the
   body is cut until it is at most 6000 characters once URL-encoded, which keeps the
   URL under GitHub's limit of about 8k characters. If a popup blocker stops the new
   tab, the strip says so and links the form. The player
   can edit and submit, or close the tab. The issue tracker is the review queue.
2. **Export file.** Settings -> export produces the full state. A "Share your log"
   paragraph next to it says what the file contains and links the issues page, for
   people who prefer a bulk hand-off.
3. **Later, with accounts (pro):** an opt-in "send attempts" toggle posts
   `{seq, ex, ok, keys, par, flag}` batches to a small Worker endpoint. No code, no
   buffers, no timing beyond ms. Off by default. Not before M7.

**Which repo.** Decided by the author on 2026-10-13: the link targets the main repo
`daniel-m-campos/vim-trainer` for now. That works while the author is the only player.
Outside testers at soft launch (M5) need a public place to file, so the decision is
revisited then (09). The repo URL is one constant in `app/src/feedback.ts`, so moving
it is a one-line change.

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

The oracle stays the arbiter. A player report never changes a par without passing
through real Neovim.

## Human review

Ingest writes; a human decides what ships. Before committing an ingest run the author:

- reads the diff of `content/idioms_learned.toml`, since one bad generalisation re-pars
  a whole template (`vimtrainer-content review --idioms` lists the entries), and sets
  each new entry's `status` to `ok` or `rejected`;
- works through `wording-queue.md` and fixes the template text, not single exercises;
- reproduces each entry in `emulator-divergences.md` in `app/e2e/editor.mjs`, then
  fixes it in `vimfixes.ts` or records it in `build/supported_commands.md` (from round
  3b the differential fuzzer in 12 finds most of these first);
- runs `make content` and `make content-check`, and closes the GitHub issue with a
  link to the commit.

## Why pars are wrong today, and the structural fix

The par search tries a fixed idiom list per skill plus the template's own variants.
That finds shorter *known* idioms, never unknown ones. Three changes narrow the gap:

1. **Kind by intent, not by skill.** `ex` kind only for drills where normal mode would
   be a repetition drill rather than the skill (`:g`, `:v`, `:normal`, `:s` over many
   lines). Copy, move and duplicate are `edit`. Done 2026-10-13 for copy_line and
   move_line; round 3a audited the remaining ex templates (03).
2. **Cross-skill idiom search.** When searching a par, try every skill's idioms, not
   only the drilled skill's, so a `t.paren` drill learns that `ct)` or `f)` can beat
   `ci(` in a given buffer. Cost is oracle time, which is cheap in batches. Not built.
3. **Player-sourced idioms** via the loop above. Built in round 3a.

## Scope and what it is not

- No leaderboards, no social. The log is yours; sharing is a deliberate act.
- No LLM involvement: reports are verified by Neovim and read by a human.
- Not a bug tracker replacement for the author; GitHub issues are.

## Release gate (see 07)

Pro is not offered until the loop has run for a while and the flag rate is low. The
numbers are in 07-monetization.md under "Stability gate".
