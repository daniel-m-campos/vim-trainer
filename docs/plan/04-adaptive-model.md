# Adaptive model

How the trainer decides what you are weak at, what to drill next, when a skill is
mastered, and when to bring it back. The loop is keybr's, with three additions for Vim:
an efficiency dimension (keystrokes vs par), minimum-sample and accuracy gates, and
spaced review of mastered skills.

All computation runs client-side on the exercise log. The model is deterministic given
the log, so it can be recomputed from an export and unit-tested offline in Python.

## Inputs

Each attempt produces one record (see 05-grading.md for how fields are computed):

```json
{ "t": 1760200000, "ex": "py/t.quote/0193", "skill": "t.quote", "lang": "python",
  "ok": true, "ms": 4200, "keys": 16, "par": 12, "hint": false, "retry": false, "undo": 0 }
```

Retries and hinted attempts are logged but do not update confidence. Skips are logged
as `ok: false`.

## Per-skill state

```
time_ema      EMA of ms on correct attempts, alpha 0.1 (keybr's value)
eff_ema       EMA of keys/par on correct attempts, alpha 0.1
acc           correct / attempts over the last 20 attempts
n             number of counted attempts (not retries, not hinted)
confidence    see below
last_seen     timestamp of last counted attempt
status        locked | active | mastered | review
```

## Confidence

keybr: `confidence = target_time / time_ema`, mastered at 1.0. We keep that and add
efficiency and accuracy as gates rather than multiplying them in, so a fast, sloppy
learner and a slow, precise learner both show up as "not yet" for the right reason.

```
speed      = target_ms(skill) / time_ema           # 1.0 = at target
efficiency = 1 / eff_ema                            # 1.0 = at par, 0.5 = double par
confidence = min(speed, 1.0) * clamp(efficiency, 0.5, 1.0) / 1.0
mastered   = speed >= 1.0 and eff_ema <= 1.25 and acc >= 0.9 and n >= 8
```

- **target_ms** is per skill, derived from par: `target_ms = base + per_key * par`,
  with `base` ≈ 1200 ms (read the task, find the target) and `per_key` ≈ 180 ms. These
  are first guesses; recalibrate from the author's own data, then from the first users'
  distributions (target = roughly the 70th percentile of mastered users).
- **Efficiency** matters as much as speed for persona B. An expert who types `f"ci"` is
  fast but inefficient, and the model should keep nudging toward `ci"`.
- `n >= 8` and `acc >= 0.9` close keybr's known exploit, where a single lucky fast
  attempt unlocks the next key.

## Unlocking

The skill graph (02) gives each skill prerequisites. A skill is **active** when every
prerequisite is mastered, or when the placement test scored it above 0.6, or when the
user forces it from the stats screen. Tier 0 is active from the start.

Unlike keybr, which unlocks one letter at a time, several skills can be active at once
(target: 4–7). Too few and sessions are monotonous; too many and nothing converges.
When fewer than 4 are active and nothing new is unlockable, the model pulls the next
tier's lowest-prerequisite skill in anyway and marks it `introduced`, with a one-line
explainer on first appearance.

## Choosing the next exercise

1. **Pick the focus skill**: weakest first, but spread across the active skills. Each
   skill's priority is `1 - (1 - confidence) * weight`, using the language weight from 02.
   The steps run in order, and each filter is skipped when it would leave no candidate:
   1. **Review slot.** With probability 0.2, pick the most overdue `review` skill (below).
   2. **Starvation guard.** A skill with weight 0.3 or less that has not been picked in the
      last 11 picks is picked now. Its low weight keeps its priority high, so without this
      guard it would almost never be the focus.
   3. **Interleave.** Don't pick the same skill more than 3 times in a row.
   4. **Share cap.** Drop any skill that has 4 of the last 9 picks. No skill then takes
      more than 4 of any 10 consecutive picks (40%), unless it is the only active skill.
   5. **Weighted draw among the 3 weakest.** Keep the 3 skills with the lowest priority.
      Draw one with weight `(highest priority of the three - priority) + 0.1`. For
      priorities 0.2, 0.3 and 0.4 the weights are 0.3, 0.2 and 0.1, so the weakest is picked
      half the time, the next a third, and the third a sixth.

   The draws come from a seeded RNG, so the choice is deterministic given the log and the
   clock.

   Why: the first version picked the lowest-priority skill every time and only broke runs
   of 3. In every e2e session, `m.find` and `m.rel` took 13 of the 15 picks, and in
   simulation one plateaued skill (`o.dot`) took 20-23 of 30 attempts a day. Practice
   time spent on one stuck skill teaches little, and the other active skills never got
   the samples they needed to master. With the rules above, the simulated `o.dot` gets
   8-11 of 30 and four other operators master alongside it.
2. **Pick the exercise**: from the focus skill's pool for the current language, prefer
   exercises not seen in the last 50 attempts, then weight by the language's node
   weights (02), then random. Never repeat the same exercise twice in a session unless
   the pool is exhausted.
