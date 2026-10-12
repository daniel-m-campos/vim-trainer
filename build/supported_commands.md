# Supported commands

Command shapes used by canonical solutions, verified in nvim 0.12.5.
Inserted text is shown as `{text}`, counts as `N`.
Browser (codemirror-vim) verification: `make content` replays every par in the app's editor
and records `emulator.web` per exercise (see stats/emulator_web.json).
VSCodeVim and IdeaVim verification is not done yet: TODO(mvp).

| skill | command shape | exercises |
|---|---|---|
| a.dot | `*cgn{new}<Esc>..` | 16 |
| a.dot | `*cgn{new}<Esc>...` | 12 |
| a.dot | `*cgn{new}<Esc>.....` | 4 |
| a.dot | `*cgn{new}<Esc>.......` | 3 |
| a.dot | `*cgn{new}<Esc>....` | 3 |
| a.dot | `*cgn{new}<Esc>......` | 2 |
| a.macro | `qaf=Wi{text}(<Esc>A)<Esc>+qN@a` | 20 |
| m.find | `f.` | 25 |
| m.find | `f(` | 15 |
| m.find | `f,` | 9 |
| m.find | `f=lcw{text}<Esc>` | 8 |
| m.find | `f=` | 4 |
| m.find | `f{` | 4 |
| m.find | `f:` | 3 |
| m.find | `Nf=lcw{text}<Esc>` | 3 |
| m.find | `f[` | 2 |
| m.find | `f)` | 2 |
| m.find | `f<` | 2 |
| m.find | `Nf:` | 1 |
| m.find | `f=lct){text}<Esc>` | 1 |
| m.find | `f>` | 1 |
| m.match | `%` | 80 |
| m.rel | `Nj` | 43 |
| m.rel | `Nk` | 37 |
| n.unmatched | `])` | 35 |
| n.unmatched | `[{` | 19 |
| n.unmatched | `]}` | 18 |
| n.unmatched | `[(` | 8 |
| o.case | `gUiw` | 39 |
| o.case | `gUi"` | 24 |
| o.case | `gUi'` | 14 |
| o.case | `guiw` | 3 |
| o.change | `f,wcw{text}<Esc>` | 29 |
| o.change | `C{text}<Esc>` | 20 |
| o.change | `C{text};<Esc>` | 19 |
| o.change | `f,wct){text}<Esc>` | 7 |
| o.change | `cw{text}<Esc>` | 3 |
| o.change | `Nf,wcw{text}<Esc>` | 2 |
| o.delete | `d}` | 35 |
| o.delete | `Ndd` | 22 |
| o.delete | `f#D` | 15 |
| o.delete | `dG` | 4 |
| o.delete | `dNj` | 2 |
| o.delete | `f/D` | 2 |
| o.indent | `<i{` | 25 |
| o.indent | `>i{` | 15 |
| o.indent | `>}` | 12 |
| o.indent | `<}` | 11 |
| o.indent | `N>>` | 6 |
| o.indent | `<G` | 6 |
| o.indent | `N<<` | 4 |
| o.indent | `>G` | 1 |
| o.join | `J` | 31 |
| o.join | `NJ` | 9 |
| o.number | `N<C-a>` | 24 |
| o.number | `{new}<C-a>` | 14 |
| o.number | `N<C-x>` | 2 |
| o.put | `yykP` | 32 |
| o.put | `yyNkP` | 8 |
| o.yank | `yyp` | 32 |
| o.yank | `yyjp` | 5 |
| o.yank | `yyNjp` | 3 |
| t.angle | `ci<{text}<Esc>` | 20 |
| t.angle | `di<` | 20 |
| t.brace | `ci{{text}<Esc>` | 37 |
| t.brace | `di{` | 28 |
| t.bracket | `di[` | 37 |
| t.bracket | `ci[{text}<Esc>` | 20 |
| t.bracket | `da[` | 10 |
| t.para | `dap` | 40 |
| t.paren | `di(` | 33 |
| t.paren | `ci({text}<Esc>` | 31 |
| t.paren | `da(` | 16 |
| t.quote | `di'` | 22 |
| t.quote | `ci"{text}<Esc>` | 21 |
| t.quote | `di"` | 21 |
| t.quote | `ci'{text}<Esc>` | 16 |
| t.word | `ciw{text}<Esc>` | 80 |
| v.blockedit | `<C-v>NjI{text}<Esc>` | 18 |
| v.blockedit | `<C-v>Nj$A{text}<Esc>` | 11 |
| x.copymove | `:mN<CR>` | 23 |
| x.copymove | `:t.<CR>` | 16 |
| x.copymove | `:tN<CR>` | 13 |
| x.copymove | `:m+N<CR>` | 9 |
| x.copymove | `:m-N<CR>` | 9 |
| x.copymove | `:t+N<CR>` | 7 |
| x.copymove | `:t-N<CR>` | 3 |
| x.global | `:g/^$/d<CR>` | 14 |
| x.global | `:v/def/d<CR>` | 7 |
| x.global | `:v/ret/d<CR>` | 7 |
| x.global | `:v/de/d<CR>` | 4 |
| x.global | `:v/re/d<CR>` | 2 |
| x.global | `:g/#/d<CR>` | 2 |
| x.global | `:g/^ *#/d<CR>` | 2 |
| x.global | `:g/"/d<CR>` | 2 |
| x.lastsearch | `*cgn{new}<Esc>..` | 17 |
| x.lastsearch | `*cgn{new}<Esc>...` | 11 |
| x.lastsearch | `*cgn{new}<Esc>....` | 6 |
| x.lastsearch | `*cgn{new}<Esc>.....` | 3 |
| x.lastsearch | `*cgn{new}<Esc>.......` | 3 |
| x.normal | `VNj:norm gUe<CR>` | 4 |
| x.normal | `VNj:norm I{text}<CR>` | 3 |
| x.normal | `VNj:norm ^gUe<CR>` | 1 |
| x.subst | `:%s/{old}/{new}<CR>` | 36 |
| x.subst | `:%s/{old}/{new}/g<CR>` | 20 |
| x.subst | `:%s/\<{old}/{new}<CR>` | 9 |
| x.subst | `:%s/{old}\>/{new}/g<CR>` | 7 |
| x.subst | `:%s/{old}\>/{new}<CR>` | 4 |
| x.subst | `:%s/\<{old}\>/{new}/g<CR>` | 3 |
| x.subst | `:%s/\<{old}/{new}/g<CR>` | 1 |
