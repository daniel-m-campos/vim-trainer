# Monetization

From research/02: ads on developer traffic pay almost nothing (52–72% blocked, $60–250
a month at 50k pageviews), a $1 tier nets $0.45 after fees and anchors the price low,
time-limited licences are attacked every time, and one-time lifetime pricing at $15–39
is what the community tolerates. No trainer sells a ~$1 tier; the lowest is $2.49/month.

## Decisions

1. **Free core, forever, no ads.** The practice loop, the adaptive model, all v1
   languages, the skill grid, local history. This is the product persona B evangelises.
2. **No payments in the MVP.** Ship, get a few hundred monthly users, then price-test.
3. **Pro is a one-time lifetime purchase, $15–25.** Never a subscription, never a
   time-limited licence. Price-test $15 / $19 / $25 on landing-page variants before
   charging anyone.
4. **Pro contents** (things persona B asked for that cost us server or build effort):
   accounts and cross-device sync; full history beyond 90 days; animated par replay;
   advanced tracks (tiers 7–9, 11–12) curriculum guidance; data export to CSV; the
   Neovim companion plugin when it exists.
   Never paywall: the adaptive loop, any language, the result strip, hints.
5. **GitHub Sponsors** link from day one (0% fee), framed as "buy me a coffee", no
   perks. Expect ~0.05% of visitors; it's a signal, not revenue.
6. **Merchant of record**: Polar (dev-focused, 5% + 50¢) or Paddle. Lemon Squeezy is
   migrating into Stripe. Non-EU sellers owe EU VAT from the first sale; an MoR handles
   it.
7. **Teams/education** is the only route to real money in this category (TypingClub's
   school seats). Not in scope until the consumer product has 1,000+ MAU; note it as
   the growth option.

## Stability gate (added 2026-10-13)

The author's first sessions found a drill that rejected a correct solution and pars
that could be shorter. A paid tier on top of that would earn refunds and the "slop"
label the research warned about. So pro is gated on measured stability, not on a date:

- The feedback loop in 11-feedback-loop.md has been live for at least 8 weeks.
- Over the last 4 weeks, fewer than 0.5% of counted attempts carry a `wrong-par` or
  `emulator` flag, and no ingested `beatPar` report has lowered a par in the last 2
  weeks (the idiom libraries have converged).
- Every `wording` flag older than 2 weeks is resolved or deliberately closed.
- At least 200 monthly active users, so the rates mean something.

Until then: free, no ads, GitHub Sponsors link only. The "tell me when pro exists" email
field stays. This supersedes the "price-test after a few hundred MAU" line below where
they conflict.

## Revenue model (planning numbers, not forecasts)

| MAU | pro conversion | lifetime buyers / month | at $20 |
|---|---|---|---|
| 500 | 1–3% | 5–15 | $100–300 |
| 2,000 | 1–3% | 20–60 | $400–1,200 |
| 5,000 | 1–3% | 50–150 | $1,000–3,000 |

Lifetime pricing means revenue tracks *new* users, not installed base. That is fine for
a side project and wrong for a business; we are building the former.

## Costs

Static hosting: $0. Domain: ~$15/yr. Accounts/sync (later): Cloudflare Workers + D1
free tier covers thousands of users. Fonts and CDN: $0. Payment fees: 5% + 50¢ per
sale. The only real cost is the author's time.

## Launch sequence

1. Dogfood 4 weeks (author only). Recalibrate the model.
2. Soft launch to 10–20 people from r/neovim who answer a "want to try an adaptive
   Vim trainer?" comment. Fix what they hit.
3. Show HN + r/neovim + r/vim post on the same day, free product only, with the
   supported-command list and the "pars verified by real Neovim" claim front and
   centre. Mention the VSCodeVim/IdeaVim tracks in the post body.
4. Collect emails only via "tell me when pro exists" (optional field).
5. Pro ships after launch feedback, not before.

## What we will not do

Ads in or near the practice area; a subscription; a time-limited licence; a $1 tier;
LLM-generated exercise content presented as curated; dark-pattern upsells inside the
loop; selling the exercise log.
