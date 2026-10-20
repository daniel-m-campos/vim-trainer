# model/ - adaptive model (Python mirror, simulators, shared vectors)

This directory holds the Python half of the adaptive model. The TypeScript half lives in
`app/src/model/model.ts`. The two halves are kept identical by 26 JSON scenarios (vectors) that both test suites
replay. The vectors are generated, not committed: `gen_vectors.py` runs each scenario through
the Python model in a few seconds and stores the outputs as `expect`.

## Layout

| path | what |
|---|---|
| `gen_graph.py` | parses the tables in `skill-graph.md` and writes `skill-graph.json` (plus the copy at `app/src/model/skill-graph.json`) |
| `skill-graph.json` | 93 skills: id, tier, keys, prereqs, emulator flags, `targetBase` 1200, `perKey` 180, `langWeights` for 16 language ids, `enabled`, and `tips` |
| `tips.json` | "try in your editor today" lines for 53 skills (source for `graph.tips`) |
| `vimtrainer_model/` | the model: `state`, `attempt`, `placement`, `selection`, `projection`, `summary`, `rng`, `graph`, `vectors` (shared runner) |
| `gen_vectors.py` | builds the 26 scenarios and stores the Python outputs as `expect` (`--out DIR`, default `.cache/vectors/`) |
| `.cache/vectors/*.json` | the generated scenarios (gitignored; `make vectors`) |
| `simulate.py` | the four simulated learners from the validation plan |
| `tests/` | pytest suite (vectors, gates, unlocking, placement, selection, projection, summary, purity) |

## How to run

```sh
# from the repo root
uv run --project model python model/gen_graph.py     # regenerate skill-graph.json (both copies)
make vectors                                         # write model/.cache/vectors/*.json from Python
make test-model                                      # pytest; generates its own copy in a temp dir and replays it
make test-app                                        # includes the TS mirror against model/.cache/vectors (Node >= 23)
uv run --project model python model/simulate.py      # all four learners; or name one: fast_sloppy, slow_precise, plateaued_expert, quitter
uv run --project model python model/simulate.py picks plateaued_expert 40 5   # 40 focus picks after 5 days, with their distribution
```

After any change to model behaviour, run both suites; `make test-model` and `make test-app`
regenerate the vectors first, so the TS mirror is always checked against the current Python
model. `tests/test_vectors.py` also generates the vectors twice and requires identical bytes.

To inspect a vector, generate them and read the file:

```sh
make vectors
cat model/.cache/vectors/24_share_cap.json
```

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
- **`AttemptRecord.seq?`, `beatPar?`, `flag?`** (optional, written by the app). `seq` is
  the player's key sequence, normalised and replayable in Neovim (a `jk` escape is
  written as `<Esc>`). `beatPar` is true when the attempt
  was ok with fewer keys than par. `flag` is `{reason, note?}`, set when the player
  reports the exercise with `!`; `reason` is one of `wrong-par`, `wording`, `emulator`,
  `other`. The model ignores all three and logs the record unchanged, so the fields reach
  `ingest` through the exported log. `digest` does not read record contents, so the
  vectors do not change.
- **Composite records.** `AttemptRecord.skill` stays a string. A composite names its
  skills joined by `+`, for example `"m.find+o.change"`, and every named skill is credited.
- **`focusHistory`** holds the primary skill of the last 20 attempts and drives the
  "max 3 in a row" rule, the share cap and the starvation guard (decision 18). Retries are not appended: a retry repeats the exercise just
  shown and is not another pick of the skill.
- **Forced skills.** The stats screen can force a locked skill. Its first counted attempt
  sets it active (forcing makes a skill active), so it can be mastered.
- **New language.** A skill mastered in another language starts mastered in the new one
  with its first review due at once; a skill only unlocked elsewhere is carried over as
  active while fewer than 7 are in rotation. This keeps the "no re-lock" rule without
  flooding the new language's rotation.
- **Placement per language.** The app runs one placement test per language, and each
  test is one `applyPlacement` call with records of that language only. A second
  placement touches only the new language's states: skills mastered in the first
  language start mastered with a review due at once (`ensureSkill`), and a pass infers
  prerequisites in the new language only. `rebuild(log)` groups consecutive placement
  records into one batch and closes the batch when `record.lang` changes, so a Python
  placement followed directly by a C++ placement replays as two `applyPlacement` calls.
  Vector `26_second_language_placement` checks this in both mirrors.

### Exercise index shape (`build/index.json`)

`chooseExercise` reads `index.langs[lang].skills[skill].ids`, the shape the content pipeline
writes. It also accepts `index.langs[lang][skill]`, `index[lang][skill]`,
a bare array in place of `{ids}`, and `exercises` as an alias of `ids`. Each item is either
an id string or `{id, skills}`. A `{id, skills}` item with two or more skills is a
composite. The pipeline should list composites under each skill they tag (it emits none yet).

## Modelling decisions

1. **target_ms per skill.** See `parEma` above. Every skill uses `base` 1200 ms and
   `per_key` 180 ms. Recalibration means changing one value in the graph.
