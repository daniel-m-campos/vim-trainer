# Roadmap

Milestones, not dates, with completion dates added as they happen. Each has an exit
criterion. The author is the only user through M3.

Status on 2026-10-12: M0 to M3 built, M4 in progress.

## M0 — Plan complete (this document set). Done 2026-10-11
Exit: every `docs/plan/*.md` has no "To research" item that blocks the MVP; the
remaining items are listed in 09 with how they will be resolved during build.

## M1 — Spikes (de-risk the two unknowns). Done 2026-10-11
1. codemirror-vim key logger: capture normalised keystrokes, mode changes, and a
   reliable command-done signal in a throwaway page. Test Chrome, Firefox, Safari.
2. Oracle round-trip: a Python script takes one exercise JSON, replays the canonical in
   `nvim --headless --clean`, compares, prints pass/fail and timing. Then the same via
   Playwright + codemirror-vim.
Exit: both work; decisions recorded in `docs/decisions/`.
Result: both work (0002, 0003). The Playwright half of spike 2 became the browser
replay inside `make content` (0005). Real Safari and Firefox with a physical keyboard
were not tested; Playwright's WebKit and Firefox stood in.

## M2 — Content pipeline, Python only. Done 2026-10-11
Sources allowlist; Python language mapping; 5 templates (change_inner, delete_inner,
jump_match, delete_trailing_comment, goto_line_rel); oracle with best-par search;
review CLI; ATTRIBUTION.md; ≥ 20 exercises for each of 10 skills.
Exit: `make content` produces `build/` from scratch with every par verified in CI.
Result: 17 templates instead of 5, 587 exercises over 15 skills (at least 27 each).
CI is written but has not run on GitHub yet (see 09).

## M3 — Practice loop MVP (author dogfood). Built 2026-10-11, dogfood not started
Practice screen per the mock; result strip with hints; adaptive model (TS + Python
mirror with shared test vectors); placement test; localStorage; export/import; settings.
Stats screen can be a plain table at this stage.
The build is complete: practice loop, model, placement, stats table, export and
import. A review round on 2026-10-12 fixed nine of ten findings. The dogfood exit
below is still open.
Exit: the author practises 10 min/day for 4 weeks; model constants recalibrated from
that log; at least one "this changed how I edit" moment written down.

## M4 — Breadth. In progress (started 2026-10-12)
C++ then TypeScript content; templates for tiers 5–8; emulator oracle flags and the
generated supported-command list; VSCodeVim and IdeaVim profiles with verified flags;
stats screen with charts and projection; session summary.
In this round: C++ content, templates for tiers 5 to 8, and stats charts. Not started:
TypeScript content, VSCodeVim and IdeaVim verification, session summary beyond the
text version already in the app. The emulator oracle and the generated
supported-command list for Neovim exist (0005); the browser side of the list does not.
Exit: all v1 languages at ≥ 20 exercises per non-zero (language, skill); every
"verify" flag in 02 is resolved.

## Round 3: feedback loop and fidelity (inside M3/M4)
Started 2026-10-13 after the first dogfood sessions (ADRs 0007, 0008, 0009). Split into
four rounds; each ends with `make test`, `make e2e`, `make content-check`, a green CI
run and a republished artifact.

- **3a. Built 2026-10-13.** Attempt records carry `seq`, `beatPar` and `flag`; the
  `beat par` band; the `!` flag picker and prefilled GitHub issue; the `ingest` CLI with
  `idioms_learned.toml`; the anti-shortcut gate fix and `x.normal` for C++; the
  template kind audit; `keys.mjs` accepts every key token the oracle accepts. (11, 03,
  05.)
- **3b. Built 2026-10-13.** `difftest`: a differential fuzzer between headless Neovim
  and the emulator. A seeded generator draws key sequences over exercise and adversarial
  buffers. A Node worker types them into the real editor over JSON lines, and a
  minimiser reduces each divergence to a few keys. Findings are classified a-d and
  checked against `content/difftest/known.jsonl`, which is seeded with the known
  divergences. `make difftest` runs it, and a nightly CI job (`difftest.yml`, sharing
  the setup action with `ci.yml`) fails only on new findings. Next: a first
  50,000-sequence local run and triage into `vimfixes.ts` and the supported-command
  list (12).
- **3c.** Placement per language: `placementDone` per language, rebuild splits
  placement batches by language, a new model vector, e2e for the language switch.
- **3d.** Mock-user QA: a workflow of Sonnet agents with personas driving the site
  through Playwright; no code. Their findings become round 4.

## Round 4: QA fixes and launch hardening (inside M4)
Started 2026-10-14 from the 55 ranked mock-user findings
(`docs/qa/2026-10-13-mock-users.md`). Contents:

- Placement efficiency gate `max(2 * par, par + 6)` and placement progress that
  survives reloads (04, ADR 0011).
- The "not quite — u to undo" nudge (05).
- Hash routes as the single source of truth for the screen; Back and reload behave;
  a placement-complete moment; onboarding copy with no skill ids before the first
  exercise (10).
- Error ring buffer in the export and in the issue body; a real version string (11).
- Emulator class-a fixes in `vimfixes.ts`, with `known.jsonl` pruned after them (12).

Soft-launch sequence after round 4: (1) a public feedback repo and the deploy pipeline
(`make content && make build`) land; (2) 10–20 invited switchers, not an open post;
(3) cross-browser e2e before widening; (4) then the r/neovim testers of M5. See 09 for
the hardening list.

## M5 — Soft launch
Hosting, domain, FAQ ("why no mobile", "why these commands"), GitHub Sponsors link,
10–20 invited switchers first, then testers from r/neovim, bug fixing, opt-in anonymous log upload.
Decide where outside testers file feedback (a public feedback repo; see 09).
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
