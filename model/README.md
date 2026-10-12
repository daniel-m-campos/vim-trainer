# model/ - adaptive model (Python mirror, simulators, shared vectors)

This directory holds the Python half of the adaptive model from
`docs/plan/04-adaptive-model.md` and `05-grading.md`. The TypeScript half lives in
`app/src/model/model.ts`. The two halves are kept identical by the JSON scenarios in
`vectors/`, which both test suites replay.

## Layout

| path | what |
|---|---|
| `gen_graph.py` | parses the tables in `docs/plan/02-skill-graph.md` and writes `skill-graph.json` (plus the copy at `app/src/model/skill-graph.json`) |
| `skill-graph.json` | 93 skills: id, tier, keys, prereqs, emulator flags, `targetBase` 1200, `perKey` 180, `langWeights` for 16 language ids, `enabled`, and `tips` |
| `tips.json` | "try in your editor today" lines for 53 skills (source for `graph.tips`) |
| `vimtrainer_model/` | the model: `state`, `attempt`, `placement`, `selection`, `projection`, `summary`, `rng`, `graph`, `vectors` (shared runner) |
| `gen_vectors.py` | builds the 23 scenarios and stores the Python outputs as `expect` |
| `vectors/*.json` | the shared scenarios |
| `simulate.py` | the four simulated learners from the validation plan |
| `tests/` | pytest suite (vectors, gates, unlocking, placement, selection, projection, summary, purity) |

## How to run

```sh
# from the repo root
uv run --project model python model/gen_graph.py     # regenerate skill-graph.json (both copies)
uv run --project model python model/gen_vectors.py   # regenerate vectors/*.json from Python
uv run --project model pytest model                  # 69 tests incl. doctests and every vector
node --test app/src/model/model.test.ts              # TS mirror against the same vectors (Node >= 23, zero install)
uv run --project model python model/simulate.py      # all four learners; or name one: fast_sloppy, slow_precise, plateaued_expert, quitter
```

After any change to model behaviour, regenerate the vectors and run both suites.
`tests/test_vectors.py` fails when the scenario inputs drift from the stored files.

## Interface

TypeScript uses the camelCase names below. Python uses the snake_case equivalents
(`new_state`, `apply_attempt`, ...), and its state dicts use the same camelCase keys, so
a state serialises identically from either side.

```
newState(graph) -> ModelState
applyAttempt(state, record, graph) -> ModelState
applyPlacement(state, records, graph) -> ModelState
chooseFocus(state, lang, graph, nowSeconds, seed?) -> skillId | null
chooseExercise(state, skillId, lang, index, rngSeed, graph?) -> exerciseId | null
projection(state, skillId, lang, graph?) -> {fit, attemptsToTarget, r2}
sessionSummary(state, sinceT, graph) -> {improved: [{skill, delta}], mastered, unlocked, tip}
extras: rebuild(log, graph), diagnose(state, skillId, lang, graph), chooseWarmup(state, lang, graph),
        applyProfile(graph, profile, extraTiers), exercisePool(index, lang, skill), Mulberry32, deriveSeed
```

No function reads the clock or global randomness. Every function returns a new state and
leaves its input unchanged.

### Where the shared interface was extended

The spec asked for exactly the listed interface. These are the places that needed
something extra, and why:

- **`SkillState.parEma`** (extra field). `target_ms = base + per_key * par` depends on the
  exercise's par, which varies within a skill. The model keeps an EMA of par alongside the
  EMA of time (same alpha, same attempts) and uses `targetBase + perKey * parEma` as the
  skill's target.
- **`AttemptRecord.placement?`** (optional flag). `applyPlacement` logs its records with
  `placement: true`, so `rebuild(log)` can replay placement. Without the flag the model
  would not be "deterministic given the log".
- **`sessionSummary(state, sinceT, graph)`**. The state before the session is rebuilt from
  the log, which needs the graph. The tips come from `graph.tips`.
- **Optional trailing arguments.** `chooseFocus` takes an optional `seed`, which defaults
  to `deriveSeed(log.length, now)`. `chooseExercise` and `projection` take an optional
  `graph`, used for language weights and per-skill targets.
- **Composite records.** `AttemptRecord.skill` stays a string. A composite names its
  skills joined by `+`, for example `"m.find+o.change"`, and every named skill is credited.
- **`focusHistory`** holds the primary skill of the last 20 attempts and drives the
  "max 3 in a row" rule. Retries are not appended: a retry repeats the exercise just
  shown and is not another pick of the skill.
- **Forced skills.** The stats screen can force a locked skill. Its first counted attempt
  sets it active (04: forcing makes a skill active), so it can be mastered.
