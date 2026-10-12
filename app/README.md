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
On the result strip: `space` next, `r` retry, `?` hints, `p` replay (pro, disabled), `q` end session,
`s` stats, `,` settings. Stats (`src/stats/`): `tab` / `1` `2` `3` skills grid / progress / sessions,
`h` `j` `k` `l` move, `enter` history chart, `f` drill this next, `Esc` back. Straight after placement
`enter` starts the session. `stats-demo.html` renders the view on a simulated learner (`npm run e2e:stats`).

State lives in `localStorage["vim-trainer.v1"]`; export/import JSON in settings.
