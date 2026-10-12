// vim-trainer app: first visit, placement, the practice loop with its result
// strip, stats, settings and the session summary (docs/plan/10-ux.md).
//
// Keyboard ownership: while the editor has focus every key goes to Vim. The
// trainer's own keys are only live when focus is elsewhere: on the result strip
// (after an exercise ends the editor is locked and the strip takes focus), on
// the header, and on the full-screen pages. The single exception is F1, the
// mid-exercise hint, which the recorder stops before Vim sees it (an unmapped key
// would clear a pending command); `Esc Esc` in normal mode gives up.

import "./style.css";
import * as M from "./modelApi.ts";
import type { AttemptRecord, ModelState, SkillGraph, SkillState } from "./modelApi.ts";
import { loadIndex, loadExercise, skillsWithContent } from "./content.ts";
import { baseGraph, drillGraph, graphNodes } from "./graph.ts";
import { mountEditor, type EditorHandle } from "./editor.ts";
import {
  tokenize, displayKeys, checkPass, isGiveUp, band, BAND_LABEL, chooseHint, diffLines, linesEqual, exerciseHints,
  type Band, type DiffLine, type Mode, type Snapshot, type Token,
} from "./grading.ts";
import { load, save, clear, exportJson, parseImport, type Saved } from "./storage.ts";
import { skillInfo, EDITOR_TIPS } from "./skills.ts";
import { $, esc, code, taskHtml, confidenceBar, fmtSeconds } from "./dom.ts";
import type { ContentIndex, EditorProfile, EscapePref, Exercise, Settings } from "./types.ts";

// --- constants ------------------------------------------------------------------

const LANGS: [string, string][] = [
  ["python", "Python"], ["cpp", "C++"], ["typescript", "TypeScript"], ["javascript", "JavaScript"],
  ["go", "Go"], ["rust", "Rust"], ["lua", "Lua"],
];
const PROFILES: [EditorProfile, string, string][] = [
  ["neovim", "Neovim / Vim", "everything"],
  ["vscodevim", "VS Code + VSCodeVim", "hides unsupported commands"],
  ["ideavim", "JetBrains + IdeaVim", "hides unsupported commands"],
];
const ESCAPES: [EscapePref, string][] = [["esc", "<Esc>"], ["ctrl-[", "<C-[> (Ctrl-[)"], ["jk", "jk (insert-mode mapping)"]];
const DEFAULTS: Settings = { lang: "python", profile: "neovim", relativeNumbers: true, escape: "esc" };
const STOP_MS = 15 * 60 * 1000;
const STOP_COUNT = 40;
const WARMUPS = 2;
const PLACEMENT_SIZE = 12;

const langName = (id: string) => LANGS.find(([k]) => k === id)?.[1] ?? id;
const nowSec = () => Math.round(Date.now()) / 1000;
const rngSeed = () => crypto.getRandomValues(new Uint32Array(1))[0];

// --- state ---------------------------------------------------------------------

type View = "onboarding" | "placement-intro" | "practice" | "stats" | "settings" | "summary" | "message" | "loading";
type Role = "placement" | "warmup" | "practice";

interface Result {
  ok: boolean;
  tokens: Token[];
  keys: number;
  ms: number;
  band: Band;
  hint: string | null;
  diff: DiffLine[] | null;
  cursorAt: [number, number];
}

interface Current {
  ex: Exercise;
  skill: string;
  role: Role;
  retry: boolean;
  hintUsed: boolean;
  editor: EditorHandle;
  phase: "solving" | "result";
  result: Result | null;
  showAllHints: boolean;
  proNote: boolean;
}

let graph: SkillGraph;
let index: ContentIndex;
let saved: Saved;
let view: View = "loading";
const backStack: View[] = []; // where Esc returns to from stats / settings
let cur: Current | null = null;
let session = { startMs: Date.now(), sinceT: nowSec(), count: 0, warmupsLeft: WARMUPS, seen: new Set<string>(), recorded: false };
let placement: { queue: { skill: string; id: string }[]; i: number; records: AttemptRecord[] } | null = null;
let forced: string | null = null;
let afterPlacement = false;
let statsTab: "skills" | "sessions" = "skills";
let statsSel = 0;
let onboard = { step: 0, sel: 0 };
let settingsMsg = "";
let resetArmed = false;
let summaryData: { minutes: number; exercises: number; improved: { skill: string; delta: number }[]; mastered: string[]; unlocked: string[]; tip: string | null } | null = null;
let loadSeq = 0;

const S = () => saved.settings;
function persist(): void {
  if (!save(saved)) console.warn("vim-trainer: localStorage unavailable; progress will not survive a reload. Use export.");
}

// --- model helpers --------------------------------------------------------------------

function skillState(skill: string, lang = S().lang): SkillState | null {
  return saved.model.skills[skill]?.[lang] ?? null;
}

const STATUS_RANK: Record<string, number> = { mastered: 4, review: 3, active: 2, introduced: 1, locked: 0 };
/** Unlocking is shared across languages (04): best status over all languages. */
function skillStatus(skill: string): string {
  let best = "locked";
  for (const s of Object.values(saved.model.skills[skill] ?? {})) if ((STATUS_RANK[s.status] ?? 0) > (STATUS_RANK[best] ?? 0)) best = s.status;
  return best;
}

