# Open questions

Collected from every plan doc. Each says when it must be answered and how.

## Blocking M1 (spikes)
| question | from | resolve by |
|---|---|---|
| Does codemirror-vim give a reliable command-done and mode-change signal? | 05, 06 | M1 spike 1 |
| Can `<Esc>` be captured without blurring the editor in Firefox/Safari? | 05, 10 | M1 spike 1 |
| `pynvim` RPC vs `subprocess` per batch for the oracle? `nvim_feedkeys` vs `nvim_input` determinism? | 03 | M1 spike 2 |
| Playwright vs jsdom for the emulator oracle? | 03, 06 | M1 spike 2 |

## Blocking M2 (content)
| question | from | resolve by |
|---|---|---|
| Exercism track licences: confirm MIT per track used | 03 | check LICENSE at pinned commit, record in sources allowlist |
| Grammar node names per language (`string` vs `string_literal`) | 03 | read each grammar's `node-types.json` when writing its mapping |
| Does `--clean` disable anything exercises need (`filetype` for `gcc`)? | 03 | test in spike 2; document the option set |
| Reuse vimhjkl's par and buffer-sizing heuristics? | 03 | read its source (MIT) during M2 |

## Blocking M3 (model)
| question | from | resolve by |
|---|---|---|
| `target_ms` constants (`base`, `per_key`) | 04 | measure the author over 20 skills in week 1 of dogfood |
| EMA alpha 0.1 vs 0.15 for shorter Vim sessions | 04 | compare on the dogfood log |
| Active-skill count 4–7: variety or noise? | 04 | author judgement after 2 weeks |
| Implicit skill detection (credit `a.dot` when `.` is used well anywhere)? | 04 | decide after dogfood; default off |

## Blocking M4 (breadth)
| question | from | resolve by |
|---|---|---|
| VSCodeVim and IdeaVim support for every `verify`/`partial` flag in 02 | 02 | scripted test in both editors; publish the matrix |
| Per-emulator profiles vs a single Switcher exclusion list | 02, 04 | decided by the matrix: if differences are few, one list |
| Measured per-language node frequencies to replace guessed weights | 02, 03 | emitted by the M2 build |
| Which plugin-dependent skills (surround, treesitter objects) belong in tier 12 | 02 | after launch feedback |

## Not blocking anything (decide when reached)
| question | from |
|---|---|
| Framework for the stats screen (none / Preact / Svelte) | 06 |
| Commit `build/` or generate on deploy | 06 |
| Bundle one monospace font or rely on system fonts | 10 |
| Show a diff on passes as well as fails | 10 |
| Emacs evil-mode as a third emulator | 02 |
| FSRS replacing SM-2 | 04 |
| Teams/education offering | 07 |

## Resolved
- Lua vs Python for tooling: Python (author's language). 2026-10-11.
- Ads + $1 tier: rejected; free core + lifetime pro later. 2026-10-11 (07).
- Real Vim in the browser: no; codemirror-vim + headless Neovim oracle. 2026-10-11 (06).
- Gamification: none in v1. 2026-10-11 (10).
