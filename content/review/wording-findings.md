# Task wording review (Python corpus)

Sample: 150 exercises drawn with `random.seed(1)` from the 587 in
`build/exercises/python` (committed build, before this change). Every template that
produced an exercise is in the sample. "After" is what the fixed template now writes for
the same window and target (`content/.cache/scratch-templates/beforeafter.py` regenerates
the table).

The fixes are in `content/src/vimtrainer_content/templates.py`. They change the
generators, not individual exercises, so every rebuilt exercise gets them.

## Findings by root cause

### 1. Replacement text did not fit the node (change_inner, change_nth_arg, change_kwarg_value, change_to_end)

Replacements came from one fixed list per node type, so a string argument could become
`x + 1`, a parameter list could become `self`, and many tasks read "to `value`". 26 of the
150 sampled tasks had this problem, counting change_nth_arg.

Fix: the new `_fit_value` picks text of the same kind as the node it replaces:

- a string gets another string with the same quotes. It is a word (`unknown`, `pending`)
  when the original is one word, a message (`not found`, `out of range`) when it has
  spaces, and a format string when it has `%s`.
- a number gets a number.
- an identifier gets a fresh name with the same role and case style (see 2).
- `self.x` gets `self.<new name>`.
- a literal list, dict or call on the right-hand side gets `[]`, `{}` or `None`.

`_inner_text` swaps the items of argument lists, tuples and parameter lists that hold two
or more items: it is a plausible edit and every character still has to be typed. A
single item gets a value that fits it. Regex-looking strings are skipped for
change_inner, because "change this regex to `skipped`" is not a real edit. An f-string
field is changed only when it holds a name or an attribute, and an attribute field
(`{self.numer}`) gets a bare name: `self.x` to `self.y` changes so few characters that
the anti-shortcut gate rejects it.

| before | after |
|---|---|
| Change the contents of this parameter list `(index, list_obj)` to `value` | Change the contents of the parameter list `(index, list_obj)` to `list_obj, index` |
| Change the contents of this parameter list `(year, month, week, day_of_week)` to `self` | ... to `day_of_week, week, month, year` |
| Change the contents of this parameter list `(number, dice)` to `*args, **kwargs` | ... to `dice, number` |
| Change the contents of this argument list `(digit_set, total_count)` to `x + 1` | ... to `total_count, digit_set` |
| Change the contents of this f-string field `{self.numer}` to `count:>3` | ... to `result` |
| Change the contents of this f-string field `{self.subscriber_number}` to `value!r` | ... to `count` |
| Change the contents of this string `'Englishman'` to `retrying` | ... to `unknown` |
| Change the contents of this string `'frame less than 10'` to `unknown` | ... to `out of range` |
| Change the contents of this string `'^([^aeiou]?qu\|[^aeiouy]+\|y(?=[aeiou]...` to `skipped` | not generated (regex) |
| Change the contents of this subscript `minefield[index1 - 1][low:high]` to `0` | ... to `::2` (a slice stays a slice) |
| Change the 2nd argument of `wrap(...)` from `'li'` to `x + 1` | Change the second argument of `wrap(...)` from `'li'` to `'missing'` |
| Change the 2nd argument of `re.sub(...)` from `''` to `self.items` | ... from `''` to `'skipped'` |
| Change the 2nd argument of `tree_from_traversals(...)` from `right_inorder` to `*args` | ... to `entry` |
| Change the 2nd argument of `count_neighbors(...)` from `c` to `*args` | ... to `entry` |
| Change the value of `children=` from `children` to `'utf-8'` | ... to `result` |
| Replace the value assigned to `self.y_coordinate` with `{}` | Replace the value assigned to `self.y_coordinate` with `data` (the old value is a name) |
| Replace the value assigned to `self.dexterity` with `len(items)` | ... with `None` |

### 2. New names ignored the old name's role and case style (rename_here, rename_all_subst)

One list of nouns was used for every rename. Constants became lowercase (`OCR_LIST` to
`entry`, `ALPHA_LEN` to `current`), functions became nouns (`add_missing_stops` to
`text`), and collections became counts (`list_two` to `size`).

Fix: `_new_name` now uses `_role`. A function or call target gets a verb (`process`,
`compute`, `load`). A class gets a class noun. A name ending in a collection word or a
plural gets a plural (`items`, `entries`). A count, index or text name gets a name of
the same kind. Then `_styled` writes the new name in the old name's case style
(UPPER_CASE, CamelCase, camelCase, snake_case, leading underscores). Python builtins
and dunders are never renamed, by any template.

A pure case-style variant of the original (`right_half` to `rightHalf`) was tried and
rejected: it changes only a few characters, so the anti-shortcut gate (gate 5) rejects
nearly every such exercise, because `x` and `i` beat `ciw` there.

| before | after |
|---|---|
| Rename this `OCR_LIST` to `entry` (only this one) | Rename the `OCR_LIST` under the cursor to `PARTS` (only this one) |
| Rename this `__init__` to `letters` (only this one) | not generated (dunder) |
| Rename this `add_missing_stops` to `text` (only this one) | ... to `load` |
| Rename this `search_list` to `entry` (only this one) | ... to `names` |
| Rename this `unique_chars` to `item` (only this one) | ... to `entries` |
| Rename every `ALPHA_LEN` to `current` (3 occurrences) | Rename every `ALPHA_LEN` to `LIMIT` (3 occurrences) |
| Rename every `sorted` to `buffer` (4 occurrences) | not generated (builtin) |
| Rename every `number` to `letters` (8 occurrences) | Rename every `number` to `offset` (8 occurrences) |
| Rename every `line` to `target` (3 occurrences) | Rename every `line` to `message` (3 occurrences) |