function counted(skill: string, lang = S().lang): AttemptRecord[] {
  return saved.model.log.filter((r) => r.skill === skill && r.lang === lang && !r.retry && !r.hint);
}

/** Trend from time on correct attempts: last 5 vs the 5 before. */
function trend(skill: string): string {
  const ms = counted(skill).filter((r) => r.ok).map((r) => r.ms);
  if (ms.length < 6) return "&ndash;";
  const last = ms.slice(-5), prev = ms.slice(-10, -5);
  const avg = (a: number[]) => a.reduce((x, y) => x + y, 0) / a.length;
  const ratio = avg(last) / avg(prev);
  return ratio < 0.95 ? "&uarr;" : ratio > 1.05 ? "&darr;" : "&rarr;";
}

function available(): Set<string> {
  return new Set(skillsWithContent(index, S().lang));
}

/** Rebuild the model's graph after the language, editor profile or content changes. */
function refreshGraph(): void {
  graph = drillGraph(S().profile, available());
}

function focusSkill(): string {
  const avail = available();
  let s = "";
  try {
    s = M.chooseFocus(saved.model, S().lang, graph, nowSec());
  } catch (err) {
    console.error("chooseFocus failed", err);
  }
  if (avail.has(s)) return s;
  // TODO(mvp): chooseFocus does not know which skills have content; fall back to
  // the weakest unlocked skill that does, then the lowest tier with content.
  const tiers = new Map(graphNodes(graph).map((n) => [n.id, n.tier]));
  const list = [...avail].sort((a, b) => (tiers.get(a) ?? 99) - (tiers.get(b) ?? 99));
  const unlocked = list.filter((id) => skillStatus(id) !== "locked");
  const pool = unlocked.length ? unlocked : list;
  pool.sort((a, b) => (skillState(a)?.confidence ?? 0) - (skillState(b)?.confidence ?? 0));
  return pool[0] ?? "";
}

function pickExercise(skill: string): string {
  const ids = index.langs[S().lang]?.skills[skill]?.ids ?? [];
  for (let k = 0; k < 4; k++) {
    let id = "";
    try {
      id = M.chooseExercise(saved.model, skill, S().lang, index, rngSeed(), graph);
    } catch (err) {
      console.error("chooseExercise failed", err);
      break;
    }
    if (ids.includes(id) && (!session.seen.has(id) || ids.every((x) => session.seen.has(x)))) return id;
  }
  const unseen = ids.filter((i) => !session.seen.has(i));
  const pool = unseen.length ? unseen : ids;
  return pool[rngSeed() % pool.length];
}

function warmupSkill(): string | null {
  try {
    const w = M.chooseWarmup(saved.model, S().lang, graph);
    return w && available().has(w) ? w : null;
  } catch (err) {
    console.error("chooseWarmup failed", err);
    return null;
  }
}

function placementQueue(): { skill: string; id: string }[] {
  const avail = available();
  const nodes = graphNodes(graph);
  const tierOf = new Map(nodes.map((n) => [n.id, n.tier]));
  const skills = [...avail].sort((a, b) => (tierOf.get(a) ?? 99) - (tierOf.get(b) ?? 99));
  const picks: string[] = [];
  // One per tier 1-9, then three more from tiers 3-4, then anything left (04).
  for (let tier = 1; tier <= 9; tier++) {
    const s = skills.find((id) => tierOf.get(id) === tier && !picks.includes(id));
    if (s) picks.push(s);
  }
  for (const s of skills.filter((id) => [3, 4].includes(tierOf.get(id) ?? -1) && !picks.includes(id)).slice(0, 3)) picks.push(s);
  for (const s of skills) if (picks.length < PLACEMENT_SIZE && !picks.includes(s) && (tierOf.get(s) ?? 0) > 0) picks.push(s);
  const used = new Set<string>();
  const queue: { skill: string; id: string }[] = [];
  for (const skill of picks.slice(0, PLACEMENT_SIZE)) {
    const id = pickExercise(skill);
    if (id && !used.has(id)) {
      used.add(id);
      queue.push({ skill, id });
    }
  }
  return queue.sort((a, b) => (tierOf.get(a.skill) ?? 99) - (tierOf.get(b.skill) ?? 99));
}

// --- views ---------------------------------------------------------------------

function show(v: View): void {
  view = v;
  $("#practice").hidden = v !== "practice";
  $("#page").hidden = v === "practice";
  renderHeader();
  if (v === "practice" && cur) {
    if (cur.phase === "solving") cur.editor.view.focus();
    else $("#foot").focus();
  }
}

function renderHeader(): void {
  $("#hdr-ctx").innerHTML = `${esc(langName(S().lang).toLowerCase())} &middot; ${esc(S().profile)}`;
  const skill = cur?.skill ?? (saved.placementDone ? focusSkill() : "");
  const info = skill ? skillInfo(skill) : null;
  $("#hdr-focus").innerHTML = info && view === "practice" ? `focus: ${code(info.keys)} &nbsp;${esc(info.name)}` : "";
}

