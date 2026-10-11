# Content pipeline

How real code becomes exercises, per programming language, with every par verified by
real Neovim. The pipeline is offline: it runs at build time and emits static JSON that
the site loads. Nothing here runs in the user's browser.

## Goals

1. Exercises feel like real editing because they are cut from real code.
2. Every skill node in `02-skill-graph.md` has exercises in every supported language
   where its weight is non-zero.
3. Every exercise has a par (optimal keystroke count) proven against `nvim --headless`,
   not against the browser emulator.
4. Adding a language is a tree-sitter grammar, a node→skill mapping, and a weight table.
5. Every snippet's origin and licence is recorded and shown.

## The exercise

An exercise is a small, self-contained edit on a short buffer.

```json
{
  "id": "ts/t.quote/0193",
  "skill": "t.quote",
  "lang": "typescript",
  "kind": "edit",                       // "edit" | "cursor" | "ex"
  "task": "Change the string passed to `logger.warn` to `retrying`",
  "start": { "lines": ["...", "..."], "cursor": [4, 12] },
  "expect": { "lines": ["...", "..."] },   // for kind=edit
  "par": { "keys": "ci\"retrying<Esc>", "count": 12, "verified": "nvim 0.12.5 2026-10-11" },
  "alternates": ["f\"ci\"retrying<Esc>"],
  "hints": ["ci\" works from anywhere inside the quotes"],
  "tags": ["string", "call-argument"],
  "source": { "repo": "github.com/org/repo", "path": "src/x.ts", "commit": "abc123", "license": "MIT" },
  "emulator": { "vscodevim": "ok", "ideavim": "ok" }
}
```

- **kind=edit**: pass when the buffer equals `expect.lines`. Cursor position ignored.
- **kind=cursor**: pass when the cursor lands on `expect.cursor`; buffer must be unchanged.
- **kind=ex**: pass when the buffer matches and the keystroke log contains a `:` command
  (prevents solving `:g/foo/d` with repeated `dd`).
- **par.count** counts keystrokes after normalisation (see Grading). Pass band is
  ≤ 2× par; "at par" is ≤ 1.0× par. Both are recorded per skill.

## Sources

Only permissive licences, recorded per snippet, with an `ATTRIBUTION.md` generated at
build time listing every repo, path, commit and licence used.

| source | licence | why | notes |
|---|---|---|---|
| Exercism exercise repos (`exercism/<lang>`) | MIT | small idiomatic files in 70+ languages, consistent style | example solutions and stubs; ideal first source |
| Author's own code (dotfiles, inkmd.nvim) | own | Lua content, zero licence risk | bootstraps the Lua track |
| Selected MIT/Apache-2.0/BSD repos per language | permissive | realistic production code | keep an allowlist; check `LICENSE` at the pinned commit |
| vimhjkl challenges (MIT, 230, skill-tagged) | MIT | ready-made drills, already verified against Vim | attribute; partially LLM-generated, so review before import |
| Vimtutor Sequel, OpenVim, VimMaster content | MIT | motion drills | attribute |

Excluded: VimGolf challenge texts (no licence stated on vimgolf.com), Rosetta Code
(CC BY-SA, copyleft), any GPL/AGPL/LGPL repo, anything with "all rights reserved" or no
LICENSE file, StackOverflow snippets (CC BY-SA).

Snippet size: 8–40 lines, ≤ 100 columns. Longer files are windowed around the target
node. Strip or shorten licence headers and author comments from the snippet itself.

## From code to exercises: tree-sitter

The generator is a Python package (`py-tree-sitter` with the per-language grammar
wheels, e.g. `tree-sitter-python`, `tree-sitter-cpp`). For each snippet it parses the
file and walks the syntax tree, mapping node types to skill nodes. Neovim is only used
as a subprocess oracle (below); no Lua is written beyond a ~50-line `oracle.lua`.

The author writes Python and C++, so the pipeline, review CLI and oracle driver are
Python. The browser app is necessarily TypeScript (see 06-tech-stack.md).

### Node → skill mapping (per language, declarative)

