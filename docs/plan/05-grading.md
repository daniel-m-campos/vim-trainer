# Grading

How a single attempt becomes the record the adaptive model consumes. All grading is
client-side and instant; the result strip must never wait on a network call.

## Capturing the attempt

The editor wrapper records, from the moment the exercise renders:
- every key event delivered to the Vim emulator, normalised (below), with timestamps;
- every mode change;
- the buffer and cursor after each command completes (codemirror-vim exposes a
  command-done hook; see 06 and the To research note);
- undo count (`u` presses and `:undo`).

The attempt ends when the pass condition is met, or the user skips (`Esc Esc` from
normal mode with an unchanged buffer), or the user retries (`r` on the result strip,
which only exists after a pass or an explicit give-up).

There is no timeout. A quiet tool doesn't fail you for thinking.

## Pass conditions by exercise kind

| kind | passes when | notes |
|---|---|---|
| edit | buffer lines == `expect.lines` | trailing whitespace stripped per line; cursor ignored |
| cursor | cursor == `expect.cursor` and buffer unchanged | checked after each command, so overshoot-then-correct passes but costs keys |
| ex | buffer matches and the key log contains at least one `:`-command execution | prevents solving `:g` drills with repeated `dd` |

Checking after every command (not every keystroke) means a user who types `ci"ret` has
not passed yet, and pressing `<Esc>` with the right text completes the edit. The final
`<Esc>` is counted in the par for consistency (vimhjkl convention).

## Keystroke normalisation

Keys are logged in Vim's angle-bracket notation so they display and count the same
everywhere: `<Esc>`, `<CR>`, `<BS>`, `<C-v>`, `<C-r>`, `<Space>` inside command lines.
Each notation token counts as **one** keystroke. Shift is not counted separately: `A`
is one key. Modifier chords count as one (`<C-v>` = 1).

Escape alternatives: a user who has configured `jk` or `<C-[>` to escape still gets one
keystroke counted for the escape (setting in 10-ux). Otherwise par would penalise the
most common Vim customisation.

## Efficiency

`eff = keys / par`, where `par` is the verified best count from the content pipeline
(03). Bands used in the UI and the model:

| band | eff | shown as |
|---|---|---|
| at par | ≤ 1.0 | par |
| close | ≤ 1.25 | close |
| pass | ≤ 2.0 | passed, with hint |
| over | > 2.0 | passed, result strip shows par prominently |

A pass at any efficiency updates the model; the efficiency EMA does the discriminating.
There is no "fail for being slow" or "fail for too many keys".

## Time

`ms` = from the exercise render (task and code visible) to the passing command. It
includes reading time by design; the model's `base` constant accounts for it. Time is
not shown during the attempt (10-ux).

## Hint selection on the result strip

The strip shows one hint, chosen by matching the key log against detectors, in order:

1. Exercise-specific hint whose trigger pattern matches (from `hints` in the exercise;
   e.g. trigger `^f"` → "ci\" works from anywhere inside the quotes").
2. Generic detectors: `j{4,}` or `k{4,}` → relative jump; `l{5,}` or `h{5,}` → `f`/`t`
   or `w`; `x{3,}` → `d{motion}`; insert-mode arrow keys → leave insert; `dd` repeated
   on matching lines → `:g`; repeated identical edit sequence → `.` or a macro;
   `0` then motion when `^` fits → `^`.
3. Fallback: show the par and nothing else.

Hints are one sentence, name the better command, and never scold.

## Undo

Undo is allowed and counted as keystrokes. An attempt with `undo > 0` still passes;
accuracy in the model only counts outright fails and skips. (An attempt that reaches
the expected buffer by undoing a mistake is still a correct edit.)

## Fail and skip

- **Give up**: `Esc Esc` in normal mode. Logged `ok: false`, result strip shows the
  expected buffer as a diff and the par.
- **Wrong edit, then stuck**: there is no detection of "wrong"; the user sees the buffer
  diverging and either fixes it (undo counts) or gives up.
- **Skip** is the same as give-up from the model's view.

## Anti-cheat

None beyond the `ex` kind rule. There are no leaderboards, so there is nothing to cheat
for. A user who games their own chart is only lying to themselves, and the quiet-tool
stance is to let them.

## Edge cases to decide

- Exercises whose expected buffer can be reached with the cursor on a different line in
  insert mode vs normal mode (we ignore cursor for `edit`, so fine).
- Auto-indent and `'expandtab'` differences between the emulator and the oracle: the
  oracle runs `--clean` with a documented option set; the emulator must use the same
  (`shiftwidth`, `expandtab`, `autoindent`), and the content pipeline avoids exercises
  where auto-indent affects the result.
- Clipboard: `"+` and `"*` in the browser map to the emulator's internal register;
  system clipboard is out of scope.

## To research

- The exact codemirror-vim hooks: a reliable "command completed" event, access to the
  key buffer, mode-change event robustness (issue #251).
- Whether `<Esc>` in the browser can be captured without blurring the editor on every
  platform (Firefox/Safari differences).
- Timing precision: `performance.now()` is fine; check that tab-switching pauses are
  excluded (pause the clock on `visibilitychange`).