const MODE_LABEL: Record<Mode, string> = {
  normal: "NORMAL", insert: "INSERT", replace: "REPLACE", visual: "VISUAL", "visual-line": "V-LINE", "visual-block": "V-BLOCK",
};

function renderModeline(): void {
  if (!cur) return;
  const m = cur.editor.recorder.mode();
  const el = $("#mode");
  el.textContent = MODE_LABEL[m];
  el.className = `mode ${m.startsWith("visual") ? "visual" : m}`;
  const snap = cur.editor.recorder.snapshot();
  $("#pos").textContent = `${snap.cursor[0]}:${snap.cursor[1] + 1}`;
  let progress = "";
  if (cur.role === "placement" && placement) {
    const n = cur.phase === "result" && !cur.retry ? placement.i : placement.i + 1; // finish() already advanced i
    progress = `placement ${Math.min(n, placement.queue.length)} of ${placement.queue.length}`;
  }
  else if (cur.role === "warmup") progress = `warm-up ${WARMUPS - session.warmupsLeft} of ${WARMUPS}`;
  else progress = `exercise ${session.count + (cur.phase === "solving" && !cur.retry ? 1 : 0)} of session`;
  if (cur.retry) progress += " (retry)";
  $("#progress").textContent = progress;
}

function renderSolvingFooter(): void {
  if (!cur) return;
  const st = skillState(cur.skill);
  const c = st?.confidence ?? 0;
  $("#foot").innerHTML = `
    <div class="skill">
      ${code(skillInfo(cur.skill).keys)}
      ${confidenceBar(c)}
      <span>confidence ${c.toFixed(2)}</span>
      <span>${st?.n ?? 0} reps</span>
      <span>trend ${trend(cur.skill)}</span>
      <span class="keys"><span><kbd>F1</kbd> hint</span><span><kbd>Esc</kbd><kbd>Esc</kbd> skip</span></span>
    </div>
    <div class="hint midhint" id="midhint" hidden></div>`;
}

function revealMidHint(): void {
  if (!cur || cur.phase !== "solving") return;
  const hints = exerciseHints(cur.ex);
  const text = hints[0]?.text ?? `the target is highlighted; ${skillInfo(cur.skill).keys} is the skill being drilled.`;
  cur.hintUsed = true; // logged: a hinted attempt does not move confidence (04)
  const el = $("#midhint");
  el.textContent = text;
  el.hidden = false;
}

/** A note in the mid-exercise hint slot that is not a hint (does not mark the attempt hinted). */
function showMidNote(text: string): void {
  const el = $("#midhint");
  el.textContent = text;
  el.hidden = false;
}

function renderResult(): void {
  if (!cur || !cur.result) return;
  const r = cur.result;
  const ex = cur.ex;
  const status = r.ok ? `<span class="ok">&#10003; correct</span>` : `<span class="fail">&#10007; gave up</span>`;
  const you = r.tokens.length
    ? `<span class="you">you ${code(displayKeys(r.tokens))} <span class="dim">${r.keys} keys &middot; ${fmtSeconds(r.ms)}${r.ok ? ` &middot; ${BAND_LABEL[r.band]}` : ""}</span></span>`
    : `<span class="you dim">no keys</span>`;
  const prominent = !r.ok || r.band === "over";
  const par = `<span class="par${prominent ? " prominent" : ""}">par ${code(ex.par.keys)} <span class="dim">${ex.par.count}</span></span>`;
  let extra = "";
  if (r.hint) extra += `<div class="hint">${esc(r.hint)}</div>`;
  if (!r.ok && r.diff) {
    extra += `<pre class="diff" aria-label="expected buffer diff">${r.diff
      .filter((d, i, a) => d.op !== " " || a.slice(Math.max(0, i - 1), i + 2).some((x) => x.op !== " "))
      .map((d) => `<span class="${d.op === "-" ? "del" : d.op === "+" ? "add" : ""}">${d.op} ${esc(d.text)}</span>`)
      .join("\n")}</pre>`;
  } else if (!r.ok && ex.kind === "cursor" && ex.expect.cursor) {
    extra += `<div class="note">target: line ${ex.expect.cursor[0]}, column ${ex.expect.cursor[1] + 1}; you were at ${r.cursorAt[0]}:${r.cursorAt[1] + 1}</div>`;
  }
  if (cur.showAllHints) {
    const all = [...exerciseHints(ex).map((h) => h.text), ...(ex.alternates ?? []).map((a) => `also accepted by the oracle: ${a}`)];
    extra += all.length ? `<ul class="allhints">${all.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>` : `<div class="note">no more hints for this exercise.</div>`;
  }
  if (cur.proNote) extra += `<div class="note">replaying the par keystroke by keystroke is planned for pro; it is not available yet.</div>`;
  if (cur.role !== "placement" && (Date.now() - session.startMs >= STOP_MS || session.count >= STOP_COUNT))
    extra += `<div class="stopline">good place to stop: ${session.count} exercises in ${Math.round((Date.now() - session.startMs) / 60000)} min. <kbd>q</kbd> ends the session.</div>`;
  const nextLabel = cur.role === "placement" && placement && placement.i >= placement.queue.length ? "finish placement" : "next";
  $("#foot").innerHTML = `
    <div class="result" id="result">
      <div class="row1">${status}${you}${par}</div>
      ${extra}
      <div class="keys"><span><kbd>space</kbd> ${nextLabel}</span><span><kbd>r</kbd> retry</span><span><kbd>?</kbd> hint</span><span class="off"><kbd>p</kbd> replay par <span class="dim">(pro)</span></span><span><kbd>q</kbd> end session</span></div>
    </div>`;
}

