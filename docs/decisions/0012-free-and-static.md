# 0012: Free and static, with no accounts, ads or payments

Date: 2026-10-17. Status: accepted.

## Context

The trainer is a static site. Exercises are generated and verified at build time
(ADR 0005, ADR 0010), the adaptive model runs in the browser (`docs/design/adaptive-model.md`),
and progress lives in the browser's localStorage with JSON export and import. Feedback
travels as a GitHub issue the player chooses to file (`docs/design/feedback-loop.md`).
GitHub Pages serves the site at no cost, and its running cost does not grow with
traffic: every visitor downloads the same files, and nothing runs on a server.

ADR 0008 kept the browser emulator instead of a hosted Neovim partly for this reason: a
server would add cost, a per-session sandbox and latency.

## Decision

- The trainer is free to use, with no accounts, no ads, no payments and no analytics.
- The site stays static. Nothing the player does is sent anywhere unless the player
  files an issue or attaches an export.
- The source is open under the MIT licence.

## Consequences

- No feature depends on a server: no sync between devices beyond export and import, no
  leaderboards, no central measurement. Quality signals come from filed issues and
  shared exports.
- No code path exists for gating, upselling or tracking, so there is nothing of that
  kind to maintain or audit.
