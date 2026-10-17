# QA findings

On 2026-10-13 a QA pass played the app against a local build in eight sessions, each
focused on one area: import and export, text objects, hjkl-heavy play, macros, random
clicking and key mashing, C++ content, and the wording of Python and C++ tasks. They
reported 55 findings. The first 12 were re-checked against the browser, the source or the
exercise JSON. This page keeps the technical record: what broke, what was fixed, and
what is still open. The finding numbers are cited from other design docs and ADRs.

## Summary

The core loop held up: pars, the result strip, `Esc Esc` to skip, the diff on give-up
and the `!` flag behaved as designed, and idiomatic solutions were accepted and scored
correctly. The app survived key mashing with no console errors.

The serious defects were:

- Macro failure handling (`99@a` and recursive macros) differed from Neovim, and a
  recursive macro froze the tab (#2).
- Import accepted an incomplete file that broke the app on every reload (#1).
- Hash routes, browser Back, reloading mid-placement and switching language
  mid-placement left the app on the wrong screen or restarted placement (#11, #14–#18).
- Placement marked brute-forced skills as mastered (#8).

Many generated tasks made arbitrary or code-breaking edits: renaming inside strings,
uppercasing `#include` paths, calling non-constants "constant names" (#7, #27, #28).

## Fixed

| # | What broke | Fix | Test |
|---|---|---|---|
| 1 | Import accepted structurally incomplete files (missing `model.skills`, unknown language, missing `placementDone`), saved them, and broke the app on every load | `parseImport` (`app/src/storage.ts`) rejects the file before anything is saved and names the bad field. `normalize()` repairs saves that are already broken by filling in empty `model.skills`, `recent` or `focusHistory`. `boot()` in `main.ts` resets an unknown saved language to Python | `storage.test.ts`; `e2e/run.mjs` reloads a save with `model.skills` deleted and `lang: "klingon"` into practice |
| 2 | A failing command inside a macro did not abort it: `99@a` ran past the target, and recursive macros hung the tab | A failing command aborts `@` and `:normal`; recursion guard (`vimfixes-macros-indent.ts`) | `app/e2e/cases/macros-indent.json` |
| 3 | A wrong end state gave no feedback (`dap` on a delete-function task was silently not accepted) | The "not quite — u to undo" nudge (`grading.unrecoverable`, grading.md) | `grading.test.ts` |
| 4 | The announced starting skill did not match the first practice exercise, and the pick varied between runs | The focus is computed once at the end of placement. Cause: `chooseFocus` seeds its RNG from the log length and the clock, and stats and the drill each called it | `e2e/run.mjs` |
| 5 | The editor font rendered code ligatures (`!=`, `<=`), so the screen did not show the real characters | `font-variant-ligatures: none` and `liga`/`calt` off on `.code .cm-content` | e2e checks the computed style |
| 7 | "Rename every X to Y" changed text inside strings, docstrings, includes and namespaces | Renames touch only code identifiers (`templates.py`) | `test_renames_only_touch_code_identifiers` |
| 8 | Placement marked brute-forced skills mastered (eleven `l` presses on a par-2 exercise) | Placement passes only within `max(2·par, par+6)` keys (ADR 0011, `grading.placementPass`) | `grading.test.ts` |
| 9 | Untested skills showed as "locked" at 0.00, which read as a gate | The tile pill reads `untested` when the status is locked and n is 0 | e2e: no pill reads `locked` after placement |
| 11 | Changing or loading `#stats` or `#settings` did not switch the view | The hash decides the view (`render()` in `main.ts`, ux.md "Routes, Back and reload") | — |
| 13 | `x.subst` tasks did not say "whole word" although the par used `\<` `\>` | "as a whole word" when the par needs it | `test_subst_says_whole_word_when_the_par_needs_it` |
| 14 | A skipped placement could be re-entered from stats | Route guards in `render()` | `e2e/session.mjs` |
| 15 | Switching language mid-placement carried the placement counter over | Switching ends the running placement first | `e2e/session.mjs` |
| 16 | After a language switch, `Esc` landed on an empty stats page | `Esc` goes to practice after a switch. Browser Back can still reach an older stats entry | — |
| 17 | Browser Back from stats left the app | App navigation pushes history entries | `e2e/run.mjs` |
| 18 | Reloading mid-placement restarted placement and dropped the answers | Placement progress is saved and resumed | `e2e/run.mjs` |
| 20 | change_inner tasks quoted the delimiters on one side only | One inner-text-object phrase, both sides quoted without delimiters | `test_inner_tasks_share_one_wording` |
| 23 | Rename targets were semantically arbitrary | Role-based new names (`ROLE_NAMES`) | `test_new_names_fit_the_role_and_are_fresh` |
| 27 | `#include` paths were used as string targets | Excluded as targets | `test_include_paths_are_never_string_targets` |
| 28 | "Make X a constant name" targeted non-constants | `upper_word` targets only real constants | `test_case_drills_only_target_constants` |
| 29 | Long quotes were truncated with "..." inside the backticks | `...` outside the backticks, cut on a whole token | `test_quotes_hold_no_ellipsis` |
| 30 | `x.subst` exercises from one template had mixed kinds | Every `x.subst` exercise is `ex` (content-pipeline.md, Template kind rule) | `test_rename_all_subst_is_always_ex` |
| 31 | The placement intro always showed "first visit · 4 of 4" | Intro text depends on the visit | `e2e/run.mjs` |
| 33 | Ungrammatical "Rename every words to parts" | No "every `<plural>`" wording | — |
| 34 | First-visit setup showed the internal id `m.rel` | No skill ids before the first exercise (ux.md, Onboarding copy rules) | `e2e/run.mjs` |
| 36 | No "placement complete" moment | "placement complete: N skills placed, M mastered." | — |
| 41 | Raw JSON parse errors on a bad import | Fixed with #1: "that file is not valid JSON (it may be cut off)", and a clear version-mismatch message | `storage.test.ts` |
| 44 | The app version in the flag issue was the placeholder 0.0.0 | `package.json` version plus the short commit (`vite.config.ts`) | `feedback.test.ts` checks the version line |
| 49 | Three terms for the inner text object in sibling skills | One phrase | `test_inner_tasks_share_one_wording` |
| 50 | `o.number` tasks did not say which number on the line | "(the Nth number on the line)" | `test_number_tasks_say_which_number` |
| 52 | Awkward or inconsistent template phrasing | See `content/review/wording-findings.md` | — |
| 54 | The change_to_end label showed a stray pointer star | Names the declared identifier | `test_change_to_end_names_the_declared_variable` |

## Open

| # | Finding | Area |
|---|---|---|
| 6 | Task text does not single out the target when the quoted text repeats or brackets nest (the cursor starts inside the target, so the par is right) | wording |
| 10 | The hint for a long but correct solution is generic; generic detectors run before the exercise's own fallback hint | grading |
| 12 | Some C++ snippets are trivial stubs, context-free fragments, truncated cuts or Exercism scaffold comments | content |
| 19 | Import replaces all progress with no confirmation | app |
| 21 | A correct `:%s` ends with a red "Found N matches" message | emulator |
| 22 | `rename_all_dot` text does not say whether `:s` counts; `a.dot` and `x.lastsearch` share the same text | wording |
| 24 | The header shows `s stats` and `, settings` on screens where those keys do nothing | app |
| 26 | Indent tasks do not name the operator; the line count includes blank lines the highlight skips | content |
| 32 | Placement is a fixed 12 exercises with no early stop | design |
| 35 | The session summary does not split solved and skipped | app |
| 37 | The footer label `5j` reads like the answer when the task needs `7k` | wording |
| 38 | Keys typed on the result strip can leak into the next exercise's count | app |
| 39 | The keys display shows `<Space>` in Ex commands for "you" but a literal space for "par" | app |
| 40 | A solution rejected by the "only a `:` command" rule is explained only in a small footer note | app |
| 42 | Export gives no visible confirmation | app |
| 43 | Stats opens at the previous screen's scroll position | app |
| 45 | The cursor start position is not stated, so text-object pars are hard to plan | design |
| 46 | After typing, the page can scroll and cut off the task text | layout |
| 47 | Practice can repeat a skill back to back with little variety | model |
| 48 | In the flag picker, digits after the first choice go into the note field | app |
| 51 | "Put self. back at the start" presumes earlier state | wording |
| 53 | C++ `x.normal` comment-out drills target class member declarations in headers | content |
| 55 | No QA run observed the "beat par" band on real content (the e2e suite checks it on a sample) | coverage |

Finding 25 (a disabled replay key shown on the result strip) was resolved by removing
the key.