// --- the exercise loop -------------------------------------------------------------

function mountExercise(ex: Exercise, skill: string, role: Role, retry: boolean): void {
  cur?.editor.destroy();
  // kind=ex only passes through a ':' command (05), which the task text does not say.
  $("#task").innerHTML = taskHtml(ex.task) + (ex.kind === "ex" ? ` <span class="req">using an Ex <kbd>:</kbd> command</span>` : "");
  show("practice");
  const editor = mountEditor($("#code"), ex, { relativeNumbers: S().relativeNumbers, escape: S().escape });
  const me: Current = { ex, skill, role, retry, hintUsed: false, editor, phase: "solving", result: null, showAllHints: false, proNote: false };
  cur = me;
  session.seen.add(ex.id);
  renderHeader();
  renderSolvingFooter();
  renderModeline();
  editor.recorder.onChange(() => cur === me && renderModeline());
  editor.recorder.onCommandDone((snap) => {
    if (cur !== me || me.phase !== "solving") return;
    const tokens = tokenize(editor.recorder.events, S().escape, snap.mode);
    if (checkPass(ex, snap, tokens)) finish(me, true, snap);
    else if (ex.kind === "ex" && snap.mode === "normal" && ex.expect.lines && linesEqual(snap.lines, ex.expect.lines))
      showMidNote("the buffer is right, but this drill counts only a : command. u undoes back to the start.");
  });
  editor.recorder.onHintKey(() => cur === me && revealMidHint());
  editor.recorder.onKey(() => {
    if (cur !== me || me.phase !== "solving") return;
    // Let Vim handle the second <Esc> first, then end the attempt.
    if (isGiveUp(editor.recorder.events)) setTimeout(() => cur === me && me.phase === "solving" && finish(me, false, editor.recorder.snapshot()), 0);
  });
}

function finish(me: Current, ok: boolean, snap: Snapshot): void {
  const rec = me.editor.recorder;
  const ms = Math.round(rec.activeMs());
  const events = ok ? rec.events : rec.events.slice(0, -2); // drop the give-up <Esc><Esc>
  const tokens = tokenize(events, S().escape, snap.mode);
  const keys = tokens.length;
  const lang = S().lang;
  const record: AttemptRecord = {
    t: nowSec(), ex: me.ex.id, skill: me.skill, lang, ok, ms, keys, par: me.ex.par.count,
    hint: me.hintUsed, retry: me.retry, undo: rec.undoCount(),
  };
  const wantLines = me.ex.expect.lines;
  me.result = {
    ok, tokens, keys, ms,
    band: band(keys, me.ex.par.count),
    hint: chooseHint(me.ex, tokens, ok),
    diff: !ok && wantLines && !linesEqual(snap.lines, wantLines) ? diffLines(snap.lines, wantLines) : null,
    cursorAt: snap.cursor,
  };
  me.phase = "result";

  if (me.role === "placement" && placement) {
    if (!me.retry) {
      placement.records.push(record);
      placement.i++;
    }
  } else if (me.role === "practice") {
    try {
      saved.model = M.applyAttempt(saved.model, record, graph);
    } catch (err) {
      console.error("applyAttempt failed", err);
    }
  } // warm-ups are not counted (04)
  if (me.role !== "placement") {
    if (!me.retry) session.count++; // a retry is another attempt at the same exercise
    recordSession();
  }
  persist();

  me.editor.setLocked(true);
  renderResult();
  renderModeline();
  $("#foot").focus();
}

function recordSession(): void {
  const entry = { start: session.startMs, end: Date.now(), exercises: session.count, improved: [] as string[] };
  if (!session.recorded) {
    saved.sessions.push(entry);
    session.recorded = true;
  } else saved.sessions[saved.sessions.length - 1] = entry;
}

async function nextExercise(): Promise<void> {
  const seq = ++loadSeq;
  const lang = S().lang;
  let skill: string, id: string, role: Role;
  if (placement) {
    if (placement.i >= placement.queue.length) return finishPlacement();
    ({ skill, id } = placement.queue[placement.i]);
    role = "placement";
  } else {
    const w = session.warmupsLeft > 0 && !forced ? warmupSkill() : null;
    if (w) {
      skill = w;
      role = "warmup";
      session.warmupsLeft--;
    } else {
      session.warmupsLeft = 0;
      skill = forced && available().has(forced) ? forced : focusSkill();
      forced = null;
      role = "practice";
    }
    id = pickExercise(skill);
  }
  if (!skill || !id) {
    showMessage("No exercises for this language yet", `There is no content for ${langName(lang)} in build/. Pick another language in settings (,).`);
    return;
  }
  try {
    const ex = await loadExercise(id, skill, lang);
    if (seq !== loadSeq) return;
    mountExercise(ex, skill, role, false);
  } catch (err) {
    console.error(err);
    showMessage("Could not load an exercise", `${esc(id)}: ${esc((err as Error).message)}. Press enter to try another.`);
  }
}

