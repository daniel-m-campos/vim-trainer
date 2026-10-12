// The stats screen (docs/plan/10-ux.md "The stats screen"): Skills grid, Progress charts
// and the Sessions table, rendered into a root element and driven by the keyboard.
//
//   const view = renderStatsView(root, state, graph, lang, { tab, selected, onSelect, onForce });
//   document.addEventListener("keydown", (e) => view.handleKey(e.key, e.shiftKey) && e.preventDefault());
//
// Keys: tab / shift-tab or 1 2 3 switch tabs; h j k l (or arrows) move in the grid;
// enter opens the selected skill's history chart; f forces it as the next focus
// (opts.onForce); esc closes the history chart. handleKey returns false for keys it does
// not use (esc with no chart open included) so the caller can handle them.

import "./stats.css";
import * as M from "../model/model.ts";
import type { AttemptRecord, ModelState, SkillGraph, SkillState, Status } from "../model/model.ts";
import { esc } from "../dom.ts";
import { skillInfo } from "../skills.ts";
import type { SessionRecord } from "../types.ts";
import { stepChart, timeChart, type Point } from "./charts.ts";

export type StatsTab = "skills" | "progress" | "sessions";

export const STATS_TABS: readonly StatsTab[] = ["skills", "progress", "sessions"];

export interface StatsViewOptions {
  tab: StatsTab;
  /** Index into the grid's skill order (tier, then graph order). */
  selected: number;
  onSelect: (index: number, skillId: string) => void;
  /** "Drill this": the caller makes the skill the next focus. */
  onForce: (skillId: string) => void;
  onTab?: (tab: StatsTab) => void;
  /** Focus skill to outline; default M.chooseFocus at `now`. Pass "" for none. */
  focus?: string | null;
  /** Skills shown in the grid; default every enabled skill of tiers 0-12. */
  skills?: string[];
  /** Sessions table rows; default derived from the log (30-minute gaps split sessions). */
  sessions?: SessionRecord[];
  /** Clock in seconds for chooseFocus; default the last log time, else Date.now(). */
  now?: number;
}

export interface StatsViewHandle {
  /** Handle one KeyboardEvent.key; true when the view used it. */
  handleKey(key: string, shift?: boolean): boolean;
  /** Re-render with a new state (after an attempt, a language change, ...). */
  update(state: ModelState, graph?: SkillGraph): void;
  readonly tab: StatsTab;
  readonly selected: number;
  destroy(): void;
}

// Data ============================================================================================

const IN_ROTATION: readonly Status[] = ["active", "introduced"];
const STATUS_RANK: Record<Status, number> = { locked: 0, introduced: 1, active: 2, review: 3, mastered: 4 };
const SESSION_GAP_S = 30 * 60;
const TREND_WINDOW = 5;
const WEAKEST = 3;
const MAX_DERIVED_SESSIONS = 12;

export interface SkillRow {
  id: string;
  tier: number;
  status: Status;
  st: SkillState | null;
  confidence: number;
  /** Best confidence in any other language (04: shown as a faint marker). */
  otherMax: number;
}

/** Counted (not hinted, not retried) correct attempts of a skill in a language, oldest first. */
export function skillAttempts(state: ModelState, graph: SkillGraph, skillId: string, lang: string): AttemptRecord[] {
  return state.log.filter(
    (rec) => rec.lang === lang && rec.ok && !rec.retry && !rec.hint && M.recordSkills(graph, rec).includes(skillId),
  );
}

/** Trend of time to solve: mean of the last 5 vs the 5 before; null with fewer than 6. */
export function trendOf(times: number[]): "up" | "down" | "flat" | null {
  if (times.length < TREND_WINDOW + 1) return null;
  const mean = (a: number[]) => a.reduce((x, y) => x + y, 0) / a.length;
  const ratio = mean(times.slice(-TREND_WINDOW)) / mean(times.slice(-2 * TREND_WINDOW, -TREND_WINDOW));
  if (ratio < 0.95) return "up"; // faster
  if (ratio > 1.05) return "down";
  return "flat";
}

function statusOf(state: ModelState, graph: SkillGraph, id: string, lang: string): Status {
  const own = state.skills[id]?.[lang];
  if (own) return own.status;
  // Language not seen yet: unlocking is shared across languages (04).
  let best: Status = graph.skills[id]?.tier === 0 ? "active" : "locked";
  for (const st of Object.values(state.skills[id] ?? {})) if (STATUS_RANK[st.status] > STATUS_RANK[best]) best = st.status;
  return best;
}

