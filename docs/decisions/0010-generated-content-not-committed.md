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
