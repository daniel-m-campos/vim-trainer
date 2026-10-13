# Differential testing of the emulator

Goal: find every way codemirror-vim (as patched in app/src/vimfixes.ts) behaves
differently from Neovim for the commands we drill, before a player does. ADR 0008.

## Idea

The par replay proves one keystroke string per exercise. A differential fuzzer proves
many: generate key sequences from a grammar of the skill graph's commands, run each in
`nvim --headless --clean` (the oracle) and in headless Chromium through the real app's
editor, starting from the same buffer and cursor, and compare the result: buffer lines,
cursor position, mode, and (where cheap) register contents. Any difference is a finding.

## Generator

- Alphabet: every key in docs/plan/02-skill-graph.md tiers 0-9 plus insert-mode keys,
  counts 1-9, and text objects, weighted by the per-language weights.
- Grammar: `[count] operator [count] motion|textobject`, visual sequences, `:` commands
  from a small template set (`:s`, `:g`, `:m`, `:t`, `:normal`), macros `q{a}...q@{a}`,
  `.` after an edit, `u` and `<C-r>`.
- Buffers: real snippets from the content corpus (both languages), plus adversarial
  ones: empty, one line, trailing whitespace, tabs, brackets alone on lines, unbalanced
  brackets, Unicode, very long lines.
- Seeded; a failing (buffer, sequence) pair is reproducible by seed.

## Oracle and emulator harness

- Neovim: the existing oracle, run in batches over pynvim; returns lines, cursor, mode.
- Emulator: Playwright drives `app/emulator-check.html`, types the sequence with
  `e2e/keys.mjs`, reads lines, cursor and mode from `window.emu.status()`.
- Both run with the same option set (expandtab, shiftwidth, autoindent, ignorecase).

## Minimisation and triage

- Delta-debug a failing sequence to the shortest prefix that still diverges; then try to
  drop keys from the middle. Most findings should reduce to 2-4 keys.
- Classify: (a) emulator bug to fix in vimfixes.ts, (b) emulator limitation to record in
  build/supported_commands.md and exclude from drills, (c) oracle/harness artefact
  (option mismatch, timing), (d) Neovim-specific behaviour we accept differing from Vim.
- Every (a) fix gets a regression case in app/e2e/editor.mjs. Every (b) adds an entry
  to the generated supported-command list and, if a drill depends on it, the content
  gate marks the exercise web-unsupported.

## Budget

- Nightly in CI: 2,000 sequences across 200 buffers, under 10 minutes.
- Before a release: 50,000 sequences locally.
- The fuzzer ships as `uv run vimtrainer-content difftest --seed N --count K`, Python
  driving both harnesses; Playwright already runs from Python for the emulator oracle.

## Known divergences to seed the run (from reviews so far)

Linewise `i{`/`i(`/`i[` in visual mode (`vi{`); `<BS>` and `<CR>` inside a block
insert; the exclusive-linewise rule for `c}`, `y}`, `gU}` and search motions; Select
mode (absent); `%` on some bracket shapes; `U`; `g@`; long or recursive macros
(codemirror-vim #177); `gn` behaviour; numbered registers.

## What it will not catch

Rendering (how it looks), timing, and anything outside the drilled command set. Those
stay with the player feedback loop (11).
