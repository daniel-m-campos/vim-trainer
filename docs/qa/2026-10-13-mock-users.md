# Mock-user QA, 2026-10-13

Eight scripted personas played the app against the live build: data-abuser, intermediate-textobjects, switcher-hjkl, expert-macros, chaos-clicker, cpp-user, wording-reader-python and wording-reader-cpp. They reported 55 findings. A verifier re-checked the first 12 against the browser, the source or the exercise JSON. This round fixed 3 small, certain findings plus one that the import fix covered. The rest are deferred.

## How it felt

The core loop works well. Pars, the result strip, Esc Esc to skip, the diff on give-up and the `!` flag were easy to learn. The expert found most idiomatic solutions accepted and scored correctly.

The weak points are getting into the app and the screens after placement. The onboarding copy uses jargon. The stats grid shows brute-forced skills as mastered and untested skills as locked. The announced starting skill rarely matches the first exercise.

Two defects are serious enough to lose a session:

- Macro failure handling (`99@a` and recursive macros) differs from Neovim, and the recursive case freezes the tab.
- Import accepts an incomplete file that bricks the app on every reload. Fixed this round.

Navigation is fragile in a different way. The app survived key mashing with no console errors. Hash routes, Back, reloading mid-placement and switching language mid-placement all leave the user in the wrong place or restart placement.

The exercise wording is mostly clean and leaks no internals. Many generated tasks make arbitrary or code-breaking edits, though: renaming inside strings, uppercasing `#include` paths, and calling non-constants "constant names". Coverage was incomplete. Practice mode was barely exercised, and no persona triggered "beat par" (the e2e suite does check that band on its sample exercise).

## What changed this round

| # | Finding | Change | Test |
|---|---|---|---|
| 1 | Import accepts incomplete files and bricks the app | `parseImport` (`app/src/storage.ts`) now rejects the file before anything is saved and names the bad field: `model`, `model.log`, `model.skills`, `settings`, `placementDone`, or an unknown `settings.lang`. `normalize()` repairs saves that are already bricked, giving a missing `model.skills`, `recent` or `focusHistory` empty values that the model fills in again. `boot()` in `main.ts` resets an unknown saved language to Python. | `storage.test.ts`: rejects no `model.skills`, rejects `klingon`, rejects a bad `placementDone`. `e2e/run.mjs`: a save with `model.skills` deleted and `lang: "klingon"` reloads into practice. |
| 5 | Code ligatures in the editor | `.code .cm-content { font-variant-ligatures: none; font-feature-settings: "liga" 0, "calt" 0; }` in `style.css`. | e2e: computed `font-variant-ligatures` on the editor is `none`. |
| 9 | Untested skills read as "locked" | A tile pill reads `untested` when the status is `locked` and n is 0 (`pillText` in `statsView.ts`). When any tile is untested, the skills lead line adds "untested skills can be drilled too". The `sv-locked` dimming class is unchanged. | e2e: no stats pill reads `locked` after placement. |
| 41 | Raw JSON errors on import | Fixed as part of #1. A truncated file now gives "that file is not valid JSON (it may be cut off)". A version mismatch now gives "export is version N, this app reads version 1". | `storage.test.ts` |

Checks run: `npm test` (65 pass), `npm run typecheck` (clean) and `npm run e2e` (all checks pass).

## All findings, ranked

