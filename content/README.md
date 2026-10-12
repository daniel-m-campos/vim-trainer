# content pipeline

The content pipeline turns real source code into verified Vim exercises. The design is in
`docs/plan/03-content-pipeline.md`, and the top-level `README.md` lists the make targets.

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

`cpp.WEIGHTS` holds the C/C++ column of the weight table in `02-skill-graph.md`.
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

`build.py` builds both languages: `build.LANGS` maps each language to its windowing,
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