function startSession(): void {
  session = { startMs: Date.now(), sinceT: nowSec(), count: 0, warmupsLeft: WARMUPS, seen: new Set(), recorded: false };
  void nextExercise();
}

function startPlacement(): void {
  placement = { queue: placementQueue(), i: 0, records: [] };
  if (!placement.queue.length) return finishPlacement();
  void nextExercise();
}

function finishPlacement(): void {
  if (placement) {
    try {
      saved.model = M.applyPlacement(saved.model, placement.records, graph);
    } catch (err) {
      console.error("applyPlacement failed", err);
    }
  }
  placement = null;
  saved.placementDone = true;
  persist();
  cur?.editor.destroy();
  cur = null;
  afterPlacement = true;
  backStack.length = 0;
  openStats();
}

function endSession(): void {
  if (placement) return finishPlacement();
  const sum = (() => {
    try {
      return M.sessionSummary(saved.model, session.sinceT, graph);
    } catch (err) {
      console.error("sessionSummary failed", err);
      return { improved: [], mastered: [], unlocked: [], tip: null };
    }
  })();
  const practised = saved.model.log.filter((r) => r.t >= session.sinceT && !r.retry).map((r) => r.skill);
  const top = sum.improved[0]?.skill ?? practised.sort((a, b) => practised.filter((x) => x === b).length - practised.filter((x) => x === a).length)[0];
  const tip = sum.tip ?? (top ? EDITOR_TIPS[top] ?? null : null);
  summaryData = {
    minutes: Math.max(0, Math.round((Date.now() - session.startMs) / 60000)),
    exercises: session.count,
    improved: sum.improved,
    mastered: sum.mastered,
    unlocked: sum.unlocked,
    tip,
  };
  if (session.recorded) {
    const last = saved.sessions[saved.sessions.length - 1];
    last.end = Date.now();
    last.improved = sum.improved.map((i) => i.skill);
  }
  persist();
  cur?.editor.destroy();
  cur = null;
  show("summary");
  renderSummary();
}

// --- pages -----------------------------------------------------------------------

function showMessage(title: string, html: string): void {
  show("message");
  $("#page").innerHTML = `<h1>${esc(title)}</h1><p>${html}</p><div class="keysline"><span><kbd>enter</kbd> continue</span><span><kbd>,</kbd> settings</span></div>`;
}

function renderSummary(): void {
  const d = summaryData;
  if (!d) return;
  const improved = d.improved.length
    ? `<ul>${d.improved.map((i) => `<li>${code(skillInfo(i.skill).keys)} ${esc(skillInfo(i.skill).name)} <span class="dim">+${i.delta.toFixed(2)}</span></li>`).join("")}</ul>`
    : `<p class="dim">no skill moved by 0.1 or more this time.</p>`;
  const unlock = [...d.mastered.map((s) => `mastered ${code(skillInfo(s).keys)}`), ...d.unlocked.slice(0, 1).map((s) => `unlocked ${code(skillInfo(s).keys)}`)];
  $("#page").innerHTML = `
    <h1>Session done</h1>
    <p class="lead">${d.minutes} min &middot; ${d.exercises} exercises</p>
    <h2>Skills improved</h2>${improved}
    ${unlock.length ? `<p>${unlock.join(" &middot; ")}</p>` : ""}
    ${d.tip ? `<h2>Try in your editor today</h2><p>${esc(d.tip)}</p>` : ""}
    <div class="keysline"><span><kbd>enter</kbd> new session</span><span><kbd>s</kbd> stats</span><span><kbd>,</kbd> settings</span></div>`;
}

interface StatRow { id: string; tier: number }

/** Skills with exercises in the current language, by tier (the rest cannot be drilled yet). */
function statRows(): StatRow[] {
  const avail = available();
  const order = new Map(Object.values(graph.skills).map((n) => [n.id, n.order]));
  const nodes = graphNodes(graph).filter((n) => n.tier <= 12 && avail.has(n.id));
  return nodes.sort((a, b) => a.tier - b.tier || (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0)).map((n) => ({ id: n.id, tier: n.tier }));
}

function openStats(): void {
  if (view !== "stats") backStack.push(view);
  show("stats");
  const rows = statRows();
  const focus = saved.placementDone ? focusSkill() : "";
  const i = rows.findIndex((r) => r.id === (forced ?? focus));
  statsSel = i >= 0 ? i : 0;
  renderStats();
}

