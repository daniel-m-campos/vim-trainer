# vim-trainer app

Vite + TypeScript, no framework. CodeMirror 6 + `@replit/codemirror-vim`.
The repo-level `Makefile` wraps all of this (`make setup`, `make dev`, `make test`, `make e2e`).

```
cd app
npm ci
PLAYWRIGHT_BROWSERS_PATH=0 npx playwright install chromium   # once; add firefox webkit for --all
npm run dev            # http://localhost:5173/
npm test               # node --test: grading, the build/ contract, the TS model mirror
                       #   (needs ../build from `make content` and ../model/.cache/vectors from `make vectors`;
                       #    `make test-app` from the repo root runs both first)
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
vectors that `make vectors` generates into `model/.cache/vectors/`), imported through `src/modelApi.ts`. The skill graph `src/model/skill-graph.json`
is bundled; `src/graph.ts` applies the editor profile and disables skills that have no exercises
in the current language, so the model only rotates through drillable skills (a TODO in `graph.ts`).

Emulator: `src/vimfixes.ts` patches the places where codemirror-vim differs from `nvim --clean`
(numbered fixes in its header: exclusive and linewise ranges, a failing motion aborting its
operator, `>`/`<` on empty lines, cursor placement after `y`/`g~`/`p`, `J`, counts, `:m` / `:t` /
`:copy`, case-sensitive search, block objects). It reaches codemirror-vim's private motion,
operator and action tables through `grabTable()` and wraps entries. `src/vimfixes-macros-indent.ts`
(installed by `installVimFixes()`) handles macros and `:normal` (a failing command aborts them,
with a recursion guard), Python/C++ auto-indent, Insert-mode `<C-w>`, `:j` and ex errors. Pure
helpers are unit-tested in `src/vimfixes.test.ts`. `e2e/editor.mjs` types the key sequences in
`e2e/cases/*.json` and compares the result with Neovim's. The cases are inputs only: a buffer, a
start cursor and keys. Before the browser starts, the harness runs `uv run vimtrainer-content
expect` in `content/` once (about 3 s), which replays every case in headless Neovim. So
`npm run e2e:editor` needs `nvim` and `uv` on PATH, as `make content` does. A case may carry
`oracle: "typed"` (replay as typed keys, so a failing motion aborts a macro), `skip: ["cursor"]`
with a `why` (an open divergence), or `xfailIn: ["firefox"]` (an engine-specific failure that
is reported but not counted).
`e2e/emulator.mjs` + `emulator-check.html` replay every par in the browser;
`make content` runs it with `--write`, which sets `emulator.web` and drops browser mismatches from the index.

Keys: in the editor every key goes to Vim, except `F1` (hint). `Esc Esc` in normal mode gives up.
On the result strip: `space` next, `r` retry, `?` hints, `!` flag, `q` end session,
`s` stats, `,` settings. Stats (`src/stats/`): `tab` / `1` `2` `3` skills grid / progress / sessions,
`h` `j` `k` `l` move, `enter` history chart, `f` drill this next, `Esc` back. Straight after placement
`enter` starts the session. Browser Back and Forward move between the same views (see Reading note: routing). `stats-demo.html` renders the view on a simulated learner (`npm run e2e:stats`).

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
  `Esc` then goes through `goBack()` to `#practice`, whose guard opens the placement intro.
  A placement still running is finished first by `closePlacement()` with the samples it
  has, so the new language starts its own intro and counter.
- `persist()` copies the running `placement` into `saved.placement`, so a reload resumes
  at the same exercise with the records kept. `finish()` sets a placement record's `ok`
  with `placementPass(ok, keys, par)` from `src/grading.ts`: a correct answer over
  `max(2 * par, par + 6)` keys is logged as not passed.

## Reading note: routing

`location.hash` decides the view: `#practice` (the default), `#stats`, `#settings`,
`#placement` and `#placement-intro`. Three functions in `src/main.ts` change it:

- `navigate(route)` is for a key or link the player used (`s`, `,`, the header links). It
  pushes a history entry, so browser Back returns to the previous view.
- `redirect(route)` is for internal hops (end of placement, a guard). It replaces the
  current entry, so Back never lands on it.
- `render()` draws the view for the current hash. It runs after both, and on `hashchange`
  (Back, Forward, an edited URL). Its guards make every hash safe to load directly:
  `#practice` while a placement runs goes to `#placement`, `#placement-intro` for a placed
  language goes to `#practice`, and on a first visit everything except `#settings` shows
  the setup questions.

`Esc` on stats or settings calls `goBack()`: `history.back()` when the app pushed the
current entry (so `Esc` and Back agree), otherwise `redirect("practice")`.

## Reading note: errors and version

There is no telemetry. `window` `error` and `unhandledrejection` handlers in `src/main.ts`
call `recordError()`, which keeps the last 20 as `saved.errors` (`pushError` in
`src/storage.ts`): time, version, route, message and the first 5 stack lines. Export
writes them, the "!" issue body lists the newest three while they fit under the URL cap,
and the footer says "something broke" once. `VERSION` in `src/feedback.ts` is
`__APP_VERSION__`, which `vite.config.ts` defines as `package.json` "version" plus the
short commit sha; settings shows it at the bottom.

What each file is for:

- `src/main.ts`: screens, the practice loop, the result strip and the key handler. `finish()`
  builds the attempt record, including `seq` (the keys typed, from `replayKeys`) and `beatPar`.
- `src/feedback.ts`: the issue URL. `REPO` is the one place that names the GitHub repo.
- `src/grading.ts`: pure functions. Key tokens, pass checks and the efficiency `band()`
  (`"beat"` when keys < par). `placementPass()` is the placement key cap (a pass needs keys <= max(2 × par, par + 6));
  `unrecoverable()` gives the reason for the "not quite — u to undo" nudge, or null. `displayKeys` is what the strip shows; `replayKeys` is the
  same string with a `jk` escape written as `<Esc>`, so Neovim can replay the logged `seq`.
- `src/storage.ts`: localStorage load/save and JSON export/import.
- `src/model/model.ts`: the adaptive model (TypeScript mirror of the Python model). It
  ignores `seq`, `beatPar` and `flag`.
- `src/dom.ts`: `$` (querySelector) and HTML-escaping helpers.
