# vim-trainer

An adaptive Vim-motions trainer in the browser. It measures your speed and keystroke
efficiency per skill (`ci"`, `f,`, `dap`, `:g`, macros, ...), drills the weakest one, and
charts your progress over time, in the spirit of keybr.com. The drills are cut from real
code, and every par (the shortest known keystroke solution) is verified in Neovim.

**Try it:** https://daniel-m-campos.github.io/vim-trainer/

It runs entirely in your browser. There is no account and no server; your progress stays
in the browser's localStorage, with export and import in settings. Content today: Python,
C++, JavaScript and TypeScript, about 2,960 exercises.

## How it works

**Content pipeline** (`content/`, Python). Snippets are cut from pinned, MIT-licensed
sources (`exercism/python`, `exercism/cpp`, `exercism/javascript`, `exercism/typescript`) and
parsed with tree-sitter. Per-language
templates turn syntax nodes into drills: change the string inside these quotes, jump to
the matching brace, rename every use of this identifier with `:s`. Each drill's candidate
solutions are replayed in `nvim --headless --clean`, and the shortest passing one becomes
the par. Quality gates reject drills that retyping would beat, drills whose par a shorter
motion beats, and task text that does not single out its target.

**Emulator and differential testing** (`app/`, TypeScript). You type into CodeMirror 6
with `@replit/codemirror-vim`. That emulator is a reimplementation of Vim, so the build
replays every par in it (headless Chromium) and never serves a drill the browser cannot
reproduce. `app/src/vimfixes*.ts` patch the places where it differs from Neovim. A
differential fuzzer (`make difftest`) runs random key sequences in both Neovim and the
browser editor from the same buffer, compares lines, cursor and mode, and minimises every
divergence to a few keys.

**Adaptive model** (`model/` in Python, `app/src/model/` in TypeScript). Each skill
tracks a time EMA, a keys-per-par EMA and recent accuracy. A skill is mastered when it is
at target speed, within 1.25x of par and at least 90 % accurate over enough samples.
Focus goes to the weakest skills, with rules that keep one stuck skill from taking over a
session; mastered skills come back on a spaced-review schedule. A 12-exercise placement
test seeds the model. The Python and TypeScript halves are kept identical by shared
scenario vectors.

## Run it locally

On macOS, from a fresh clone:

```sh
brew install uv node neovim     # node >= 23; neovim verifies every par in `make content`
git clone https://github.com/daniel-m-campos/vim-trainer.git && cd vim-trainer
make setup                      # uv sync for content/ and model/, npm ci and Playwright Chromium for app/
make content                    # generate build/ (~5 min: fetches the pinned sources, pars in nvim, replay in Chromium)
make dev                        # open http://localhost:5173/
```

On Linux, install the same tools from your package manager or their release pages;
`.github/actions/setup/action.yml` is the setup CI uses on Ubuntu. CI pins Neovim
0.12.5. Use that version: pars and `make content-check` depend on the Neovim that built
`build/`, so a different version can change pars and fail the byte-identical check.

The first visit asks three questions (language, editor, relative numbers) and then runs a
placement test of 12 exercises. After that, every visit starts a practice session.
Keys inside the editor go to Vim, except `F1` (hint). `Esc Esc` in normal mode skips an
exercise. On the result strip, `space` goes to the next exercise, `r` retries, `?` shows
hints, `!` flags the exercise, `q` ends the session, `s` opens stats and `,` opens
settings. In stats, `tab` (or `1` `2` `3`) switches between the skills grid, progress
charts and sessions; `h` `j` `k` `l` move in the grid, `enter` shows a skill's history,
`f` drills it next and `Esc` goes back.

Other targets:

```sh
make test           # unit tests: content (pytest), model (pytest), app grading + TS model mirror (node --test), typecheck
make e2e            # Playwright in Chromium: the bundled-sample flow, placement + a session on build/,
                    #   the stats-view demo page, and editor key sequences checked against nvim
make e2e-all        # the same in Chromium, Firefox and WebKit (first: make setup BROWSERS="chromium firefox webkit")
make content-check  # determinism check: rebuild into content/.cache/build-check and diff it against build/
make emulator       # report-only: replay every par and alternate in the browser
make difftest       # differential test of the browser editor against Neovim (SEED=, COUNT=, STRICT=)
make build          # static site in app/dist/
```

`build/` is generated, not committed: `make test`, `make e2e`, `make difftest`
and `make build` refuse to run until `make content` has produced it. After changing
anything under `content/`, run `make content` again. CI (`.github/workflows/ci.yml`)
generates `build/` on every run and checks that the pipeline is deterministic; a nightly
workflow runs the differential test; `deploy.yml` publishes the site to GitHub Pages from
`main`.

## Repository layout

- `content/` — the content pipeline (Python, uv): sources, tree-sitter mappings, templates,
  the Neovim oracle, quality gates, player-log ingest and the differential tester. Writes
  `build/`. See `content/README.md`.
- `build/` — generated exercises, `index.json` and `ATTRIBUTION.md` (gitignored).
- `model/` — the adaptive model in Python, the skill-graph tables and generator, scenario vectors and
  learner simulations. See `model/README.md`.
- `app/` — the browser app (TypeScript, Vite, CodeMirror 6 + codemirror-vim, no framework).
  `app/src/model/` is the TypeScript mirror of the model. See `app/README.md`, which has a
  reading guide.

## Contributing

Bug reports, wrong pars and unclear tasks are most useful straight from the app: press
`!` on the result strip to open a prefilled GitHub issue. For code, see
[CONTRIBUTING.md](CONTRIBUTING.md). The one rule that is not negotiable: every par is
verified in Neovim, never by hand.

## License and attribution

The code is MIT-licensed (see [LICENSE](LICENSE)). Exercise snippets come from
[exercism/python](https://github.com/exercism/python),
[exercism/cpp](https://github.com/exercism/cpp),
[exercism/javascript](https://github.com/exercism/javascript) and
[exercism/typescript](https://github.com/exercism/typescript) at pinned commits
(`content/sources.toml`), all MIT; the build checks each licence at the pinned commit. `make content` writes `build/ATTRIBUTION.md` with every repo, path,
commit and licence used, and the site links it from settings. Each exercise also shows its
source on the result strip.

The site is free and static, with no accounts, ads or payments. The editor is
[CodeMirror 6](https://codemirror.net/) with
[`@replit/codemirror-vim`](https://github.com/replit/codemirror-vim), both MIT.