export function skillRows(state: ModelState, graph: SkillGraph, lang: string, ids?: string[]): SkillRow[] {
  const order = M.skillIds(graph);
  const wanted = ids ? new Set(ids) : null;
  const shown = order.filter((id) => (wanted ? wanted.has(id) : graph.skills[id].enabled !== false && graph.skills[id].tier <= 12));
  return shown.map((id) => {
    const st = state.skills[id]?.[lang] ?? null;
    let otherMax = 0;
    for (const [l, s] of Object.entries(state.skills[id] ?? {})) if (l !== lang) otherMax = Math.max(otherMax, s.confidence);
    return { id, tier: graph.skills[id].tier, status: statusOf(state, graph, id, lang), st, confidence: st?.confidence ?? 0, otherMax };
  });
}

/** Focus skill plus the 3 weakest in-rotation skills (lowest confidence, graph order on ties). */
export function progressSkills(rows: SkillRow[], focus: string): string[] {
  const weakest = rows
    .filter((row) => IN_ROTATION.includes(row.status) && row.id !== focus)
    .sort((a, b) => a.confidence - b.confidence)
    .slice(0, WEAKEST)
    .map((row) => row.id);
  return focus ? [focus, ...weakest] : weakest;
}

export interface History {
  times: number[];
  ratios: number[];
  targetMs: number | null;
  projection: M.Projection;
  line: Point[] | null;
  crossing: number | null;
}

/** Everything one skill's charts need, with the projection fitted as model.projection fits it. */
export function skillHistory(state: ModelState, graph: SkillGraph, id: string, lang: string): History {
  const records = skillAttempts(state, graph, id, lang);
  const times = records.map((rec) => rec.ms);
  const ratios = records.map((rec) => (rec.par > 0 ? rec.keys / rec.par : 1));
  const st = state.skills[id]?.[lang];
  const targetMs = st && st.parEma !== null ? M.targetMs(graph, id, st.parEma) : null;
  const projection = M.projection(state, id, lang, graph);
  let line: Point[] | null = null;
  let crossing: number | null = null;
  if (projection.fit !== "none") {
    // Same window and degree as model.projection (last 30 counted correct attempts).
    const ys = times.slice(-M.PROJECTION_WINDOW);
    const coeffs = M.fitPolynomial(ys, ys.length >= M.PROJECTION_QUADRATIC_N ? 2 : 1);
    const offset = times.length - ys.length;
    const ahead = projection.attemptsToTarget === null ? M.PROJECTION_AHEAD : Math.min(M.PROJECTION_AHEAD, projection.attemptsToTarget + 3);
    line = [];
    for (let i = ys.length - 1; i <= ys.length - 1 + ahead; i++) line.push({ x: offset + i, y: M.evaluatePolynomial(coeffs, i) });
    if (projection.attemptsToTarget !== null) crossing = times.length - 1 + projection.attemptsToTarget;
  }
  return { times, ratios, targetMs, projection, line, crossing };
}

/** Sessions from the log: a gap of 30 minutes or more starts a new one. */
export function deriveSessions(log: AttemptRecord[]): SessionRecord[] {
  const sessions: SessionRecord[] = [];
  let cur: SessionRecord | null = null;
  let lastT = -Infinity;
  for (const rec of log) {
    if (rec.placement) continue;
    if (!cur || rec.t - lastT >= SESSION_GAP_S) {
      cur = { start: rec.t * 1000, end: rec.t * 1000, exercises: 0, improved: [] };
      sessions.push(cur);
    }
    cur.end = rec.t * 1000;
    if (!rec.retry) cur.exercises += 1;
    lastT = rec.t;
  }
  return sessions;
}

/** Fill `improved` for derived sessions (the last 12; each needs a rebuild of the log). */
function withImproved(state: ModelState, graph: SkillGraph, sessions: SessionRecord[]): SessionRecord[] {
  return sessions.map((s, i) => {
    if (i < sessions.length - MAX_DERIVED_SESSIONS) return s;
    try {
      const upto = M.rebuild(
        state.log.filter((rec) => rec.t * 1000 <= s.end),
        graph,
      );
      return { ...s, improved: M.sessionSummary(upto, s.start / 1000, graph).improved.map((x) => x.skill) };
    } catch (err) {
      console.error("stats: session summary failed", err);
      return s;
    }
  });
}

// Rendering =======================================================================================

const code = (s: string) => `<code>${esc(s)}</code>`;
const keysOf = (id: string) => skillInfo(id).keys;

