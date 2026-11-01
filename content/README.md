# content pipeline

The content pipeline turns real source code into verified Vim exercises. The top-level
`README.md` lists the make targets.

## Ingesting player logs

`ingest` replays what players typed in real Neovim and folds the results back into the
corpus. It reads either of two inputs:

- an exported progress file (app Settings > export). Its `model.log` records carry the
  player's keys (`seq`), `beatPar` and the `!` flag;
- a GitHub issue body from the app's `!` flag, saved to a text file. The body is read as
  `label: value` lines (`exercise`, `player keys` or `seq`, `reason`, `note`), case-insensitive.

```sh
cd content
uv run vimtrainer-content ingest ~/Downloads/vim-trainer-2026-10-12.json issue-42.md
```

A record is replayed when it beat par or was flagged `wrong-par` or `emulator`. The result
depends on the Neovim verdict:

| Neovim verdict | effect |
|---|---|
| passes in fewer keys than par | the exercise in `build/` gets `seq` as `par.keys`; the old canonical moves to `alternates`; the generalised idiom is appended to `idioms_learned.toml` |
| passes in par keys or more | `seq` is appended to the exercise's `alternates`; the generalised idiom is appended to `idioms_learned.toml`, so the rebuild keeps it as an alternate |
| fails, but the app accepted it | an entry in `review/emulator-divergences.md` |
| passes, but the app rejected it | also an entry in `review/emulator-divergences.md` |

`wording` flags go to `review/wording-queue.md`, grouped by template. Every run appends a
dated section to `review/ingest-log.md`. A second run on the same file adds no duplicate
alternates, idioms or queue entries.

An idiom is generalised before it is stored. Counts become `{{k}}`, so `yy2jp` is stored as
`yy{{k}}jp`. Typed insert text becomes `{{text}}`, so `ciwfoo<Esc>` is stored as
`ciw{{text}}<Esc>`. An idiom already in `idioms_learned.toml` for the skill (any status) is
not added again; built-in idioms do not count, because the build only tries them as
candidates and never as variants. `par_search.IDIOMS` merges the file at import and expands `{{k}}` to the counts 1-9.

The edits to `build/` last only until the next `make content`, because the build
regenerates every exercise from its template. The learned idiom is what survives: the
rebuild replays it on every exercise of the skill, and `build.evaluate` adds it to the
canonical variants after the template's own. When it passes and is shortest it becomes
the par, so gate 4 does not reject the exercise. A tie keeps the template's canonical and
ships the idiom as an alternate. Adding the idiom to the template's `variants` is still
the tidy fix, and `review/ingest-log.md` names the template.

Learned idioms start with `status = "new"`. `vimtrainer-content review --idioms` lists them.
To review one, set its `status` to `"ok"` in `idioms_learned.toml`. Set it to `"rejected"`
to stop the par search from using it.

## Differential testing (difftest)

`difftest` looks for places where the browser emulator disagrees with Neovim. It
generates random key sequences, runs each in `nvim --headless --clean` and in the app's
editor (headless Chromium), and compares lines, cursor and mode.

```sh
make difftest                                   # from the repo root: today's seed, 2000 cases, --strict
make difftest SEED=20261013 COUNT=50000         # before a release
cd content
uv run vimtrainer-content difftest --seed 20261013 --only-index 417          # replay one case
uv run vimtrainer-content difftest \
    --to-editor-case .cache/difftest/20261013/findings.jsonl                 # editor.mjs cases, one per finding
uv run vimtrainer-content difftest --accept .cache/difftest/20261013/findings.jsonl \
    --class b --note "why this is accepted"                                  # append to known.jsonl
```

Outputs go to `.cache/difftest/<seed>/`:

- `summary.md`: counts (cases, incomplete, minimised findings, new, unminimised) and one
  row per minimised finding shape;
- `findings.jsonl`: every finding with both sides, the class guess and the minimised keys;
- `cases.jsonl`: every generated case, only with `--dump`.

To triage, read `summary.md` and decide the class of each new shape:

| class | meaning | what to do |
|---|---|---|
| a | emulator bug | `--to-editor-case`, add the case to `app/e2e/editor.mjs`, fix `app/src/vimfixes.ts` |
| b | emulator limitation | `--accept --class b`; the command goes on the supported-command list and out of drills |
| c | harness artefact (errors, indent noise, flaky) | fix the harness, or `--accept --class c` |
| d | Neovim-specific behaviour we accept | `--accept --class d` with a note |

