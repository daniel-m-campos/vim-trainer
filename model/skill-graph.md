# Skill graph data

This file is the source of `model/skill-graph.json` and `app/src/model/skill-graph.json`.
Edit the tables here, then regenerate both with `uv run --project model python model/gen_graph.py`.
Emulator column: support in VSCodeVim (VSC) and IdeaVim (IJ); weights: 1.0 normal, 0 skip, 1.5 emphasise.

## Tier 0 — Foundations (assumed; placement test confirms)

| id | keys | what it is | emulator |
|---|---|---|---|
| f.modes | `i a I A o O Esc` | enter insert at cursor / after / line start / line end / new line below / above | full |
| f.hjkl | `h j k l` | basic movement | full |
| f.undo | `u Ctrl-r` | undo, redo | full |
| f.xdd | `x dd yy p P` | delete char, delete line, yank line, paste after/before | full |
| f.save | `:w :q :wq` | write, quit | full |

## Tier 1 — Horizontal motions

| id | keys | what it is | prereqs | emulator |
|---|---|---|---|---|
| m.word | `w b e ge` | next word start, prev word start, word end, prev word end | f.hjkl | full |
| m.WORD | `W B E` | same, but whitespace-delimited (skips punctuation) | m.word | full |
| m.line | `0 ^ $` | line start, first non-blank, line end | f.hjkl | full |
| m.find | `f F t T` | jump to / till a character forward or back, on the current line | m.line | full |
| m.repeatfind | `; ,` | repeat last f/t forward or back | m.find | full |
| m.count | `3w 5l 2f,` | counts prefix any motion | m.word | full |

## Tier 2 — Vertical and file motions

| id | keys | what it is | prereqs | emulator |
|---|---|---|---|---|
| m.file | `gg G 42G :42` | file start, end, line N | f.hjkl | full |
| m.para | `{ }` | previous / next blank line (paragraph) | f.hjkl | full |
| m.rel | `5j 12k` | relative line jumps, with `relativenumber` on | m.count | full |
| m.screen | `Ctrl-d Ctrl-u Ctrl-f Ctrl-b` | half-page / page scroll | f.hjkl | full |
| m.screenpos | `H M L zz zt zb` | cursor to screen top/middle/bottom; scroll line to centre/top/bottom | m.screen | full |
| m.match | `%` | jump to matching bracket | f.hjkl | full (VSC has edge cases) |
| m.search | `/ ? n N` | search forward/back, next/prev match | f.hjkl | full |
| m.star | `* #` | search word under cursor forward/back | m.search | full |
| m.sentence | `( )` | sentence motions (prose, comments, docs) | m.para | full |

## Tier 3 — Operators (the verbs)

| id | keys | what it is | prereqs | emulator |
|---|---|---|---|---|
| o.delete | `d{motion} D dd` | delete; `D` to end of line | m.word m.line | full |
| o.change | `c{motion} C cc S s` | delete then insert; `C` to end of line; `s` one char | o.delete | full |
| o.yank | `y{motion} Y yy` | copy into a register | o.delete | full |
| o.put | `p P ]p` | paste after/before, with indent | o.yank | full (`]p` verify) |
| o.dot | `.` | repeat the last change | o.change | full |
| o.indent | `>> << >{motion} ={motion} ==` | shift and auto-indent | o.delete | full |
| o.case | `~ g~ gu gU gUiw guu` | toggle / lower / upper case | o.delete | full |
| o.join | `J gJ` | join lines with / without space | o.delete | full |
| o.replace | `r R` | replace one char / enter replace mode | f.modes | full |
| o.number | `Ctrl-a Ctrl-x 5Ctrl-a` | increment / decrement number under cursor | m.count | full |
| o.filter | `!{motion}cmd` `:.!cmd` | pipe lines through a shell command | o.delete | none in VSC; IJ verify |

## Tier 4 — Text objects (the nouns)

| id | keys | what it is | prereqs | emulator |
|---|---|---|---|---|
| t.word | `iw aw iW aW` | inner / a word | o.change | full |
| t.quote | `i" a" i' a' i\` a\`` | inside / around quotes | o.change | full |
| t.paren | `i( a( ib ab i) a)` | inside / around parentheses | m.match | full |
| t.bracket | `i[ a[ i] a]` | square brackets | t.paren | full |
| t.brace | `i{ a{ iB aB i} a}` | curly braces / blocks | t.paren | full |
| t.angle | `i< a<` | angle brackets (generics, HTML) | t.paren | full |
| t.tag | `it at` | XML/HTML tag contents / whole tag | t.brace | full (JSX verify) |
| t.para | `ip ap` | paragraph | m.para | full |
| t.sentence | `is as` | sentence | m.sentence | full |
| t.compose | `ci" da( yap cit >ip` | operator + text object fluency | all of tier 4 | full |

