# 0007: Player feedback loop before any payment

Date: 2026-10-13. Status: accepted.

The author's first practice sessions found a drill that rejected a correct solution
(copy_line was ex-kind, so `yyjp` failed) and pars that a player could beat. The oracle
only verifies the solutions we thought of; players find the ones we did not.

Decided:
- Record each attempt's keystroke sequence, whether it beat par, and an optional player
  flag (wrong-par / wording / emulator / other). Local only; shared by a deliberate act
  (prefilled GitHub issue, or export). See docs/plan/11-feedback-loop.md.
- An `ingest` step verifies player pars in real Neovim before any par changes.
- Pro is gated on measured stability (docs/plan/07-monetization.md "Stability gate"),
  not on a date or a user count alone.
- `ex` kind is reserved for drills that retyping would defeat; copy/move/duplicate are
  `edit`.
