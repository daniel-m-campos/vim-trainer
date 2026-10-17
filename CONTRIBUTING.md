# Contributing

Thanks for helping. Setup is in the README (`make setup`, then `make content`). The design
documents in `docs/design/` explain why things are the way they are; the decision records
in `docs/decisions/` record the choices that are expensive to reverse.

## The one rule: every par is verified in Neovim

A par is the shortest known keystroke solution for an exercise. It is never written or
edited by hand. Every par comes from replaying candidate solutions in
`nvim --headless --clean` (`content/src/vimtrainer_content/oracle.lua` and `oracle.py`),
and the build then replays it in the browser editor. This holds for every path into the
content:

- a new template or idiom: `make content` verifies it;
- a player's shorter solution: `vimtrainer-content ingest` replays it in Neovim before it
  changes anything;
- an editor regression case: Neovim supplies the expected result at test time.

If Neovim and the browser editor disagree, Neovim is right and the editor gets fixed (or
the command is marked unsupported).

## Make targets

| target | what it does |
|---|---|
| `make setup` | `uv sync` for `content/` and `model/`, `npm ci` and Playwright Chromium for `app/` |
| `make content` | generate `build/`: fetch the pinned sources, verify pars in Neovim, replay them in the browser |
| `make dev` | the app at http://localhost:5173/ |
| `make test` | pytest for `content/` and `model/`, `node --test` and the typecheck for `app/` |
| `make e2e` | Playwright end-to-end tests in Chromium, including the editor cases checked against Neovim |
| `make e2e-all` | the same in Chromium, Firefox and WebKit |
| `make content-check` | rebuild into a scratch directory and require a byte-identical `build/` |
| `make emulator` | report-only replay of every par and alternate in the browser |
| `make difftest` | differential test of the browser editor against Neovim (`SEED=`, `COUNT=`, `STRICT=`) |
| `make vectors` | regenerate the model's shared scenario vectors from the Python model |
| `make build` | the static site in `app/dist/` |

Run `make test` and `make e2e` before opening a pull request. After a change under
`content/`, run `make content` and `make content-check`. After a change to model
behaviour, both model suites must pass (`make test-model`, `make test-app`).

## Adding an editor case

Editor cases are regression tests for the browser editor. A case holds inputs only: a
buffer, a start cursor and keys. It never holds an expected result; `app/e2e/editor.mjs`
asks Neovim for that at test time (`uv run vimtrainer-content expect`) and compares the
browser's lines, cursor and mode with it.

Add one line to `app/e2e/cases/editor.json` (or `macros-indent.json` for macros and
auto-indent):

```json
{"name": "a failing f{c} aborts the operator", "lines": ["abc def"], "cursor": [1, 0], "keys": "dfz"}
```

- `lines`: the buffer; `cursor`: `[line 1-based, column 0-based]`; `keys`: Vim
  angle-bracket notation (`<Esc>`, `<CR>`, `<C-v>`).
- `lang` (optional): `python` or `cpp`, for filetype-dependent behaviour such as indent.
- `oracle: "typed"`: replay the keys in Neovim as typed instead of through the batch
  oracle. Use it for macros and `:normal`, where a failing motion must abort the rest.
- `skip: ["cursor"]` with a `why`: compare everything except the listed fields, for an
  open divergence.
- `xfailIn: ["firefox"]`: an engine-specific failure that is reported but not counted.

Then run `make e2e` and watch the case pass or fail.

## Triaging a difftest finding

`make difftest` writes `content/.cache/difftest/<seed>/summary.md` and `findings.jsonl`.
For each new shape in `summary.md`, decide its class (`docs/design/differential-testing.md`):

| class | meaning | action |
|---|---|---|
| a | emulator bug | turn it into an editor case and fix `app/src/vimfixes.ts` |
| b | emulator limitation | accept it; the command stays out of drills and on the supported-command list |
| c | harness artefact (errors, indent noise, flaky) | fix the harness, or accept it |
| d | Neovim-specific behaviour we accept | accept it with a note |

For a class-a finding:

```sh
cd content
uv run vimtrainer-content difftest --seed S --only-index N                   # replay the case
uv run vimtrainer-content difftest --to-editor-case .cache/difftest/S/findings.jsonl   # print editor cases
```

Copy the printed line into `app/e2e/cases/editor.json`, watch it fail with `make e2e`, fix
`vimfixes.ts` until it passes, then rerun the seed: the shape should be gone. If the shape
has an entry in `content/difftest/known.jsonl`, remove it in the same change.

To accept a b, c or d finding:

```sh
uv run vimtrainer-content difftest --accept .cache/difftest/S/findings.jsonl --class b --note "why"
```

Review the appended lines in `known.jsonl` and commit them.

## Flagging from the app

On the result strip after any exercise, press `!`, pick a reason (`1` wrong par, `2`
wording, `3` editor differs from Vim, `4` other), optionally add a note and press
`Enter`. The app opens a prefilled GitHub issue with the exercise id, your keys, the par
and the app version; you can edit it or close the tab. A maintainer runs
`vimtrainer-content ingest` on the issue body, which replays your keys in Neovim before
any par changes (`docs/design/feedback-loop.md`).

## Style

- Python: functional style, numpy-style docstrings, `uv run` inside `content/` or `model/`.
- TypeScript: small and commented; `app/README.md` has a reading guide.
- Docs: one topic per file in `docs/design/`; a new decision gets the next number in
  `docs/decisions/`.