function tierTitle(graph: SkillGraph, tier: number): string {
  const node = Object.values(graph.skills).find((n) => n.tier === tier && n.tierName);
  const name = node?.tierName?.replace(/\s*\(.*\)\s*$/, "") ?? "";
  return `tier ${tier}${name ? ` <span class="sv-tiername">${esc(name)}</span>` : ""}`;
}

const TREND_HTML = {
  up: `<span class="sv-trend" title="faster over the last 5 attempts">&uarr;</span>`,
  down: `<span class="sv-trend" title="slower over the last 5 attempts">&darr;</span>`,
  flat: `<span class="sv-trend" title="steady over the last 5 attempts">&rarr;</span>`,
  none: `<span class="sv-trend sv-muted" title="fewer than 6 correct attempts">&ndash;</span>`,
};

function bar(row: SkillRow): string {
  const pct = (v: number) => Math.round(Math.max(0, Math.min(1, v)) * 100);
  const marker = row.otherMax > row.confidence ? `<b style="left:${pct(row.otherMax)}%" title="best in another language ${row.otherMax.toFixed(2)}"></b>` : "";
  return `<span class="sv-bar" aria-hidden="true"><i style="width:${pct(row.confidence)}%"></i>${marker}</span>`;
}

function cell(row: SkillRow, i: number, focus: string, selected: number, times: number[]): string {
  const info = skillInfo(row.id);
  const cls = ["sv-cell", `sv-${row.status}`, row.id === focus ? "sv-focus" : "", i === selected ? "sv-sel" : ""].join(" ");
  const trend = TREND_HTML[trendOf(times) ?? "none"];
  return `<div class="${cls}" data-i="${i}" role="gridcell" aria-selected="${i === selected}">
    <div class="sv-cell-top">${code(info.keys)}${row.id === focus ? `<span class="sv-focus-tag">focus</span>` : ""}</div>
    <div class="sv-name">${esc(info.name)}</div>
    <div class="sv-conf">${bar(row)}<span class="sv-num">${row.confidence.toFixed(2)}</span></div>
    <div class="sv-meta"><span class="sv-num">n ${row.st?.n ?? 0}</span><span class="sv-pill sv-pill-${row.status}">${row.status}</span>${trend}</div>
  </div>`;
}

function caption(id: string, h: History): string {
  const k = code(keysOf(id));
  const p = h.projection;
  if (h.times.length < M.PROJECTION_MIN_N) return `${k} projection after ${M.PROJECTION_MIN_N} correct attempts (${h.times.length} so far)`;
  if (p.fit === "none") return `${k} no projection yet: times too uneven to fit (R&sup2; ${p.r2.toFixed(2)})`;
  if (p.attemptsToTarget === 0) return `${k} at target now`;
  if (p.attemptsToTarget === null) return `${k} not at target within ${M.PROJECTION_AHEAD} attempts at this rate`;
  return `${k} at target in ~${p.attemptsToTarget} attempt${p.attemptsToTarget === 1 ? "" : "s"}`;
}

function diagnosisLine(state: ModelState, graph: SkillGraph, id: string, lang: string): string {
  const d = M.diagnose(state, id, lang, graph);
  if (d.status === null || d.n === 0) return `<span class="sv-muted">no attempts in this language yet</span>`;
  const parts = [
    `speed <span class="sv-num">${d.speed.toFixed(2)}</span>x target`,
    `efficiency <span class="sv-num">${d.efficiency === null ? "&ndash;" : d.efficiency.toFixed(2)}</span>`,
    `accuracy <span class="sv-num">${Math.round(d.acc * 100)}%</span>`,
    `n <span class="sv-num">${d.n}</span>`,
  ].join(" &middot; ");
  const gates = d.failing.length ? `not mastered yet: ${d.failing.join(", ")}` : "all mastery gates met";
  return `${parts}<br><span class="sv-muted">${gates}</span>`;
}

function card(state: ModelState, graph: SkillGraph, id: string, lang: string, role: string, detail: boolean): string {
  const info = skillInfo(id);
  const h = skillHistory(state, graph, id, lang);
  const status = statusOf(state, graph, id, lang);
  const charts = h.times.length
    ? `<div class="sv-charts">
        <figure><figcaption>time to solve, by attempt</figcaption>${timeChart({ times: h.times, targetMs: h.targetMs, projection: h.line, crossing: h.crossing, label: `${info.keys} time to solve` })}</figure>
        <figure><figcaption>keys / par, by attempt (mastery limit ${M.MASTER_EFF.toFixed(2)})</figcaption>${stepChart({ ratios: h.ratios, limit: M.MASTER_EFF, label: `${info.keys} keys per par` })}</figure>
      </div>
      <p class="sv-caption">${caption(id, h)}</p>`
    : `<p class="sv-empty">no correct attempts yet${status === "locked" ? "; press <kbd>f</kbd> to drill it anyway" : ""}.</p>`;
  return `<section class="sv-card${detail ? " sv-detail" : ""}" data-skill="${esc(id)}">
    <header>${code(info.keys)} <span>${esc(info.name)}</span>${role ? ` <span class="sv-role">${esc(role)}</span>` : ""}<span class="sv-pill sv-pill-${status}">${status}</span></header>
    ${detail ? `<p class="sv-diag">${diagnosisLine(state, graph, id, lang)}</p>` : ""}
    ${charts}
    ${detail ? `<p class="sv-keys"><span><kbd>f</kbd> drill this next</span><span><kbd>esc</kbd> close</span></p>` : ""}
  </section>`;
}