```python
# content/lang/python.py
LANG = Language(
    grammar="python",
    nodes={
        "string":             Map(skills=["t.quote"], templates=["change_inner", "delete_inner", "yank_inner"]),
        "argument_list":      Map(skills=["t.paren", "m.find"], templates=["change_nth_arg", "delete_all_args", "jump_to_close"]),
        "keyword_argument":   Map(skills=["m.find", "o.change"], templates=["change_kwarg_value"]),
        "list":               Map(skills=["t.bracket"], templates=["change_inner", "delete_nth_item"]),
        "dictionary":         Map(skills=["t.brace"], templates=["change_inner", "delete_nth_item"]),
        "block":              Map(skills=["t.para", "o.indent", "m.para"], templates=["indent_block", "delete_block", "jump_block_end"]),
        "comment":            Map(skills=["m.find", "o.delete", "nv.comment"], templates=["delete_trailing_comment", "toggle_comment"]),
        "identifier":         Map(skills=["t.word", "o.change", "x.subst", "a.dot"], templates=["rename_here", "rename_all_dot", "rename_all_subst"]),
        "decorator":          Map(skills=["o.delete", "x.copymove"], templates=["delete_line", "move_line_down"]),
        "import_from_statement": Map(skills=["x.copymove", "o.yank"], templates=["move_line_up", "duplicate_line"]),
    },
    find_targets=["(", ")", "=", ":", ",", ".", "["],   # for m.find drills
    comment_leader="#",
)

# content/lang/cpp.py adds: call_expression/argument_list, compound_statement (t.brace, m.match),
# template_argument_list (t.angle), string_literal, raw_string_literal, preproc_include,
# namespace_definition, field_expression (`.`/`->` for m.find), comment_leader="//".
```

Grammars for v1: python, cpp, c, typescript, javascript, tsx, java, go, rust, lua,
html, json, yaml, markdown. All are published as `tree-sitter-<lang>` PyPI wheels.

### Templates

A template turns a (snippet, node) pair into an exercise. Each template knows which
skills it exercises, how to describe the task in words, how to compute `expect`, and
one or more canonical solutions. Examples:

| template | start cursor | task | canonical | skills |
|---|---|---|---|---|
| change_inner | inside node | Change the contents of this {node} to `X` | `ci{delim}X<Esc>` | t.* |
| delete_inner | inside node | Empty this {node} | `di{delim}` | t.* |
| delete_around | inside node | Remove this {node} entirely | `da{delim}` | t.* |
| change_nth_arg | start of call | Change the {n}th argument to `X` | `f(` + `{n-1}f,` + `lct,X<Esc>` or `ci(` variants | t.paren m.find m.repeatfind |
| jump_match | on `{` | Move to the matching `}` | `%` | m.match |
| jump_to_close | inside block | Move to the closing brace of this block | `]}` | n.unmatched |
| delete_trailing_comment | line start | Remove the comment at the end of this line | `f{leader}hD` or `f{leader}D` | m.find o.delete |
| rename_all_dot | first occurrence | Rename every `a` in this snippet to `b` | `*cgnb<Esc>` + `.` × k | x.lastsearch a.dot |
| rename_all_subst | anywhere | Rename every `a` to `b` | `:%s/\<a\>/b/g<CR>` | x.subst x.regex |
| delete_matching_lines | anywhere | Delete every line containing `X` | `:g/X/d<CR>` | x.global |
| append_each_line | first line | Add `;` to the end of lines {i}–{j} | `Ctrl-v` + `{n}j$A;<Esc>` or `:i,jnormal A;` | v.blockedit x.normal |
| move_line | on line | Move this line below the next one | `ddp` or `:m+1<CR>` | x.copymove |
| indent_block | inside block | Indent this block one level | `>i{` | o.indent t.brace |
| upper_word | on identifier | Uppercase this identifier | `gUiw` | o.case t.word |
| increment | on number | Change this number to {n+3} | `3Ctrl-a` | o.number |
| goto_line_rel | k lines away | Move the cursor to the highlighted line | `{k}j` or `{k}k` | m.rel |
| find_char | line start | Move to the {n}th `X` on this line | `{n}fX` or `fX;;` | m.find m.repeatfind |
| record_macro | line 1 | Apply the shown edit to lines 1–{n} | `qa...q{n-1}@a` or `:2,{n}normal @a` | a.macro a.macrorange |

Templates for tier 7–8 (Ex, macros) need multi-line buffers with repeated structure;
the generator prefers snippets with ≥ 3 sibling nodes of the same type for those.

### Anti-shortcut buffer sizing (from vimhjkl)

The buffer must be large enough that retyping it is slower than the intended skill, and
distractors must exist: a `t.quote` exercise needs other strings nearby so `f"` alone is
ambiguous; a `m.rel` exercise needs the target far enough that `jjjj` loses to `7j`.
The generator checks `par.count < retype_cost / 3` and discards exercises that fail.

## Par verification: Neovim as the oracle

For each exercise, each canonical and alternate solution is replayed in real Neovim:

```sh
nvim --headless --clean -u content/oracle.lua \
  -c 'lua Oracle.run("build/exercises/ts/t.quote/0193.json")'
```

