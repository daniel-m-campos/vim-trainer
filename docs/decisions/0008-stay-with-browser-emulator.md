# 0008: Stay with the browser emulator; find divergences by differential testing

Date: 2026-10-13. Status: accepted.

Considered after the first practice sessions: replace codemirror-vim with real
Neovim on a server behind a WebSocket (perfect fidelity, all logic in Python) versus
keep the static browser app (zero hosting cost, offline, instant keystrokes, but a
JavaScript reimplementation of Vim that can disagree with the real thing).

Decided: keep the emulator. Reasons: the practice experience is already good; static
hosting is free at any scale while a server adds cost, a per-session sandbox and
latency; and divergences are a bounded, testable problem. The author will learn enough
TypeScript to review app/.

Consequences:
- Divergences are found by differential testing (docs/design/differential-testing.md):
  generate key sequences, run them in headless Neovim and in the emulator from identical
  buffers, compare buffer, cursor and mode, minimise failures, fix in vimfixes.ts or
  record in supported_commands.md.
- The build-time browser replay of every par stays as the last line of defence.
- app/ is reviewable code, not a black box: keep it small, commented, and documented in
  app/README.md with a reading order for someone new to TypeScript.