`content/difftest/known.jsonl` holds the accepted shapes; commit it after `--accept`.
With `--strict`, the run exits 1 only for minimised findings that match no entry there
(a long unminimised sequence has a shape of its own, so it is counted, not judged).
Class-a entries are open emulator bugs; remove one when its fix lands. The nightly CI job
`.github/workflows/difftest.yml` runs `make difftest STRICT=` (report-only while the class-a
backlog is open) and uploads `.cache/difftest/`.

## C++

C++ is the second content language. Its sources, mapping and windowing live in
`src/vimtrainer_content/lang/cpp.py`.

### Source

The C++ source is `github.com/exercism/cpp`, pinned in `sources.toml` (entry
`exercism-cpp`). The licence is MIT and was checked at the pinned commit
`e6e47e11fb47e561d0eca71c6197163695b44caf`. The build reads these files:

- `exercises/practice/*/.meta/example.cpp`
- `exercises/practice/*/.meta/example.h`
- `exercises/concept/*/.meta/exemplar.cpp`

That is 182 files and about 5,400 lines. The parser is `tree-sitter-cpp` (grammar 0.23),
a dependency in `pyproject.toml`.

### Windows

`cpp.windows(text, source)` replaces `snippets.windows` for C++ files. It groups top-level
items into windows of 8-40 lines, at most 100 columns wide. When an item is longer than 40
lines, it recurses into the item's body. That covers namespaces, classes, functions,
`template <...>` declarations and `#ifndef` header guards. Short spans are merged only with
spans at the same nesting level. Without that rule, a merged window could swallow a
namespace's closing `}` and fail to parse. A trailing `}  // namespace x` comment stays
with the `}` it follows. On the exercism corpus this gives 253 windows covering 4,775 of
about 5,400 lines.

A window never starts inside a comment block that began above it and never ends on
comment-only lines (`snippets.trim_comment_edges`, every language). The build then applies
the snippet quality gate, `snippets.quality_problem`, to every window of every language.
It rejects scaffold (`TODO`, `Waiting to be implemented`, `NotImplementedError`, Exercism
instruction comments) and windows with fewer than 20 code tokens. For C++ it also rejects
declaration-only windows: fewer than 3 statements and fewer than 40 code tokens, which is
a header of prototypes. A class declaration with more code than that passes. On the
exercism corpus the gate drops 76 of 253 C++ windows (73 declaration-only, 3 scaffold)
and 3 of 237 Python windows. `stats/gates.json` counts each dropped window under
`snippet-window` and the drafts it would have made under `snippet`, per skill and template.

### Node -> skill mapping

| node type | skill | template (exercise `template` field) |
|---|---|---|
| `string_literal` | t.quote, o.case | change_inner / delete_inner (`ci"` `di"`), upper_inner (`gUi"`) |
| `argument_list`, `parameter_list`, `condition_clause`, `parenthesized_expression` | t.paren, m.match, n.unmatched | change_inner / delete_inner, jump_match (`%`), jump_block_end (`])` `[(`) |
| `argument_list` of a `call_expression` | o.change | change_nth_arg (`f,wct,X`) |
| `compound_statement` | t.brace, m.match, n.unmatched, o.indent | change_inner / delete_inner (one line), delete_inner (multi-line body, `di{`), jump_match, jump_block_end, indent_block (`>i{` / `<i{`) |
| `initializer_list` | t.brace, m.match, n.unmatched | as for `compound_statement` |
| `field_declaration_list` (class body) | t.brace, m.match, o.indent | delete_inner (`di{`), jump_match, indent_block |
| `template_argument_list`, `template_parameter_list` | t.angle | change_inner / delete_inner (`ci<` `di<`) |
| `subscript_argument_list`, `lambda_capture_specifier` | t.bracket, m.match | change_inner / delete_inner (`ci[` `di[`), jump_match |
| `comment` (`//` and `/* */`, single line, after code) | o.delete | delete_trailing_comment (`f/D`) |
| `function_definition`, `if_statement`, `for_statement`, `for_range_loop`, `while_statement` | o.delete | delete_lines (`Ndd`, `d}`) |
| `identifier`, `field_identifier` | t.word, o.case, x.subst | rename_here (`ciw`), upper_word (`gUiw`), rename_all_subst (`:%s`) |
| `field_expression` (`.` and `->`) | m.find | find_char (`f.`, `f-`) |
| `preproc_include`, `using_declaration`, `field_declaration`, one-line `declaration` and `expression_statement` | x.copymove | move_line (`:m`), copy_line (`:t`) |
| one-line `declaration` / `expression_statement` with `=` | o.change | change_to_end (`C X;` or `ct;X`) |
| (every line) | m.rel, m.find | goto_line_rel (`7j`), find_char on `( ) { } ; , = < > . -> ::` |

