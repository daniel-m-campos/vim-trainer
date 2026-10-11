# Monetization economics: display ads + ~$1 premium tier for a small developer-audience web app (Vim-motions trainer)

Research date: 2026-10-11. All prices/fees below were read from the vendors' live pages on that date unless another date is given. Figures labeled "estimate" are my arithmetic on sourced inputs, not sourced numbers.

## Key Question 1: What would 10k / 50k / 200k monthly pageviews of developer traffic realistically earn from display ads, given adblock rates?

### Takeaway
Developer traffic is the most heavily ad-blocked audience online (52–72% depending on survey), and the developer-specific networks pay $2–3 CPM (EthicalAds) or an undisclosed share of a $6 advertiser CPM (Carbon). After adblock, a realistic planning range is roughly $5–50/month at 10k pageviews, $40–250/month at 50k, and $150–1,000/month at 200k; the two best-fit developer networks also gate entry at 10k (Carbon, by invitation) and 50k (EthicalAds) pageviews.

### Cited Findings

**Developer ad networks (rates and thresholds)**
- EthicalAds: "You earn 70% of what we charge advertisers"; "Most publishers on our network earn between $2.25 and $2.75 CPM", assuming "more than half of your audience is located in North America and Western Europe" — [EthicalAds revenue calculator](https://www.ethicalads.io/publishers/calculator/) (read 2026-10-11)
- EthicalAds publisher FAQ: "Your site needs at least 50,000 pageviews per month"; "publishers see around $2.50 per 1,000 pageviews (CPM)" assuming EU/NA traffic; AU/NZ similar, "rest of the world usually bring in less"; impressions count only when "in the viewport for a full second"; EthicalAds is "on some ad blocker allow lists such as Acceptable Ads which helps minimize ads being blocked" — [EthicalAds publisher FAQ](https://www.ethicalads.io/publishers/faq/) (read 2026-10-11)
- EthicalAds publisher guide: "actively seeking developer-focused sites with 50k+ monthly pageviews"; $50 minimum payout; paid via PayPal, OpenCollective, GitHub Sponsors or Stripe bank transfer; "EthicalAds should be the only ad on the page"; ad must be above the fold on desktop and mobile — [EthicalAds publisher guide](https://www.ethicalads.io/publisher-guide/) (read 2026-10-11)
- EthicalAds network scale: paid publishers $124,300 in January 2026, $161.8k in Q1 2026, projecting >$500k across 2026 — [EthicalAds newsletter April 2026](https://www.ethicalads.io/blog/2026/04/ethicalads-newsletter-april-2026/)
- Carbon Ads media kit: advertiser pricing "$6 CPM" for developer audience, "$5 CPM" for creator audience, with "Optimized ROW Blend" that excludes 20+ non-English countries; publisher revenue share not disclosed; network established 2010, 350+ sites — [Carbon Ads media kit](https://www.carbonads.net/more-info) (read 2026-10-11)
- Carbon Ads is invitation-only; applicants are judged on relevance, monthly pageviews, maintenance, and ability to meet placement/exclusivity terms; target audience is English-speaking developers/designers in US, Canada, Europe — [Carbon Ads FAQ](https://www.carbonads.net/faq)
- Third-party claim (aggregator, unverified): Carbon requires ~10,000 pageviews/month in Google Analytics and publishers "typically earn about $0.50–$1.10 CPM" — [monetizes.net Carbon Ads review](https://monetizes.net/networks/carbon-ads); the same site, when fetched directly, says revenue share is "not disclosed" and there is "no published minimum traffic figure", so treat the $0.50–$1.10 as low-confidence. Monthly PayPal payouts; single ad unit "caps earnings well below what header bidding or a managed partner like Mediavine could deliver at the same traffic" — [monetizes.net](https://monetizes.net/networks/carbon-ads)

**General networks (thresholds and tech-niche RPM)**
- Mediavine standard: 50,000 monthly sessions; Mediavine "Journey" tier: 10,000 sessions. Monumetric: 10,000 monthly pageviews. Ezoic: no minimum since 2023 — [Publift comparison](https://www.publift.com/blog/ezoic-vs-mediavine-vs-publift); [xpay.sh Ezoic vs Monumetric](https://www.xpay.sh/publishers/compare/ezoic-vs-monumetric/)
- Monumetric "Propel" tier (10k–80k pageviews) charges a one-time $99 setup fee; waived at higher tiers — [Blogging Explorer Monumetric review](https://bloggingexplorer.com/monumetric-review/); [Adgatescore](https://adgatescore.com/blog/monumetric-requirements)
- AdSense technology-niche page RPM estimates (aggregator, 2025 data): "Technology blogs average $5–$20 in AdSense Page RPM"; Tier-1 geo traffic reports RPM 40–120% higher than globally mixed traffic — [Techconda AdSense RPM benchmarks](https://www.techconda.com/2026/02/adsense-rpm-benchmarks.html)
- AdSense programming-tutorial anecdote (aggregator, Jan 2026): a programming-tutorials blog with ~100K monthly visits earned about $500/month from AdSense (implied ~$5 RPM); "Python tutorials" keywords $2–5 CPC vs "coding bootcamp" $15–25 CPC — [eastondev.com AdSense niches](https://eastondev.com/blog/en/posts/media/20260108-adsense-high-cpc-niches/)
- A different aggregator claims technology RPM $25–45 and "Software and SaaS" $30–65 — [adstimate.com](https://adstimate.com/blog/highest-paying-adsense-niches.html); this conflicts with the $5–20 figure above and with the $500/100k-visits anecdote, and has no stated methodology. I weight the lower range.

**Adblock rates for developers / tech audiences**
- Stack Overflow 2018 Developer Survey (100,000+ respondents, 183 countries): 72% of developers use ad blockers; 71% turn blockers off for specific sites, 45% of those "to support the website"; only 40% had ever clicked an online ad — [B2B Marketing summary of Stack Overflow data](https://www.b2bmarketing.net/majority-of-tech-developers-using-ad-blockers/) (survey year 2018; no newer developer-specific survey found)
- Aggregator claims (2026, methodology not shown): "52% of developers and tech professionals use ad blockers on desktop"; "Developer tools and SaaS sites see 40-60% of traffic blocked, the highest of any vertical measured" — [Scalify ad blocker stats](https://www.scalify.ai/blog/how-many-people-use-ad-blockers-impact-website-revenue-2026); [SQ Magazine](https://sqmagazine.co.uk/ad-blocker-usage-statistics/). Low-confidence: primary source not identified.
- General population baseline: 29.5% of internet users 16+ used an ad blocker in Q2 2025 (GWI/DataReportal); US 32.5%; US desktop 37% vs mobile 15%; men 49% vs women 33%; ages 18–24 at 41% — [Backlinko ad blocker statistics](https://backlinko.com/ad-blockers-users)
- eyeo (2025): 30.0% global block rate; ~1.1B ad-blocking users, 448M on desktop; desktop blocking declined 4% since 2023 while mobile grew 27% — [SignalBridge Data](https://www.signalbridgedata.com/blog/ad-blocker-statistics-2026)

**Operator anecdotes**
- Monkeytype (typing trainer, closest structural analog): funded by Patreon, Ko-fi, merchandise and optional ads that users must opt in to; founder says Monkeytype is "my primary 'job'"; 2M registered users and ~120,000 daily active users as of May 2023; no revenue disclosed — [kbd.news interview, 2023-05-19](https://kbd.news/Interview-3-years-of-Monkeytype-2019.html)
- Third-party traffic-estimator revenue guesses for monkeytype.com range from ~$4,800/month to ~$45,000/month in ad revenue — [siteworthtraffic](https://www.siteworthtraffic.com/report/monkeytype.com); these are formula estimates, not disclosures; I do not rely on them.
- HN 2015 anecdote: a free guestbook site's donations averaged ~$200/month (average donation $12) and "outperformed ad revenue" — [Ask HN: donations vs ads](https://news.ycombinator.com/item?id=10042204)

### Inferences
- Estimate (my arithmetic, inputs cited above). Assume 50% of developer pageviews are unblocked (midpoint of 40–60% blocked; Stack Overflow's 72% would be worse), and EthicalAds' $2.25–2.75 CPM applies to counted (viewed, unblocked) impressions:
  - 10k pageviews: below EthicalAds' 50k gate. Carbon (if accepted): 5,000 unblocked × $0.50–$1.10 = **~$3–6/month**; if Carbon's share is 50–70% of $6 CPM ($3.00–4.20), **~$15–21/month**. AdSense at $5–20 RPM on 5,000 counted views: **~$25–100/month**, lower if ads sit on a tool page rather than article pages.
  - 50k pageviews: EthicalAds 25,000 × $2.50 = **~$60/month** (range $55–70; roughly $110–140 if EthicalAds' "per 1,000 pageviews" already nets adblock, which their FAQ wording suggests but does not confirm). AdSense: **~$125–500/month**. Carbon: $12–100/month depending on the unknown share.
  - 200k pageviews: EthicalAds **~$250/month** (range $225–275; up to ~$500 under the alternate reading). AdSense **~$500–2,000/month**. Carbon ~$50–420/month.
- A Vim-motions trainer generates few pageviews per minute of use (one page, long sessions, keyboard focus). Ad RPMs above come from article-style content sites, so a single-page trainer should expect the low end of each range; EthicalAds' one-second-in-viewport rule helps a long-dwell page, but its one-ad-per-page and above-the-fold rules constrain layout.
- The developer-network CPMs ($2–3) are about half of the midpoint tech-niche AdSense RPM, but they are far less likely to be blocked (EthicalAds is on Acceptable Ads allow lists) and do not require consent banners/tracking, so the effective gap after adblock is narrower than the headline numbers.
- Given 45% of developers whitelist sites "to support the website" (2018), an explicit "ads are off by default, turn them on to support" model (Monkeytype's approach) is plausible for this audience but caps impressions at a small opt-in fraction.

### Gaps
- No post-2018 developer-specific adblock survey found; the 52% and 40–60% figures are from SEO aggregators without visible methodology.
- Carbon Ads' publisher revenue share and real payout CPM are undisclosed; only aggregator estimates exist. A first-hand Carbon vs Ezoic post (linguinecode.com) could not be fetched.
- Whether EthicalAds' "$2.50 per 1,000 pageviews" is per site pageview or per counted ad impression is ambiguous in their FAQ.
- No publisher has published ad revenue for a Vim/typing trainer specifically; Monkeytype does not disclose revenue.

## Key Question 2: What does a $1 sale net after fees on each processor, and at what price does a one-time purchase start to make sense?

### Takeaway
A $1 card sale nets $0.40–0.67 on every mainstream processor except PayPal Micropayments (~$0.90, approval required) and GitHub Sponsors from personal accounts (100%); merchant-of-record services net $0.45 or less. Fixed per-transaction fees stop dominating around $5 (85–91% retained) and are near-negligible at $10+, and Paddle explicitly treats sub-$10 products as a special case.

### Cited Findings

**Fee schedules (read 2026-10-11)**
- Stripe US: "2.9% + 30¢ per successful transaction"; +1.5% international cards; +1% currency conversion; Stripe Tax Basic 0.5% per transaction (no-code) or $0.50 per transaction (API) only where registered; Stripe Tax Complete from $90/month — [Stripe pricing](https://stripe.com/pricing)
- Stripe minimum charge: "Stripe enforces a minimum payment amount for all charges to make sure the Stripe fee doesn't exceed your charge" — 0.50 USD, 0.50 EUR, 0.30 GBP — [Stripe currencies docs](https://docs.stripe.com/currencies)
- Stripe Managed Payments (merchant of record): "adds 3.5% per successful transaction to your standard Stripe processing fees"; covers global indirect tax, fraud, disputes, Link customer support; aimed at SaaS/digital content/virtual goods — [Stripe Managed Payments](https://stripe.com/managed-payments). Third parties compute ~6.4% + 30¢ domestic, 7.9–8.9% + 30¢ international, with the 3.5% charged on the tax-inclusive amount; previewed Feb 2026, pricing "may change at general availability" — [Paritydeals](https://www.paritydeals.com/stripe-managed-payments-fees/); [aliteq](https://aliteq.com/stripe-managed-payments-fees-2026)
- Lemon Squeezy: 5% + 50¢ base; "+1.5% for international (outside of the US) transactions"; "+1.5% for PayPal transactions"; "+0.5% for subscription payments"; payouts free to US banks, 1% to non-US banks, PayPal payouts $0.50 (US) or 3% capped at $30 (non-US) — [Lemon Squeezy fees doc](https://docs.lemonsqueezy.com/help/getting-started/fees). Pricing page: $0/month, merchant of record, "We take on the liability of tax collection and calculation across all jurisdictions" — [Lemon Squeezy pricing](https://www.lemonsqueezy.com/pricing)
- Lemon Squeezy status: acquired by Stripe in 2024; CEO JR Farr's January 2026 update said support is slower and product updates fewer, with the stated goal of migrating users to Stripe Managed Payments; the 5% + 50¢ is described as legacy pricing — [Paritydeals](https://www.paritydeals.com/stripe-managed-payments-vs-lemon-squeezy-fees/); [Fungies](https://fungies.io/lemon-squeezy-stripe-acquisition-saas-founders-2026/)
- Paddle: "5% + 50¢ per Checkout transaction", no monthly fee, merchant of record; "If you're selling product with under 10$ value you can contact us for bespoke pricing" — [Paddle pricing](https://www.paddle.com/pricing)
- Polar: Starter "5% + 50¢"; Pro "3.8% + 40¢"; Growth "3.6% + 35¢"; Scale "3.4% + 30¢"; "+1.5% for international cards (non-US)"; Early Member plans +0.5% on subscriptions; payouts "$2 per month of active payout(s)" plus "0.25% + $0.25 per payout" and 0.25–1% cross-border; "$15 per dispute"; "Polar is the Merchant of Record"; paid plans replace the per-transaction MoR premium with a fixed monthly fee — [Polar fees docs](https://polar.sh/docs/merchant-of-record/fees). Organizations created before 2026-05-27 keep an Early Member rate of 4% + 40¢ — [Snagr comparison](https://www.snagr.sh/blog/polar-vs-lemon-squeezy-vs-gumroad)
- Gumroad: "10% + $0.50 per transaction" for direct sales; "30% per transaction" for marketplace-discovered sales; merchant of record since 2025-01-01 — [Gumroad pricing](https://gumroad.com/pricing). A third-party comparison adds ~3% payment processing on top of the 10% ($100 sale nets ~$87) — [veloxthemes](https://veloxthemes.com/blog/polar-vs-lemonsqueezy-vs-gumroad); the pricing page I read does not state whether processing is included, so treat the +3% as unconfirmed.
- Ko-fi: free plan 0% on one-off donations (only after switching off the default "Contributor" setting), 5% on shop, memberships and commissions; Gold $12/month removes the 5%; Stripe/PayPal processing fees apply on all plans — [Cartmango Ko-fi fees](https://cartmango.com/ko-fi-fees/); [Schoolmaker Ko-fi pricing](https://schoolmaker.com/blog/ko-fi-pricing). Ko-fi's own help page returned 403; these are secondary sources.
- GitHub Sponsors: "does not charge any fees for sponsorships from personal accounts, so 100% of these sponsorships go to the sponsored developer"; organizations pay up to 6% (3% card + 3% GitHub) — [GitHub Docs](https://docs.github.com/en/sponsors/getting-started-with-github-sponsors/about-github-sponsors)
- PayPal Micropayments: 5% + $0.05 for transactions under ~$10, "only available with explicit approval from PayPal"; on a $5 sale the standard fee is $0.64 vs $0.30 at the micropayment rate — [Checkoutpage PayPal fees 2026](https://checkoutpage.com/blog/paypal-fees); [Airwallex calculator](https://www.airwallex.com/en-us/paypal-fees-calculator)
- Liberapay takes 0% (only Stripe/PayPal processing) — [WPForms BMAC alternatives](https://wpforms.com/best-buy-me-a-coffee-alternatives/)

**Worked examples (estimate; my arithmetic on the fee schedules above; US domestic card, no VAT/sales tax added, no payout fees)**

| Processor (fee basis) | $1 sale net | $2 sale net | $5 sale net | $10 sale net |
|---|---|---|---|---|
| Stripe direct (2.9% + 30¢) | $0.67 (67%) | $1.64 (82%) | $4.56 (91%) | $9.41 (94%) |
| Stripe Managed Payments (~6.4% + 30¢) | $0.64 | $1.57 | $4.38 | $9.06 |
| Lemon Squeezy / Paddle / Polar Starter (5% + 50¢) | $0.45 (45%) | $1.40 (70%) | $4.25 (85%) | $9.00 (90%) |
| Lemon Squeezy, international card (6.5% + 50¢) | $0.44 | $1.37 | $4.18 | $8.85 |
| Polar Pro (3.8% + 40¢, excl. monthly fee) | $0.56 | $1.52 | $4.41 | $9.22 |
| Gumroad direct (10% + 50¢) | $0.40 (40%) | $1.30 | $4.00 (80%) | $8.50 |
| PayPal standard (~2.99% + 49¢) | $0.48 | $1.45 | $4.36 | $9.21 |
| PayPal Micropayments (5% + 5¢, approval needed) | $0.90 (90%) | $1.85 | $4.70 (94%) | $9.45 |
| Ko-fi tip via Stripe (0% + 2.9% + 30¢) | $0.67 | $1.64 | $4.56 | $9.41 |
| Ko-fi shop, free plan (5% + Stripe) | $0.62 | $1.54 | $4.31 | $8.91 |
| GitHub Sponsors, personal sponsor (0%) | $1.00 | $2.00 | $5.00 | $10.00 |

Notes on the table: Stripe's $0.50 minimum charge means a $0.49 price is impossible; Paddle asks sub-$10 sellers to negotiate bespoke pricing; Polar also deducts $2/month plus 0.25% + $0.25 per payout; MoR processors charge their percentage on the VAT-inclusive total in the EU/UK, so EU buyers at a $1 display price yield less than shown if the price is tax-inclusive.

### Inferences
- At $1 the fixed component dominates: an MoR keeps 55% of the sale, Stripe direct keeps 33%. At $5 the retained share rises to 85–91%; at $10 to 90–94%. The knee of the curve is around $4–5, which is where the per-transaction 30–50¢ falls below 10% of revenue.
- The only ways to make a literal $1 price net more than ~70% are PayPal Micropayments (requires PayPal approval and PayPal-only checkout) or routing "support" through GitHub Sponsors/Ko-fi tips (donations, not product sales, so no VAT handling but also no entitlement contract). Bundling (e.g., $5 for the same thing, or $12/year) is the simpler fix.
- Paddle's "contact us under $10" and Stripe's hard $0.50 floor are signals that the processor ecosystem is not designed for ~$1 digital goods.

### Gaps
- Polar Pro/Growth/Scale monthly platform fees were not on the fees page I fetched; only the per-transaction rates are confirmed. One aggregator says Polar Scale costs $597.20 at $15,800/month volume vs $890 on Paddle/Lemon Squeezy — [aliteq cheapest MoR](https://aliteq.com/cheapest-merchant-of-record) — but I could not verify the fixed fees.
- Gumroad: unclear from its pricing page whether card processing is inside or on top of 10% + 50¢.
- PayPal standard commercial rate (2.99% + 49¢) is from a fee-calculator site, not PayPal's own page.
- Ko-fi's own fee page could not be fetched (403); numbers are from two 2026 secondary sources that agree with each other.

## Key Question 3: What conversion rates do free-to-paid tiers see for small consumer dev tools, do $1 "test" tiers give a useful signal or anchor too low, and how do tip jars / pay-what-you-want perform?

### Takeaway
Developer-facing freemium converts about 1–3% of free users (general SaaS median 2–5%); donation buttons on free sites convert roughly 0.02–0.13% of visitors, and PWYW reduces purchase rates versus a low fixed price in controlled field experiments. The only Vim-specific data point (vim.so at $25) reports that raising the price left conversion "pretty much exactly the same", and multiple sources argue low anchors depress willingness to pay, so a $1 tier is likely to test the checkout flow rather than price sensitivity.

### Cited Findings

**Free-to-paid conversion**
- OpenView 2023 SaaS Benchmarks: median freemium conversion 2–5%; developer-focused products "often between 1-3%"; examples GitLab ~5%, Postman ~3%, MongoDB Atlas ~2%, GitHub pre-Microsoft ~10% (2.7M paying vs 28M free) — [Monetizely](https://www.getmonetizely.com/articles/whats-the-right-ratio-of-free-to-paid-users-in-developer-saas)
- "Conversion benchmarks for indie desktop tools sit at 0.5–3%"; a free tier converting under 3% is argued to be a cost center; median cost to support a free SaaS user is $1–5/month — [dev.to indie dev SaaS monetization](https://dev.to/kanta13jp1/indie-dev-saas-monetization-how-to-improve-free-to-paid-conversion-5dhk) (blog, not primary data)
- Price-change anecdote: developers raising prices "find that the conversion rate impact is smaller than feared"; one developer at $9/month learned a user's team saved ~$300/month of value — [dev.to pricing framework](https://dev.to/whoffagents/how-to-price-your-developer-tool-a-framework-that-maximizes-revenue-3d9h) (anecdotal)

**Vim-course case study**
- vim.so (interactive Vim course), $25 one-time, ~$10,000 total revenue as of April 2021; a prior 4-month Python course "made $0"; the HN post itself produced "$600 in sales"; author: "when I raised the price, the conversion rate stayed pretty much exactly the same" — [HN: How I made a profitable Vim course, 2021-04-15](https://news.ycombinator.com/item?id=26825566)
- Vim Adventures sold "6 months access" for $25; HN users argued for a one-time purchase instead — [HN thread, 2015](https://news.ycombinator.com/item?id=9250490); no revenue disclosed.

**Donations / tip jars**
- Blog experiment (Sept 2020): 4,000 visitors, 5 clicks on a Buy Me a Coffee button (0.125% click rate), 1 completed $3 donation; effective RPM $0.75; author: "a $0.75 RPM is a waste of prime screen real-estate"; most clickers abandoned on the BMAC page — [Shaun Poore](https://www.shaunpoore.com/conversion-rate-donation-buttons/)
- Indie Hackers report of 1 donation per 4,206 visitors (~0.024%) on Buy Me a Coffee — [Indie Hackers post](https://www.indiehackers.com/post/1-4206-conversion-rate-on-buy-me-a-coffee-1ed21a2288) (page returned 403 on fetch; figure from the title/search snippet)
- HN anecdotes on free dev tools: an app netting ~$5/week; a widely used Go HTML sanitizer getting ~$10/month from one donor; an NPM author with millions of weekly downloads earning ~$5.50/month on Patreon; a free online Mexican Train game earning $500–1,000/month purely from donations; "even the most popular and well-maintained open source software basically sees nothing from donation links" — [HN: Funding yourself as a free software developer](https://news.ycombinator.com/item?id=15970412); [HN: Sponsor the open source projects you depend on](https://news.ycombinator.com/item?id=35519706)
- Counter-example: a free guestbook site's donations averaged ~$200/month (avg $12 each) and beat its ad revenue — [HN 2015](https://news.ycombinator.com/item?id=10042204)

**Pay-what-you-want**
- Gneezy, Gneezy, Riener & Nelson (PNAS 2012, 109(19):7236–7240), cruise-ship photo field experiment: demand rose when price fell from $15 to $5, but "fewer people chose to buy the photo when they could choose how much to pay than when the price was $5", even though PWYW buyers could have paid $5; identity/self-image concerns predict PWYW payment amounts — [Springer summary of Gneezy et al.](https://link.springer.com/article/10.1057/s41272-018-00184-0); [paper PDF](https://marketing.wharton.upenn.edu/wp-content/uploads/2020/07/Pay-What-You-Want-PAPER-Gneezy-Ayelet-4-12-2012.pdf)
- Review literature: PWYW "will result in fewer purchases than a standard fixed price scheme" under some conditions; it can be more profitable "when the marginal cost is low and the deadweight loss is high" — [Schmidt, Spann & Zeithammer, PWYW can it be profitable?](https://www.sciencedirect.com/science/article/abs/pii/S2214804314000998); [integrative review](https://www.researchgate.net/publication/312006648_Pay-What-You-Want_pricing_An_integrative_review_of_the_empirical_research_literature)
- Radiohead "In Rainbows": 38% of downloads were paid, average $6.00 — [Tom Morkes](https://tommorkes.com/3-ways-pay-what-you-want-leads-to-more-profit-than-fixed-pricing/) (secondary)

**Low-price anchoring**
- App-store history: "$0.99 and $0 ... were the norm"; "the race-to-the-bottom strategy ... only erodes your product's value"; low perceived value "contributes to lower user retention and lower willingness to pay" — [Paddle blog on mobile pricing](https://www.paddle.com/blog/mobile-apps-saas-pricing)
- Experimental: advertising a low price "may backfire and reduce the price people are willing to pay"; a high anchor increases willingness to pay relative to a low anchor — [ResearchGate: anchoring, framing and WTP](https://www.researchgate.net/publication/327164185_The_Influence_of_Pricing_Strategies_on_Willingness_to_Pay_for_Accommodations_Anchoring_Framing_and_Metric_Compatibility)
- Subscription-app data: high-priced apps show median Year-1 LTV of $55.21 per paying subscriber, ~7x low-priced apps; apps that lead with the most expensive plan convert mid-tier at 2–3x — [Appalize](https://www.appalize.com/blog/monetization/how-to-price-your-app-subscription-data-driven-guide) (vendor blog)
- HN "Do people actually pay for small web tools?" (2025-05-20): commenters say "$5/month is a terrible price" for profitability; strong stated preference for "one-time $20-$25 payments" over "$5/month subscriptions"; one tool reports >150 subscribers at $6–10/month or $60–85/year with annual "by far the most popular plan" — [HN thread](https://news.ycombinator.com/item?id=44019193)
- Indie Hackers pricing lore: "most indie hackers are 50 to 200 percent underpriced"; lifetime deals "attract cheap customers"; LTDs should be priced at 14–16x the monthly fee — [Listen Up IH](https://www.listenupih.com/raise-your-prices/); [IH: I don't understand your lifetime deals](https://www.indiehackers.com/post/indie-hackers-i-dont-understand-your-lifetime-deals-ad389d4825)

### Inferences
- Estimate: at 1–3% free-to-paid and $1 net $0.45–0.67 (MoR vs Stripe), 1,000 monthly active users produce 10–30 sales and $5–20/month. At $5 the same conversion yields $43–137/month. For the $1 tier to beat ads at 50k pageviews (~$60–250/month) it would need several thousand monthly actives converting at the high end.
- A $1 price tests willingness to enter a card number, not willingness to pay; the Gneezy result (PWYW buyers declined to buy even though they could pay $5) and the anchoring literature suggest the price itself becomes part of the perceived value, and vim.so's experience is that in this exact niche conversion did not fall when the price rose to $25.
- Tip-jar conversion of ~0.02–0.13% of visitors means a tip jar at 50k pageviews yields roughly 10–60 clicks and a handful of completed $3–5 tips per month; comparable to or below the ad estimate for the same traffic.
- A free/supporter model where supporters pay $5–25 one-time (vim.so's $25, Vim Adventures' $25, HN commenters' $20–25 preference) has more precedent in this niche than a $1 tier.

### Gaps
- No controlled study found that compares $1 vs $5 vs $10 one-time prices for developer tools; the evidence is anecdotal (vim.so) plus general anchoring research.
- No published conversion data for Vim/typing trainers specifically; Monkeytype, Vim Adventures and vimtyper do not disclose revenue or conversion.
- The Indie Hackers Buy Me a Coffee post could not be fetched directly; the 1/4,206 figure is from its title.

## Key Question 4: Which processors act as merchant of record (handle VAT/sales tax), what do they charge, and what is the tax burden if you do not use one?

### Takeaway
Paddle, Lemon Squeezy, Polar, Gumroad (since Jan 2025) and Stripe Managed Payments (2026) are merchants of record; they cost roughly 5% + 50¢ (or ~6.4% + 30¢ at Stripe) versus Stripe direct at 2.9% + 30¢, i.e. an MoR premium of ~2–3.5 points plus 20¢. Without an MoR, a non-EU seller owes destination-country VAT on EU B2C digital sales from the first euro (the €10,000 threshold applies only to sellers established in one EU state) and must register via OSS or a non-Union scheme.

### Cited Findings
- Merchant-of-record status confirmed on vendor pages: Lemon Squeezy ("We take on the liability of tax collection and calculation across all jurisdictions") — [Lemon Squeezy pricing](https://www.lemonsqueezy.com/pricing); Paddle ("payments, billing, tax compliance") — [Paddle pricing](https://www.paddle.com/pricing); Polar ("Polar is the Merchant of Record") — [Polar fees](https://polar.sh/docs/merchant-of-record/fees); Gumroad (MoR since 2025-01-01, "handles ALL your tax obligations") — [Gumroad pricing](https://gumroad.com/pricing); Stripe Managed Payments (global indirect tax, disputes, support for +3.5%) — [Stripe](https://stripe.com/managed-payments)
- Not MoR: Stripe direct (Stripe Tax calculates but you remain liable and must register: 0.5% or $0.50/transaction where registered, or $90+/month) — [Stripe pricing](https://stripe.com/pricing); Ko-fi, GitHub Sponsors, Liberapay (donation platforms; recipient reports income) — [GitHub Docs](https://docs.github.com/en/sponsors/getting-started-with-github-sponsors/about-github-sponsors)
- EU VAT on B2C digital services: charged at the customer's country rate; EU-wide €10,000/year cross-border threshold "requires establishment in exactly one Member State"; above it (or for non-EU sellers, from the first sale) you register once in one country and file one quarterly OSS return instead of 27 registrations — [Dodo Payments EU VAT guide 2026](https://dodopayments.com/blogs/eu-vat-saas-guide-2026); [Fungies OSS guide](https://fungies.io/eu-vat-oss-scheme-saas/); [vatcalc](https://www.vatcalc.com/eu/eu-vat-on-b2c-digital-services-after-1-july-2021-moss-oss/)
- MoR description: "The MoR is the legal seller of record, charges VAT at the correct rate, files the OSS returns, and handles audits" — [Dodo Payments](https://dodopayments.com/blogs/eu-vat-saas-guide-2026)
- Cost comparison on a $100 sale: Gumroad nets ~$87, Lemon Squeezy ~$92, Polar ~$92 — [veloxthemes](https://veloxthemes.com/blog/polar-vs-lemonsqueezy-vs-gumroad); Stripe Managed Payments $6.70 vs Lemon Squeezy $5.50, with SMP costing more above ~$14/transaction — [Paritydeals](https://www.paritydeals.com/stripe-managed-payments-vs-lemon-squeezy-fees/)
- Lemon Squeezy is winding toward migration to Stripe Managed Payments (CEO update, January 2026) — [Paritydeals](https://www.paritydeals.com/stripe-managed-payments-vs-lemon-squeezy-fees/)

### Inferences
- Estimate: at ~$1 sales the MoR premium is about 20¢ of fixed fee plus 2.1 points: Stripe direct nets $0.67 vs MoR $0.45, so an MoR costs ~33% of your net at $1 but only ~7% at $5 and ~4% at $10. For a solo developer, the alternative (OSS registration, quarterly returns, UK and other non-EU regimes, US state nexus tracking) is a recurring compliance task with real penalty risk; at the revenue levels implied by Q1–Q3 (tens to low hundreds of dollars a month) the MoR premium is a few dollars a month and almost certainly cheaper than the time.
- If the paid feature is framed as a donation/sponsorship (GitHub Sponsors, Ko-fi tips) there is no VAT-able supply and no MoR needed, but you also cannot reliably gate features behind it and GitHub Sponsors requires a GitHub account from the payer.
- Platform risk: Lemon Squeezy is in a transition; Polar and Paddle are the stable MoR options for a new small product today, and Paddle wants a conversation for sub-$10 items.

### Gaps
- No primary EU source fetched; the OSS/threshold facts come from three consistent 2026 vendor guides.
- UK VAT (no threshold for non-UK sellers of digital services) and US state sales-tax thresholds for digital goods were not researched.

## Key Question 5: Case studies of small dev-tool or learning sites reporting revenue

### Takeaway
Reported numbers for small developer-facing tools cluster in the $500–1,000/month range for products that charge $5–25, come mostly from one-time or annual pricing, and the one Vim product with disclosed revenue (vim.so) made ~$10k total at $25. No free developer learning tool was found reporting meaningful ad revenue; the richest analog, Monkeytype, is donation/opt-in-ad funded and undisclosed.

### Cited Findings
- vim.so: $25 one-time, ~$10,000 lifetime revenue by April 2021; HN launch day $600; raising price did not change conversion — [HN 2021-04-15](https://news.ycombinator.com/item?id=26825566)
- Ask HN "Those making $500+/month on side projects in 2024" (Jan 2024): Quastor newsletter >$500/month at $12/month; Bear Blog >$500/month at ~$5/month; Zest UI (Rails component kit) crossed $500/month on one-time purchases; Mockoon (open-source API mocking, 500k+ downloads) ~$1,000/month via sponsorships and SaaS — [HN thread](https://news.ycombinator.com/item?id=38935714)
- Ask HN "Do people actually pay for small web tools?" (2025-05-20): a Kindle-to-article tool with >150 subscribers at $6–10/month or $60–85/year; OnlineTools.com cited at ~$6/month annual; consensus that $5/month is too low to build on and users prefer one-time $20–25 — [HN thread](https://news.ycombinator.com/item?id=44019193)
- Indie Hackers: NicheTools, $99 one-time plus recurring plans, ~$30,000 cumulative; TinyOwl (Mac image compressor) $9 one-time — [Indie Hackers subscriptions vs one-time](https://www.indiehackers.com/post/subscriptions-vs-one-time-payments-a-developers-honest-take-f153e48960) (post itself returned 403; figures from search snippet)
- Monkeytype: one-person project, "primary job", 120k DAU (May 2023), funded by Patreon, Ko-fi, merch, opt-in ads; revenue undisclosed — [kbd.news](https://kbd.news/Interview-3-years-of-Monkeytype-2019.html)
- Open-source donation reality: ~$5/week, ~$10/month, ~$5.50/month anecdotes for widely used free libraries — [HN](https://news.ycombinator.com/item?id=15970412); outlier: free browser game at $500–1,000/month in donations — [HN](https://news.ycombinator.com/item?id=35519706)
- EthicalAds as a network paid all its publishers combined $124,300 in January 2026 — [EthicalAds](https://www.ethicalads.io/blog/2026/04/ethicalads-newsletter-april-2026/); with "350+" sites on Carbon and an undisclosed count on EthicalAds, the average developer-network publisher earns on the order of hundreds of dollars a month (estimate).

### Inferences
- The disclosed successes in this space charge $9–25 one-time or $5–12/month and reach $500–1,000/month; none report success from a ~$1 price or from display ads alone.
- A reasonable planning model for a Vim trainer at 50k pageviews/month: ads $60–250/month (Q1), tips a few dollars to a few tens (Q3), and a $5–25 one-time "pro" tier at 1–3% of actives as the only lever that scales with engagement rather than pageviews.

### Gaps
- No open-startup dashboard for a Vim/typing/keyboard-skills product was found; no "Show HN" revenue follow-up for a Vim trainer exists in search results.
- Monkeytype, Vim Adventures, vimtyper, VimDrill: no revenue disclosures found.
