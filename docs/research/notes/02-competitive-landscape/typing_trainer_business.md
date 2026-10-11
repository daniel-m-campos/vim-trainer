# Typing-trainer sites as businesses (keybr, monkeytype, typing.com, typingclub, 10fastfingers, typeracer, nitrotype, ratatype)

Research date: 2026-10-11. All prices and traffic figures are as found on that date unless a different date is stated. Figures labelled "estimate" come from third-party traffic estimators, not from the operators.

## Key question 1: How does keybr pick the next lesson and chart progress? Is its source open and under what licence?

### Takeaway
keybr is open source under AGPL-3.0 (4.8k GitHub stars). The algorithm is simple and fully inspectable: each key gets a confidence score `targetTime / EMA(timeToType)` with alpha 0.1 and a default target of 175 CPM (35 WPM); the first 6 letters are always unlocked, the next letter unlocks once every included key has hit confidence 1.0 at least once, and every lesson word is forced to contain the single weakest unlocked key. Progress prediction fits a polynomial (linear/quadratic/cubic by sample count) over the last 30 lessons and projects up to 50 lessons ahead, only when R² >= 0.5.

### Cited Findings
- Licence is GNU Affero General Public License v3.0; repo has 4.8k stars; stack is Node.js/TypeScript, Webpack, Docker, GitHub Actions; the README describes "personalized lessons focused on weaker keys", per-key statistics, and predicted time to reach a speed goal — [GitHub aradzie/keybr.com](https://github.com/aradzie/keybr.com)
- Per-key confidence = `targetTime / EMA(timeToType)`; EMA alpha = 0.1; default target 175 CPM (35 WPM); confidence 1.0 = mastered; only error-free keystrokes feed the EMA; accuracy does not affect unlocking; no minimum sample count, so a key can unlock after one fast lesson — [velvet issue #5 (third-party analysis of keybr source)](https://github.com/pauldavidkelly/velvet/issues/5)
- `keystats.ts` confirms `makeFilter(0.1)` for the EMA, tracks `filteredTimeToType`, keeps `bestTimeToType = min(best, filtered)`, ignores samples with `timeToType <= 0`, records `hitCount` / `missCount` per sample — [keybr-result/lib/keystats.ts](https://github.com/aradzie/keybr.com/blob/master/packages/keybr-result/lib/keystats.ts)
- `guided.ts`: `minSize = 6`; `maxSize = 6 + (total_letters - 6) * alphabetSize_setting`; keys below maxSize are force-included; beyond that a key is included only when all earlier keys have confidence >= 1.0; the `recoverKeys` setting switches between "now above the target speed" (current confidence) and "were once above the target speed" (best historical confidence). Focus letter = included key with the lowest confidence < 1.0 (`lessonKeys.focus(weakestKeys[0].letter)`) — [keybr-lesson/lib/guided.ts](https://github.com/aradzie/keybr.com/blob/master/packages/keybr-lesson/lib/guided.ts)
- Letter unlock order follows language letter frequency (e, n, i, t, r, l, s, a...), optionally reordered to favour home-row keys; no persistent "unlocked" flag is stored, inclusion is recomputed before every lesson — [velvet issue #5](https://github.com/pauldavidkelly/velvet/issues/5)
- Word generation: phonetic (Markov-style) pseudo-words from the language model; optional "natural words" fetches up to 1,000 dictionary words restricted to unlocked letters and containing the focus letter; if fewer than 15 natural words match, pseudo-words fill in; capitals and punctuation are probability sliders, not gated keys; `generateFragment()` applies capitalization, punctuation and repetition settings — [guided.ts](https://github.com/aradzie/keybr.com/blob/master/packages/keybr-lesson/lib/guided.ts); [velvet issue #5](https://github.com/pauldavidkelly/velvet/issues/5)
- Lesson score formula: `cpm * distinctChars / (errors + 1) * length / 50`, so one error roughly halves the score — [velvet issue #5](https://github.com/pauldavidkelly/velvet/issues/5)
- Learning rate / "lessons remaining": regresses speed (from `filteredTimeToType`) against lesson index over the latest break-free session, max 30 samples (`samples.slice(-30)`); cubic fit if > 20 samples, quadratic if > 10, else linear; iterates forward up to 50 lessons to find when the curve crosses the target; only reports `learningRate`, `certainty`, `remainingLessons` when R² (`certainty`) >= 0.5, otherwise NaN — [keybr-lesson/lib/learningrate.ts](https://github.com/aradzie/keybr.com/blob/master/packages/keybr-lesson/lib/learningrate.ts)
- User sentiment on the algorithm (HN, 2022): praised for "fixing my weak spots fast"; main complaint is "many of the words are made up, which means I have to think more about individual letters" — [HN thread 31097516](https://news.ycombinator.com/item?id=31097516)
- Some users report that workarounds can artificially boost confidence (algorithm gaming) — [search summary citing HN/keybr group](https://news.ycombinator.com/item?id=31097516)

### Inferences
- The whole adaptive loop is about four ideas (per-item EMA of latency, confidence ratio against a target, unlock gate on all-items-mastered, bias generation toward the weakest item). It ports directly to Vim motions: replace "key" with "motion", "timeToType" with "time to complete the edit", and "dictionary word containing focus letter" with "edit task requiring the focus motion".
- The "no minimum sample count" and "accuracy does not gate unlock" choices are known weaknesses users exploit; a Vim trainer could add a minimum-sample and accuracy gate (as ngram-type does: 40 WPM and 100% accuracy defaults).
- AGPL-3.0 means code can be studied freely, but reusing it in a closed hosted product would trigger the network-copyleft clause. Reimplementing the (simple) ideas avoids that.

### Gaps
- Could not load keybr.com/help directly (page is client-rendered); algorithm details come from source code and a third-party source analysis, not from keybr's own prose docs.
- The `@keybr/math` confidence helper was not read directly; the confidence formula is corroborated by the third-party analysis only.

## Key question 2: What do these sites charge, and what is behind the paywall?

### Takeaway
Consumer paywalls are almost all "remove ads + cosmetics + data retention", priced from about $2.49/month (Nitro Type Gold) to $9.99/month (Ratatype), or $20/year (TypeRacer) to $49.99/year (Ratatype). Only keybr sells a one-time lifetime ad-removal (reported at ~US$13-14, secondary sources). The large operators (Typing.com, TypingClub/edclub) make their real money from schools at roughly $1-10 per student per year with 20-seat minimums.

### Cited Findings
- keybr: free with ads; premium is a single lifetime payment that removes ads and trackers and gives "quick loading time of pages"; reported price S$12.88 one-time — [startyouronlinejobs blog, Jul 2025](https://startyouronlinejobs.blog/2025/07/10/typing/); another third party reports "$14 lifetime to remove ads and support the project" — [Typing Monkey listing](https://typingmonkey.app/r/833/keybr-com-free). Review sites as of Jul 2026 still describe keybr simply as "completely free to use" — [Educational App Store, updated 2026-07-20](https://www.educationalappstore.com/website/keybr)
- keybr history: in May 2015 the author ("Alex") rejected a subscription, saying "My plan is to sell it [a desktop app]... This will remove the ads from the web site too" and that he wanted to "give people a product in exchange for money"; users were still asking for a paid ad-free option in Aug-Sep 2018, one noting ads were "lagging the typing speed" — [keybr Google Group "Pay to remove ads"](https://groups.google.com/g/keybr/c/PsYcvOkJyWE); more users asked again Oct 2019-Jan 2020 for donations / one-time / annual ad removal — [keybr Google Group "im using adblocker..."](https://groups.google.com/g/keybr/c/DaxclxCNaJQ)
- Monkeytype: no paywall at all; funding via Patreon, Ko-Fi, merch, and opt-in ads with three levels ("Result" = one ad on result page, "on" = floating vertical banners, "sellout" = multiple ads on every page) — [kbd.news interview, 2023-05-19](https://kbd.news/Interview-3-years-of-Monkeytype-2019.html); [cosmickeys review](https://cosmickeys.app/en/blog/monkeytype-review); [GitHub monkeytypegame/monkeytype](https://github.com/monkeytypegame/monkeytype)
- Typing.com: free plan has unlimited students/classes, all lessons, games, reporting, SSO; Premium removes ads, adds unlimited data retention, transferable seats, priority support; "pricing varies by individual, classroom, school-wide, or district-wide plan"; 50+ users get custom volume pricing — [spotsaas](https://www.spotsaas.com/product/typing-com/pricing). Third parties quote $7.99/student/year at home, $9.59/student/year for teacher upgrades, "as low as $1.14 per student" for school accounts — [numaschool](https://numaschool.com/learn/glossary/typing-com); [search summary](https://www.commonsense.org/education/reviews/typingcom). Popular Science (Jun 2023) listed "one-time payment starting at $8" — [PopSci](https://www.popsci.com/free-web-apps-speed-typing/)
- TypingClub / edclub: individual Premium 7.50 EUR/month or 29.50 EUR/year (2.46 EUR/month) — [typingclub plans page](https://www.typingclub.com/sportal/plans.html); PopSci (2023) listed $8.50/month or $78/year — [PopSci](https://www.popsci.com/free-web-apps-speed-typing/). School Pro: minimum 20 student licences at $120/year for TypingClub, or $290/year for all edclub products — [edclub licensing FAQ](https://s.typingclub.com/docs/faq/licensing-purchasing.html); Pro adds custom lessons, ad removal, attempt playback, advanced reporting, unlimited students/classes/instructors (Free: 3 classes / 2 instructors), data retention beyond 30 days, DPA/COI, 60-day trial, 10%/15% off for 2/3-year terms — [edclub pricing](https://www.edclub.com/pricing)
- TypeRacer: Premium $20/year (30% off promo Sep 2023); perks: no ads, custom avatars, CSV export of all scores, save practice scores, profile picture / about-me, message and friend any user, "Racer" level label, premium badge on scorecard — [TypeRacer wiki](https://typeracer.fandom.com/wiki/Premium_Account); [TypeRacer blog Sep 2023](https://blog.typeracer.com/2023/09/13/try-out-typeracer-premium-absolutely-free-for-1-month-back-to-school-special/); premium introduced Aug 2010 — [TypeRacer blog 2010](https://blog.typeracer.com/2010/08/13/premium-accounts-and-experience-levels/); TypeRacer also sells a Schools product — [TypeRacer Schools sheet (PDF)](https://data.typeracer.com/public/docs/TRSchoolsProductSheet.pdf)
- Nitro Type Gold: monthly only since 2025-12-20, at $2.49, $2.99 or $3.99/month "randomly assigned for each individual account" (i.e. live price testing); annual was $19.99/year from Sep 2019 to Dec 2025 — [Nitro Type wiki](https://nitro.fandom.com/wiki/Gold_Membership)
- Ratatype Plus: $49.99/year ($4.17/month) or $9.99/month, auto-renewing; adds unlimited exercises, no ads, certificates, dark mode, extra "Dino" hero, faster page loads; no ads-only tier — [Ratatype Plus page](https://www.ratatype.com/ratatype-plus/); classroom add-on exists — [Ratatype Plus for classes](https://www.ratatype.com/ratatype-plus-for-classes/)
- 10FastFingers: free with ads; no official premium tier found as of 2026; reviewers describe the free tier as "ad-heavy" — [cosmickeys 10FastFingers review](https://cosmickeys.app/en/blog/10fastfingers-review); [typingfix comparison](https://typingfix.com/blogs/typingfix-vs-10fastfingers)
- Smaller trainers (PopSci, Jun 2023): The Typing Cat $4.50/month or $32/year; TypingAcademy from $2/month — [PopSci](https://www.popsci.com/free-web-apps-speed-typing/)

### Inferences
- The consumer "premium" in this category is essentially an ad-removal fee with cosmetic extras; nobody gates the core learning loop (keybr, typing.com, typingclub all keep lessons free). Unlimited history/data retention is the one non-cosmetic feature that recurs (Typing.com, TypingClub, TypeRacer CSV export).
- Nitro Type's randomized $2.49-$3.99 monthly price is the closest thing to a published low-price experiment; it is the only site found actively A/B testing price.
- keybr's lifetime one-off (~$13-14) is the model closest to a "tiny-price premium" and it took the author 4+ years of user requests (2015 to at least 2020) to ship it.

### Gaps
- keybr's official premium price could not be read from keybr.com (account page is client-rendered); the S$12.88 and US$14 figures are secondary and may be stale.
- Typing.com's current individual price could not be read from typing.com/student/upgrade (client-rendered); the $7.99-$9.59 figures are third-party.
- TypingClub school per-seat price beyond the 20-seat minimum requires their quote calculator.

## Key question 3: Public numbers on traffic, ad revenue, premium conversion or donations

### Takeaway
Traffic is large (Monkeytype ~14M visits/month, Typing.com ~12M, TypingClub ~6M, Nitro Type and 10FastFingers ~4M each, keybr ~3.6M, TypeRacer ~2.4M; Similarweb estimates, May-Aug 2026). Donation revenue is tiny relative to traffic: Monkeytype's Patreon shows ~96-110 paid members paying ~$167-195/month total despite ~120k daily actives, implying a donor conversion well under 0.1%. No operator publishes ad revenue or premium conversion.

### Cited Findings
- Similarweb-derived monthly visits, May 2026: Monkeytype 13.9M, Typing.com 12.4M, TypingClub 6.3M, Nitro Type ~4M, 10FastFingers ~4M, keybr 3.6M, TypeRacer 2.4M (estimates) — [TypoTrainer blog citing Similarweb](https://typotrainer.lukadevv.com/blog/best-typing-practice-tools)
- Similarweb, Aug 2026: Typing.com ranked #41 in Education and #2820 globally; monkeytype.com global rank moved from 6,257 to 5,614 over three months (estimates) — [Similarweb typing.com](https://www.similarweb.com/website/typing.com/); [Similarweb monkeytype.com](https://www.similarweb.com/website/monkeytype.com/)
- Monkeytype scale (May 2023): 2M registered users, ~120,000 daily active users, 819M tests started / 278M completed; Miodec works on it full time as his "primary job", solo, from the UK; won Semrush Awards 2022 (1M-10M traffic range); no revenue figures disclosed; "the greatest thing everyone can do is just share the site" — [kbd.news interview 2023-05-19](https://kbd.news/Interview-3-years-of-Monkeytype-2019.html)
- Monkeytype Patreon (fetched 2026-10-11): 806 members, 96 paid, $167.30/month — [Patreon monkeytype](https://www.patreon.com/monkeytype/about); a search snapshot earlier showed 713 members / 110 paid / $194.60 per month (same page, earlier date) — [search summary](https://www.patreon.com/monkeytype/about)
- Monkeytype GitHub: 20.9k stars (snapshot in search; the fork page cited), 0 GitHub Sponsors shown for Miodec — [yhype Miodec profile](https://yhype.me/github/@miodec); [GitHub monkeytype](https://github.com/Miodec/monkeytype)
- Monkeytype users complained ads were "more annoying than they need to be" (GitHub issue #928) — [monkeytype issue 928](https://github.com/Miodec/monkeytype/issues/928)
- Typing.com / Teaching.com revenue: Latka estimates "$86.4M revenue" and "785 person team" for 2025, bootstrapped (estimate, methodology unclear) — [getlatka typing.com](https://getlatka.com/companies/typing.com); ZoomInfo lists Teaching.com at "<$5M revenue, 11-50 employees" and Nitro Type at "<$5M, 1-10 employees" (estimates; conflicts sharply with Latka) — [ZoomInfo Teaching](https://www.zoominfo.com/c/teaching/454172672); [ZoomInfo Nitro Type](https://www.zoominfo.com/c/nitro-type/368392922)
- Nitro Type claims "over 40 million users", "millions of races daily", and Teaching.com reaches "75 million students and 1.7 million educators"; founder Austin Butler started as a school lab assistant — [Teach Your Kids Substack](https://teachyourkids.substack.com/p/the-lab-assistant-who-turned-typing)
- TypeRacer hit 1 million users at its 5th anniversary (Aug 2013) — [TypeRacer blog 2013](https://blog.typeracer.com/2013/08/08/typeracer-5th-anniversary-and-1-million-users/)
- keybr: no public traffic, ad revenue or premium numbers from the author found; the only revenue signal is the author's 2015 statement that he preferred selling a product to a subscription — [keybr group](https://groups.google.com/g/keybr/c/PsYcvOkJyWE)

### Inferences
- Donations convert terribly even for a beloved product: ~100 paying patrons out of ~120k DAU is under 0.1% of daily users (estimate based on the two figures above). Monkeytype's full-time livelihood therefore most likely rests on opt-in ads and merch, not Patreon, though this is inferred.
- The two Teaching.com revenue estimates differ by >15x; treat both as unreliable. The direction (schools B2B being the real business) is consistent across sources.
- At ~3.6M visits/month, keybr is a mid-sized ad property; a Vim-motions trainer addresses a far smaller audience (developers who use Vim), so ad revenue alone will be proportionally small.

### Gaps
- No operator publishes ad RPM, premium conversion, or churn. No Indie Hackers / HN posts by the keybr, 10FastFingers, TypeRacer or Ratatype founders with revenue were found.
- Monkeytype's Ko-Fi and merch income not found.

## Key question 4: Lessons indie developers of typing/skill trainers share about monetization

### Takeaway
Few founder write-ups exist. The clearest signals: Monkeytype's creator chose opt-in ads plus donations and treats word-of-mouth as the main growth lever; keybr's author resisted subscriptions for years in favour of a one-time product sale; TypeRacer waited two years after launch (2008 to 2010) before adding a $20/year premium; and the only operator visibly testing prices (Nitro Type) dropped annual plans in favour of monthly in Dec 2025.

### Cited Findings
- Miodec: funding is "Patreon, Ko-Fi, by buying merch or by enabling ads", all optional; growth advice is "share the site with their friends"; he develops full time, solo, with open-source contributors — [kbd.news interview 2023](https://kbd.news/Interview-3-years-of-Monkeytype-2019.html)
- Monkeytype keeps ads opt-in and even jokes about it ("sellout" mode shows ads on every page) — [cosmickeys review](https://cosmickeys.app/en/blog/monkeytype-review)
- keybr author (May 2015): "My plan is to sell it... I want to give people a product in exchange for money" rather than a subscription; users countered that desktop apps hurt Linux/multi-device users and kept asking for a web ad-free tier through 2018-2020 — [keybr group](https://groups.google.com/g/keybr/c/PsYcvOkJyWE); [keybr group 2019](https://groups.google.com/g/keybr/c/DaxclxCNaJQ)
- Users explicitly said ads hurt the core experience ("lagging the typing speed") and that they resorted to adblockers despite willingness to pay — [keybr group](https://groups.google.com/g/keybr/c/PsYcvOkJyWE)
- TypeRacer introduced premium accounts and XP levels in Aug 2010 — [TypeRacer blog](https://blog.typeracer.com/2010/08/13/premium-accounts-and-experience-levels/); runs seasonal promos (30% off, free month, Sep 2023) — [TypeRacer blog 2023](https://blog.typeracer.com/2023/09/13/try-out-typeracer-premium-absolutely-free-for-1-month-back-to-school-special/)
- Nitro Type: annual Gold ($19.99) removed 2025-12-20; now only monthly at per-account randomized $2.49/$2.99/$3.99 — [Nitro Type wiki](https://nitro.fandom.com/wiki/Gold_Membership)
- General indie context: Stripe-verified Indie Hackers data shows median product revenue in the tens of dollars per month, with ~5% above ~$8,000/month — [HN thread on verified IH revenue](https://news.ycombinator.com/item?id=32151172)
- A newer entrant, "Monkey Type for Devs", posted a Show HN in 2026, signalling continuing indie interest in developer-targeted typing tools — [Show HN](https://news.ycombinator.com/item?id=48110104)

### Inferences
- Ads on a latency-sensitive practice UI are a known pain point (keybr users, Monkeytype issue #928). An ad-free tier sells best when ads measurably degrade the practice loop, which argues for placing ads outside the typing area (results page, sidebar) as Monkeytype does.
- The successful solo operator (Monkeytype) never built a paywall; the one that did (keybr) kept it to a single lifetime fee. For a niche Vim trainer with a developer audience, a one-time lifetime "no ads + stats history" purchase mirrors the only proven consumer model in this category.

### Gaps
- No Indie Hackers or HN founder post with hard revenue for a typing trainer was found; "TypingMind" results in IH searches are an unrelated AI chat product.
- The keybr author's statements after 2015 (when premium actually shipped, and why) were not found.

## Key question 5: Does any site use a very low price point (~$1) or pay-what-you-want, and how did it go?

### Takeaway
No typing trainer sells a ~$1 consumer tier or pay-what-you-want. The lowest found are Nitro Type Gold at $2.49/month (randomized up to $3.99) and Typing.com's school seats at "as low as $1.14 per student" per year. keybr's reported ~$13-14 lifetime one-off is the lowest total-cost consumer option. Monkeytype's donation model is effectively pay-what-you-want and yields on the order of $170-195/month from ~100 patrons.

### Cited Findings
- Nitro Type Gold: $2.49 / $2.99 / $3.99 per month, price randomized per account — [Nitro Type wiki](https://nitro.fandom.com/wiki/Gold_Membership)
- Typing.com school ad removal "as low as $1.14 per student" (annual, school accounts) vs $7.99 at home — [search summary / Common Sense](https://www.commonsense.org/education/reviews/typingcom)
- TypingAcademy from $2/month (2023) — [PopSci](https://www.popsci.com/free-web-apps-speed-typing/)
- keybr lifetime one-off reported at S$12.88 (~US$9.50) or US$14 (secondary sources) — [startyouronlinejobs](https://startyouronlinejobs.blog/2025/07/10/typing/); [Typing Monkey](https://typingmonkey.app/r/833/keybr-com-free)
- keybr users in 2015 themselves proposed "$1-3/month" subscriptions modelled on Ars Technica — [keybr group](https://groups.google.com/g/keybr/c/PsYcvOkJyWE)
- Monkeytype Patreon (pay-what-you-want style): 96 paid of 806 members, $167.30/month (2026-10-11) — [Patreon](https://www.patreon.com/monkeytype/about)

### Inferences
- The absence of a ~$1 tier across eight sites is itself informative: payment-processor fixed fees (roughly $0.30 + 3% on Stripe-type processors) eat most of a $1 charge, which is presumably why the lowest-priced operator (Nitro Type) sits at $2.49 and bundles monthly. A $1 one-off is viable only if the processor fee is acceptable as a cost of goodwill, or if the price is set per year rather than per month.
- Nitro Type's per-account randomized $2.49-$3.99 suggests its operator found demand elastic enough in that range to keep testing; the removal of the $19.99 annual option suggests monthly recurring outperformed annual for them (inferred, not stated).

### Gaps
- No published result of a pay-what-you-want experiment in this category. No data on how keybr's lifetime premium converts.
- Processor-fee reasoning above is inference, not sourced from any operator.

## Key question 6: What users praise or complain about (cross-site)

### Takeaway
keybr is praised for fast weak-spot repair and analytics, criticised for pseudo-words and gameable unlocks; Monkeytype for minimalism and customization, criticised for ad placement and lack of lesson structure; Typing.com/TypingClub for structured beginner curricula; TypeRacer/Nitro Type for competitive motivation; 10FastFingers for ad-heaviness.

### Cited Findings
- keybr pros: "intelligent adaptive learning algorithm", "excellent progress analytics", "natural word generation improves muscle memory"; cons: "limited gamification", desktop-only, beginner guidance "could be more interactive" — [Educational App Store, 2026-07-20](https://www.educationalappstore.com/website/keybr)
- keybr: "really good at fixing my weak spots fast" vs "many of the words are made up" (HN 2022) — [HN 31097516](https://news.ycombinator.com/item?id=31097516)
- Monkeytype: "minimalist, highly customizable", preferred by "intermediate to elite typists"; keybr "targets your weakest key combinations"; TypeRacer "real-time multiplayer races"; Typing.com "lesson plans" for beginners; TypingClub "structured visual guides" — [TypoTrainer blog](https://typotrainer.lukadevv.com/blog/best-typing-practice-tools)
- Monkeytype has no unlocking/curriculum; useful mainly for metrics (WPM, raw, accuracy, consistency) — [velvet issue #5](https://github.com/pauldavidkelly/velvet/issues/5)
- Monkeytype ad complaint: issue #928 "Ads are more annoying than they need to be" — [GitHub](https://github.com/Miodec/monkeytype/issues/928)
- 10FastFingers: "ad-heavy experience with prominent advertisements" — [cosmickeys](https://cosmickeys.app/en/blog/10fastfingers-review)
- keybr users: ads "lagging the typing speed" — [keybr group](https://groups.google.com/g/keybr/c/PsYcvOkJyWE)

### Inferences
- For an adaptive Vim trainer, the keybr complaint about artificial content maps to "contrived edit tasks"; using real code snippets for the focus motion (analogous to keybr's "natural words" option) addresses the top complaint.
- Ads that introduce input latency or layout shift in the practice area are the single most-cited negative across keybr, Monkeytype and 10FastFingers.

### Gaps
- No systematic review data (app-store ratings, Trustpilot) collected; findings are from forum and review snippets.