- **New language.** A skill mastered in another language starts mastered in the new one
  with its first review due at once; a skill only unlocked elsewhere is carried over as
  active while fewer than 7 are in rotation. This keeps the "no re-lock" rule without
  flooding the new language's rotation.

### Exercise index shape (`build/index.json`)

`chooseExercise` reads `index.langs[lang].skills[skill].ids`, the shape the content pipeline
writes. It also accepts `index.langs[lang][skill]`, `index[lang][skill]`,
a bare array in place of `{ids}`, and `exercises` as an alias of `ids`. Each item is either
an id string or `{id, skills}`. A `{id, skills}` item with two or more skills is a
composite. The pipeline should list composites under each skill they tag (it emits none yet).

## Decisions where the doc was ambiguous or silent

1. **target_ms per skill.** See `parEma` above. Every skill uses `base` 1200 ms and
   `per_key` 180 ms, as the spec asked. Recalibration means changing one value in the graph.
2. **Alpha.** Kept at 0.1 as specified. The doc's To-research item suggests trying 0.15;
   that is `ALPHA` in both mirrors.
3. **Accuracy window.** `acc` is computed from the log over the last 20 counted attempts
   of (skill, lang). Retries and hinted attempts are excluded. Undo does not lower accuracy.
4. **Mastery is sticky.** A mastered skill is never demoted by ordinary attempts (from
   composites or warm-ups). Only a failed review demotes it.
5. **Review failure, "drop confidence by 20%".** If the drop were stored only in
   `confidence`, the next attempt would recompute it away. The model therefore slows
   `timeEma` so that the confidence formula gives exactly 0.8x the old value, and the drop
   lasts until the user earns it back. A failure also sets the status back to `active` and
   the next mastery restarts the review interval at 1 day.
6. **Due reviews.** A mastered skill whose `nextReview <= now` becomes `review`, both when
   an attempt is applied and inside `chooseFocus`. A due skill gets only the 0.2 slot; it
   is never in normal rotation. The most overdue due skill is picked first.
7. **Language weights in focus choice.** The doc gives weights "how often a skill is
   drilled" but defines focus as "lowest confidence". The model ranks skills by
   `1 - (1 - confidence) * weight`, so weight 1.5 amplifies a deficit and 0.3 shrinks it.
   Skills with weight 0 in a language are never active there. In exercise choice, a
   candidate's weight is the product of its tagged skills' weights.
8. **Prerequisites that can never be met in a language** (weight 0, such as `t.angle` and
   `t.tag` in Python, or skills disabled by the editor profile) count as satisfied.
   Without this rule, `t.compose` ("all of tier 4") could never unlock in Python.
9. **4-7 active.** Prerequisite unlocking stops at 7 active skills, filling slots in
   (tier, document order). Skills that are eligible beyond that wait. The `introduced`
   pull-in runs while fewer than 4 are active. It picks the lowest locked tier, then the
   fewest unmet prerequisites, then the fewest prerequisites. A skill stays `introduced`
   until mastered. The UI should show the one-line explainer while `n == 0`.
10. **Composites.** When 2 or more unlocked skills are above 0.8 confidence, 1 in 5 draws
    (seeded roll, p = 0.2) comes from exercises that tag the focus skill plus other
    *unlocked* skills. The other 4 in 5 draws use single-skill exercises. Composites that
    tag a locked skill are never served.
11. **"Never repeat in a session".** The 50-id `recent` list stands in for the session
    (sessions are about 40 exercises). When every candidate is recent, the model picks the
    one seen longest ago.
12. **Placement.** A pass is `ok`. A pass infers every transitive prerequisite mastered
    (confidence 1.0, n = 8, acc 1.0), except prerequisites that were sampled and failed.
    A pass on a tier 3 or higher skill also infers all of tier 0, because the doc says tier
    0 is "assumed; placement test confirms" and the Advanced track "never drills these".
    Inferred skills get their first review after 4 days (`reviewsPassed = 2`), so 10-20 of
    them do not all come due the next morning. A sampled skill becomes active when its
    confidence is above 0.6 or its prerequisites hold. An unsampled skill whose
    prerequisites hold starts active at 0.5, up to the 7-active cap.
13. **Projection.** It uses correct counted attempts only (a give-up's `ms` is
    meaningless). It needs at least 3 points. The fit is linear below 15 points and
    quadratic from 15. With R^2 < 0.5 the result is `fit: 'none'`. `attemptsToTarget` is
    0 when the fit is already at target, and null when the fit does not reach target
    within 30 attempts.
