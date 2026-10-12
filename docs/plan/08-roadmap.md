# Roadmap

Milestones, not dates. Each has an exit criterion. The author is the only user through
M3.

## M0 — Plan complete (this document set)
Exit: every `docs/plan/*.md` has no "To research" item that blocks the MVP; the
remaining items are listed in 09 with how they will be resolved during build.

## M1 — Spikes (de-risk the two unknowns)
1. codemirror-vim key logger: capture normalised keystrokes, mode changes, and a
   reliable command-done signal in a throwaway page. Test Chrome, Firefox, Safari.
2. Oracle round-trip: a Python script takes one exercise JSON, replays the canonical in
   `nvim --headless --clean`, compares, prints pass/fail and timing. Then the same via
   Playwright + codemirror-vim.
Exit: both work; decisions recorded in `docs/decisions/`.

## M2 — Content pipeline, Python only
Sources allowlist; Python language mapping; 5 templates (change_inner, delete_inner,
jump_match, delete_trailing_comment, goto_line_rel); oracle with best-par search;
review CLI; ATTRIBUTION.md; ≥ 20 exercises for each of 10 skills.
Exit: `make content` produces `build/` from scratch with every par verified in CI.

## M3 — Practice loop MVP (author dogfood)
Practice screen per the mock; result strip with hints; adaptive model (TS + Python
mirror with shared test vectors); placement test; localStorage; export/import; settings.
Stats screen can be a plain table at this stage.
Exit: the author practises 10 min/day for 4 weeks; model constants recalibrated from
that log; at least one "this changed how I edit" moment written down.

## M4 — Breadth
C++ then TypeScript content; templates for tiers 5–8; emulator oracle flags and the
generated supported-command list; VSCodeVim and IdeaVim profiles with verified flags;
stats screen with charts and projection; session summary.
Exit: all v1 languages at ≥ 20 exercises per non-zero (language, skill); every
"verify" flag in 02 is resolved.

## M5 — Soft launch
Hosting, domain, FAQ ("why no mobile", "why these commands"), GitHub Sponsors link,
10–20 testers from r/neovim, bug fixing, opt-in anonymous log upload.
Exit: five testers return for a second week unprompted.

## M6 — Public launch
Show HN + Reddit. Free product only. Email capture for pro interest.
Exit: a week of feedback triaged into the backlog; pro feature list confirmed or
changed by what people asked for.

## M7 — Pro
Accounts, sync, history, replay, export; Polar/Paddle; price test at $15/19/25.
Exit: first 50 sales; refund rate < 5%.

## Later
Neovim companion plugin (real-editing telemetry into the model); Emacs evil profile;
teams/education; community exercise contributions with the oracle as gatekeeper; FSRS
once there is data to fit it.
