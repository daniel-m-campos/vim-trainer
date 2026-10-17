# Differential testing of the emulator

Goal: find every way codemirror-vim (as patched in app/src/vimfixes.ts) behaves
differently from Neovim for the commands we drill, before a player does. ADR 0008.

The par replay proves one keystroke string per exercise. `difftest` proves many. It
generates random key sequences from the drilled command set and runs each one twice
from the same buffer and cursor: once in `nvim --headless --clean` (the oracle) and once
in headless Chromium through the app's real editor. Then it compares the buffer lines,
the cursor and the mode. Any difference is a finding.

## Running it

```sh
make difftest                       # SEED = today (YYYYMMDD), COUNT = 2000, --strict
make difftest SEED=20261013 COUNT=50000
make difftest STRICT=               # report-only: exit 0 whatever it finds (what the nightly runs)
cd content && uv run vimtrainer-content difftest --seed 20261013 --only-index 417
```

Output goes to `content/.cache/difftest/<seed>/`: `findings.jsonl` (one finding per
line), `summary.md` (counts, then one table row per finding shape) and, with `--dump`,
`cases.jsonl` with every generated case. Main flags: `--count` (2000), `--buffers` (200),
`--lang python cpp`, `--max-len` (24 tokens), `--web-pages` (4), `--include screen`,
`--no-minimise`, `--max-findings` (200), `--minimise-budget-s` (240), `--strict`.

## Module map

Python package `content/src/vimtrainer_content/difftest/`, plus one Node worker.

| file | job |
|---|---|
| `generate.py` | `Buffer`, `Case`; `load_buffers()` samples exercise buffers from `build/exercises/**` and adds the adversarial set in `content/difftest/buffers/*.json`; `generate(seed, count, buffers)` draws key sequences from a weighted grammar; `FORBIDDEN` rejects keys that leave the buffer or touch the outside world |
| `run.py` | the `difftest` subcommand: the Neovim side through `oracle.subprocess_runner` (batches of 200, 5 s timeout, bisects on timeout), the web side through `WebWorker`, compare, dedupe by shape, minimise, write output |
| `web.py` | `WebWorker`: spawns `node e2e/difftest-worker.mjs` in `app/` and talks JSON lines to it |
| `compare.py` | `Side`; `nvim_side()` and `web_side()` normalise both results; `compare()`, `classify()`, `shape()`; `Finding`; `known.jsonl` matching; `render_summary()` |
| `shrink.py` | `minimise()`: delta-debugs a diverging case to its smallest form |
| `app/e2e/difftest-worker.mjs` | starts vite and `emulator-check.html` as `e2e/emulator.mjs` does, types keys with `e2e/keys.mjs`, replies with the editor state |

### Generator

Each case uses its own `random.Random(seed * 1_000_003 + index)`, so `--only-index N`
replays case N of a seed without generating the others. A case is a list of
statements drawn with these weights: edit 45, motion 20, visual 10, ex 8, insert 7,
undo 4, dot 3, macro 2, register 1. Statements cover the tier 0-9 alphabet of
02-skill-graph: counts, text objects, `f{c}` with characters taken from the buffer,
insert text with `<CR> <BS> <Tab> <C-w>`, `:s :%s :g :v :m :t :norm`, `q{a}...q @{a}`
without recursion, and `.` only after a change. Screen motions (`H M L <C-d>` and so on)
are off unless `--include screen` is given, because the two window heights differ.
Every token must be one that `keys.mjs` can type (a test checks this).

### Worker protocol

`web.py` starts one worker per run: `node e2e/difftest-worker.mjs --pages N`. The two
processes exchange one JSON object per line on stdin and stdout.

```text
-> {"id": 7, "lang": "python", "lines": ["x = 1"], "cursor": [1, 0], "keys": "dwu"}
<- {"id": 7, "lines": ["x = 1"], "cursor": [1, 0], "mode": "normal", "ms": 41}
<- {"id": 8, "error": "timeout"}            # or "pageerror: <message>"
```