Some differences from the task wording:

- `subscript_expression` maps through its `subscript_argument_list` child. In grammar 0.23
  that child holds the `[ ]`.
- `initializer_list` maps to t.brace, not t.bracket, because `{1, 2, 3}` is a brace pair.
- `raw_string_literal` is mapped, but no exercise comes from it. `ci"` on `R"(text)"`
  would change the `(text)` delimiters too.
- For `->` and `::`, the motion is `f` plus the token's first character. A target is used
  only when every `-` or `:` before it belongs to an earlier `->` or `::`. In practice
  that means the first `::` on a line, and any `->` with no stray `-` before it.

`cpp.WEIGHTS` holds the C/C++ column of the weight table in `model/skill-graph.md`.
`tests/test_cpp.py` checks it against `model/skill-graph.json`.

### Templates

The shared templates in `templates.py` were written for Python. Some need nothing beyond a
C++ node: `jump_match`, `jump_block_end`, `rename_here`, `upper_word`, `rename_all_subst`,
`goto_line_rel`, `delete_lines` and `delete_trailing_comment`. These are reused through
thin wrappers. Each wrapper first fills the window cache with C++ facts: which rows hold
only a comment, which cells sit inside strings or comments, and how many delimiter pairs
of each kind exist. The shared helpers read those cache entries instead of looking for
Python `string` and `#` nodes.

The rest have C++ versions in `cpp.py`, and their exercises keep the shared template
names:

- `change_inner`, `delete_inner` and `upper_inner`. The shared versions read Python
  `string_start` / `string_end` children and Python node names. The C++ versions also
  handle `<>` and multi-line `{}` bodies, and choose replacement text that fits the node:
  a number for a number, a string for a string.
- `change_nth_arg`. The shared version needs a Python `call` node.
- `change_to_end`. A C++ line ends in `;`, so the drill is `C X;` or `ct;X`, not `C X`.
- `indent_block`. Python blocks are defined by indentation; a C++ body sits between `{`
  and `}` lines, and `>i{` is the canonical solution.
- `move_line` and `copy_line`. The parents differ (`compound_statement`,
  `translation_unit`), and a preprocessor line ends at column 0 of the next row.
- `find_char`, for the multi-character targets `->` and `::`.

`cpp.generate(win)` runs `templates.generate` with the `cpp_*` templates registered for
that one call. The shared registry has no per-language hook, so C++ windows must go
through `cpp.generate`.

### Building C++ on its own

`build.py` builds every language: `build.LANGS` maps each language to its windowing,
node-frequency and draft functions and its default skills (`cpp.windows`,
`cpp.node_frequency`, `cpp.generate`, `cpp.TARGET_SKILLS`). To try C++ alone without
touching `build/`, write to a scratch directory:

```sh
cd content
uv run vimtrainer-content build --offline --out .cache/scratch-cpp/out \
    --skills t.quote t.paren t.brace t.bracket t.angle t.word m.find m.match m.rel \
             n.unmatched o.delete o.change o.indent o.case x.subst x.copymove
```

(`--skills` applies to every language, so Python also builds the skills it has from that
list. For C++ only, call `build.build(...)` with a `sources_toml` holding just the cpp entry.)

Verified counts for exercism/cpp, with no per-skill cap (build cap 40 in brackets):

| skill | exercises | | skill | exercises |
|---|---|---|---|---|
| t.quote | 133 (40) | | m.rel | 190 (40) |
| t.paren | 677 (40) | | n.unmatched | 162 (40) |
| t.brace | 338 (40) | | o.delete | 236 (40) |
| t.bracket | 27 (27) | | o.change | 148 (40) |
| t.angle | 177 (40) | | o.indent | 241 (40) |
| t.word | 224 (40) | | o.case | 505 (40) |
| m.find | 176 (40) | | x.subst | 313 (40) |
| m.match | 335 (40) | | x.copymove | 540 (40) |

