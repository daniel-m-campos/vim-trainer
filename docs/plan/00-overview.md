# Overview

## One-line pitch
keybr for Vim: adaptive drills on real code that find your weakest motion and fix it.

## Who it is for
1. The author (first customer): Neovim 0.12 + VSCodeVim user, intermediate, wants to be very proficient.
2. Developers who already use Vim keybindings daily and have plateaued.
3. Beginners after `vimtutor`, as a secondary audience.

## What makes it different (see research/02)
- Per-skill speed and accuracy tracked over time, with charts and a projection.
- Drill selection driven by the weakest skill (keybr loop), with min-sample and accuracy gates.
- Practice content generated from real code, selectable by programming language.
- Efficiency (keystrokes vs par) scored alongside speed, with replays.
- Pars verified against real Neovim, not the browser emulator.
- Hints rather than blocking; respects relative numbers / arrow-key preferences.

## Non-goals (v1)
- Teaching Vim from zero (vimtutor does this).
- Leaderboards, social features.
- Running real Vim in the browser (vim.wasm is frozen, Neovim WASM is blocked).
- Payments in the MVP.

## Plan documents
- 01-personas-and-jobs.md
- 02-skill-graph.md
- 03-content-pipeline.md
- 04-adaptive-model.md
- 05-grading.md
- 06-tech-stack.md
- 07-monetization.md
- 08-roadmap.md
- 09-open-questions.md
- 10-ux.md
- 11-feedback-loop.md
- 12-differential-testing.md
