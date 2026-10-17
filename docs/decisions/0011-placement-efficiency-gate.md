# 0011: Placement samples pass only within an efficiency cap

Date: 2026-10-14. Status: accepted.

## Context

A placement sample passed whenever the buffer reached the target. Each pass marks the
skill and all its prerequisites mastered (`docs/design/adaptive-model.md`), so one pass
carries a lot of weight. The scripted QA run (`docs/design/qa-findings.md`, finding #8) showed a tester that did
not know the motion reaching the target by brute force: eleven presses of `l` on a
par-2 cursor exercise. Placement marked the skill and its prerequisites mastered, and
the practice loop then never offered them.

Placement also lost its progress on reload, so a tester who reloaded mid-test started
over or, worse, kept a half-seeded model.

## Decision

- A placement sample counts as passed only when `ok` and
  `keys <= max(2 * par, par + 6)`. `placementPass` in `app/src/grading.ts` holds the
  rule. A sample over the cap seeds the skill as a fail.
- `2 * par` is the cap for long pars. The `+ 6` floor keeps short pars (1 to 6 keys)
  from failing on one detour, such as an extra motion before the edit.
- Placement progress is saved after each sample and resumes after a reload or Back.
- The gate applies to placement only. Practice attempts keep the bands of
  `docs/design/grading.md`; a slow pass there still updates the model through its efficiency term.

## Consequences

- Placement will under-place some learners who know a command but fumble under test. That
  is the cheaper error: an under-placed skill comes back in practice and is mastered
  again quickly, while an over-placed one is never shown.
- The cap uses the median par, which is the same par the result strip shows.
- Revisit once real placement logs show how far over par passes land.
