# Feedback loop

Added 2026-10-13 after the author's first practice sessions. Two observations drove it:
some drills rejected correct solutions (copy_line was ex-kind, so `yyjp` failed), and
the author found pars that could be shorter. Neither can be caught by the oracle alone,
because the oracle only verifies the solutions we already thought of. Players are the
search engine we are missing.

## What we record

Every attempt already logs `keys` (a count). It will also log the sequence:

```json
{ "t": ..., "ex": "py/x.copymove/03ed26c61c", "ok": true, "ms": 2100, "keys": 4, "par": 4,
  "keySeq": "yyjp", "beatPar": false, "flag": null }
```

- `keySeq`: the normalised keystrokes (angle-bracket notation, as the result strip shows
  them). Optional field; both model mirrors ignore it, so no vector changes.
- `beatPar`: true when `ok && keys < par`. The result strip says so plainly ("you beat
  par: 3 keys vs 4") and the attempt is kept in a local `candidates` list.
- `flag`: set by the player on the result strip with `!` and one of: `wrong-par`
  (a shorter or rejected solution), `wording` (the task text was unclear or wrong),
  `emulator` (Vim behaved differently from real Vim), `other`. An optional one-line note.

Nothing is sent anywhere automatically. The log stays in localStorage and in the
export file.

## How it gets back to us (no backend in v1)

1. **Prefilled GitHub issue.** On the result strip, `!` then `enter` opens a new tab on
   the repo's new-issue page with the body prefilled: exercise id, language, kind, the
   player's `keySeq`, the par, the flag reason, and the app version. The player can edit
   and submit, or close the tab. Works with no server, and the issue tracker is the
   review queue. A `feedback` label is applied via the URL.
2. **Export file.** Settings -> export already produces the full state. A
   "share my log" explainer says what is in it and offers the same GitHub route or
   email. This is for people who prefer a bulk hand-off.
3. **Later, with accounts (pro):** an opt-in "send attempts" toggle posts
   `{keySeq, ex, ok, keys, par, flag}` batches to a small Worker endpoint. No code,
   no buffers, no timing beyond ms. Off by default. Not before M7.

## What the pipeline does with it

`uv run vimtrainer-content ingest <issue-or-export.json>`:

- For every `beatPar` or `wrong-par` report, replay `keySeq` in the oracle against the
  exercise. If it passes and is shorter than par, it becomes the new canonical and the
  old one an alternate; the template's idiom library gains the pattern (generalised,
  e.g. `yy{k}jp`) so every sibling exercise gets re-par'd on the next build. If it
  passes at equal length, it is added as an alternate. If it fails in the oracle, it is
  logged as an emulator divergence to investigate (the browser accepted something real
  Vim does not, or vice versa).
- `wording` reports are grouped by template and shown in the review CLI as a batch.
- `emulator` reports are reproduced in `app/e2e/editor.mjs` and either fixed in
  vimfixes.ts or recorded in `build/supported_commands.md`.
- Every ingest run appends to `content/review/ingest-log.md`: date, source, outcome.

The oracle stays the arbiter. A player report never changes a par without passing
through real Neovim.

## Why pars are wrong today, and the structural fix

The par search tries a fixed idiom list per skill plus the template's own variants.
That finds shorter *known* idioms, never unknown ones. Three changes narrow the gap:

1. **Kind by intent, not by skill.** `ex` kind only for drills where retyping defeats
   the point (`:g`, `:v`, `:normal`, `:s` over many lines). Copy, move and duplicate
   are `edit`. Done 2026-10-13 for copy_line and move_line.
2. **Cross-skill idiom search.** When searching a par, try every skill's idioms, not
   only the drilled skill's, so a `t.paren` drill learns that `ct)` or `f)` can beat
   `ci(` in a given buffer. Cost is oracle time, which is cheap in batches.
3. **Player-sourced idioms** via the loop above.

## Scope and what it is not

- No leaderboards, no social. The log is yours; sharing is a deliberate act.
- No LLM involvement: reports are verified by Neovim and read by a human.
- Not a bug tracker replacement for the author; GitHub issues are.

## Release gate (see 07)

Pro is not offered until the loop has run for a while and the flag rate is low. The
numbers are in 07-monetization.md under "Stability gate".