3. **Composite exercises**: when 2+ active skills have confidence > 0.8, 1 in 5
   exercises is a composite that requires both (e.g. `m.find` + `o.change`:
   "change the second argument"). Composites credit every skill they tag, which is how
   `t.compose` and `a.dot` get data without their own drills.

This follows keybr's "every word contains the weakest key", with real code standing in
for dictionary words. keybr can put the weakest key in every word because each word also
practises other letters; a Vim exercise drills one skill, so the focus has to rotate.

## Spaced review

Mastered skills decay. Without review, the model would never notice that the user
stopped using `"_d` three months ago. Each mastered skill gets a review interval:

```
interval_days = min(2 ** (reviews_passed), 60)       # 1, 2, 4, 8 ... 60
```

A due skill moves to `review` status and competes for the 0.2 review slot. Passing a
review (ok, ≤ 1.5× par, ≤ 1.3× target time) doubles the interval; failing resets it to
1 day and drops confidence by 20% so the skill re-enters normal rotation.

This is SM-2-shaped. FSRS was considered (see research/02) and rejected for v1: it needs
per-user parameter fitting and far more data than a Vim trainer will have per skill.
Revisit when there are 10k+ sessions to fit against.

## Placement test

Twelve exercises, chosen as one per tier 1–9 plus three more from tiers 3–4, at the
median par for each. Each result seeds the skill's state with `n = 1` and a
confidence computed as above, then propagates: a pass on a skill marks its
prerequisites mastered with confidence 1.0 and `n = 8` (we assume you can `w` if you
can `ci"`); a fail leaves prerequisites untouched. Skills not sampled start locked
unless all prerequisites were inferred mastered, in which case they start active at 0.5.

Result: an Advanced-track user sees 10–20 skills inferred mastered and 4–7 active in
tiers 4–7; a Switcher sees tiers 0–1 mastered and 3–4 active in tiers 1–3.

Placement is per language. `placementDone` in the saved state is a map
`{lang: true}`; an old save's single `true` migrates to `{<saved language>: true}`. The
first switch to a language with no placement opens that language's placement intro;
`x` skips it and marks the language done. A second language's placement skips every
skill already mastered (or due for review) in another language, since those carry over
(see Per-language state). It keeps one skill per tier 1–9 among the rest and fills the
remaining slots with the skills that weigh most in the new language (`langWeights`).

## Projection (the chart line)

Copied from keybr: fit a polynomial (linear, then quadratic when n ≥ 15) over the last
30 counted attempts' `ms`, project up to 30 attempts ahead, and show the line only when
R² ≥ 0.5. The caption converts the crossing of `target_ms` into "about N more
attempts". For efficiency, show a step chart of `keys/par` instead; it is discrete and a
fit is misleading.

## Session shaping

No fixed length. Within a session:
- First 2 exercises are warm-ups from a mastered skill at high confidence (fast wins,
  re-establish rhythm). Not counted.
- After 15 minutes or 40 exercises, the result strip adds a quiet "good place to stop"
  line. Nothing blocks.
- The session summary (10-ux) reports: skills whose confidence rose ≥ 0.1, any new
  mastery, any new unlock, and the "try in your editor today" line, chosen as the skill
  with the largest confidence gain that has a real-editor tip attached.

## Per-language state

Confidence is tracked per (skill, language) but unlocking uses the max across
languages, so switching from Python to C++ doesn't re-lock `ci"`. The stats grid shows
the current language's numbers with the cross-language max as a faint marker.

A skill mastered in any language enters a new language as mastered with its first
review due at once, so the new language's placement does not sample it and the first
review confirms it. Placement records carry their own `lang` and seed only that
language's states; a rebuild of the log never merges two languages' placements into
one batch.

## Emulator profile

The editor profile (Neovim / VSCodeVim / IdeaVim) filters which skills can ever become
active, from the emulator flags in 02. Skills marked `none` for the profile are hidden;
`partial` skills are active but exercises are limited to the supported subset.

## What the model does not do

- No ELO or leaderboards: confidence is against a fixed target, not other users.
- No hidden adjustment of target to flatter the user. Targets are global constants per
  skill (until recalibrated from data, which is a published change).
- No mid-exercise intervention. Everything is post-hoc (10-ux).

## Validation plan

1. Implement as a pure Python module with the JSON log as input, before any UI.
2. Simulate learners: a "fast sloppy", a "slow precise", a "plateaued expert" and a
   "quitter who returns after 60 days". Check that each is diagnosed correctly and that
   the focus skill moves sensibly.
3. Dogfood on the author for 4 weeks; recalibrate `base`, `per_key` and the unlock
   count from that log before any external user sees it.

## To research

- Reasonable `target_ms` constants: measure the author's times across 20 skills first.
- Whether `alpha = 0.1` is too slow for Vim, where a user may do 40 attempts per
  session (keybr lessons are longer). Try 0.15.
- How vimhjkl's Leitner implementation and 25-rep mastery compare in practice.
- Whether to credit `o.dot` automatically when the keystroke log shows `.` used well in
  any exercise (implicit skill detection), which would make tier 8 data far richer.
