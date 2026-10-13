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

The attempt ends when the pass condition is met, or the user skips or gives up (`Esc Esc` from
normal mode, see Fail and skip), or the user retries (`r` on the result strip,
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
| beat par | < 1.0 | beat par; the result strip says "you beat par: 3 vs 4" |
| at par | = 1.0 | par |
| close | ≤ 1.25 | close |
| pass | ≤ 2.0 | passed, with hint |
| over | > 2.0 | passed, result strip shows par prominently |

A pass at any efficiency updates the model; the efficiency EMA does the discriminating.
There is no "fail for being slow" or "fail for too many keys".

The `beat` band was added in round 3a (2026-10-13). A pass below par means the shipped
par is wrong, so the attempt is recorded with `beatPar: true` and its key sequence, and
`ingest` verifies it in Neovim before any par changes (11, ADR 0009). The model treats
it like any other pass at or under par.

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

## Resolved

From the M1 key-logger spike and the M3 build (2026-10-11).

- **Command-done hook.** `vim-command-done` fires on every insert-mode keystroke and
  when `ci"` enters insert mode, so it only means the input state was reset.
  `vim-keypress` misses insert-mode and command-line keys. `vim-mode-change` fires
  `normal` twice when leaving visual mode. The app does not trust any of them alone.
  It schedules one microtask check from the signals, CM6 updates and command-line blur,
  and emits command-done only when the mode is not insert or replace, no command is
  pending (`vim.inputState`), the command line is closed and the buffer or cursor
  changed. The mode is read from state (`vim.insertMode`, `vim.visualMode` and
  related), not from the event payload. Issue #251 was not read.
- **Key capture.** A capture-phase `keydown` listener on a wrapper around `view.dom`
  runs before CodeMirror, and uses `Vim.vimKeyFromEvent` for angle-bracket notation.
  It also sees keys typed in the `:` and `/` line. IME composition is skipped.
- **`<Esc>` and blur.** In headless Chromium, Firefox and WebKit, `<Esc>` keeps focus
  once a bubble-phase guard calls `preventDefault` on an `<Esc>` Vim left unhandled.
  A real keyboard in real Safari or Firefox is untested. In fullscreen the browser
  takes `<Esc>` and a page cannot stop that.
- **Tab blur.** `Tab` is the real blur risk: without the guard it moves focus out of
  the editor in Chromium and WebKit. The guard stops it, and in insert mode inserts 4
  spaces to match the oracle's `expandtab` and `shiftwidth=4`.
- **Clock.** `performance.now()` minus the time `document.visibilityState` was hidden.
  Tab-switch pauses are excluded.
- **Hint key.** `?` is Vim's backward search, so the mid-exercise hint is `F1`, which
  the recorder consumes and does not pass to Vim. On the result strip `?` shows all
  hints and alternates.
- **Give-up.** Two `<Esc>` (or `<C-[>`, `<C-c>`) presses in normal mode within 800 ms.
  There is no buffer condition, because the diff shown after a give-up needs an edit
  to have happened. The Esc that leaves insert mode does not count.
- **`jk` escape.** Implemented as `Vim.map('jk', '<Esc>', 'insert')`. It counts as one
  key and shows as `jk`.
- **Ex tasks.** Every `ex` task ends with "using an Ex : command". If the buffer
  matches without one, a note says only a `:` command counts, and does not mark the
  attempt as hinted.

## To research

- Give-up by accident: `<Esc>` to cancel a pending `d`, then a second `<Esc>` within
  800 ms, ends the attempt. The recorder could ignore an Esc that cancelled a pending
  command.
- IME and dead keys in normal mode are skipped by the key logger.
- Tab in insert mode always inserts 4 spaces instead of moving to the next shiftwidth
  stop.
- Visiting stats or settings mid-exercise (mouse only) does not pause the clock.
- Long or recursive macro replay (issue #177) is untested. Only a one-key macro was
  tested.
