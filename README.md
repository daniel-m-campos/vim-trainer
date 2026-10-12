# vim-trainer (codename)

An adaptive Vim-motions trainer in the browser, modelled on keybr.com: it measures
speed and accuracy per skill, drills the weakest one, and charts progress over time.
Practice content is generated from real code, per programming language.

Status: **MVP (M3 practice loop)**. Python only: 587 exercises across 15 skills, every par
verified in Neovim and replayed in the browser editor. The first user is the author, who is
learning Vim. See `docs/plan/08-roadmap.md` for what comes next.

## Run it

On macOS, from a fresh clone:

```sh
brew install uv node neovim     # node >= 23 (tested on 26); neovim is only needed for `make content`
git clone <this repo> vim-trainer && cd vim-trainer
make setup                      # uv sync for content/ and model/, npm ci and Playwright Chromium for app/
make dev                        # open http://localhost:5173/
```

The first visit asks three questions (language, editor, relative numbers) and then runs a
placement test of 12 exercises. After that, every visit starts a practice session.
Keys inside the editor go to Vim, except `F1` (hint). `Esc Esc` in normal mode skips an exercise.
On the result strip, `space` goes to the next exercise, `r` retries, `?` shows hints, `q` ends
the session, `s` opens stats and `,` opens settings. Progress is stored in this browser's
localStorage. Settings has export, import and reset.

Other targets:

```sh
make test       # unit tests: content (pytest), model (pytest), app grading + TS model mirror (node --test), typecheck
make e2e        # Playwright in Chromium: the bundled-sample flow, then placement + a 15-exercise session on build/
make e2e-all    # the same in Chromium, Firefox and WebKit (first: make setup BROWSERS="chromium firefox webkit")
make content    # rebuild build/ from scratch (needs nvim; fetches the pinned exercism/python), then replay every par in the browser
make emulator   # report-only: replay every par and alternate in the browser
make build      # static site in app/dist/
```

`build/` is committed, so `make dev` works without Neovim. CI (`.github/workflows/ci.yml`)
rebuilds it and fails if the result differs from the committed copy. After changing the
pipeline, run `make content` and commit `build/`.

## Layout

- `content/` — the content pipeline (Python, uv): snippets from real code, templates, Neovim par oracle. Writes `build/`.
- `build/` — generated exercises, `index.json`, `ATTRIBUTION.md` (committed).
- `model/` — the adaptive model (Python, uv), scenario vectors, the skill graph generator and learner simulations.
- `app/` — the browser app (TypeScript, Vite, CodeMirror 6 + codemirror-vim). `app/src/model/` is the TS mirror of the model.
- `docs/plan/` — the product plan, one file per topic. Start with `00-overview.md`.
- `docs/decisions/` — short decision records (ADRs). One file per decision.
- `docs/research/` — the two research reports this plan is based on, plus their raw notes.

## Principles (from the research)

1. Differentiate on measurement, not on lessons. Nobody charts per-skill speed/accuracy.
2. Free core, no ads in the practice loop. A one-time lifetime "pro" later, never a subscription.
3. Real Vim is the oracle: every exercise's par is verified with `nvim --headless`.
4. Content from real code, per language, under permissive licences with attribution.
5. Tooling in Python (the author's language); only the browser app is TypeScript.