function fmtDate(ms: number): string {
  return new Date(ms).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function sessionsTable(sessions: SessionRecord[]): string {
  if (!sessions.length) return `<p class="sv-empty">no sessions yet.</p>`;
  const rows = [...sessions]
    .reverse()
    .map(
      (s) => `<tr><td>${esc(fmtDate(s.start))}</td><td class="sv-r">${Math.max(0, Math.round((s.end - s.start) / 60000))}</td><td class="sv-r">${s.exercises}</td><td>${
        s.improved.map((x) => code(keysOf(x))).join(" ") || `<span class="sv-muted">&ndash;</span>`
      }</td></tr>`,
    )
    .join("");
  return `<table class="sv-sessions"><thead><tr><th>date</th><th class="sv-r">minutes</th><th class="sv-r">exercises</th><th>skills improved</th></tr></thead><tbody>${rows}</tbody></table>`;
}

// View ============================================================================================

export function renderStatsView(
  root: HTMLElement,
  state: ModelState,
  graph: SkillGraph,
  lang: string,
  opts: StatsViewOptions,
): StatsViewHandle {
  let tab: StatsTab = opts.tab;
  let selected = opts.selected;
  let detail = false;
  let rows: SkillRow[] = [];
  let focus = "";
  let sessionsCache: SessionRecord[] | null = null;

  function computeFocus(): string {
    if (opts.focus !== undefined && opts.focus !== null) return opts.focus;
    const now = opts.now ?? (state.log.length ? state.log[state.log.length - 1].t : Date.now() / 1000);
    try {
      return M.chooseFocus(state, lang, graph, now) ?? "";
    } catch (err) {
      console.error("stats: chooseFocus failed", err);
      return "";
    }
  }

  function refresh(): void {
    rows = skillRows(state, graph, lang, opts.skills);
    focus = computeFocus();
    sessionsCache = null;
    selected = Math.max(0, Math.min(rows.length - 1, selected));
  }

  function sessions(): SessionRecord[] {
    sessionsCache ??= opts.sessions ?? withImproved(state, graph, deriveSessions(state.log));
    return sessionsCache;
  }

  function skillsTab(): string {
    const timesById = new Map(rows.map((row) => [row.id, skillAttempts(state, graph, row.id, lang).map((rec) => rec.ms)]));
    let html = "";
    let i = 0;
    while (i < rows.length) {
      const tier = rows[i].tier;
      let cells = "";
      let hasSel = false;
      for (; i < rows.length && rows[i].tier === tier; i++) {
        cells += cell(rows[i], i, focus, selected, timesById.get(rows[i].id) ?? []);
        hasSel ||= i === selected;
      }
      html += `<section class="sv-tier"><h3>${tierTitle(graph, tier)}</h3><div class="sv-grid" role="row">${cells}</div></section>`;
      if (detail && hasSel && rows[selected]) html += card(state, graph, rows[selected].id, lang, rows[selected].id === focus ? "focus" : "history", true);
    }
    const sel = rows[selected];
    const lead = sel
      ? `<p class="sv-lead"><kbd>enter</kbd> history of ${code(keysOf(sel.id))} &middot; <kbd>f</kbd> drill ${code(keysOf(sel.id))} next</p>`
      : `<p class="sv-empty">no skills to show.</p>`;
    return `${lead}<div class="sv-tiers" role="grid">${html}</div>`;
  }

  function progressTab(): string {
    const ids = progressSkills(rows, focus);
    if (!ids.length) return `<p class="sv-empty">no skills in rotation yet.</p>`;
    return ids.map((id, k) => card(state, graph, id, lang, k === 0 && id === focus ? "focus" : "weak", false)).join("");
  }

  function render(): void {
    const tabs = STATS_TABS.map(
      (t, k) => `<button type="button" class="sv-tab${t === tab ? " sv-on" : ""}" data-tab="${t}" aria-selected="${t === tab}" role="tab"><kbd>${k + 1}</kbd> ${t}</button>`,
    ).join("");
    const body = tab === "skills" ? skillsTab() : tab === "progress" ? progressTab() : sessionsTable(sessions());
    const keys =
      tab === "skills"
        ? `<span><kbd>h</kbd><kbd>j</kbd><kbd>k</kbd><kbd>l</kbd> move</span><span><kbd>enter</kbd> history</span><span><kbd>f</kbd> drill this next</span><span><kbd>tab</kbd> next view</span>`
        : `<span><kbd>tab</kbd> next view</span><span><kbd>1</kbd><kbd>2</kbd><kbd>3</kbd> jump to view</span>`;
    root.innerHTML = `<div class="sv" data-tab="${tab}"><nav class="sv-tabs" role="tablist">${tabs}</nav><div class="sv-body">${body}</div><p class="sv-keys">${keys}</p></div>`;
    root.querySelector(".sv-sel")?.scrollIntoView?.({ block: "nearest" });
    if (detail) root.querySelector(".sv-detail")?.scrollIntoView?.({ block: "nearest" });
  }

  function select(i: number): void {
    if (i === selected || i < 0 || i >= rows.length) return;
    selected = i;
    detail = false;
    opts.onSelect(i, rows[i].id);
    render();
  }

  function setTab(t: StatsTab): void {
    if (t === tab) return;
    tab = t;
    detail = false;
    opts.onTab?.(t);
    render();
  }

  /** Grid neighbour by on-screen geometry, so j/k follow the wrapped layout. */
  function vertical(dir: 1 | -1): number {
    const cells = [...root.querySelectorAll<HTMLElement>(".sv-cell")];
    const cur = cells.find((c) => Number(c.dataset.i) === selected);
    if (!cur) return selected;
    const box = cur.getBoundingClientRect();
    const cx = box.left + box.width / 2;
    let best: { i: number; dy: number; dx: number } | null = null;
    for (const c of cells) {
      const b = c.getBoundingClientRect();
      const dy = (b.top - box.top) * dir;
      if (dy <= 2) continue;
      const dx = Math.abs(b.left + b.width / 2 - cx);
      if (!best || dy < best.dy - 2 || (Math.abs(dy - best.dy) <= 2 && dx < best.dx)) best = { i: Number(c.dataset.i), dy, dx };
    }
    return best ? best.i : selected;
  }

  function onClick(e: MouseEvent): void {
    const target = e.target as HTMLElement;
    const tabEl = target.closest<HTMLElement>("[data-tab]");
    if (tabEl && tabEl.classList.contains("sv-tab")) return setTab(tabEl.dataset.tab as StatsTab);
    const cellEl = target.closest<HTMLElement>(".sv-cell");
    if (cellEl) {
      const i = Number(cellEl.dataset.i);
      if (i === selected) {
        detail = !detail;
        render();
      } else select(i);
    }
  }
  root.addEventListener("click", onClick);

  function handleKey(key: string, shift = false): boolean {
    if (key === "Tab") {
      const k = STATS_TABS.indexOf(tab);
      setTab(STATS_TABS[(k + (shift ? STATS_TABS.length - 1 : 1)) % STATS_TABS.length]);
      return true;
    }
    if (key === "1" || key === "2" || key === "3") {
      setTab(STATS_TABS[Number(key) - 1]);
      return true;
    }
    if (tab !== "skills") return false;
    switch (key) {
      case "l":
      case "ArrowRight":
        select(Math.min(rows.length - 1, selected + 1));
        return true;
      case "h":
      case "ArrowLeft":
        select(Math.max(0, selected - 1));
        return true;
      case "j":
      case "ArrowDown":
        select(vertical(1));
        return true;
      case "k":
      case "ArrowUp":
        select(vertical(-1));
        return true;
      case "Enter":
        if (!rows[selected]) return false;
        detail = !detail;
        render();
        return true;
      case "f":
        if (!rows[selected]) return false;
        opts.onForce(rows[selected].id);
        return true;
      case "Escape":
        if (!detail) return false;
        detail = false;
        render();
        return true;
    }
    return false;
  }

  refresh();
  render();

  return {
    handleKey,
    update(next: ModelState, nextGraph?: SkillGraph) {
      state = next;
      if (nextGraph) graph = nextGraph;
      refresh();
      render();
    },
    get tab() {
      return tab;
    },
    get selected() {
      return selected;
    },
    destroy() {
      root.removeEventListener("click", onClick);
      root.innerHTML = "";
    },
  };
}