## Tier 5 — Visual modes

| id | keys | what it is | prereqs | emulator |
|---|---|---|---|---|
| v.char | `v` + motions + operator | character-wise selection | o.delete | full |
| v.line | `V` | line-wise selection | v.char | full |
| v.block | `Ctrl-v` | column selection | v.line | full |
| v.blockedit | `Ctrl-v` then `I A c $ r` | insert/append/change on every line of a block | v.block | full (VSC `$A` verify) |
| v.objects | `viw vi( vip` | select by text object | t.compose | full |
| v.reselect | `gv o` | reselect last visual; swap selection end | v.char | full |
| v.ops | `> < = u U J ~ :` on selection | operators on a selection | v.char | full |

## Tier 6 — Registers

| id | keys | what it is | prereqs | emulator |
|---|---|---|---|---|
| r.named | `"ayy "ap "Ayy` | yank/put to a named register; uppercase appends | o.yank | full |
| r.yank0 | `"0p` | the yank register survives deletes | r.named | full |
| r.numbered | `"1p "2p` and `"1p...` | last deletes, 1–9 | r.named | partial (verify) |
| r.blackhole | `"_d` | delete without touching registers | r.named | full |
| r.system | `"+y "+p "*y` | system clipboard | r.named | full |
| r.insert | `Ctrl-r a` in insert mode and `:` | paste a register while typing | r.named | full |
| r.view | `:reg :reg a` | inspect registers | r.named | full |

## Tier 7 — Search, replace and Ex ranges

| id | keys | what it is | prereqs | emulator |
|---|---|---|---|---|
| x.subst | `:s/a/b/ :%s/a/b/g` flags `g c i e` | substitute | m.search | full |
| x.substrange | `:'<,'>s :5,20s :.,$s :.,+3s` | ranges | x.subst | full |
| x.regex | `\< \> \( \) \1 & \= .* \s \d` | Vim regex essentials | x.subst | full |
| x.lastsearch | `/foo` then `:%s//bar/` and `cgn` + `.` | reuse the search pattern; change-next-match repeatable | x.subst o.dot | `gn` verify in VSC |
| x.global | `:g/pat/d :g/pat/normal A;` `:v/pat/d` | run a command on matching lines | x.subst | partial (VSC verify); IJ full |
| x.normal | `:normal` `:'<,'>normal .` | run normal-mode keys over a range | x.global | VSC partial, IJ full |
| x.copymove | `:t :m :t. :m+1 :m'<-2` | copy / move lines | x.substrange | full |
| x.cmdline | `Ctrl-r Ctrl-w` `q:` `@:` `Ctrl-f` in `:` | insert word under cursor, command history, repeat last Ex | x.subst | partial |

## Tier 8 — Repetition and automation

| id | keys | what it is | prereqs | emulator |
|---|---|---|---|---|
| a.dot | deliberate `.` patterns: `cw` + `n.`, `A;` + `j.` | design edits to be repeatable | o.dot | full |
| a.macro | `qa ... q` `@a` `@@` `5@a` | record and replay | r.named | full |
| a.macrorange | `:'<,'>normal @a` | macro over a range | a.macro x.normal | VSC partial |
| a.macroedit | `"ap` edit `"ayy` | paste, fix and re-yank a macro | a.macro | full |
| a.recursive | `qaq` then `qa ... @a q` | recursive macro to end of file | a.macro | full |

## Tier 9 — Marks, jumps and structural navigation

| id | keys | what it is | prereqs | emulator |
|---|---|---|---|---|
| n.marks | `ma 'a \`a` | set / jump to a mark (line / exact) | m.file | full |
| n.autmarks | `'' \`\` '. \`. '^` | last jump, last change, last insert | n.marks | partial |
| n.jumplist | `Ctrl-o Ctrl-i` | jump back / forward | m.search | full |
| n.changelist | `g; g,` | previous / next change position | n.jumplist | verify |
| n.lastinsert | `gi` | insert where you last inserted | n.autmarks | full |
| n.unmatched | `[{ ]} [( ])` | enclosing bracket | m.match | full |
| n.section | `[[ ]] [m ]m` | section / method starts (brace languages) | m.para | partial |
| n.folds | `zo zc za zR zM zj zk` | open / close / toggle folds | m.file | partial |

## Tier 10 — Insert-mode efficiency

