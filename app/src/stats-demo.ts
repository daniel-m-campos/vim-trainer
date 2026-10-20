// Stats screen demo (stats-demo.html): a learner simulated through the real model, a short
// placement then 60 attempts over 4 sessions with a seeded RNG, rendered by
// renderStatsView. Deterministic, so the e2e check (e2e/stats-demo.mjs) is stable.
//
//   npm run dev  ->  http://localhost:5173/stats-demo.html

import "./style.css";
import { baseGraph } from "./graph.ts";
import * as M from "./model/model.ts";
import type { AttemptRecord, ModelState, SkillGraph } from "./model/model.ts";
import type { SessionRecord } from "./types.ts";
import { renderStatsView, type StatsTab } from "./stats/statsView.ts";

const LANG = "python";
const T0 = 1_760_000_000; // fixed epoch seconds (Oct 2025), not the clock
const SESSIONS = 4;
const PER_SESSION = 15;

interface Learner {
  par: number; // typical par of the skill's exercises
  slow: number; // how far above target the first attempts are (x target)
  rate: number; // attempts to shed ~63% of the excess time
}

function learnerFor(id: string, rng: M.Mulberry32): Learner {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return { par: 2 + (h % 6), slow: 0.6 + rng.next() * 1.6, rate: 4 + rng.next() * 10 };
}

function attempt(graph: SkillGraph, id: string, k: number, t: number, l: Learner, rng: M.Mulberry32): AttemptRecord {
  const target = M.targetMs(graph, id, l.par);
  const decay = Math.exp(-k / l.rate);
  const noise = 1 + (rng.next() - 0.5) * 0.3;
  const ms = Math.round(target * (0.85 + l.slow * decay) * noise);
  const extra = rng.next() < 0.25 + 0.5 * decay ? 1 + Math.floor(rng.next() * 4 * decay + rng.next()) : 0;
  return {
    t,
    ex: `${id}.${String(k % 9).padStart(3, "0")}`,
    skill: id,
    lang: LANG,
    ok: rng.next() < 0.82 + 0.15 * (1 - decay),
    ms,
    keys: l.par + extra,
    par: l.par,
    hint: rng.next() < 0.03,
    retry: false,
    undo: 0,
  };
}

function simulate(graph: SkillGraph): { state: ModelState; sessions: SessionRecord[] } {
  const rng = new M.Mulberry32(20261012);
  const learners = new Map<string, Learner>();
  const learner = (id: string) => learners.get(id) ?? (learners.set(id, learnerFor(id, rng)), learners.get(id)!);
  const seen = new Map<string, number>();

  // Placement: passes ci" and f (inferring their prerequisites), misses :s.
  const placement: AttemptRecord[] = [
    { ...attempt(graph, "t.quote", 6, T0, learner("t.quote"), rng), ok: true, hint: false },
    { ...attempt(graph, "m.find", 8, T0 + 40, learner("m.find"), rng), ok: true, hint: false },
    { ...attempt(graph, "x.subst", 0, T0 + 95, learner("x.subst"), rng), ok: false, hint: false },
  ];
  let state = M.applyPlacement(M.newState(graph), placement, graph);

  const sessions: SessionRecord[] = [];
  let t = T0 + 600;
  for (let s = 0; s < SESSIONS; s++) {
    const since = t;
    let exercises = 0;
    for (let i = 0; i < PER_SESSION; i++) {
      const id = M.chooseFocus(state, LANG, graph, t, Math.floor(rng.next() * 2 ** 32));
      if (!id) break;
      const k = seen.get(id) ?? 0;
      seen.set(id, k + 1);
      const rec = attempt(graph, id, k, t, learner(id), rng);
      state = M.applyAttempt(state, rec, graph);
      exercises += 1;
      t += Math.round(rec.ms / 1000) + 12 + Math.floor(rng.next() * 20);
      // A failed attempt is retried once now and then (not counted by the model).
      if (!rec.ok && rng.next() < 0.5) {
        state = M.applyAttempt(state, { ...rec, t, ok: true, retry: true, ms: Math.round(rec.ms * 0.8) }, graph);
        t += 15;
      }
    }
    const summary = M.sessionSummary(state, since, graph);
    sessions.push({ start: since * 1000, end: t * 1000, exercises, improved: summary.improved.map((x) => x.skill) });
    t += 86400 + Math.floor(rng.next() * 3600 * 6); // next day
  }
  return { state, sessions };
}

const graph = M.applyProfile(baseGraph(), "neovim");
const { state, sessions } = simulate(graph);
const root = document.getElementById("stats-root") as HTMLElement;
const status = document.getElementById("demo-status") as HTMLElement;

const params = new URLSearchParams(location.search);
const tab = (["skills", "progress", "sessions"].includes(params.get("tab") ?? "") ? params.get("tab") : "skills") as StatsTab;

const view = renderStatsView(root, state, graph, LANG, {
  tab,
  selected: 0,
  sessions,
  onSelect: (i, id) => (status.textContent = `selected ${i}: ${id}`),
  onForce: (id) => (status.textContent = `forced next focus: ${id}`),
  onTab: (t) => (status.textContent = `tab: ${t}`),
});

document.addEventListener("keydown", (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (view.handleKey(e.key, e.shiftKey)) e.preventDefault();
});

status.textContent = `${state.log.length} log records, ${sessions.length} sessions`;
