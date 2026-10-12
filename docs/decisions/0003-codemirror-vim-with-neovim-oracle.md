# 0003: codemirror-vim in the browser, headless Neovim as the par oracle

Date: 2026-10-11. Status: accepted.

The user types into CodeMirror 6 with `@replit/codemirror-vim`. Every par is verified
by replaying the key string in `nvim --headless --clean` at build time. The build then
replays every par and alternate in the app's own editor (`app/e2e/emulator.mjs`, run by
`make content`). An exercise whose par fails in the browser is recorded in `webFail`
in `index.json` and is never served. Passing exercises carry `emulator.web = "pass"`.

Why: real Neovim in the browser is not available (vim.wasm is frozen, Neovim WASM is
blocked), and an emulator that disagrees with Vim would teach wrong keys. The oracle
proves the par; the browser replay proves the user can reproduce it where they practise.

First replay result: 58 of 587 pars failed in the browser. `app/src/vimfixes.ts` fixes
them through the public Vim API, without patching `node_modules`. After the fixes all
587 pass in Chromium, Firefox and WebKit.

The vimfixes list:
- `:move` and `:copy` (`:m`, `:t`) do not exist in codemirror-vim. They are registered
  as `movelines` and `copylines`, so the bare `:15` line jump keeps working. On Enter,
  `:m8` is rewritten to `:m 8`, because the emulator reads `\w+` as the command name.
  This fixed all 40 x.copymove exercises.
- `d}` does not apply Vim's exclusive-linewise rule, and `dG` leaves an empty last
  line. The rule is applied only for `d` with `}` or `)`, so `dw` keeps its special case.
  This fixed 16 o.delete exercises.
- `:s` and `/` are case-insensitive in the emulator, which forces ignorecase and
  smartcase, while `nvim --clean` is case-sensitive. The `i` flag is stripped from the
  search query after every reset of Vim's global state. This fixed 2 x.subst exercises.
- `Vim.setOption('pcre', false)` is set so `:s` and `/` use Vim regex, not JavaScript.

Known gap: the exclusive-linewise rule is not patched for `c}`, `y}`, `gU}` or searches
used as motions. No shipped par depends on them. A user's own alternative might.

Related findings from the key-logger spike: there is no `basicSetup` (its auto-closing
brackets and indent-on-input would diverge from the oracle), `history()` is required or
`u` does nothing, and the editor's option set follows the oracle's.