| id | keys | what it is | prereqs | emulator |
|---|---|---|---|---|
| i.delete | `Ctrl-w Ctrl-u Ctrl-h` | delete word / to line start / char without leaving insert | f.modes | full |
| i.oneshot | `Ctrl-o {cmd}` | run one normal command, stay in insert | f.modes | full |
| i.register | `Ctrl-r "` `Ctrl-r 0` | paste a register | r.named | full |
| i.indent | `Ctrl-t Ctrl-d` | indent / dedent current line | f.modes | full |
| i.complete | `Ctrl-n Ctrl-p` | keyword completion | f.modes | partial (editor completion takes over) |
| i.escape | `Ctrl-[` `Ctrl-c` and `jk`-style maps | leave insert without reaching for Esc | f.modes | full |
| i.last | `Ctrl-a` `Ctrl-@` | re-insert last inserted text | f.modes | verify |

## Tier 11 — Buffers, windows and files (editor-dependent)

| id | keys | what it is | prereqs | emulator |
|---|---|---|---|---|
| w.split | `:sp :vs Ctrl-w s v` | split windows | f.save | full (maps to editor splits) |
| w.move | `Ctrl-w h j k l w p c o` | move between / close windows | w.split | full |
| w.buffers | `:ls :b N :bn :bp :bd Ctrl-^` | buffer list and switching | f.save | partial |
| w.tabs | `:tabnew gt gT` | tab pages | w.split | partial |
| w.args | `:args :argdo` | multi-file operations | x.global | none in VSC |
| w.quickfix | `:copen ]q [q :cdo` | quickfix navigation | x.global | none in VSC |

## Tier 12 — Neovim-native (real Neovim only)

| id | keys | what it is | prereqs |
|---|---|---|---|
| nv.lsp | `grn gra grr gri gd K Ctrl-]` | default LSP maps (0.11+) | w.quickfix |
| nv.diag | `]d [d Ctrl-w d` | diagnostics | nv.lsp |
| nv.comment | `gcc gc{motion}` | built-in commenting (0.10+) | o.delete |
| nv.treesitter | `af if ac ic` via mini.ai / textobjects | syntax-aware text objects (plugin) | t.compose |

## Per-language weights

| skill group | Lua | Python | JS/TS | Java/C# | C/C++ | Go | Rust | HTML/JSX | JSON/YAML | Markdown |
|---|---|---|---|---|---|---|---|---|---|---|
| m.match, t.brace, n.unmatched | 1.2 | 0.3 | 1.5 | 1.5 | 1.5 | 1.5 | 1.5 | 1.0 | 1.5 | 0.2 |
| t.paren (calls, args) | 1.2 | 1.5 | 1.5 | 1.5 | 1.5 | 1.5 | 1.5 | 0.5 | 0.2 | 0.2 |
| t.bracket | 0.8 | 1.5 | 1.5 | 1.2 | 1.2 | 1.2 | 1.2 | 0.3 | 1.5 | 1.0 |
| t.quote | 1.5 | 1.5 | 1.5 | 1.2 | 1.0 | 1.2 | 1.2 | 1.5 | 1.5 | 0.5 |
| t.angle | 0 | 0 | 1.0 (TS generics) | 1.5 | 1.5 | 0.3 | 1.5 | 1.0 | 0 | 0 |
| t.tag | 0 | 0 | 1.2 (JSX) | 0.3 | 0 | 0.3 | 0 | 1.5 | 0 | 0.5 |
| t.para, m.para | 1.0 | 1.5 | 1.0 | 0.8 | 0.8 | 1.0 | 0.8 | 0.5 | 0.5 | 1.5 |
| t.sentence, m.sentence | 0.2 | 0.3 | 0.2 | 0.2 | 0.2 | 0.2 | 0.2 | 0.5 | 0 | 1.5 |
| o.indent | 1.0 | 1.5 | 1.0 | 1.0 | 1.0 | 0.5 (gofmt) | 0.8 | 1.0 | 1.2 | 0.5 |
| m.find on punctuation | 1.0 | 1.2 (`:` `,` `=`) | 1.5 (`(` `=` `.` `;`) | 1.5 | 1.5 | 1.2 | 1.5 | 1.2 (`<` `>` `=`) | 1.2 (`:` `"`) | 0.5 |
| v.block | 0.8 | 0.8 | 1.0 | 1.2 | 1.2 | 1.0 | 1.0 | 0.8 | 1.5 | 1.0 |
| x.subst, x.global | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.5 | 1.5 |
| o.number | 0.5 | 0.8 | 0.8 | 0.8 | 1.0 | 0.8 | 0.8 | 0.5 | 1.2 | 1.0 |
| n.section (`[[ ]]`) | 0.3 | 0 | 0.5 | 1.2 | 1.5 | 1.2 | 1.0 | 0 | 0 | 0 |
| comment edits (`f-D`, `f#D`, `f/D`, `gc`) | 1.0 (`--`) | 1.0 (`#`) | 1.0 (`//`) | 1.0 | 1.0 | 1.0 | 1.0 | 0.5 | 0.5 (`#`) | 0 |