t.bracket is the thinnest skill. Most subscripts in the corpus are short, like `[i]` or
`[pos]`, and `di[` on those does not beat `x`, so the anti-shortcut gate rejects them.
Only 3 o.delete exercises are trailing comments. Exercism C++ has few comments after code
other than `}  // namespace x`, which is skipped because retyping `}` is cheaper.

### Known issue: py-tree-sitter 0.26.0

In tree-sitter 0.26.0 for Python, reading `Point.row` or `Point.column` on a value above
256 drops a reference the binding does not own. The interpreter then crashes later, at an
unrelated line. Small ints (up to 256) are immortal, so files shorter than 257 lines never
hit the bug. Indexing (`point[0]`) is safe. `cpp.py` indexes points wherever it walks a
whole file. `snippets.windows` (Python) still reads `.row` on whole-file trees, so a
Python source longer than 256 lines would crash the build.

## JavaScript and TypeScript

JavaScript and TypeScript are the third and fourth content languages. One module,
`src/vimtrainer_content/lang/js.py`, serves both: `js.LANG_JS` (`lang` `javascript`, ids
`js/...`) and `js.LANG_TS` (`lang` `typescript`, ids `ts/...`). TypeScript's node types are
a superset of JavaScript's, so the two share one node mapping. The module follows `cpp.py`
function by function. The grammar-agnostic helpers both modules use (text and highlight
helpers, bracket scanning, span merging, template registration) live in
`src/vimtrainer_content/lang/braces.py`. The templates themselves are duplicated rather
than shared, because cpp's templates read cpp's own tables.

### Sources

| entry in `sources.toml` | files | commit |
|---|---|---|
| `exercism-javascript` | `exercises/practice/*/.meta/proof.ci.js`, `exercises/concept/*/.meta/exemplar.js` | `ff04f35158cdf61eebfdf18a774010495a1fd6d9` |
| `exercism-typescript` | `exercises/practice/*/.meta/proof.ci.ts`, `exercises/concept/*/.meta/exemplar.ts` | `1ce80b07d40d2d707dd6d651c640774c5c884410` |

Both are MIT, checked at the pinned commit. JavaScript has 169 files and about 8,400 lines.
TypeScript has 112 files and about 5,900 lines; its track has a single concept exemplar.
The parsers are `tree-sitter-javascript` (grammar 0.25) and `tree-sitter-typescript`
(grammar 0.23, its `typescript` dialect).

### Windows

`js.windows_js` and `js.windows_ts` work like `cpp.windows`, with two differences.

- Exercism's JavaScript and TypeScript are indented by two spaces. `js.reindent` turns each
  level into four spaces, the oracle's `shiftwidth`, so that `>>` shifts by one level of the
  code. An indent `i` becomes `i + 2 * (i // 2)`, which also keeps a block comment's ` * `
  lines aligned. The inside of a multi-line template string is string content, so it stays
  as it is.
- A method or a `key: value` entry does not parse on its own. A class body or object
  literal longer than 40 lines is therefore cut into windows of whole members, and each
  window keeps the class (or object) header line and its closing line around them. The
  window's `first_line` / `last_line` (and the exercise's `source.lines`) are those of the
  members. ATTRIBUTION.md says so. A function body longer than 40 lines is split into its
  statements, as in C++.

On the exercism corpus this gives 326 JavaScript windows covering 7,258 lines and 231
TypeScript windows covering 5,102 lines. The quality gate drops 42 JavaScript windows and
6 TypeScript windows, all of them thin (fewer than 20 code tokens).

### Node -> skill mapping

