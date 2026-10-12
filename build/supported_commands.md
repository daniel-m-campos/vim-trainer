# Supported commands

Command shapes used by canonical solutions, verified in nvim 0.12.5 2026-10-11.
Inserted text is shown as `{text}`, counts as `N`.
Browser (codemirror-vim) verification: `make content` replays every par in the app's editor
and records `emulator.web` per exercise (see stats/emulator_web.json).
VSCodeVim and IdeaVim verification is not done yet: TODO(mvp).

| skill | command shape | exercises |
|---|---|---|
| m.find | `f(` | 16 |
| m.find | `f,` | 8 |
| m.find | `f=` | 4 |
| m.find | `f[` | 4 |
| m.find | `f.` | 3 |
| m.find | `f)` | 2 |
| m.find | `f:` | 2 |
| m.find | `Nf:` | 1 |
| m.match | `%` | 40 |
| m.rel | `Nj` | 22 |
| m.rel | `Nk` | 18 |
| n.unmatched | `])` | 24 |
| n.unmatched | `[(` | 8 |
| n.unmatched | `[{` | 4 |
| n.unmatched | `]}` | 4 |
| o.case | `gUiw` | 19 |
| o.case | `gUi'` | 14 |
| o.case | `gUi"` | 4 |
| o.case | `guiw` | 3 |
| o.change | `C{text}<Esc>` | 19 |
| o.change | `f,wcw{text}<Esc>` | 14 |
| o.change | `f,wct){text}<Esc>` | 3 |
| o.change | `cw{text}<Esc>` | 3 |
| o.change | `f,wct,{text}<Esc>` | 1 |
| o.delete | `f#D` | 15 |
| o.delete | `d}` | 13 |
| o.delete | `Ndd` | 7 |
| o.delete | `dG` | 3 |
| o.delete | `dNj` | 2 |
| o.indent | `>}` | 12 |
| o.indent | `<}` | 11 |
| o.indent | `N>>` | 6 |
| o.indent | `<G` | 6 |
| o.indent | `N<<` | 4 |
| o.indent | `>G` | 1 |
| t.brace | `ci{{text}<Esc>` | 23 |
| t.brace | `di{` | 4 |
| t.bracket | `di[` | 19 |
| t.bracket | `da[` | 13 |
| t.bracket | `ci[{text}<Esc>` | 8 |
| t.paren | `da(` | 16 |
| t.paren | `di(` | 12 |
| t.paren | `ci({text}<Esc>` | 12 |
| t.quote | `di'` | 23 |
| t.quote | `ci'{text}<Esc>` | 16 |
| t.quote | `di"` | 1 |
| t.word | `ciw{text}<Esc>` | 40 |
| x.copymove | `:mN<CR>` | 10 |
| x.copymove | `:tN<CR>` | 9 |
| x.copymove | `:t.<CR>` | 7 |
| x.copymove | `:m-N<CR>` | 7 |
| x.copymove | `:t+N<CR>` | 3 |
| x.copymove | `:m+N<CR>` | 3 |
| x.copymove | `:t-N<CR>` | 1 |
| x.subst | `:%s/{old}/{new}<CR>` | 21 |
| x.subst | `:%s/{old}/{new}/g<CR>` | 12 |
| x.subst | `:%s/\<{old}\>/{new}/g<CR>` | 2 |
| x.subst | `:%s/{old}\>/{new}/g<CR>` | 2 |
| x.subst | `:%s/{new}s/{new}<CR>` | 1 |
| x.subst | `:%s/\<{old}\>/{new}<CR>` | 1 |
| x.subst | `:%s/{old}\>/{new}<CR>` | 1 |