The worker mounts each request as an exercise with `expect: {}`, so `passed` never
latches. It types the keys, waits one animation frame and reads `window.emu.status()`.
In Visual mode the cursor comes from codemirror-vim's own `vim.sel.head` (CodeMirror's
selection head is one past it), clamped to the line length as Vim reports it after `$`.
The mode is `pending` while an operator, count or register is unfinished and `cmdline`
while the `:` or `/` input has focus.
Requests are spread over N pages. Each job has a 10 s watchdog; on timeout the worker
replaces the page. `web.py` respawns the worker when it prints nothing for 60 s.

### Comparison

Both sides become `Side(lines, cursor, mode, error)`. Neovim cursor columns are bytes,
so `nvim_side()` converts them to UTF-16 code units, which is what CodeMirror counts.
Mode names map to one set: normal, insert, replace, visual, visual-line, visual-block,
pending, cmdline, select, other, timeout, error. Lines compare exactly, without
stripping. A case that ends in pending, cmdline, select, other, timeout or error on
either side is counted as incomplete and is not a finding. A page error in the browser
is a finding of its own (field `error`, class a).

Three settings keep the Neovim side comparable:

- `oracle.lua` records lines, cursor and mode in its end-marker mapping, before its
  final `<C-\><C-n>`. That key would otherwise move an Insert-mode cursor one left and
  apply a pending insert count (`3iW` would show `WWW`). Outcomes that end in Normal
  mode, the only ones grading accepts, are unchanged.
- Keys that end mid-command (a bare `<C-w>`, `"`, `q`) swallow the end marker. The
  outcome then has `done = false` and the side becomes `pending`.
- `run.py` turns `startofline` on for the Neovim side, as in Vim. Neovim's default
  `nostartofline` keeps the column after `dd`, `>>`, `gg`, `G` and linewise operators,
  where codemirror-vim follows Vim; every such case would otherwise diverge. That is a
  Neovim-specific default (class d), recorded here instead of in `known.jsonl`.

## Classes and what each triggers

`classify()` guesses a class; the author confirms it during triage.

| class | meaning | guessed when | action |
|---|---|---|---|
| a | emulator bug | a browser page error, or nothing below matches | fix in `app/src/vimfixes.ts`; add a regression case to `app/e2e/editor.mjs` |
| b | emulator limitation | the keys use a `LIMITATIONS` token (`U`, `g@`, `gn`, `"1`-`"9`, `vi{`, `<BS>`/`<CR>` in block insert) | record it in `build/supported_commands.md`; keep it out of drills; the content gate marks dependent exercises web-unsupported |
| c | harness artefact | either side errored, or only leading whitespace differs after `o`, `O` or `<CR>` (filetype indent vs CodeMirror indent), or the case is flaky | fix the harness or accept in `known.jsonl` |
| d | Neovim-specific behaviour we accept | never guessed; set by the author | accept in `known.jsonl` with a note |

Findings are deduplicated by `shape(keys)`, which writes digits as `N`, character
arguments as `{c}`, insert text as `{text}` and words as `{word}`. Only one finding per
shape is minimised, shortest keys first, at most `--max-findings` within the time budget.
After minimisation the finding carries the minimised run's two sides and is
deduplicated again by its minimised shape.

A random 24-key sequence usually runs into several divergences at once, so before
minimisation nearly every diverging case has a shape of its own. Only minimised
findings are therefore triaged and judged by `--strict`; the rest are counted as
`unminimised` in `summary.md` and kept in `findings.jsonl`. With `--no-minimise` every
finding is judged.

## Minimisation

`minimise()` first finds the shortest diverging prefix, running the prefixes in
batches. It then deletes single tokens greedily, keeping only results that still
diverge and still avoid `FORBIDDEN`. The result is confirmed twice on the web side. A
case that no longer diverges returns `None`; it is recorded as flaky (class c) and
never counts as new. The budget is 120 runs per case and 240 s per run of the tool.

