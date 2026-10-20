# Spike: codemirror-vim key logger

Throwaway. It answers the open questions about key capture for grading.
Keep it until the
real attempt recorder exists, then delete it.

## Run

```
cd app
npm install
PLAYWRIGHT_BROWSERS_PATH=0 npx playwright install chromium   # add firefox webkit for --all
npm run dev                    # open http://localhost:5173/spike-keylogger.html
npm run spike:test             # headless Chromium checks
node src/spike/verify.mjs --all  # Chromium, Firefox, WebKit
```

Files:

- `keylogger.ts` holds the recorder (keys, modes, command-done, clock, browser-key guard).
- `main.ts` sets up the page: the editor setup, the log view, and `window.spike` for Playwright.
- `verify.mjs` runs the Playwright checks. It starts Vite itself.

Pinned versions: `@replit/codemirror-vim` 6.4.0, `@replit/codemirror-vim-core` 0.1.0,
`@codemirror/view` 6.43.14, Vite 8.3.4, TypeScript 7.0.2,
Playwright 1.64.0. The spike bundle is 163 KB gzip, which includes the Python grammar.

## Results

All checks pass in Chromium, Firefox and WebKit (Playwright builds, headless).

| check | result |
|---|---|
| `ci"retrying<Esc>` from column 0 of `logger.warn("timeout, trying again")` | the buffer matches nvim, and the cursor is at 5:32, the same as `nvim --headless --clean` |
| key log for that edit | `c i " r e t r y i n g <Esc>`, 12 tokens |
| command-done events | exactly one, on `<Esc>` (key #11). None after `c`, `ci`, `ci"`, or the typed text |
| `d` then `w`, `3j`, `u`, `.`, `qaxq`, `@a` | none after `d`. Then one each after `dw`, `3j`, `u`, `.`, the `x` inside the recording, and `@a`. A simple macro did not hang (#177) |
| `:s/logger/log/<CR>` | the key log includes the command-line keys, and there is one command-done on `<CR>` |
| modes `v V <C-v> R i a` | normal / visual / visual-line / visual-block / replace / insert, all correct |
| `<Esc><Esc>` in normal mode | 2 keys, no command-done, editor keeps focus, keydown is `defaultPrevented` |
| `<Tab>` in normal and insert mode | editor keeps focus. Insert mode inserts `\t` |
| `<C-[>` | logged as one token `<C-[>`, and Vim treats it as `<Esc>` |
| hidden tab for 400 ms | active clock advances < 1 ms, and two `clock` events are logged |

## Which hooks work

**Works:**

- `Vim.vimKeyFromEvent(e, cm.state.vim)` is the emulator's own normaliser. It returns
  `<Esc>`, `<CR>`, `<BS>`, `<C-v>`, `<C-[>`, `<Space>`, `<Tab>`, `<S-Left>` and so on,
  and returns `undefined` for bare modifiers. Using it guarantees that the log
  says what Vim saw.
- A capture-phase `keydown` listener on a wrapper element around `view.dom`
  runs before CodeMirror and Vim, so their `stopPropagation` cannot hide keys
  from it. It also sees keys typed into the `:` / `/` command line, because
  that `<input>` lives inside `view.dom` (in a CM6 panel).
- Reading the mode from state is exact in every test:
  `vim.insertMode` (+ `cm.state.overwrite` for replace), `vim.visualMode`,
  `vim.visualLine` and `vim.visualBlock`.
- `vim.inputState` (`keyBuffer`, `operator`, `prefixRepeat`, `motionRepeat`)
  says whether a command is still pending.
- The CM6 `EditorView.updateListener` (`docChanged`, `selectionSet`) fires on
  every buffer or cursor change, including ex commands.
- `focusin` / `focusout` of the command-line `<input>` is the reliable way to
  tell that the command line is open.

**Unreliable or unusable on its own:**

- The `vim-command-done` signal is emitted from `clearInputState`. That
  function runs on every insert-mode keystroke: 10 signals for the 12 keys of
  `ci"retrying<Esc>`. It also runs when `ci"` enters insert mode, and on
  unmatched keys. The signal only means "the input state was reset", not
  "a command completed". It is useful as a trigger, never as the event itself.
- The `vim-keypress` signal fires only for keys Vim consumed. It misses every
  insert-mode character (it saw `c i " <Esc>` for the 12-key edit) and every
  command-line key. Do not use it for logging.
- The `vim-mode-change` signal fired for every transition we tried, but it
  fires `normal` twice when leaving visual mode, and it carries `subMode`
  rather than a mode name. Issue #251 reports it as flaky (not re-checked
  here). Use it as a trigger and read the mode from state.
- `cm.state.dialog` does not mean the command line is open. After `:s` it holds
  the "Found N matches" notification for 5 s.
- The `inputEvent` signal (`{type: "handleKey", key}`) duplicates what the
  keydown listener gets, minus the command line. It is not needed.

**Gotchas found along the way (they matter for parity with the nvim oracle):**

- Without `basicSetup` you must add `history()` from `@codemirror/commands`.
  Otherwise `u` is a silent no-op.
- Do not use `basicSetup`. Its `closeBrackets`, autocompletion and indent-on-input
  change what insert mode produces, so the result would diverge from
  `nvim --clean`.
- `Vim.setOption("pcre", false)` makes `:s` and `/` use Vim regex semantics.
  The default is JavaScript regex.
- `ci"` with the cursor before the first quote, at column 0 of the line, jumps
  to the string just as nvim does.

## Recommended key-capture design for the real app

1. **Keys.** Put one capture-phase `keydown` listener on the editor wrapper.
   - Skip `e.isComposing`, `keyCode 229`, `Process` and `Unidentified`.
   - Normalise each remaining key with `Vim.vimKeyFromEvent(e, cm.state.vim)`.
   - Log `{key, t: performance.now(), active, mode, cmdline}`.
   - Each token counts as one keystroke. The display layer can render
     `<Space>` inside insert-mode text as a space. When the user's escape
     preference is set, `<C-[>` (and `jk`) count as `<Esc>`.
   - Do no state reads in this listener. In Chromium and WebKit its microtask
     checkpoint runs *before* Vim handles the key.
2. **Command done.** Several events schedule one microtask check:
   `vim-command-done`, `vim-mode-change`, a CM6 update with `docChanged` or
   `selectionSet`, and the command-line input losing focus. The check emits
   `command-done` only when all of these hold:
   - the mode is not insert or replace;
   - no command is pending in `vim.inputState`;
   - the command-line input does not have focus;
   - the doc (`Text.eq`) or the cursor changed since the last emission.

   Grading checks the pass condition on this event only. That gives exactly
   the grading semantics: `ci"ret` is not a pass, and the `<Esc>` that
   finishes it is.
3. **Mode.** Derive the mode from state inside the same check, and emit a mode
   event only when it changes. Ignore the signal's payload.
4. **Browser keys.** Add a bubble-phase `keydown` listener on the wrapper.
   - Call `preventDefault` on any `Escape` or `Tab` that Vim left unhandled.
   - In insert mode, run `insertTab` for `Tab`.

   CM6 leaves `Tab` to the browser, and the browser moves focus out of the
   editor (Chromium, WebKit). Vim does not consume `<Esc>` in normal mode.
5. **Clock.** Use `performance.now()` minus the time spent with
   `document.visibilityState === "hidden"`. Attempt `ms` uses active time.
6. **Ex rule.** For the `ex` kind, accept a `<CR>` key logged with
   `cmdline: true` after a `:` as a command-line execution.
7. **Undo count.** Count `u` and `<C-r>` tokens in normal mode from the key log,
   plus `:undo`/`:u` command lines. No hook is needed.

## Not verified here

- Real Safari and Firefox on macOS with a physical keyboard. Playwright's
  WebKit and Firefox builds are close, but they are not the shipping browsers.
  Two things the tests cannot cover:
  - The browser takes `Esc` in fullscreen to exit fullscreen, and a page
    cannot stop that.
  - Safari has its own handling of `Cmd`-chords.
- IME and dead-key input in normal mode. The emulator reads these from the
  text input path, and this spike skips logging them (`TODO` in
  `keylogger.ts`).
- Long or recursive macros, which are the subject of the #177 hang. Only a
  one-key macro was tested.