Severity is the persona's rating. "Verified" is the verifier's rating where one exists; the verifier checked findings 1 to 12. Status is **fixed**, **deferred** (needs emulator, template, content or design work) or **open** (small and fixable, but not in this round's fix list).

| # | Finding | Kind | Severity | Verified | Status | Personas |
|---|---|---|---|---|---|---|
| 1 | Import accepts structurally incomplete files (missing `model.skills`, unknown lang, missing `placementDone`), saves them, and can brick the app on every load | bug | high | reproduced, medium | **fixed** | data-abuser |
| 2 | A failing command inside a macro does not abort it: `99@a` runs past the target, and recursive macros hang the tab | emulator | high | reproduced, high | **fixed** round 4: a failing command aborts `@` and `:normal`; recursion guard (`vimfixes-macros-indent.ts`, `e2e/cases-macros-indent.mjs`) | expert-macros |
| 3 | A wrong end state gives no feedback: `dap` on a delete-function task is silently not accepted | ux | high | reproduced, medium | **fixed** round 4: "not quite — u to undo" nudge (`grading.unrecoverable`, 05-grading.md) | intermediate-textobjects |
| 4 | The announced starting skill does not match the first practice exercise, and the pick varies between runs | ux | medium | reproduced, medium | **fixed** round 4: focus computed once at the end of placement (`e2e/run.mjs`) | intermediate-textobjects, switcher-hjkl, data-abuser, cpp-user |
| 5 | The editor font renders code ligatures (`!=`, `<=`, `>=`, `==`), so the screen does not show the real characters | ux | medium | partly reproduced, low | **fixed** | intermediate-textobjects, switcher-hjkl, cpp-user |
| 6 | Task text does not single out the target when the quoted text repeats or the brackets nest | ux | medium | reproduced, low (cursor starts inside the target) | deferred: wording queue | wording-reader-python, wording-reader-cpp, switcher-hjkl |
| 7 | "Rename every X to Y" changes text inside strings, docstrings, includes and namespaces | wording | medium | reproduced, low | **fixed** round 4: renames only code identifiers (`templates.py`, `test_templates_wording.py`) | wording-reader-python, cpp-user |
| 8 | Placement scoring marks brute-forced skills as mastered (1.00, n 8) | bug | medium | reproduced, low (inference is by design) | **fixed** round 4: placement passes only within max(2·par, par+6) keys (ADR 0011, `grading.placementPass`) | switcher-hjkl, intermediate-textobjects |
| 9 | Untested skills show as "locked" at 0.00, which reads as a gate | wording | medium | reproduced, low | **fixed** | intermediate-textobjects, expert-macros |
| 10 | The hint for a long but correct solution is generic and does not name the focus skill (`])` exercise) | ux | medium | reproduced, low | deferred: hint ordering in grading.ts follows 05-grading.md | switcher-hjkl |
| 11 | Hash navigation is out of sync: changing or loading `#stats` or `#settings` does not switch the view | bug | medium | reproduced, low (feature not built) | **fixed** round 4: the hash decides the view (`main.ts` render) | chaos-clicker, data-abuser |
| 12 | C++ snippets include trivial stubs, context-free fragments, a truncated cut, reused snippets and Exercism scaffold comments | ux | medium | reproduced, low | deferred: content pipeline | wording-reader-cpp, cpp-user |
| 13 | x.subst tasks do not say "whole word", although the par uses `\<` or `\>` | wording | medium | not verified | **fixed** round 4: "as a whole word" wording when the par needs `\<`/`\>` | wording-reader-cpp, cpp-user |
| 14 | A skipped placement can be re-entered: Esc from Stats goes back to the intro | bug | medium | not verified | **fixed** round 4 (`e2e/session.mjs`) | cpp-user |
| 15 | Switching language mid-placement carries the placement counter over and skips the new-language intro | bug | medium | not verified | **fixed** round 4: switching ends placement early (`e2e/session.mjs`) | cpp-user |
| 16 | After a language switch, Esc lands on an empty all-locked Stats page | ux | medium | not verified | **fixed** round 4 for Esc; browser Back after a switch can still reach an older stats entry | cpp-user |
| 17 | Browser Back from Stats leaves the app and loses the placement session | ux | medium | not verified | **fixed** round 4: history entries for app navigation (`e2e/run.mjs`) | chaos-clicker |
| 18 | Reloading mid-placement restarts at placement 1 of 12 and drops the attempts already made | ux | medium | not verified | **fixed** round 4: placement progress saved and resumed (`e2e/run.mjs`) | chaos-clicker |
| 19 | Import silently replaces all current progress with no confirmation | ux | medium | not verified | open | data-abuser |
| 20 | change_inner tasks quote the delimiters in "from" but not in "to" | wording | medium | not verified | **fixed** round 4: one inner-text-object phrase, both sides quoted without delimiters | wording-reader-python |
| 21 | A correct `:%s` ends with a red "Found N matches for pattern" message | emulator | medium | not verified | deferred: round 4 emulator | switcher-hjkl |
| 22 | rename_all_dot text does not say whether `:s` counts; a.dot and x.lastsearch share identical text | ux | low | not verified | deferred: wording queue | switcher-hjkl, intermediate-textobjects, wording-reader-python |
| 23 | Rename and change targets are semantically arbitrary | wording | low | not verified | **fixed** round 4: role-based new names (`ROLE_NAMES`) | wording-reader-python, wording-reader-cpp, cpp-user |
| 24 | The header shows "s stats" and ", settings" on screens where those keys do nothing | ux | low | not verified | open | chaos-clicker, cpp-user |
| 25 | The dimmed "p replay par (pro)" key is shown but not available, and "? hint" is listed while the hint is already shown | ux | low | not verified | open | switcher-hjkl, cpp-user |
| 26 | Indent tasks do not name the operator; the line count includes blank lines but the highlight skips them | ux | low | not verified | deferred: highlight and content | switcher-hjkl, intermediate-textobjects |
| 27 | `#include` paths are used as string targets | ux | low | not verified | **fixed** round 4: `#include` paths are no longer targets | cpp-user, wording-reader-cpp |
| 28 | "Make X a constant name" changes one occurrence of a non-constant | wording | low | not verified | **fixed** round 4: upper_word targets only real constants | wording-reader-python, wording-reader-cpp |
| 29 | Task text truncates long quotes with a literal "...", sometimes inside the backticks | wording | low | not verified | **fixed** round 4: `...` outside the backticks, cut on a whole token | wording-reader-python, wording-reader-cpp |
| 30 | x.subst exercises built from identical templates have mixed kind values (ex and edit) | bug | low | not verified | **fixed** round 4: every x.subst exercise is `ex` | wording-reader-python, wording-reader-cpp |
| 31 | The placement intro always shows "first visit · 4 of 4" and the carry-over sentence | wording | low | not verified | **fixed** round 4 (`e2e/run.mjs`) | cpp-user, data-abuser |
| 32 | Placement is a fixed 12 exercises with no early stop (the brief and the e2e test say 3) | ux | low | not verified | deferred: design | intermediate-textobjects, data-abuser |
| 33 | Ungrammatical task text: "Rename every words to parts" | wording | low | not verified | **fixed** round 4: no "every `<plural>`" wording | switcher-hjkl |
| 34 | First-visit setup shows the internal id "m.rel" and puts "python · neovim" in the header before any choice | wording | low | not verified | **fixed** round 4 (`e2e/run.mjs`) | switcher-hjkl |
| 35 | The session summary says "N exercises" without solved and skipped counts | ux | low | not verified | open | switcher-hjkl |
| 36 | No "placement complete" moment; Stats opens directly | ux | low | not verified | **fixed** round 4: "placement complete: N skills placed, M mastered." | switcher-hjkl |
| 37 | The footer label "5j" reads like the answer when the task needs 7k | wording | low | not verified | open | intermediate-textobjects |
| 38 | Keys typed in the result strip leak into the next exercise's keystroke count | ux | low | not verified | deferred: input timing (e2e covers the double-space case) | chaos-clicker |
| 39 | The keys display shows `<Space>` inside Ex commands for "you" but a literal space for "par" | wording | low | not verified | open | expert-macros |
| 40 | A solution rejected by the drill's rule ("only a : command") is explained only in a small footer message | ux | low | not verified | open | expert-macros |
| 41 | Raw JSON parse errors and a misleading "not a vim-trainer export" message on import failure | wording | low | not verified | **fixed** (with #1) | data-abuser |
| 42 | Export gives no visible confirmation | ux | low | not verified | open | data-abuser |
| 43 | Stats opens at the previous screen's scroll position | bug | low | not verified | open | chaos-clicker |
| 44 | The app version in the flag issue body is the placeholder 0.0.0 | docs | low | not verified | **fixed** round 4: version is package.json + short commit (`vite.config.ts`) | intermediate-textobjects |
| 45 | The cursor start position is not stated, so text-object pars are hard to plan | ux | low | not verified | deferred: design | intermediate-textobjects |
| 46 | After typing, the page scrolls and cuts off the task text | ux | low | not verified | deferred: layout | switcher-hjkl |
| 47 | Practice repeats the same skill back to back with little variety | ux | low | not verified | deferred: model tuning | switcher-hjkl |
| 48 | In the flag picker, digits after the first choice go into the note field | ux | low | not verified | deferred: decide the intended behaviour | chaos-clicker |
| 49 | Three different terms describe the inner text object in sibling skills | wording | low | not verified | **fixed** round 4: one inner-text-object phrase | wording-reader-python |
| 50 | o.number tasks do not say which number on a multi-number line is meant | ux | low | not verified | **fixed** round 4: "(the Nth number on the line)" | wording-reader-python |
| 51 | "Put self. back at the start" presumes earlier state and repeats the v.blockedit text | wording | low | not verified | deferred: templates | wording-reader-python |
| 52 | Awkward or inconsistent template phrasing | wording | low | not verified | **fixed** round 4: see `content/review/wording-findings.md` | wording-reader-python |
| 53 | x.normal "comment out" drills target class member declarations in headers | ux | low | not verified | deferred: content pipeline | wording-reader-cpp |
| 54 | The change_to_end label shows a stray pointer star: "`* next`" | wording | low | not verified | **fixed** round 4: names the declared identifier | wording-reader-cpp |
| 55 | Coverage gap: no persona observed the "beat par" band | docs | low | not verified | deferred: the e2e already checks the band on its sample (`:g/nt(/d<CR>`); real content may need its own case | expert-macros |

## Notes from the verifier

- **#1**: Settings has no `#settings` hash route. It opens with the `,` key or the header link. The crash was partly contained by try/catch in `main.ts`, so the page was empty rather than dead. The bad save still persisted, and there was no way to recover inside the app.
- **#4**: The root cause is that `M.chooseFocus` seeds its random number generator with `deriveSeed(log.length, floor(nowSec))`. `renderStats` and `drillSelected` each call it, so the skill announced on Stats and the skill drilled can differ. In 2 of 5 runs they did.
- **#6**: Each exercise's cursor starts inside its target range, so `gUi'` and `ci(` act on the intended occurrence. The task text for `cpp/m.rel/13e265eff2` does say "the highlighted line".
- **#8**: `inferMastered()` sets n to `MASTER_N` (8), which is where "n 8" comes from. 04-adaptive-model.md intends prerequisites of a passed skill to be inferred as mastered. The real gap is that keys against par do not affect the inference.
- **#10**: `chooseHint` runs the generic detectors (such as `l{5,}`) before the exercise's own untriggered hint, as 05-grading.md specifies. `skills.ts` labels n.unmatched `]}`, while its exercises use `])`.
- **#11**: The app has no `hashchange` listener and never reads `location.hash` at load.