## known.jsonl

`content/difftest/known.jsonl` holds accepted findings, one per line:
`{"shape", "class", "note", "added", "match"?}`. A finding is known when an entry's
`shape` equals its minimised shape (its original shape if it was not minimised), or
when the entry's `match` regex is found in that shape. `--strict` makes the run exit 1
when a judged finding is neither known nor flaky; nothing else fails it. The file was
seeded from the known divergences below, then extended by the first triage (seed
20261012, see below). Class-a entries are open emulator bugs; their notes start with
"Open emulator bug". They are accepted so that a nightly run fails only on new shapes;
remove an entry when its fix lands.

To accept a finding after triage:

```sh
cd content
uv run vimtrainer-content difftest --accept .cache/difftest/20261013/findings.jsonl \
    --class b --note "vi{ is charwise in codemirror-vim"
```

This appends one entry per shape in the file. Review the diff and commit it.

After a round of fixes, prune the file: run two fresh seeds (`make difftest SEED=...`
twice, neither seed used before), and remove every entry whose shape (or `match`) no
longer appears in either run. An entry that still appears on one seed stays. Commit the
pruning with the fix it follows.

## Nightly job

`.github/workflows/difftest.yml` runs at 03:00 UTC and on manual dispatch, which takes
`seed` (empty means today) and `count` (2000). It uses the shared setup action
`.github/actions/setup`, runs `make difftest STRICT=` under a 25-minute limit, writes the
head of `summary.md` to the job summary and always uploads `content/.cache/difftest/` as an
artifact. It is report-only for now: the first runs (2026-10-13) found ~130–160 minimised
shapes per 2,000 cases, overwhelmingly class a, and every fresh seed still adds ~20–30 new
shapes. After round 4 a fresh seed still adds ~35–45 new shapes (below), so the nightly
stays report-only. The rule: when a fresh seed passes `make difftest` (strict) clean
locally, drop `STRICT=` from the workflow so the nightly fails on new shapes again. To reproduce a night locally, run
`make difftest SEED=<that date>` and read `summary.md`.

## From a class-a finding to a fix

1. Replay it: `uv run vimtrainer-content difftest --seed S --only-index N`.
2. Print regression cases:
   `uv run vimtrainer-content difftest --to-editor-case .cache/difftest/S/findings.jsonl`.
   It prints one `CASES` literal per finding for `app/e2e/editor.mjs` (minimised keys
   when there are some), with Neovim's result as the expected lines and cursor. Keep
   the ones you need.
3. Paste it into `app/e2e/editor.mjs` and watch it fail with `make e2e`.
4. Fix the behaviour in `app/src/vimfixes.ts` until the case passes.
5. Rerun the seed; the shape should no longer appear.

## Budget

- Nightly in CI: 2,000 sequences across 200 buffers. Measured locally (macOS, 4 pages,
  2026-10-12): Neovim 2.7 s (about 1.4 ms per case), web 14.6 s (about 7 ms per case),
  minimisation of 200 findings 125 s; 2 min 25 s end to end.
- 10,000 sequences (seed 2): Neovim 11.9 s, web 72.7 s, minimisation 53 s; 2 min 20 s.
- Before a release: 50,000 sequences locally.

## Known divergences (seed for known.jsonl)

