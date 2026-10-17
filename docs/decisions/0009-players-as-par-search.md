# 0009: Players' sequences are the par search engine, verified in Neovim

Date: 2026-10-13. Status: accepted.

The par search tries a fixed idiom list per skill plus each template's own variants.
It finds shorter known idioms and never unknown ones, and the first practice sessions
beat several pars. Writing more idioms by hand scales with one person's Vim knowledge; players collectively know more.

Decided:
- Every attempt records its normalised key sequence (`seq`) and whether it beat par
  (`beatPar`). A player can flag an attempt with `!` (wrong-par / wording / emulator /
  other); the flag opens a prefilled GitHub issue. See docs/design/feedback-loop.md.
- `vimtrainer-content ingest` replays each beat-par or wrong-par sequence in headless
  Neovim. No par changes without that check. A shorter passing sequence becomes the
  canonical, an equal one an alternate, a failing one an emulator-divergence entry.
- Learned idioms are generalised and stored as data in `content/idioms_learned.toml`,
  which `par_search.IDIOMS` merges at import, so the next build re-pars every sibling
  exercise.
- The feedback link targets the public repo `daniel-m-campos/vim-trainer`, whose
  issue tracker is open to every player.

Consequences:
- Pars get shorter over time without new code; each ingest run is a reviewable diff of
  exercise JSON and `idioms_learned.toml`.
- One bad generalisation can re-par a whole template, so a human reads the toml diff
  before committing.
- A sequence the browser accepted but Neovim rejects is a free emulator bug report,
  complementing the differential fuzzer (ADR 0008).
- Nothing leaves the player's browser unless they file the issue or share the export.