2. **Alpha.** Kept at 0.1; 0.15 is worth trying, and
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
    A pass on a tier 3 or higher skill also infers all of tier 0, because tier 0 is
    assumed and placement only confirms it.
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
18. **Spreading the focus.** Pure argmin let two weak skills take 13 of 15 picks in every
    e2e session, and o.dot 20-23 of 30 for the plateaued expert. `chooseFocus` now runs,
    in order (each filter is skipped when it would leave no candidate):
    1. review slot: first seeded draw < 0.2 and a review is due -> most overdue review;
    2. starvation guard: an in-rotation skill with language weight in (0, 0.3] that is
       absent from the last 11 picks is picked outright (lowest graph order first);
    3. streak: the skill of the last 3 picks is dropped;
    4. share cap: a skill with 4 of the last 9 picks is dropped, so no skill exceeds 4 of
       any 10 consecutive picks;
    5. the 3 lowest by priority `1 - (1 - confidence) * weight` are kept and one is drawn
       with the second seeded draw, weight `(highest priority of the three - priority) + 0.1`.
    Example: priorities 0.2, 0.3, 0.4 give weights 0.3, 0.2, 0.1, so the weakest is picked
    1 time in 2, the next 1 in 3, the third 1 in 6. Equal priorities give a uniform draw.
    Constants: `FOCUS_CANDIDATES` 3, `FOCUS_FLOOR` 0.1, `SHARE_WINDOW` 10, `SHARE_MAX` 4,
    `LOW_WEIGHT` 0.3, `STARVE_WINDOW` 12. A review pick or a second starved skill can delay
    a starved skill by a pick or two. Vectors `24_share_cap` and `25_starvation_guard`
    check both guarantees in both mirrors.

## Simulation results (`simulate.py`)

Each learner practises daily 30-attempt sessions driven by the model
(`chooseFocus` -> `chooseExercise` -> `applyAttempt`) in Python. The latent ability per
skill improves exponentially with exposures. "next" is the focus the model would pick
after the session, followed by its failing mastery gates.

| learner | diagnosis | how the focus moved |
|---|---|---|
| fast sloppy (0.6-0.8x target time, 2.2x par improving to 1.1x, 12% give-ups) | correct: every active skill fails **efficiency** (and often **accuracy**) while speed is 1.3-1.6 | stays in tier 0 for 14 days, rotating across all 5 skills (the top skill gets 8-10 of 30 picks). Efficiency climbs from 0.47 to 0.79 of par but has not crossed the 1.25 gate |
| slow precise (2.2x target falling to 0.85x, at par, 2% errors) | correct: only **speed** fails | masters f.modes/f.xdd on day 6, which unlocks o.replace and i.*. The focus moves to those; f.save, f.undo and i.oneshot master on days 11-12 |
| plateaued expert (placement through tier 7; o.dot at 1.7x par) | correct: o.dot fails **efficiency** (eff 0.59) | placement infers 12 skills mastered. Days 0-4 sweep tiers 1-2 (13 masteries). From day 5 on, o.dot takes 8-11 of 30 attempts (was 20-23 before the share cap) and o.change, o.case, o.join and o.replace master alongside it, with reviews in the 0.2 slot |
| quitter (10 days, 60-day gap, forgets 95%) | correct: due reviews fail on return | day 70 has 3 failed reviews out of 3. Failed skills go back into rotation (f.modes, f.undo, m.word, o.replace and i.escape master on day 75) |

Excerpt (full output: run the script):

```
== plateaued_expert
day   0 | focus t.word x7, r.named x7, x.subst x7, m.file x4         | next: m.file [samples/accuracy] ...
day   4 | focus o.indent x8, o.dot x7, m.screen x3, o.put x2         | next: o.case [samples/speed] ...
day   9 | focus o.dot x11, o.case x6, o.replace x4, o.number x3      | next: o.number [samples] ...
== quitter
day  70 | focus m.word x11, i.escape x9, f.undo x6, o.replace x2     | next: f.undo [speed] speed 0.70
        reviews: 0 passed, 3 failed
day  75 | ...                  mastered: f.modes, f.undo, m.word, o.replace, i.escape
```

One 40-pick session of the plateaued expert after 5 days
(`simulate.py picks plateaued_expert 40 5`): o.dot 13 (32.5%), o.change 8, o.case 5,
x.subst 4, and 10 other skills once each (mostly reviews in the 0.2 slot). No skill
has more than 4 of any 10 consecutive picks.

### What the simulation suggests changing (open decisions)

1. **Done (decision 18).** *One weak skill can take over a session.* The interleave rule only breaks runs of 3,
   so the plateaued expert spends about 70% of every session on o.dot. Option: cap any
   one skill at about 40% of a session's attempts.
2. **The efficiency gate can block all progress.** A sloppy learner whose keys/par stays
   above 1.25 never unlocks anything, because 5 tier-0 skills stay active and the
   `introduced` pull-in only runs below 4 active. Option: let an efficiency-only failure
   after n >= 30 unlock the next skill anyway, or show the par more prominently.
3. **Unlocking ignores tier order.** Mastering `f.modes` unlocks tier 10 (`i.*`) before tier 1
   (which needs `f.hjkl`), because unlocking follows prerequisites only. Option: add an
   ordering to the graph and fill free slots in that order.
4. **Reviews are lenient for mild rust.** A first quitter run with 75% forgetting passed
   every review on return. The 1.3x target-time bar only catches large decay.
5. **Constants still need data.** `base`/`per_key` must come from
   real practice logs.
