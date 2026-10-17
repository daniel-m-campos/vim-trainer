# 0010: Generated exercise data is not committed

Date: 2026-10-14. Status: accepted. Supersedes the "`build/` is committed" bullet of 0004
and the CI rule in 0005.

## Context

`build/` holds everything `make content` produces: 1,644 exercise JSON files, `index.json`,
stats and attribution. It was committed (0004) so that a fresh clone ran the app without
Neovim and so that CI could prove the pipeline reproducible by diffing a rebuild against
the committed copy (0005). Round 3 made the cost visible: a content change arrives as a
10,000-line generated diff next to a few hundred lines of code, and every rebuild touches
all 1,644 files when the build date moves.

Deploying the site never needed the committed copy: Vite copies `build/` into `app/dist/`
at build time, and a deploy pipeline can run `make content` first.

## Decision

- `build/` is gitignored. `make content` generates it; `make test`, `make e2e`,
  `make difftest` and `make build` depend on a `need-content` guard that says so when it
  is missing.
- CI runs `make content` before the tests, then `make content-check`, which rebuilds into
  a scratch directory with `SOURCE_DATE_EPOCH` pinned to the first build's date and
  requires a byte-identical tree. Reproducibility is still checked on every run, only now
  between two builds on the same runner instead of against a committed copy.
- The nightly `difftest` workflow does the same before fuzzing (it samples buffers from
  `build/`).
- The deploy pipeline (M5) runs `make content && make build` and publishes `app/dist/`.
  Until then the author publishes `app/dist/` by hand, as before.

## Consequences

- A fresh clone needs Neovim 0.12.5 and about five minutes of `make content` before the
  app has content. `make setup` says so.
- CI runs take about five minutes longer.
- Content changes are no longer visible as a diff in review. The per-skill counts and par
  medians are in `build/index.json` and `build/stats/`; if that visibility is missed, a
  small committed summary written by `make content` is the fix, not committing `build/`
  again.
- The directory keeps its name: an ignored output directory called `build/` is the
  convention, in C++ and in web projects alike.

## CI shape (round 5)

ci.yml runs the two lines of `make content` as two steps. Stage (a) is the Python build:
it verifies every par in Neovim and writes `build/`. Stage (b) is the browser replay
(`node e2e/emulator.mjs --write`): it rewrites `index.json`, `stats/` and `emulator.web`.
Stage (a) reads only `content/` and the pinned Neovim, so its output is cached with
`actions/cache/restore` and `actions/cache/save`. The key is the runner OS, the output of
`nvim --version`, and a hash of `content/**` (without `.cache/`, `.venv/` and
`__pycache__/`) plus the setup action. The save step runs right after stage (a), so the
cache holds the tree before the replay. Stage (b) runs on every build because it depends on
`app/src/vimfixes*.ts`. `make content-check`, a second full build of both stages, runs on
pushes to main, on manual runs, and on pull requests whose `git diff` against the target
branch touches `content/`, `.github/` or the `Makefile`; the "every run" in the Decision
above now means those runs. difftest.yml shares the cache. Estimates, not measurements: an
app-only PR with a warm cache drops from 728 s to about 330 s (setup 50, restore 5, replay
about 155, unit 47, e2e 68), about 460 s with a cold cache; a content PR stays near
today's 740 s.
