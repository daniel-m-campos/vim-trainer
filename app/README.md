# vim-trainer app (M3 practice loop MVP)

Vite + TypeScript, no framework. CodeMirror 6 + `@replit/codemirror-vim`.
The repo-level `Makefile` wraps all of this (`make setup`, `make dev`, `make test`, `make e2e`).

```
cd app
npm ci
PLAYWRIGHT_BROWSERS_PATH=0 npx playwright install chromium   # once; add firefox webkit for --all
npm run dev            # http://localhost:5173/
npm test               # node --test: grading, the build/ contract, the TS model mirror
npm run typecheck
npm run e2e            # Playwright on the bundled sample (forces /build/ to 404); `-- --all` for Firefox + WebKit
npm run e2e:session    # Playwright on the real ../build: placement + a 15-exercise session, export/import
npm run e2e:editor     # Playwright: editor key sequences checked against nvim (`.` repeats, block insert, <Tab>)
npm run emulator       # replay every par in the browser; `-- --alternates`, `-- --write`
npm run build          # typecheck + dist/ (copies ../build in)
```

Content: the app fetches `build/index.json` and `build/exercises/<lang>/<skill>/<id-leaf>.json`
from the repo's `build/` (served at `/build/` by `vite.config.ts`). If it is missing it falls back
to `public/build-sample/` (3 hand-written Python exercises) and logs a console warning.

Model: `src/model/model.ts` (TypeScript mirror of `model/vimtrainer_model`, tested against the shared
`model/vectors/`), imported through `src/modelApi.ts`. The skill graph `src/model/skill-graph.json`
is bundled; `src/graph.ts` applies the editor profile and disables skills that have no exercises
in the current language, so the model only rotates through drillable skills (TODO(mvp)).

Emulator: `src/vimfixes.ts` patches the places where codemirror-vim differs from `nvim --clean` on
shipped pars (`d}` exclusive-linewise, `dG` at the end of the buffer, `:m` / `:t` / `:copy`,
case-sensitive search, Vim's linewise `i{` / `i[` / `i(` on multi-line blocks after an operator). `e2e/emulator.mjs` + `emulator-check.html` replay every par in the browser;
`make content` runs it with `--write`, which sets `emulator.web` and drops browser mismatches from the index.

Keys: in the editor every key goes to Vim, except `F1` (hint). `Esc Esc` in normal mode gives up.
On the result strip: `space` next, `r` retry, `?` hints, `p` replay (pro, disabled), `!` flag, `q` end session,
`s` stats, `,` settings. Stats (`src/stats/`): `tab` / `1` `2` `3` skills grid / progress / sessions,
`h` `j` `k` `l` move, `enter` history chart, `f` drill this next, `Esc` back. Straight after placement
`enter` starts the session. `stats-demo.html` renders the view on a simulated learner (`npm run e2e:stats`).

State lives in `localStorage["vim-trainer.v1"]`; export/import JSON in settings.

## Reading guide: the flag code path

A walk through one feature, top to bottom, for reading the TypeScript. Pressing `!` on the
result strip flags the attempt and opens a prefilled GitHub issue. The functions run in this order:

1. `onKey(e)` in `src/main.ts`. The single `keydown` listener for the whole page. In the
   `"practice"` view with `cur.phase === "result"`, the key `!` calls `openFlagPicker()`. While
   the picker is open, the same branch sends `1`-`4` to `pickFlagReason`, `Enter` to
   `confirmFlag` and `Esc` to `closeFlagPicker`, and swallows every other key.
2. `openFlagPicker()` sets `cur.flagging = true` and calls `renderResult()`. `renderResult`
   puts `flagPickerHtml()` where the key legend was, then `wireFlagPicker()` adds the click
   handlers and the note field's `Enter` handler. `onKey` ignores keys aimed at an `<input>`,
   so the note field needs its own handler.
3. `pickFlagReason(reason)` stores the reason in `cur.flagReason`, marks it in the DOM and
   moves focus to the note field.
4. `confirmFlag()` builds `{reason, note}` and finds the logged copy of the attempt by
   exercise id and time `t`. A practice attempt is in `saved.model.log`. A first placement
   attempt waits in `placement.records` until placement ends. Warm-ups and placement
   retries are not logged, so for them only the issue form opens. It sets `flag` on the
   logged copy and calls `persist()`.
5. `persist()` in `src/main.ts` calls `save()` in `src/storage.ts`, which writes `saved` to
   localStorage as JSON. The flag is a field on the attempt record (`AttemptRecord.flag` in
   `src/model/model.ts`), so export carries it with no schema change.
6. `issueUrl(report)` in `src/feedback.ts` returns the new-issue URL. The title and body
   are URL-encoded and the encoded body is capped at 6000 characters. `confirmFlag` passes
   it to `window.open`, then `closeFlagPicker()` redraws the strip as flagged, with a link
   to the form (and "popup blocked" when `window.open` returned null).

## Reading note: placement per language

`saved.placementDone` is a map such as `{python: true, cpp: true}`, one entry per
language whose placement ran or was skipped. `load()` and `parseImport()` in
`src/storage.ts` call `normalize()`, which turns an old save's `true` into
`{<saved language>: true}`.

- `placed(lang = S().lang)` in `src/main.ts` answers "has this language been placed?".
  `lang = S().lang` is a default parameter, as in Python: `placed()` asks about the
  current language. `boot()`, `goBack()`, the header and the stats page call it.
- `placementQueue()` picks up to 12 `{skill, id}` pairs. `masteredElsewhere(lang)` lists
  the skills that are mastered or due for review in another language, and the queue
  skips them. On a first visit that set is empty and the queue is one skill per tier 1–9,
  then three more from tiers 3–4. For a second language it keeps one per tier and fills
  the rest by the new language's `langWeights`, highest first.
- `startPlacement()` stores the language in `placement.lang`; `finishPlacement()` sets
  `saved.placementDone[placement.lang]`, or the current language when `x` skipped it.
- `onLangChange()` puts a message in settings for a language with no placement yet;
  `Esc` then goes through `goBack()`, which opens the placement intro.

What each file is for:

- `src/main.ts`: screens, the practice loop, the result strip and the key handler. `finish()`
  builds the attempt record, including `seq` (the keys typed, from `replayKeys`) and `beatPar`.
- `src/feedback.ts`: the issue URL. `REPO` is the one place that names the GitHub repo.
- `src/grading.ts`: pure functions. Key tokens, pass checks and the efficiency `band()`
  (`"beat"` when keys < par). `displayKeys` is what the strip shows; `replayKeys` is the
  same string with a `jk` escape written as `<Esc>`, so Neovim can replay the logged `seq`.
- `src/storage.ts`: localStorage load/save and JSON export/import.
- `src/model/model.ts`: the adaptive model (TypeScript mirror of the Python model). It
  ignores `seq`, `beatPar` and `flag`.
- `src/dom.ts`: `$` (querySelector) and HTML-escaping helpers.
