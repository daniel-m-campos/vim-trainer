# vim-trainer (codename)

An adaptive Vim-motions trainer in the browser, modelled on keybr.com: it measures
speed and accuracy per skill, drills the weakest one, and charts progress over time.
Practice content is generated from real code, per programming language.

Status: **planning**. No code yet. The first user is the author, who is learning Vim.

## Layout

- `docs/plan/` — the product plan, one file per topic. Start with `00-overview.md`.
- `docs/decisions/` — short decision records (ADRs). One file per decision.
- `docs/research/` — the two research reports this plan is based on, plus their raw notes.

## Principles (from the research)

1. Differentiate on measurement, not on lessons. Nobody charts per-skill speed/accuracy.
2. Free core, no ads in the practice loop. A one-time lifetime "pro" later, never a subscription.
3. Real Vim is the oracle: every exercise's par is verified with `nvim --headless`.
4. Content from real code, per language, under permissive licences with attribution.
5. Tooling in Python (the author's language); only the browser app is TypeScript.
