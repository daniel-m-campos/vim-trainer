# Personas and jobs to be done

Two audiences, one product. The adaptive engine and content pipeline are shared; what
differs is the entry point, the skill subset shown first, and the language of the
marketing.

## Persona A: the switcher

Uses VS Code (VSCodeVim, ~9M installs) or JetBrains (IdeaVim), or has just moved to
Neovim via kickstart/LazyVim. Knows `hjkl`, `i`, `Esc`, `:w`. Reaches for the mouse
and arrow keys when it gets hard. Has done `vimtutor` once.

Job: "Stop being slower than I was before I turned Vim mode on, in the editor I already
use, in the language I write every day."

What "better" looks like:
- Drills in their language (TS/Python/Java first, given VS Code and JetBrains demographics).
- A visible speed curve that shows the dip ending. This is the retention hook.
- No terminal, no plugin install, no config. Works in a browser tab next to their editor.
- Only Vim features that work in VSCodeVim/IdeaVim are drilled on their track
  (no Ex-heavy content early; those emulators are weak there).

Acquisition: VSCodeVim and IdeaVim README/marketplace mentions, r/vscode, "I enabled
Vim mode and I'm slower" threads, YouTube "Vim in VS Code" videos.

## Persona B: the intermediate who wants to be elite

Daily Vim/Neovim user for 1+ years. Fluent in motions and operators. Plateaued.
Doesn't use dot-repeat deliberately, rarely uses registers, macros, `:g`, `:normal`,
text objects beyond `iw`/`i"`. Knows vim-be-good, found it too basic. Has opinions.

Job: "Find the inefficiencies I can't see in my own editing and drill them out."

What "better" looks like:
- Keystrokes-vs-par scoring with replays of the optimal solution, so every exercise
  teaches something even when passed.
- Advanced tracks: dot-repeat, registers, macros, `:g`/`:normal`, visual block,
  marks/jumps, folds, multi-file.
- Per-skill history and projection. They want the data.
- Respects their config (relative numbers, leader, custom maps where feasible).
- Pars verified against real Neovim, and a published supported-command list, because
  they will test the emulator's edges and post about it.
- Phase 2: a Neovim plugin that observes real editing and feeds the skill model, so
  the trainer drills what they actually fumble at work.

Acquisition: Show HN, r/neovim, r/vim. This audience writes the reviews that persona
A reads, so it has to be won first for credibility even though it is smaller.

## How one product serves both

- One skill graph, two default **tracks** (Switcher, Advanced) that choose a starting
  subset and ordering. Both end in the same place.
- Placement test on first visit (5 minutes) that puts the user on the right track and
  seeds the per-skill confidences, so persona B never sees `hjkl` drills.
- Language selector is global and affects content for both tracks.
- Persona B is the free-tier evangelist; persona A is the larger paying base.
  Pro features (history, charts, sync, advanced tracks) must appeal to both.

## Explicitly not served in v1

- Absolute beginners who have not done `vimtutor`. Link them to `:Tutor`.
- Emacs evil-mode users (later: same engine, different emulator quirks).