The word "this" was ambiguous: the cursor could be on any occurrence of the name. The
task now says "the `x` under the cursor".

### 3. Uppercasing function names (upper_word)

"Uppercase the identifier `parse_line` under the cursor" (and `get_value_of_bills`)
asks for an edit nobody makes. Fix: names of functions, classes, call targets,
attributes and modules (`typing` in `typing.List`) are no longer uppercased. The task now says why and shows the result:

| before | after |
|---|---|
| Uppercase the identifier `parse_line` under the cursor | not generated (function name) |
| Uppercase the identifier `choice` under the cursor | not generated (attribute of `random`) |
| Lowercase the identifier `LITTLE_STRAIGHT` under the cursor | Lowercase the constant name `LITTLE_STRAIGHT` to `little_straight` |
| (new, from the scratch build) | Make `start_date` a constant name: uppercase it to `START_DATE` |

### 4. Delimiters written as literal characters (delete_inner)

"keeping the ''", "keeping the ()" and "keeping the {}" read as typos. 14 of 150 tasks
were affected. They now name the delimiters:

| before | after |
|---|---|
| Delete everything inside this string `'abundant'`, keeping the '' | Delete everything inside the string `'abundant'`, keeping the quotes |
| Delete everything inside this tuple `(True, int(input_data))`, keeping the () | ... keeping the parentheses |
| Delete everything inside this dict `{'users': [...]}`, keeping the {} | ... keeping the braces |

The tasks also say "the string `'abundant'`" when the node is quoted and "this string"
only when it is not (the highlight shows it).

### 5. "1st" ordinals (find_char, change_nth_arg)

"Move to the 1st `(` on this line" (10 of 12 find_char samples) now reads "Move to the
first `(` on this line". `ordinal()` returns words up to "ninth".

### 6. Nested backticks in quoted lines (move_line, copy_line, goto_line_rel)

"Move this line above `"""Generates all palindromes with `nd` number...`" has a quote
inside a quote, which breaks the rendered task and the destination gate. Destination
lines that contain a backtick are no longer offered. goto_line_rel drops the quote in
that case and says only "the highlighted line".

goto_line_rel also wrote "Move the cursor to the highlighted line `x` (the highlighted
one)" for duplicated lines. It now says just "Move the cursor to the highlighted line".

### 7. Calls to builtins turned into bare names (delete_around)

"Turn the call `len(...)` into the bare name `len`" (also `int`, `round`, `sorted`).
Nobody edits code that way. Fix: builtins are skipped. A user function becoming a bare
name, for example to pass it as a callback, is still drilled.

## Not changed (fine as is)

- indent_block, jump_match, jump_block_end, delete_lines, delete_trailing_comment,
  upper_inner, copy_line and move_line read well.
- goto_line_rel quotes long lines clipped with "...". The highlight carries the target,
  so the clip does no harm.

## Counted

84 of the 150 sampled tasks changed text or are no longer generated:

- 26 replacement texts (cause 1). 6 of them are change_nth_arg tasks that also had an
  ordinal.
- 22 rename tasks (cause 2): a new name, plus "this" replaced by "under the cursor".
- 4 case tasks (cause 3).
- 14 delimiter phrases (cause 4).
- 12 find_char ordinals (cause 5).
- 1 nested quote (cause 6).
- 5 delete_around calls to builtins (cause 7).

The other 66 read well and are unchanged. Most of them are indent_block, jump_*,
delete_lines, goto_line_rel, copy_line and move_line.

## Effect on the corpus (scratch build, same 15 skills)

The scratch build is `content/.cache/scratch-templates/build`, built with
`--offline --skills ...`. Every one of the 15 original skills still reaches the cap of
40 except t.brace, which has 25 (27 before). It lost change_inner on f-string fields
that held calls and gained 4 multi-line `di{` exercises from delete_block.

## Round 3: x.normal in C++ and the kind audit (new task texts)

Read from a scratch build of all skills (`content/.cache/scratch-3a`): 34 C++ and 23
Python x.normal exercises.

- C++ `prefix_each_line` has two task texts. "Put `const` back at the start of each of
  these N lines" restores a prefix that the source lines share. "Comment out these N
  lines: put `// ` at the start of each" covers runs with no shared prefix. The `// ` in
  backticks carries a trailing space, and a Markdown renderer may trim it. The highlight
  and the expect still show the space. Open question: add "(with a space)" if players
  miss it.
- 27 of the 34 C++ x.normal exercises are comment-out drills. Restoring `std::` is not
  generated. In a C++ buffer, typing `std:` at the start of a line re-indents the line as
  a label (cinkeys), so `:norm Istd::` does not give back the source line.
- C++ `upper_constants` reads "Uppercase the names of these N constants" for const and
  constexpr declarations (`:norm f=bgUe`). For enums it reads "... these N enumerators"
  (`:norm ^gUe`). The Python text ("Turn these N assignments into constants") is
  unchanged.
- `rename_all_subst` with 3 occurrences is now kind "edit". Its task text stays "Rename
  every `x` to `y` (3 occurrences)". The text does not name `:s`, which fits a drill that
  also accepts `/\<x\><CR>cgny<Esc>..`.