function renderStats(): void {
  const lang = S().lang;
  const avail = available();
  const rows = statRows();
  const focus = saved.placementDone ? focusSkill() : "";
  const sel = rows[statsSel]?.id;
  const lead = afterPlacement && focus
    ? `We'll start with ${code(skillInfo(focus).keys)}. Press enter.`
    : sel
      ? `<kbd>enter</kbd> drills ${code(skillInfo(sel).keys)} next${avail.has(sel) ? "" : ` <span class="dim">(no ${esc(langName(lang))} exercises yet)</span>`}.`
      : "";
  let body = "";
  if (statsTab === "skills") {
    let tier = -1;
    body = `<table class="skills"><thead><tr><th>skill</th><th></th><th>confidence</th><th>n</th><th>status</th><th>trend</th><th>exercises</th></tr></thead><tbody>`;
    rows.forEach((r, i) => {
      if (r.tier !== tier) {
        tier = r.tier;
        body += `<tr class="tier"><td colspan="7">tier ${tier}</td></tr>`;
      }
      const info = skillInfo(r.id);
      const st = skillState(r.id);
      const status = skillStatus(r.id);
      const c = st?.confidence ?? 0;
      const cls = [status === "locked" ? "locked" : "", r.id === focus ? "focus" : "", i === statsSel ? "sel" : ""].join(" ");
      body += `<tr class="${cls}" data-i="${i}"><td>${code(info.keys)}</td><td>${esc(info.name)}</td><td>${confidenceBar(c)} ${c.toFixed(2)}</td><td>${st?.n ?? 0}</td><td>${esc(status)}</td><td>${trend(r.id)}</td><td class="dim">${index.langs[lang]?.skills[r.id]?.count ?? 0}</td></tr>`;
    });
    body += `</tbody></table>`;
    const hidden = graphNodes(graph).filter((n) => n.tier <= 12 && !avail.has(n.id)).length;
    if (hidden) body += `<p class="note">${hidden} more skills in the plan have no ${esc(langName(lang))} exercises yet.</p>`;
  } else {
    const list = [...saved.sessions].reverse();
    body = list.length
      ? `<table class="sessions"><thead><tr><th>date</th><th>minutes</th><th>exercises</th><th>skills improved</th></tr></thead><tbody>${list
          .map((s) => `<tr><td>${esc(new Date(s.start).toLocaleString())}</td><td>${Math.round((s.end - s.start) / 60000)}</td><td>${s.exercises}</td><td>${s.improved.map((x) => code(skillInfo(x).keys)).join(" ") || '<span class="dim">&ndash;</span>'}</td></tr>`)
          .join("")}</tbody></table>`
      : `<p class="dim">no sessions yet.</p>`;
  }
  $("#page").innerHTML = `
    <h1>Stats <span class="dim" style="font-size:14px;font-weight:400">${esc(langName(lang))}</span></h1>
    <p class="lead">${lead}</p>
    <div class="tabs"><span class="${statsTab === "skills" ? "on" : ""}">Skills</span><span class="${statsTab === "sessions" ? "on" : ""}">Sessions</span><span><kbd>tab</kbd> switch</span></div>
    ${body}
    <div class="keysline"><span><kbd>j</kbd><kbd>k</kbd> move</span><span><kbd>enter</kbd> drill this</span><span><kbd>tab</kbd> skills / sessions</span><span><kbd>,</kbd> settings</span><span><kbd>Esc</kbd> back</span></div>`;
  $("#page").querySelectorAll<HTMLElement>("tr[data-i]").forEach((tr) =>
    tr.addEventListener("click", () => {
      statsSel = Number(tr.dataset.i);
      renderStats();
    }),
  );
  $("#page").querySelector("tr.sel")?.scrollIntoView({ block: "nearest" });
}

function drillSelected(): void {
  const rows = statRows();
  const id = afterPlacement ? focusSkill() : rows[statsSel]?.id;
  afterPlacement = false;
  if (id && available().has(id)) forced = id;
  if (cur && cur.phase === "solving") return show("practice");
  cur?.editor.destroy();
  cur = null;
  if (session.count === 0 && !session.recorded) startSession();
  else void nextExercise();
}