Linewise `i{`/`i(`/`i[` in visual mode (`vi{`); `<BS>` and `<CR>` inside a block
insert; the exclusive-linewise rule for `c}`, `y}`, `gU}` and search motions; Select
mode (absent); `%` on some bracket shapes; `U`; `g@`; long or recursive macros
(codemirror-vim #177); `gn` behaviour; numbered registers.

Expected noise on day one: indentation after `o`, `O` and `<CR>`, because Neovim uses the
filetype's `indentexpr` and CodeMirror uses its language indent. Triage these through
`known.jsonl` or give `mountEditor` a plain-indent option.

## First triage (2026-10-12)

About 53 % of random sequences diverge (1,067 of 2,000 for seed 20261012). A 24-key
sequence usually hits at least one of many separate bugs. Turning off Neovim's
indentexpr/cindent for the run changed nothing measurable (225 vs 222 cases whose only
difference is leading whitespace), so neither indent mitigation was kept. Most indent
differences are emulator behaviour, not indent-engine noise: Insert-mode `<CR>` gives no
indent, `S<Esc>`/`o<Esc>` keep the unused auto-indent, `>` indents empty lines.

Seeds 20261012 (2,000) and 2 (10,000) gave 136 and 132 minimised shapes. All were triaged
into `known.jsonl` (109 entries): family entries with a `match` regex, plus exact shapes
for one-offs. By class, over both seeds: a 213, b 17, c 29, d 9. The largest class-a
families:

- shift operators `<` `>`: empty lines, failing motions, counts past the end;
- sentence motions `(` `)` and objects `is` `as`;
- `y` leaves the cursor in place after a backward motion or text object;
- an operator whose motion fails (`dfz`, `ci'` with no quotes) still acts;
- Insert-mode `<CR>` and `<C-w>`, and auto-indent kept on lines left empty;
- `J` spacing; `{` `}` and `]}` `[(` at buffer edges; `:m` page error from vimfixes.ts.

The class-d entries are Neovim defaults: Visual `*`/`#` mappings, `smarttab` `<BS>`, and
`ib` searching forward. `startofline` is handled in `run.py` (see Comparison).

A fresh seed (3, 2,000 cases) still gave 27 new shapes out of 136. The nightly job will
stay red until round-4 fixes or further triage shrink the families. Small Neovim-verified
cases for the main families are commented in `app/e2e/editor.mjs`.

## Round 4 measurement (2026-10-14)

Round 4 rewrote `vimfixes.ts` and added `vimfixes-macros-indent.ts`. Pruning followed the
rule above: the 80 class-a entries whose shapes the builders reported fixed were removed,
seeds 7 and 20261101 (2,000 cases each) were run against the rest, and the 14 entries
whose shape or `match` still covered a judged finding there were put back (`c}`,
`A<CR>`, `><CR>`, `N}`, `c*`, `c-`, `va'`, `:m<CR>`, `>G`, `Vs`, `S<Esc>`, `J`,
`O<C-w>`, `vit`). 66 stay pruned. New entries: `o{text}`/`O{text}` and `c_`/`c+` (class c,
indent engine) and `Y` (class d, Neovim's `Y` is `y$`).

| seed | diverging | minimised shapes | class a | new vs known |
|---|---|---|---|---|
| 20261013 (before round 4) | 1,026 | 152 | 131 | 29 |
| 20261015 nightly (before round 4) | 1,028 | 142 | 119 | 28 |
| 7 | 534 | 145 | 107 | 72 against the pruned file; 43 after the re-adds |
| 20261101 | 546 | 137 | 105 | 71 against the pruned file; 34 after the re-adds |
| 20261014 (`make difftest`, strict) | 527 | 126 | 96 | 36 (exit 1) |

Diverging cases halved. The shape counts are capped by the 240 s minimisation budget:
each round-4 run left 319–335 findings unminimised and unjudged, so they understate the
shapes, and the build the runs sampled from is the round-4 one. The new class-a shapes
are the next backlog: undo cursor (`Ju`, `ddu`), `:d`/`:t`/`:m` with ranges or patterns,
`:s` with an empty pattern (a page error in codemirror-vim), Visual `i"`/`i'` staying
charwise in `V`, `v$d`, `*` on punctuation, `<BS>` at column 0, `y_` cursor, and error-path
divergences the classifier guessed as c (`Vp`/`vp` with an empty register, `:4t.` past
the end, `:.,2d` on a one-line buffer). These stay out of `known.jsonl`.

## What it will not catch

Rendering (how it looks), timing, registers' contents, and anything outside the drilled
command set. Those stay with the player feedback loop (11).