14. **Session summary.** `improved` lists confidence gains of at least 0.1, taking the max
    over the session's languages. `unlocked` means the skill moved from locked to
    active/introduced. The tip belongs to the skill with the largest positive gain that has
    a tip, falling back to newly mastered skills.
15. **Profiles.** Tiers 11 and 12 are disabled by default ("enabled on request").
    `applyProfile(graph, 'vscodevim', [11])` disables skills flagged `none` for that
    editor. Partial skills stay enabled; limiting their exercises is up to the content
    side.
16. **Emulator flags.** `gen_graph.py` reads the free-text cells. "VSC"/"IJ" segments set
    that editor's flag. Unmentioned editors take the cell's leading flag, or `full` when the
    cell has none. Tier 12 has no emulator column, so those skills are Neovim-only. The
    "comment edits" weight row maps to `nv.comment`. The "JS/TS" column covers
    javascript/typescript/tsx/jsx, "Java/C#" covers java/csharp, "C/C++" covers c/cpp, and
    "JSON/YAML" covers json/yaml.
17. **Warm-ups** are not modelled. The app should call `chooseWarmup` for the first 2
    exercises and not pass those attempts to `applyAttempt`.

## Simulation results (`simulate.py`)

Each learner practises daily 30-attempt sessions driven by the model
(`chooseFocus` -> `chooseExercise` -> `applyAttempt`) in Python. The latent ability per
skill improves exponentially with exposures. "next" is the focus the model would pick
after the session, followed by its failing mastery gates.

| learner | diagnosis | how the focus moved |
|---|---|---|
| fast sloppy (0.6-0.8x target time, 2.2x par improving to 1.1x, 12% give-ups) | correct: every active skill fails **efficiency** (and often **accuracy**) while speed is 1.3-1.6 | stays in tier 0 for 14 days, rotating across all 5 skills. Efficiency climbs from 0.44 to 0.78 of par but has not crossed the 1.25 gate |
| slow precise (2.2x target falling to 0.85x, at par, 2% errors) | correct: only **speed** fails | masters f.modes/f.undo on day 6, which unlocks o.replace and i.*. The focus moves to those; o.replace and i.oneshot master on day 12 |
| plateaued expert (placement through tier 7; o.dot at 1.7x par) | correct: o.dot fails **efficiency** (eff 0.58-0.60) | placement infers 12 skills mastered. Days 0-4 sweep tiers 1-2 (13 masteries). From day 5 on, o.dot takes 20-23 of 30 attempts, with reviews in the 0.2 slot (passes and a few fails) |
| quitter (10 days, 60-day gap, forgets 95%) | correct: due reviews fail on return | day 70 has 2 failed reviews out of 3. Failed skills go back into rotation (f.modes is re-mastered on day 73, i.delete and i.oneshot on day 75) |

Excerpt (full output: run the script):

```
== plateaued_expert
day   0 | focus m.find x11, t.word x7, r.named x7, x.subst x4    | next: m.find [accuracy] ...
day   4 | focus o.dot x11, m.rel x9, m.file x3, f.modes x1       | next: o.dot [efficiency/speed] speed 0.97 eff 0.60
day   9 | focus o.dot x23, o.change x7                           | next: o.dot [efficiency/speed] speed 0.98 eff 0.58
== quitter
day  70 | focus i.escape x11, o.replace x10, i.oneshot x7, ...   | next: f.modes [speed] speed 0.77
        reviews: 1 passed, 2 failed
day  73 | ...                                                    mastered: f.modes
```

### What the simulation suggests changing (for the author to decide)

1. **One weak skill can take over a session.** The interleave rule only breaks runs of 3,
   so the plateaued expert spends about 70% of every session on o.dot. Option: cap any
   one skill at about 40% of a session's attempts.
2. **The efficiency gate can block all progress.** A sloppy learner whose keys/par stays
   above 1.25 never unlocks anything, because 5 tier-0 skills stay active and the
   `introduced` pull-in only runs below 4 active. Option: let an efficiency-only failure
   after n >= 30 unlock the next skill anyway, or show the par more prominently.
3. **Unlocking ignores tracks.** Mastering `f.modes` unlocks tier 10 (`i.*`) before tier 1
   (which needs `f.hjkl`), because unlocking follows prerequisites and the Switcher /
   Advanced track orderings in 02 are not part of the model yet. Option: add a track
   order to the graph and fill free slots in track order.
4. **Reviews are lenient for mild rust.** A first quitter run with 75% forgetting passed
   every review on return. The 1.3x target-time bar only catches large decay.
5. **Constants still need data.** `base`/`per_key` (09-open-questions) must come from the
   author's first week of dogfooding.