function renderSettings(): void {
  const s = S();
  const avail = (l: string) => skillsWithContent(index, l).length > 0;
  const radio = <T extends string>(name: string, opts: [T, string][], val: T) =>
    opts.map(([v, label]) => `<label><input type="radio" name="${name}" value="${v}"${v === val ? " checked" : ""}> ${esc(label)}</label>`).join("");
  $("#page").innerHTML = `
    <h1>Settings</h1>
    <form class="settings" id="settings-form" onsubmit="return false">
      <fieldset><legend>Language</legend>
        <select name="lang">${LANGS.map(([k, n]) => `<option value="${k}"${k === s.lang ? " selected" : ""}${avail(k) ? "" : " disabled"}>${esc(n)}${avail(k) ? "" : " (no exercises yet)"}</option>`).join("")}</select>
      </fieldset>
      <fieldset><legend>Editor profile</legend>${radio("profile", PROFILES.map(([k, n]) => [k, n] as [EditorProfile, string]), s.profile)}</fieldset>
      <fieldset><legend>Line numbers</legend>${radio("rel", [["yes", "relative (default)"], ["no", "absolute"]], s.relativeNumbers ? "yes" : "no")}</fieldset>
      <fieldset><legend>Escape key (counted as one keystroke either way)</legend>${radio("escape", ESCAPES, s.escape)}</fieldset>
      <p class="note">Keyboard layout: pars count keystrokes, not physical keys, so they are the same on every layout.</p>
      <p class="note">Theme: dark (the only theme in v1).</p>
      <fieldset><legend>Your data (stored only in this browser)</legend>
        <button type="button" id="btn-export">export JSON</button>
        <button type="button" id="btn-import">import JSON</button>
        <input type="file" id="file-import" accept="application/json,.json" hidden>
        <button type="button" class="danger" id="btn-reset">${resetArmed ? "press again to erase everything" : "reset"}</button>
      </fieldset>
      <div class="msg" id="settings-msg">${esc(settingsMsg)}</div>
    </form>
    <div class="keysline"><span><kbd>tab</kbd> move between controls</span><span><kbd>Esc</kbd> back</span></div>`;
  const form = $("#settings-form") as HTMLFormElement;
  form.addEventListener("change", (e) => {
    const t = e.target as HTMLInputElement;
    if (t.name === "lang") s.lang = t.value;
    if (t.name === "profile") s.profile = t.value as EditorProfile;
    if (t.name === "lang" || t.name === "profile") refreshGraph();
    if (t.name === "rel") s.relativeNumbers = t.value === "yes";
    if (t.name === "escape") s.escape = t.value as EscapePref;
    persist();
    settingsMsg = "saved; applies from the next exercise.";
    $("#settings-msg").textContent = settingsMsg;
    renderHeader();
  });
  $("#btn-export").addEventListener("click", () => exportJson(saved));
  $("#btn-import").addEventListener("click", () => ($("#file-import") as HTMLInputElement).click());
  $("#file-import").addEventListener("change", async (e) => {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (!f) return;
    try {
      saved = parseImport(await f.text());
      saved.settings = { ...DEFAULTS, ...saved.settings };
      refreshGraph();
      persist();
      settingsMsg = `imported ${saved.model.log.length} attempts.`;
    } catch (err) {
      settingsMsg = `import failed: ${(err as Error).message}`;
    }
    renderSettings();
  });
  $("#btn-reset").addEventListener("click", () => {
    if (!resetArmed) {
      resetArmed = true;
      return renderSettings();
    }
    clear();
    location.reload();
  });
}

function openSettings(): void {
  if (view !== "settings") backStack.push(view);
  show("settings");
  settingsMsg = "";
  resetArmed = false;
  renderSettings();
}

function goBack(): void {
  afterPlacement = false;
  const to = backStack.pop();
  if (to === "stats") return show("stats"), renderStats();
  if (to === "summary" && summaryData) return show("summary"), renderSummary();
  if (to === "onboarding") return show("onboarding"), renderOnboarding();
  if (to === "placement-intro" || (!saved.placementDone && !placement && !cur)) return show("placement-intro"), renderPlacementIntro();
  if (cur) return show("practice");
  if (to === "message") return void nextExercise();
  startSession();
}

// --- first visit -------------------------------------------------------------------

function onboardOptions(): { label: string; sub: string; off: boolean; apply: () => void }[] {
  const s = S();
  if (onboard.step === 0)
    return LANGS.map(([k, n]) => {
      const off = skillsWithContent(index, k).length === 0;
      return { label: n, sub: off ? "no exercises yet" : "", off, apply: () => (s.lang = k) };
    });
  if (onboard.step === 1) return PROFILES.map(([k, n, sub]) => ({ label: n, sub, off: false, apply: () => (s.profile = k) }));
  return [
    { label: "Yes, relative line numbers", sub: "default; the m.rel drills use them", off: false, apply: () => (s.relativeNumbers = true) },
    { label: "No, absolute numbers", sub: "", off: false, apply: () => (s.relativeNumbers = false) },
  ];
}

function renderOnboarding(): void {
  const q = ["Which language do you want to practise in?", "Which editor do you use Vim keys in?", "Relative line numbers?"][onboard.step];
  const opts = onboardOptions();
  $("#page").innerHTML = `
    <p class="steps">first visit &middot; ${onboard.step + 1} of 4</p>
    <h1>${esc(q)}</h1>
    <ul class="choices">${opts.map((o, i) => `<li class="choice${i === onboard.sel ? " sel" : ""}${o.off ? " off" : ""}" data-i="${i}"><span class="n">${i + 1}</span><span>${esc(o.label)}</span><span class="sub">${esc(o.sub)}</span></li>`).join("")}</ul>
    <div class="keysline"><span><kbd>j</kbd><kbd>k</kbd> move</span><span><kbd>enter</kbd> choose</span><span><kbd>1</kbd>-<kbd>${opts.length}</kbd> pick</span></div>`;
  $("#page").querySelectorAll<HTMLElement>(".choice").forEach((el) => el.addEventListener("click", () => onboardChoose(Number(el.dataset.i))));
}

function onboardChoose(i: number): void {
  const opts = onboardOptions();
  const o = opts[i];
  if (!o || o.off) return;
  o.apply();
  onboard = { step: onboard.step + 1, sel: 0 };
  if (onboard.step >= 3) {
    refreshGraph();
    persist();
    show("placement-intro");
    renderPlacementIntro();
  } else renderOnboarding();
}

