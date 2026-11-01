# Contributing

Setup is in the README: `make setup`, then `make content`.

## The one rule: every par is verified in Neovim

A par is the shortest known keystroke solution for an exercise. It is never written or
edited by hand. Every par comes from replaying candidate solutions in
`nvim --headless --clean` (`content/src/vimtrainer_content/oracle.lua` and `oracle.py`),
and the build then replays it in the browser editor. A player's shorter solution is
replayed in Neovim by `vimtrainer-content ingest` before it changes anything. If Neovim
and the browser editor disagree, Neovim is right and the editor gets fixed (or the
command is marked unsupported).

## Make targets

| target | what it does |
|---|---|
| `make setup` | `uv sync` for `content/` and `model/`, `npm ci` and Playwright Chromium for `app/` |
| `make content` | generate `build/`: fetch the pinned sources, verify pars in Neovim, replay them in the browser |
| `make dev` | the app at http://localhost:5173/ |
| `make test` | pytest for `content/` and `model/`, `node --test` and the typecheck for `app/` |
| `make e2e` | Playwright tests in Chromium, including the editor cases checked against Neovim |
| `make content-check` | rebuild into a scratch directory and require a byte-identical `build/` |
| `make difftest` | differential test of the browser editor against Neovim (`SEED=`, `COUNT=`, `STRICT=`) |
| `make build` | the static site in `app/dist/` |

Run `make test` and `make e2e` before opening a pull request. After a change under
`content/`, run `make content` and `make content-check`.

## Adding an editor case

An editor case holds inputs only: a buffer, a start cursor and keys. `app/e2e/editor.mjs`
asks Neovim for the expected result at test time and compares the browser's lines, cursor
and mode with it. Add one line to `app/e2e/cases/editor.json` (or `macros-indent.json`):

```json
{"name": "a failing f{c} aborts the operator", "lines": ["abc def"], "cursor": [1, 0], "keys": "dfz"}
```

- `cursor` is `[line 1-based, column 0-based]`; `keys` use Vim angle-bracket notation.
- Optional: `lang` (`python` or `cpp`); `oracle: "typed"` for macros and `:normal`;
  `skip: ["cursor"]` with a `why` for an open divergence; `xfailIn: ["firefox"]`.

Then run `make e2e` and watch the case pass or fail.

## Triaging a difftest finding

`make difftest` writes `content/.cache/difftest/<seed>/summary.md` and `findings.jsonl`.
Give each new shape in `summary.md` a class:

| class | meaning | action |
|---|---|---|
| a | emulator bug | turn it into an editor case and fix `app/src/vimfixes.ts` |
| b | emulator limitation | accept it; the command stays out of drills |
| c | harness artefact (errors, indent noise, flaky) | fix the harness, or accept it |
| d | Neovim-specific behaviour we accept | accept it with a note |

For class a, print editor cases with
`uv run vimtrainer-content difftest --to-editor-case .cache/difftest/S/findings.jsonl`
(from `content/`), copy the line into `app/e2e/cases/editor.json`, watch it fail, fix
`vimfixes.ts` until it passes, and rerun the seed. Remove any matching entry from
`content/difftest/known.jsonl` in the same change. To accept a b, c or d finding:

```sh
uv run vimtrainer-content difftest --accept .cache/difftest/S/findings.jsonl --class b --note "why"
```

## Flagging from the app

On the result strip, press `!`, pick a reason (`1` wrong par, `2` wording, `3` editor
differs from Vim, `4` other), optionally add a note and press `Enter`. The app opens a
prefilled GitHub issue with the exercise id, your keys, the par and the app version.
Flagged keys go through `vimtrainer-content ingest`, which replays them in Neovim before
any par changes.

## Style

- Python: 3.12+, functional style, numpy-style docstrings, `uv run` inside `content/` or `model/`; `make lint` (ruff) must pass.
- TypeScript: small and commented; `app/README.md` has a reading guide.