| node type | skill | template |
|---|---|---|
| `string` (`'` or `"`) | t.quote, o.case | change_inner / delete_inner (`ci'` `di"`), upper_inner (`gUi'`) |
| `template_string` | t.quote | change_inner / delete_inner (``ci` `` ``di` ``) |
| `arguments`, `formal_parameters`, `parenthesized_expression` (an `if` / `while` condition too) | t.paren, m.match, n.unmatched | change_inner / delete_inner, jump_match, jump_block_end |
| `arguments` of a `call_expression` | o.change | change_nth_arg (`f,wct,X`) |
| `statement_block` | t.brace, m.match, n.unmatched, o.indent, x.normal | change_inner / delete_inner, delete_inner (multi-line, `di{`), jump_match, jump_block_end, indent_block (`>i{`), prefix_each_line |
| `object` | t.brace, m.match, n.unmatched | change_inner / delete_inner, delete_inner (multi-line), jump_match, jump_block_end |
| `class_body` | t.brace, m.match, o.indent, x.normal | delete_inner (`di{`), jump_match, indent_block, prefix_each_line |
| `array`, `subscript_expression` | t.bracket (and m.match for `array`) | change_inner / delete_inner (`ci[` `di[`), jump_match |
| `type_arguments`, `type_parameters` (TypeScript only) | t.angle | change_inner / delete_inner (`ci<` `di<`) |
| `comment` (single line, after code) | o.delete | delete_trailing_comment (`f/D`) |
| `function_declaration`, `method_definition`, `if_statement`, `for_statement`, `for_in_statement`, `while_statement` | o.delete | delete_lines (an `export` in front is deleted too) |
| `identifier`, `property_identifier` | t.word, o.case, x.subst | rename_here, upper_word (top-level `const name = literal` only), rename_all_subst |
| `member_expression` | m.find | find_char (`f.` before a property) |
| `import_statement`, class fields, one-line declarations and expression statements | x.copymove | move_line, copy_line |
| one-line `x = ...` declaration or assignment | o.change | change_to_end (`C X;` / `ct;X`, or `C X` when the line has no semicolon) |
| `program` (top level) | x.normal | prefix_each_line, upper_constants (`:norm f=bgUiw` over top-level constants) |
| (every line) | m.rel, m.find | goto_line_rel, find_char on `( ) { } [ ] ; , = . => :` |

Quotes follow the code: the drill is `ci'` on a single-quoted string, `ci"` on a
double-quoted one and ``ci` `` on a template string. Replacement strings use the string's
own quote. x.normal puts back a prefix shared by 3 or more consecutive lines (`const `,
`this.`, `private `, `readonly `, `export `, ...), or comments out statements in a function
body.

`js.WEIGHTS` holds the JS/TS column of the weight table in `model/skill-graph.md`; it is the
same for both languages. `js.JS_TARGET_SKILLS` has the 16 C++ skills other than t.angle.
`js.TS_TARGET_SKILLS` adds t.angle (generics). `tests/test_js.py` checks the weights against
`model/skill-graph.json` for `javascript` and `typescript`.

Verified counts with no per-skill cap (build cap 40 in brackets):

| skill | JavaScript | TypeScript | | skill | JavaScript | TypeScript |
|---|---|---|---|---|---|---|
| t.quote | 175 (40) | 138 (40) | | n.unmatched | 280 (40) | 202 (40) |
| t.paren | 978 (40) | 730 (40) | | o.delete | 337 (40) | 269 (40) |
| t.brace | 350 (40) | 233 (40) | | o.change | 416 (40) | 295 (40) |
| t.bracket | 182 (40) | 149 (40) | | o.indent | 314 (40) | 216 (40) |
| t.angle | - | 58 (40) | | o.case | 66 (40) | 44 (40) |
| t.word | 254 (40) | 167 (40) | | x.subst | 344 (40) | 281 (40) |
| m.find | 301 (40) | 244 (40) | | x.copymove | 419 (40) | 308 (40) |
| m.match | 456 (40) | 309 (40) | | x.normal | 78 (40) | 57 (40) |
| m.rel | 240 (40) | 169 (40) | | | | |

o.case is the thinnest skill. Most of its exercises uppercase a string (`gUi'`), because
exercism's JavaScript has few top-level constants that are used once in their window.

### Neovim indent

The oracle uses Neovim's own filetypes `javascript` and `typescript`, whose `indentexpr` is
`GetJavascriptIndent()` / `GetTypescriptIndent()`. In both, `o` after a line ending in `{`
indents one `shiftwidth`, and typing `}` at the start of a line dedents it. They differ
after a line that ends in a bare `=>`: `o` indents in JavaScript but not in TypeScript.
JavaScript's `indentkeys` also re-indent on `:` and `0#`; TypeScript's on `0,`.