function renderPlacementIntro(): void {
  const n = placementQueue().length;
  $("#page").innerHTML = `
    <p class="steps">first visit &middot; 4 of 4</p>
    <h1>Let's see where you are</h1>
    <p class="lead">${n} short exercises in ${esc(langName(S().lang))}, about five minutes. There is no pass mark; the results seed your chart.</p>
    <p class="note">Solve each one in the editor. <kbd>Esc</kbd><kbd>Esc</kbd> in normal mode skips one you don't know.</p>
    <div class="keysline"><span><kbd>enter</kbd> start</span><span><kbd>x</kbd> skip placement</span></div>`;
}

// --- keyboard -------------------------------------------------------------------

function onKey(e: KeyboardEvent): void {
  if (e.key === "F1") {
    e.preventDefault();
    if (view === "practice") revealMidHint();
    return;
  }
  const target = e.target as HTMLElement | null;
  if (target?.closest?.(".cm-editor")) return; // Vim owns every key in the editor
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const inField = target && /^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(target.tagName);
  if (inField && e.key !== "Escape") return;
  const k = e.key;
  const handled = (): void => e.preventDefault();

  switch (view) {
    case "onboarding": {
      const n = onboardOptions().length;
      if (k === "j" || k === "ArrowDown") (onboard.sel = (onboard.sel + 1) % n), renderOnboarding(), handled();
      else if (k === "k" || k === "ArrowUp") (onboard.sel = (onboard.sel + n - 1) % n), renderOnboarding(), handled();
      else if (k === "Enter") onboardChoose(onboard.sel), handled();
      else if (/^[1-9]$/.test(k) && Number(k) <= n) onboardChoose(Number(k) - 1), handled();
      return;
    }
    case "placement-intro":
      if (k === "Enter") startPlacement(), handled();
      else if (k === "x") finishPlacement(), handled();
      return;
    case "practice":
      if (!cur) return;
      if (cur.phase === "result") {
        if (k === " " || k === "Enter") handled(), void nextExercise();
        else if (k === "r") handled(), mountExercise(cur.ex, cur.skill, cur.role, true);
        else if (k === "q") handled(), endSession();
        else if (k === "?") handled(), (cur.showAllHints = !cur.showAllHints), renderResult();
        else if (k === "p") handled(), (cur.proNote = true), renderResult();
        else if (k === "s") handled(), openStats();
        else if (k === ",") handled(), openSettings();
      } else {
        // Focus left the editor mid-exercise (a click): header keys, enter returns.
        if (k === "s") handled(), openStats();
        else if (k === ",") handled(), openSettings();
        else if (k === "Enter" || k === "Escape" || k === "i") handled(), cur.editor.view.focus();
      }
      return;
    case "stats": {
      const rows = statRows();
      if (k === "Escape") handled(), goBack();
      else if (k === "Tab") handled(), (statsTab = statsTab === "skills" ? "sessions" : "skills"), renderStats();
      else if (k === "j" || k === "ArrowDown") handled(), (statsSel = Math.min(rows.length - 1, statsSel + 1)), (afterPlacement = false), renderStats();
      else if (k === "k" || k === "ArrowUp") handled(), (statsSel = Math.max(0, statsSel - 1)), (afterPlacement = false), renderStats();
      else if (k === "Enter") handled(), drillSelected();
      else if (k === ",") handled(), openSettings();
      return;
    }
    case "settings":
      if (k === "Escape") handled(), goBack();
      return;
    case "summary":
      if (k === "Enter") handled(), startSession();
      else if (k === "s") handled(), openStats();
      else if (k === ",") handled(), openSettings();
      return;
    case "message":
      if (k === "Enter") handled(), void nextExercise();
      else if (k === ",") handled(), openSettings();
      return;
  }
}

// --- boot ------------------------------------------------------------------------

async function boot(): Promise<void> {
  index = await loadIndex();
  const prior = load();
  saved = prior ?? { version: 1, settings: { ...DEFAULTS }, model: M.newState(baseGraph()), placementDone: false, sessions: [] };
  saved.settings = { ...DEFAULTS, ...saved.settings };
  refreshGraph();
  document.addEventListener("keydown", onKey);
  $("#nav-stats").addEventListener("click", (e) => (e.preventDefault(), openStats()));
  $("#nav-settings").addEventListener("click", (e) => (e.preventDefault(), openSettings()));
  $("#hdr-ctx").addEventListener("click", (e) => (e.preventDefault(), openSettings()));
  // Clicking the locked editor must not strand focus: send it back to the strip.
  $("#code").addEventListener("mousedown", (e) => {
    if (cur?.phase === "result") {
      e.preventDefault();
      $("#foot").focus();
    }
  });
  if (!prior) {
    show("onboarding");
    renderOnboarding();
  } else if (!saved.placementDone) {
    show("placement-intro");
    renderPlacementIntro();
  } else startSession();
}

declare global {
  interface Window {
    vimTrainer: { saved: () => Saved; model: () => ModelState; current: () => Current | null };
  }
}
window.vimTrainer = { saved: () => saved, model: () => saved.model, current: () => cur };

boot().catch((err) => {
  console.error(err);
  document.body.insertAdjacentHTML("afterbegin", `<p style="padding:16px;color:#d98a7a">vim-trainer failed to start: ${esc(String(err))}</p>`);
});
