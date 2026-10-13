# Open questions

Collected from every plan doc. Each says when it must be answered and how.

## Blocking M2 (content)
All four resolved; see Resolved below.

## Blocking M3 exit (dogfood)
| question | from | resolve by |
|---|---|---|
| `target_ms` constants (`base` 1200, `per_key` 180 are first guesses) | 04 | measure the author over 20 skills in week 1 of dogfood |
| EMA alpha 0.1 vs 0.15 for shorter Vim sessions (kept at 0.1) | 04 | compare on the dogfood log |
| Active-skill count 4–7: variety or noise? | 04 | author judgement after 2 weeks |
| Implicit skill detection (credit `a.dot` when `.` is used well anywhere)? | 04 | decide after dogfood; default off |
| Focus domination: one weak skill takes about 70% of a session (m.find and m.rel took 13 to 14 of 15 exercises in every e2e run), and skills with weight 0.3 are almost never chosen. The interleave rule only breaks runs of 3 | 04, model README | change both model mirrors and regenerate `model/vectors`; decide after dogfood |
| A learner above 1.25x par never unlocks anything new (5 tier-0 skills stay active) | 04, model README | same change as above |
| Unlocking follows prerequisites, not the Switcher/Advanced track order, so tier 10 opens before tier 1 | 04, 02 | decide with the focus change |
| The review pass bar of 1.3x target time only catches large decay | 04 | dogfood log |
| Human review of exercises: none of the 587 is reviewed, and some read oddly (arguments replaced with `value`, an uppercased function name) | 03 | author runs `vimtrainer-content review`, or rejects as they go |

## Blocking M4 (breadth)
| question | from | resolve by |
|---|---|---|
| VSCodeVim and IdeaVim support for every `verify`/`partial` flag in 02. Not done: profiles use the flags in 02 unverified | 02 | scripted test in both editors; publish the matrix |
| Per-emulator profiles vs a single Switcher exclusion list | 02, 04 | decided by the matrix: if differences are few, one list |
| Measured per-language node frequencies to replace guessed weights | 02, 03 | emitted by the M2 build (`build/stats/node_frequency.json`); not yet applied to the weight table |
| CI content-check determinism: does Linux Neovim reproduce the macOS `build/` byte for byte? Two local builds with 8 and 2 jobs were identical | 03 | first GitHub Actions run; if not, add `-I` patterns or regenerate `build/` on Linux |
| `t.brace` has 27 exercises, the most Python yields | 03 | a second source (author's own code via `local =`) or brace-heavy languages in M4 |
| Exclusive-linewise rule patched only for `d}` and `d)`; `c}`, `y}`, `gU}` and searches as motions may differ from Neovim | 06 | extend `app/src/vimfixes.ts` if a user alternative needs it |
| Editor profile is saved but the TS model does not filter by it yet | 02 | call `applyProfile` per profile; the matrix above |
| Which plugin-dependent skills (surround, treesitter objects) belong in tier 12 | 02 | after launch feedback |

## Not blocking anything (decide when reached)
| question | from |
|---|---|
| Framework for the stats screen (none / Preact / Svelte) | 06 |
| Show a diff on passes as well as fails | 10 |
| Emacs evil-mode as a third emulator | 02 |
| FSRS replacing SM-2 | 04 |
| Teams/education offering | 07 |

## Added from dogfooding (2026-10-13)
| question | from | resolve by |
|---|---|---|
| Cross-skill idiom search in par_search | 11 | next content round; measure oracle time |
| Stability-gate metrics need a counter in the app (flag rate per 4 weeks) | 07 | flags now live on attempt records (round 3a), so the rate is a count over `model.log`; nothing displays it yet |

## Added 2026-10-13 (architecture)
| question | from | resolve by |
|---|---|---|
| ~~Placement per language (C++ users start with no placement)~~ | 04 | done in round 3c: the first switch to a new language opens its placement; `placementDone` is per language |
| Sticky mastery across languages: a C++ placement sample that *fails* on a skill mastered in Python leaves it mastered in C++ (n=1, review due at once), via `ensureSkill` carry-over. Pinned by vector 26 as current behaviour; is it intended, or should a failed placement sample demote the carried-over skill? | 04 | author decides after dogfooding C++ |
| Reading order and comments in app/ for a TypeScript newcomer | 0008 | started in round 3a (flag path in app/README.md); continue with each app change |

## Added in round 3a
| question | from | resolve by |
|---|---|---|
| Public feedback repo at soft launch: the `!` issue link targets the private main repo `daniel-m-campos/vim-trainer`, which outside testers cannot use | 11 | M5; one constant in `app/src/feedback.ts` |
| Is the ingest generalisation rule (counts to `{{k}}`, insert text to `{{text}}`) too loose or too strict? | 11, 0009 | after the first ingest runs on real exports |

## Resolved
- Command-done and mode-change hooks: unreliable alone, so a filtered microtask check reads state. 2026-10-11 (05).
- `<Esc>` blur: held in Chromium, Firefox and WebKit (headless) with a guard; `Tab` was the real risk. Real Safari and Firefox with a keyboard are untested. 2026-10-11 (05).
- `pynvim` vs `subprocess`: batch subprocess, 2.8 vs 3.35 ms per job. 2026-10-11 (03).
- `nvim_feedkeys` vs `nvim_input`: `nvim_feedkeys(keys, 'mtx')`. 2026-10-11 (03).
- Playwright vs jsdom: Playwright; jsdom not tried. 2026-10-11 (03, 06).
- Exercism licence: MIT confirmed for `exercism/python` at 6105f6d9, read at the pinned commit. 2026-10-11 (03).
- Grammar node names for Python: taken from tree-sitter-python 0.25. 2026-10-11 (03).
- `--clean` option set: nothing needed is disabled; documented option set in 03. 2026-10-11.
- vimhjkl par heuristics: not recorded, not reused.
- Commit `build/`: yes, with a CI diff check. 2026-10-11 (0004).
- Bundle fonts: no, Google Fonts with system fallbacks. 2026-10-11 (06).
- Pattern golf in `x.subst`: whole identifiers only. 2026-10-11 (03).
- Python tooling and Neovim oracle, recorded as ADRs 0002 and 0003; no payments in MVP, 0006.
- Lua vs Python for tooling: Python (author's language). 2026-10-11.
- Ads + $1 tier: rejected; free core + lifetime pro later. 2026-10-11 (07).
- Real Vim in the browser: no; codemirror-vim + headless Neovim oracle. 2026-10-11 (06).
- Gamification: none in v1. 2026-10-11 (10).
- copy_line/move_line were ex-kind and rejected `yyjp`; now edit-kind with normal-mode variants. 2026-10-13 (11).
- No charging until the stability gate in 07 is met. 2026-10-13.
- Server-side real Neovim vs browser emulator: emulator, with differential testing. 2026-10-13 (ADR 0008).
- Per-attempt `seq`, `beatPar`, `flag`; `!` flag picker; prefilled GitHub issue to the main repo for now. 2026-10-13, round 3a (11).
- `ingest` command: Neovim-verifies player pars, writes `idioms_learned.toml`, alternates and review queues. 2026-10-13, round 3a (11, ADR 0009).
- How we find emulator divergences: `difftest`, a seeded differential fuzzer (Neovim vs the app's editor) with a minimiser, `known.jsonl` and a nightly CI job. 2026-10-13, round 3b (12).
- Template kind audit: ex only where normal mode would be a repetition drill. 2026-10-13, round 3a (03).