`oracle.lua` (the one Lua file, ~50 lines) loads `start.lines`, places the cursor,
feeds the solution with `nvim_feedkeys` (or `nvim_input`), then writes the resulting
buffer and cursor as JSON to stdout. The Python driver (`oracle.py`) spawns one
`nvim --headless` per batch of exercises via `subprocess`, parses the JSON and compares
to `expect`. It records the Neovim version and date in `par.verified`. Exercises whose
canonical solution fails are rejected at build time, never shipped.

Alternative to evaluate: `pynvim` over msgpack-RPC to a single long-lived headless
Neovim, which avoids process startup per batch and gives direct buffer access.

The oracle also **searches for a better par**: it tries a small library of candidate
idioms for the skill and keeps the shortest that passes. If a human-written canonical
loses to a candidate, the build logs it for review. This is how we avoid shipping
pars that an expert beats, which is the fastest way to lose persona B.

`--clean` matters: pars assume default settings plus a documented minimal set
(`relativenumber` for m.rel drills). User mappings never affect par.

## Emulator compatibility flags

A second oracle runs the canonical solution through `@replit/codemirror-vim` in a
headless browser (Playwright) and records pass/fail. Exercises that pass in Neovim but
fail in the emulator are shipped with `emulator.web = "unsupported"` and excluded from
the browser trainer until the emulator or the exercise is fixed. The published
supported-command list is generated from this.

VSCodeVim and IdeaVim flags are initially copied from the skill graph's per-skill
flags (see 02 To research for making them real).

## Quality gates (all automated)

1. Licence allowlist check on every source repo at the pinned commit.
2. Snippet size and width bounds.
3. Canonical solution passes in `nvim --headless --clean`.
4. No shorter candidate beats the canonical by more than 1 keystroke (else flag).
5. Anti-shortcut ratio holds.
6. Task text mentions the target unambiguously (one node of that type at that position,
   or a line/column highlight is attached).
7. Secret scan on snippets (keys, tokens, emails) before publishing.
8. Per-(language, skill) minimum: ≥ 20 exercises, else the skill is marked
   `thin` for that language and down-weighted.

## Measured language weights

The build emits `build/stats/node_frequency.json`: per language, how many nodes of each
type occur per 100 lines across the corpus. `02-skill-graph.md`'s weight table is
replaced by this once the corpus is in; weights = normalised frequency × a hand-set
importance factor per skill.

## Human review

Generated exercises are not shipped unreviewed. A Python review CLI (Textual or plain
curses) shows start → expect → canonical, with accept / reject / edit. Accepted exercise ids go in a `reviewed.txt`
allowlist. The author reviews the first corpus; this is also Vim practice.

LLM assistance is allowed for writing task descriptions and hints only, never for
generating code snippets or solutions, and its use is noted in the exercise's
`provenance` field. The community has punished LLM-generated exercise content
(vimhjkl); real code plus a real-Neovim oracle is the answer to that.

## Output

```
build/
  exercises/<lang>/<skill>/<id>.json
  index.json            # per lang, per skill: ids, counts, par stats
  stats/node_frequency.json
  supported_commands.md
  ATTRIBUTION.md
```

Static files, cacheable, loaded lazily per (language, skill). Target: ≥ 20 exercises
per non-zero (language, skill) pair for the v1 languages, so roughly 10k exercises.

## Bootstrapping order

1. Python from the author's own code and `exercism/python`, 10 skills, 5 templates,
   Neovim oracle only. Proves the tree-sitter → template → oracle loop in the language
   the author reads fastest, so review is cheap.
2. C++ from the author's own code and `exercism/cpp`. Adds brace/angle/`%`-heavy
   skills that Python lacks, which exercises the per-language weight machinery.
3. TypeScript from `exercism/typescript` (the Switcher persona's main language); add
   the emulator oracle.
4. Expand templates to tiers 7–8. Import and review vimhjkl.
5. Remaining languages are grammar + mapping + weights.

## To research

- `pynvim` RPC vs `subprocess` per batch for the oracle (startup cost vs simplicity).
- Exact `nvim_feedkeys` vs `nvim_input` semantics for replaying `<Esc>`, counts and
  `:` commands deterministically in headless mode; whether `--clean` disables anything
  the exercises need (e.g. `filetype` for `gcc`).
- Whether `@replit/codemirror-vim` can run headless without a DOM (jsdom) for the
  emulator oracle, or needs Playwright.
- Node type names differ across grammars (e.g. `string` vs `string_literal`); build the
  mapping from each grammar's `node-types.json`.
- How vimhjkl computes par and sizes buffers, to reuse its heuristics (MIT).
- Exercism repo structure per language and whether example solutions are consistently
  present and MIT (most `exercism/<track>` repos are MIT; verify each).
- Playback UI for showing the canonical solution keystroke-by-keystroke (needed by
  grading/replays, see 05).
