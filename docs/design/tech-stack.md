# Tech stack

Chosen for a solo developer who writes Python and C++, with the browser app as the one
unavoidable TypeScript surface. The stack prefers boring, well-maintained pieces: the
interesting parts are the model and the content, not the framework.

## Decisions

| layer | choice | why |
|---|---|---|
| Vim in the browser | CodeMirror 6 + `@replit/codemirror-vim` (MIT) | best fidelity for the effort; actively maintained; exposes `Vim.handleKey`, mode events and custom operators. vim.wasm is frozen and Neovim in WASM is not usable in a browser page (ADR 0003) |
| Front-end | TypeScript, Vite, no framework | the practice screen is three regions and a key handler, and the stats screen is hand-rolled SVG; a framework adds more than it saves |
| Charts | hand-rolled SVG (`app/src/stats/charts.ts`) | three chart shapes; no library needed |
| Storage | `localStorage` with JSON export and import; IndexedDB if the log ever exceeds ~2 MB | no accounts and no server (ADR 0012) |
| Content build | Python 3.12, `py-tree-sitter` + grammar wheels, batch `subprocess` to `nvim --headless --clean` | see content-pipeline.md and ADR 0002 |
| Emulator oracle | Playwright (JavaScript, `app/e2e/emulator.mjs`) driving a headless Chromium page that loads the app's own editor | shares the editor setup with the app; run by `make content` (ADR 0005) |
| Model | pure TypeScript module in the app, mirrored by a pure Python module for simulation and tests; shared JSON test vectors keep them identical | the model must be testable offline (adaptive-model.md) |
| Hosting | static files on GitHub Pages; no server | the site costs nothing to run at any traffic (ADR 0008, ADR 0012) |
| Analytics | none; the player can export the log or flag an attempt as a GitHub issue | the log is the only data the trainer needs, and sharing it is a deliberate act (feedback-loop.md) |
| CI | GitHub Actions: content build + oracle, TS and Python tests, determinism check, nightly difftest, deploy on main | pars are verified in CI, never by hand |

## Repository layout

```
app/          TypeScript: practice screen, stats, settings, model (ts)
content/      Python: sources allowlist, lang mappings, templates, oracle, review CLI, difftest
model/        Python mirror of the model + simulators + generated test vectors
build/        generated exercises, stats, ATTRIBUTION.md (gitignored; `make content` writes it, CI regenerates and checks determinism; ADR 0010)
docs/         design documents and decision records
```

## Constraints and known gaps

- codemirror-vim gaps that affect exercises: no Select mode, some `%` matching
  failures, no `U`, no `g@`, macro-replay hang (#177, guarded in
  `vimfixes-macros-indent.ts`). The emulator oracle marks affected exercises unsupported
  in the browser; the supported-command list is generated, not hand-written. The full,
  measured list of divergences comes from differential testing
  (differential-testing.md).
- `<Esc>` handling and key capture differ across browsers; `make e2e-all` runs the
  end-to-end tests in Chromium, Firefox and WebKit.
- Bundle size target: < 300 KB gzip for the practice screen including codemirror-vim
  (~40 KB) and fonts.
- Offline after first load needs a service worker, which is not built.

## Design notes

- **Hook names and reliability.** See the Design notes in grading.md. A one-day spike
  settled them, and its findings are in the app's key recorder.
- **Playwright or jsdom.** Playwright, in JavaScript under `app/e2e/`, run by
  `make content` and `make emulator` (ADR 0005). jsdom was not tried.
- **Commit `build/` or generate on deploy.** Generated, not committed (ADR 0010, which
  supersedes the committed-copy rule of ADR 0004). CI and the deploy workflow run
  `make content`.
- **Pinned versions.** `@replit/codemirror-vim` 6.4.0, `@replit/codemirror-vim-core`
  0.1.0, `@codemirror/view` 6.43.14, vite 8.3.4, typescript 7.0.2, playwright 1.64.0.
  The bundle is about 192 KB gzip against the 300 KB target.
- **Fonts.** JetBrains Mono and IBM Plex Sans from Google Fonts with system fallbacks,
  not bundled.
- **Test runner.** `node --test` with Node's built-in type stripping, so there is no
  test dependency. Node 23 or later is required.
- **Static hosting.** Vite `base` is `./`. The build copies `build/` and the skill
  graph into `dist/`, and writes `build/all.json` for hosts that cap file counts.
- **Hosting.** The site is served from GitHub Pages at
  https://daniel-m-campos.github.io/vim-trainer/. `.github/workflows/deploy.yml` builds
  the content in two stages (Neovim, then the browser replay) with the same cache as CI,
  runs `make build`, and publishes `app/dist` with `actions/upload-pages-artifact` and
  `actions/deploy-pages`. Every fetch (`build/index.json`, `build/all.json`,
  `build/ATTRIBUTION.md`) is relative to the page, so the site works under the
  `/vim-trainer/` subpath. Routing uses the URL hash, so no `404.html` fallback is
  needed, and Pages deployed from Actions does not run Jekyll, so no `.nojekyll` is needed.

## Open questions

- A service worker for offline use.
