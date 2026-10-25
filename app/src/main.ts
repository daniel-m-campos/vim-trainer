// vim-trainer app: first visit, placement, the practice loop with its result
// strip, stats, settings and the session summary.
//
// Keyboard ownership: while the editor has focus every key goes to Vim. The
// trainer's own keys are only live when focus is elsewhere: on the result strip
// (after an exercise ends the editor is locked and the strip takes focus), on
// the header, and on the full-screen pages. The single exception is F1, the
// mid-exercise hint, which the recorder stops before Vim sees it (an unmapped key
// would clear a pending command); `Esc Esc` in normal mode gives up (an <Esc> that
// cancels a pending operator or count does not start it; the first qualifying <Esc>
// shows "Esc again to give up" in the footer).

import "./style.css";
import * as M from "./modelApi.ts";
import type { AttemptRecord, ModelState, SkillGraph, SkillState } from "./modelApi.ts";
import { loadIndex, loadExercise, skillsWithContent, contentBase } from "./content.ts";
import { baseGraph, drillGraph, graphNodes } from "./graph.ts";
import { mountEditor, type EditorHandle } from "./editor.ts";
import {
  tokenize, displayKeys, replayKeys, checkPass, isGiveUp, armsGiveUp, GIVE_UP_MS, band, BAND_LABEL, chooseHint, diffLines, linesEqual, exerciseHints,
  placementPass, unrecoverable,
  type Band, type DiffLine, type Mode, type Snapshot, type Token,
} from "./grading.ts";
import { load, save, clear, exportJson, parseImport, pushError, ERRORS_MAX, type ErrorEntry, type PlacementProgress, type Saved } from "./storage.ts";
import { skillInfo, EDITOR_TIPS } from "./skills.ts";
import { $, esc, code, taskHtml, confidenceBar, fmtSeconds } from "./dom.ts";
import { issueUrl, FLAG_REASONS, ISSUES_URL, REPO, SOURCES_URL, VERSION, type FlagReason } from "./feedback.ts";
import { renderStatsView, type StatsTab, type StatsViewHandle } from "./stats/statsView.ts";
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
/** The views location.hash can name; the hash is the single source of truth for which one shows. */
type Route = "practice" | "stats" | "settings" | "placement" | "placement-intro";
const ROUTES: Route[] = ["practice", "stats", "settings", "placement", "placement-intro"];

interface Result {
  ok: boolean;
  tokens: Token[];
  keys: number;
  ms: number;
  band: Band;
  hint: string | null;
  diff: DiffLine[] | null;
  cursorAt: [number, number];
  /** Why a give-up shows no diff: the ex-kind buffer already matched. */
  note: string | null;
  /** A correct placement attempt over the key cap (grading.placementPass): logged as not passed. */
  gateNote: string | null;
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
  /** The attempt record finish() built; the "!" flag finds it in the log by identity. */
  record: AttemptRecord | null;
  flagging: boolean; // the "!" picker is open in #foot
  flagReason: FlagReason | null;
  flagged: FlagReason | null; // sent: the strip says so
  flagUrl: string; // the issue form URL, linked on the strip in case the new tab did not open
  flagBlocked: boolean; // window.open returned null: a popup blocker stopped the new tab
  nudged: boolean; // the "not quite ... u to undo" note was shown (once per exercise)
}

let graph: SkillGraph;
let index: ContentIndex;
let saved: Saved;
let view: View = "loading";
let onboarding = false; // first visit: every route shows the setup questions until they are answered
let fromOnboarding = false; // the placement intro follows the setup questions in this page load
let langChanged = false; // the language changed in settings: Esc goes to practice, not back to old stats
let cur: Current | null = null;
// solved / skipped / beat count first attempts (not retries), like count; the summary shows them (QA #35).
let session = { startMs: Date.now(), sinceT: nowSec(), count: 0, solved: 0, skipped: 0, beat: 0, warmupsLeft: WARMUPS, seen: new Set<string>(), recorded: false };
/** The placement in progress; persist() mirrors it into saved.placement so a reload resumes it. */
let placement: PlacementProgress | null = null;
let forced: string | null = null;
let afterPlacement = false;
let announced = ""; // the focus skill the post-placement stats line names; enter drills exactly this one
let placementMoment = ""; // "placement complete: N skills placed, M mastered." on the stats page after placement
const pendingErrors: ErrorEntry[] = []; // errors caught before boot loaded `saved`
let broke: "no" | "yes" | "seen" = "no"; // an error was caught: the footer says so until the next exercise
let statsTab: StatsTab = "skills";
let statsSel = 0;
let statsView: StatsViewHandle | null = null;
let onboard = { step: 0, sel: 0 };
let settingsMsg = "";
let resetArmed = false;
let pendingImport: Saved | null = null; // a checked import file waiting for y / n in settings (QA #19)
let summaryData: { minutes: number; exercises: number; solved: number; skipped: number; beat: number; improved: { skill: string; delta: number }[]; mastered: string[]; unlocked: string[]; tip: string | null } | null = null;
let loadSeq = 0;
let advancing = false; // space/enter on the strip: ignore the strip until the next exercise renders
let escCueTimer: ReturnType<typeof setTimeout> | null = null;

const S = () => saved.settings;
function persist(): void {
  if (placement) saved.placement = placement;
  else delete saved.placement;
  if (!save(saved)) console.warn("vim-trainer: localStorage unavailable; progress will not survive a reload. Use export.");
}

// --- error visibility (no telemetry) ------------------------------------------------

const BROKE_HTML = `<div class="note broke" id="broke">something broke &mdash; export your data and flag it with <kbd>!</kbd></div>`;

/** Keeps an uncaught error in saved.errors (exported, and put in the "!" issue); called by the window error handlers below. */
function recordError(message: string, stack: string | undefined): void {
  const entry: ErrorEntry = {
    t: nowSec(), version: VERSION, route: location.hash.slice(1) || view,
    message: message.slice(0, 500), stack: (stack ?? "").split("\n").slice(0, 5).join("\n"),
  };
  if (!saved) {
    if (pendingErrors.length >= ERRORS_MAX) pendingErrors.shift(); // the same cap as saved.errors
    return void pendingErrors.push(entry);
  }
  pushError(saved, entry);
  persist();
  if (broke === "no") broke = "yes";
  const foot = document.getElementById("foot");
  if (broke === "yes" && view === "practice" && foot && !document.getElementById("broke")) foot.insertAdjacentHTML("afterbegin", BROKE_HTML);
}

window.addEventListener("error", (e) => recordError(String(e.message), (e.error as Error | undefined)?.stack));
window.addEventListener("unhandledrejection", (e) => {
  const r = e.reason as unknown;
  recordError(r instanceof Error ? r.message : String(r), r instanceof Error ? r.stack : undefined);
});

// --- model helpers --------------------------------------------------------------------

function skillState(skill: string, lang = S().lang): SkillState | null {
  return saved.model.skills[skill]?.[lang] ?? null;
}

const STATUS_RANK: Record<string, number> = { mastered: 4, review: 3, active: 2, introduced: 1, locked: 0 };
/** Unlocking is shared across languages: best status over all languages. */
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
  // TODO: chooseFocus does not know which skills have content; fall back to
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

/** True once `lang`'s placement ran or was skipped; boot, goBack, stats and the header ask. */
function placed(lang = S().lang): boolean {
  return saved.placementDone[lang] === true;
}

/** Skills mastered (or due for review) in a language other than `lang`; placementQueue skips them. */
function masteredElsewhere(lang: string): Set<string> {
  const out = new Set<string>();
  for (const [id, langs] of Object.entries(saved.model.skills))
    for (const [l, st] of Object.entries(langs)) if (l !== lang && (st.status === "mastered" || st.status === "review")) out.add(id);
  return out;
}

function placementQueue(): { skill: string; id: string }[] {
  const lang = S().lang;
  const skip = masteredElsewhere(lang);
  const avail = [...available()].filter((id) => !skip.has(id));
  const nodes = graphNodes(graph);
  const tierOf = new Map(nodes.map((n) => [n.id, n.tier]));
  const skills = avail.sort((a, b) => (tierOf.get(a) ?? 99) - (tierOf.get(b) ?? 99));
  const picks: string[] = [];
  // One per tier 1-9, then three more from tiers 3-4, then anything left.
  // A second language (some skills mastered elsewhere) fills after the tier pass with
  // the skills that weigh most in this language instead.
  for (let tier = 1; tier <= 9; tier++) {
    const s = skills.find((id) => tierOf.get(id) === tier && !picks.includes(id));
    if (s) picks.push(s);
  }
  const weight = (id: string) => graph.skills[id]?.langWeights?.[lang] ?? 1;
  const rest = skip.size ? [...skills].sort((a, b) => weight(b) - weight(a)) : skills;
  if (!skip.size) for (const s of skills.filter((id) => [3, 4].includes(tierOf.get(id) ?? -1) && !picks.includes(id)).slice(0, 3)) picks.push(s);
  for (const s of rest) if (picks.length < PLACEMENT_SIZE && !picks.includes(s) && (tierOf.get(s) ?? 0) > 0) picks.push(s);
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
  if (v !== "stats" && statsView) {
    statsView.destroy();
    statsView = null;
  }
  if (v !== view) window.scrollTo(0, 0); // a new screen starts at its top, not the last one's scroll (QA #43)
  view = v;
  // The attempt clock does not run while stats or settings cover the exercise.
  if (cur?.phase === "solving") cur.editor.recorder.setAway(v !== "practice");
  $("#practice").hidden = v !== "practice";
  $("#page").hidden = v === "practice";
  renderHeader();
  if (v === "practice" && cur) {
    if (cur.phase === "solving") cur.editor.view.focus();
    else $("#foot").focus();
  }
}

function renderHeader(): void {
  // Nothing about the setup before the first question is answered (QA #34).
  $("#hdr-ctx").innerHTML = onboarding && onboard.step === 0 ? "" : `${esc(langName(S().lang).toLowerCase())} &middot; ${esc(S().profile)}`;
  const info = cur && view === "practice" ? skillInfo(cur.skill) : null;
  // A warm-up is not the focus skill: say so, so the header never names a skill the exercise is not (QA #4).
  const label = cur?.role === "warmup" ? "warm-up" : "focus";
  $("#hdr-focus").innerHTML = info ? `${label}: ${code(info.keys)} &nbsp;${esc(info.name)}` : "";
  renderNav();
}

/** The header's stats / settings links: hidden on their own page, and the key shown only where onKey handles it (QA #24); called by renderHeader. */
function renderNav(): void {
  const sKey = view === "practice" || view === "summary";
  const commaKey = sKey || view === "stats" || view === "message";
  const stats = $("#nav-stats"), settings = $("#nav-settings");
  stats.hidden = view === "stats" || view === "onboarding";
  settings.hidden = view === "settings";
  stats.innerHTML = `${sKey ? "<kbd>s</kbd> " : ""}stats`;
  settings.innerHTML = `${commaKey ? "<kbd>,</kbd> " : ""}settings`;
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
    // Position of this exercise in the queue; placement.i has already moved on once
    // the first attempt finished, so it is wrong for the strip and for retries.
    const at = placement.queue.findIndex((q) => q.id === cur!.ex.id);
    const n = at >= 0 ? at + 1 : cur.phase === "result" || cur.retry ? placement.i : placement.i + 1;
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
      <span class="keys"><span><kbd>F1</kbd> hint</span><span class="giveup" id="giveup">${GIVEUP_IDLE}</span></span>
    </div>
    <div class="hint midhint" id="midhint" hidden></div>
    <div class="note nudge" id="nudge" hidden></div>${brokeHtml()}`;
}

/** The "something broke" line while it is due; called by the two footer renderers. */
function brokeHtml(): string {
  return broke === "yes" ? BROKE_HTML : "";
}

const GIVEUP_IDLE = `<kbd>Esc</kbd><kbd>Esc</kbd> skip`;
const GIVEUP_ARMED = `<kbd>Esc</kbd> again to give up`;

/** The footer's give-up label: armed for GIVE_UP_MS after a qualifying first <Esc>. */
function setEscCue(armed: boolean): void {
  if (escCueTimer) clearTimeout(escCueTimer);
  escCueTimer = armed ? setTimeout(() => setEscCue(false), GIVE_UP_MS) : null;
  const el = document.getElementById("giveup");
  if (!el || el.classList.contains("armed") === armed) return;
  el.classList.toggle("armed", armed);
  el.innerHTML = armed ? GIVEUP_ARMED : GIVEUP_IDLE;
}

/** Muted one-line provenance of the snippet: "from exercism/python &middot; MIT". */
function sourceLine(ex: Exercise): { html: string; title: string } {
  const s = ex.source;
  if (!s?.repo) return { html: "&nbsp;", title: "" };
  if (s.repo === "author") return { html: "written for vim-trainer", title: "" }; // hand-written sample content
  const repo = s.repo.replace(/^(?:https?:\/\/)?(?:www\.)?github\.com\//, "").replace(/\.git$/, "");
  const lines = s.lines ? ` lines ${s.lines[0]}-${s.lines[1]}` : "";
  return { html: `from ${esc(repo)}${s.license ? ` &middot; ${esc(s.license)}` : ""}`, title: `${s.path ?? ""}${lines}` };
}

/** The target line with a caret under the target column, for a cursor give-up. */
function targetLineHtml(ex: Exercise, at: [number, number]): string {
  const text = ex.start.lines[at[0] - 1];
  if (text === undefined) return "";
  const pad = text.slice(0, at[1]).replace(/[^\t]/g, " ");
  return `<pre class="diff targetline" aria-label="target position"><span class="dim">${String(at[0]).padStart(3)}</span>  ${esc(text)}\n     ${pad}<span class="add">^</span></pre>`;
}

function revealMidHint(): void {
  if (!cur || cur.phase !== "solving") return;
  const hints = exerciseHints(cur.ex);
  const text = hints[0]?.text ?? `the target is highlighted; ${skillInfo(cur.skill).keys} is the skill being drilled.`;
  cur.hintUsed = true; // logged: a hinted attempt does not move confidence
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
  // r.note is set only when the "only a : command" rule rejected a matching buffer (QA #40).
  const status = r.ok ? `<span class="ok">&#10003; correct</span>` : `<span class="fail">&#10007; gave up${r.note ? ": needs an Ex (:) command" : ""}</span>`;
  const you = r.tokens.length
    ? `<span class="you">you ${code(displayKeys(r.tokens))} <span class="dim">${r.keys} keys &middot; ${fmtSeconds(r.ms)}${r.ok ? ` &middot; ${BAND_LABEL[r.band]}` : ""}</span></span>`
    : `<span class="you dim">no keys</span>`;
  const prominent = !r.ok || r.band === "over";
  const par = `<span class="par${prominent ? " prominent" : ""}">par ${code(ex.par.keys)} <span class="dim">${ex.par.count}</span></span>`;
  const beat = r.ok && r.band === "beat" ? `<span class="beat">you beat par: ${r.keys} vs ${ex.par.count}</span>` : "";
  let extra = brokeHtml();
  if (r.gateNote) extra += `<div class="note gate">${esc(r.gateNote)}</div>`;
  if (r.hint) extra += `<div class="hint">${esc(r.hint)}</div>`;
  if (!r.ok && r.diff) {
    extra += `<pre class="diff" aria-label="expected buffer diff">${r.diff
      .filter((d, i, a) => d.op !== " " || a.slice(Math.max(0, i - 1), i + 2).some((x) => x.op !== " "))
      .map((d) => `<span class="${d.op === "-" ? "del" : d.op === "+" ? "add" : ""}">${d.op} ${esc(d.text)}</span>`)
      .join("\n")}</pre>`;
  } else if (!r.ok && r.note) {
    extra += `<div class="note">${esc(r.note)}</div>`;
  } else if (!r.ok && ex.kind === "cursor" && ex.expect.cursor) {
    extra += `<div class="note">target: line ${ex.expect.cursor[0]}, column ${ex.expect.cursor[1] + 1} (marked in the editor); you were at ${r.cursorAt[0]}:${r.cursorAt[1] + 1}</div>`;
    extra += targetLineHtml(ex, ex.expect.cursor);
  }
  if (cur.showAllHints) {
    const all = [...exerciseHints(ex).map((h) => h.text), ...(ex.alternates ?? []).map((a) => `also accepted by the oracle: ${a}`)];
    extra += all.length ? `<ul class="allhints">${all.map((h) => `<li>${esc(h)}</li>`).join("")}</ul>` : `<div class="note">no more hints for this exercise.</div>`;
  }
  if (cur.role !== "placement" && (Date.now() - session.startMs >= STOP_MS || session.count >= STOP_COUNT))
    extra += `<div class="stopline">good place to stop: ${session.count} exercises in ${Math.round((Date.now() - session.startMs) / 60000)} min. <kbd>q</kbd> ends the session.</div>`;
  const nextLabel = cur.role === "placement" && placement && placement.i >= placement.queue.length ? "finish placement" : "next";
  if (cur.flagged) {
    const link = `<a href="${esc(cur.flagUrl)}" target="_blank" rel="noopener">issue form</a>`;
    extra += cur.flagBlocked
      ? `<div class="note flagged">flagged: ${esc(cur.flagged)}. Popup blocked: open the ${link} and submit it there.</div>`
      : `<div class="note flagged">flagged: ${esc(cur.flagged)}. The ${link} opened in a new tab; submit it there.</div>`;
  }
  const src = sourceLine(ex);
  const keys = cur.flagging
    ? flagPickerHtml()
    : `<div class="keys"><span><kbd>space</kbd> ${nextLabel}</span><span><kbd>r</kbd> retry</span><span><kbd>?</kbd> hint</span><span><kbd>!</kbd> flag</span><span><kbd>q</kbd> end session</span></div>`;
  $("#foot").innerHTML = `
    <div class="result" id="result">
      <div class="row1">${status}${beat}${you}${par}</div>
      ${extra}
      <div class="src" id="src"${src.title ? ` title="${esc(src.title)}"` : ""}>${src.html}</div>
      ${keys}
    </div>`;
  if (cur.flagging) wireFlagPicker();
}

// --- the "!" flag ------------------------------------------------------------------
// onKey "!" -> openFlagPicker; 1-4 -> pickFlagReason; enter -> confirmFlag (saves the
// flag on the logged record, opens the issue form); Esc -> closeFlagPicker.

/** The picker row that replaces the key legend while flagging; rendered by renderResult. */
function flagPickerHtml(): string {
  const opts = FLAG_REASONS.map(([r, label], i) =>
    `<span class="flag-opt${cur?.flagReason === r ? " sel" : ""}" data-r="${r}"><kbd>${i + 1}</kbd> ${esc(label)}</span>`).join("");
  return `<div class="keys flagpick" id="flagpick"><span>flag:</span>${opts}
    <input type="text" id="flag-note" maxlength="300" placeholder="optional note" autocomplete="off">
    <span><kbd>tab</kbd> note</span><span><kbd>enter</kbd> open issue</span><span><kbd>Esc</kbd> cancel</span></div>`;
}

/** Click and enter handlers for the picker's DOM; called by renderResult after it renders the picker. */
function wireFlagPicker(): void {
  document.querySelectorAll<HTMLElement>("#flagpick .flag-opt").forEach((el) =>
    el.addEventListener("click", () => pickFlagReason(el.dataset.r as FlagReason)));
  // onKey ignores keys aimed at an <input>, so the note field handles its own enter.
  $("#flag-note").addEventListener("keydown", (e) => {
    if (e.key === "Enter") e.preventDefault(), confirmFlag();
  });
}

/** "!" on the result strip: show the reason picker; called by onKey. */
function openFlagPicker(): void {
  if (!cur) return;
  cur.flagging = true;
  cur.flagReason = null;
  renderResult();
}

/**
 * 1-4 (or a click) in the picker: mark the reason; called by onKey and the click handlers.
 * Focus stays on the strip, so a second digit changes the reason instead of typing into
 * the note (QA #48); tab, or a click on the note, moves into it.
 */
function pickFlagReason(reason: FlagReason): void {
  if (!cur?.flagging) return;
  cur.flagReason = reason;
  document.querySelectorAll<HTMLElement>("#flagpick .flag-opt").forEach((el) => el.classList.toggle("sel", el.dataset.r === reason));
}

/** Esc in the picker: back to the plain strip; called by onKey and confirmFlag. */
function closeFlagPicker(): void {
  if (!cur) return;
  cur.flagging = false;
  renderResult();
  $("#foot").focus();
}

/**
 * Enter in the picker: store the flag on the logged copy of this attempt (practice
 * records are in the model log; a first placement attempt waits in placement.records
 * until placement ends; warm-ups and placement retries are not logged), save, and open
 * the prefilled issue form. Called by onKey and the note field's enter handler.
 */
function confirmFlag(): void {
  if (!cur?.flagging || !cur.result) return;
  if (!cur.flagReason) {
    $("#flag-note").setAttribute("placeholder", "pick a reason first: 1-4 or click");
    return;
  }
  const note = ($("#flag-note") as HTMLInputElement).value.trim();
  const flag = note ? { reason: cur.flagReason, note } : { reason: cur.flagReason };
  const rec = cur.record;
  const logged = rec ? [...saved.model.log, ...(placement?.records ?? [])].find((r) => r === rec) : undefined;
  if (logged) logged.flag = flag;
  persist();
  const r = cur.result;
  cur.flagUrl = issueUrl({ ex: cur.ex, seq: replayKeys(r.tokens), keys: r.keys, ok: r.ok, reason: cur.flagReason, note, profile: S().profile, errors: saved.errors });
  // No "noopener" feature: with it window.open always returns null, so a blocked popup
  // could not be told apart. The opener link is cut by hand instead.
  const w = window.open(cur.flagUrl, "_blank");
  if (w) w.opener = null;
  cur.flagBlocked = !w;
  cur.flagged = cur.flagReason;
  closeFlagPicker();
}

// --- the exercise loop -------------------------------------------------------------

function mountExercise(ex: Exercise, skill: string, role: Role, retry: boolean): void {
  cur?.editor.destroy();
  setEscCue(false);
  if (broke === "yes" && document.getElementById("broke")) broke = "seen"; // the note was shown on the last exercise
  // kind=ex only passes through a ':' command, which the task text does not say.
  $("#task").innerHTML = taskHtml(ex.task) + (ex.kind === "ex" ? ` <span class="req">using an Ex <kbd>:</kbd> command</span>` : "");
  const want: Route = role === "placement" ? "placement" : "practice";
  if (hashRoute() !== want) history.replaceState(null, "", `#${want}`); // a load that finished after a route change
  show("practice");
  const editor = mountEditor($("#code"), ex, { relativeNumbers: S().relativeNumbers, escape: S().escape });
  const me: Current = { ex, skill, role, retry, hintUsed: false, editor, phase: "solving", result: null, showAllHints: false, record: null, flagging: false, flagReason: null, flagged: null, flagUrl: "", flagBlocked: false, nudged: false };
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
    else if (!me.nudged && snap.mode === "normal" && ex.expect.lines && !linesEqual(snap.lines, ex.expect.lines)) {
      // Back in normal mode with a buffer that can no longer reach the target: say so once.
      const why = unrecoverable(ex.start.lines, snap.lines, ex.expect.lines);
      if (why) {
        me.nudged = true;
        const el = $("#nudge");
        el.textContent = `not quite: ${why} — u to undo`;
        el.hidden = false;
      }
    }
  });
  editor.recorder.onHintKey(() => cur === me && revealMidHint());
  editor.recorder.onKey((ev) => {
    if (cur !== me || me.phase !== "solving") return;
    // Let Vim handle the second <Esc> first, then end the attempt.
    if (isGiveUp(editor.recorder.events)) {
      setEscCue(false);
      setTimeout(() => cur === me && me.phase === "solving" && finish(me, false, editor.recorder.snapshot()), 0);
    } else setEscCue(armsGiveUp(ev));
  });
}

function finish(me: Current, ok: boolean, snap: Snapshot): void {
  const rec = me.editor.recorder;
  const ms = Math.round(rec.activeMs());
  const events = ok ? rec.events : rec.events.slice(0, -2); // drop the give-up <Esc><Esc>
  const tokens = tokenize(events, S().escape, snap.mode);
  const keys = tokens.length;
  const lang = me.ex.lang || S().lang;
  const record: AttemptRecord = {
    t: nowSec(), ex: me.ex.id, skill: me.skill, lang, ok, ms, keys, par: me.ex.par.count,
    hint: me.hintUsed, retry: me.retry, undo: rec.undoCount(),
    seq: replayKeys(tokens), beatPar: ok && keys < me.ex.par.count,
  };
  // Placement: a correct answer far over par is not evidence of the skill (QA #8).
  let gateNote: string | null = null;
  if (me.role === "placement") {
    record.ok = placementPass(ok, keys, me.ex.par.count);
    if (ok && !record.ok) gateNote = `placement counts this one as not yet known: ${keys} keys, and up to ${Math.max(2 * me.ex.par.count, me.ex.par.count + 6)} count.`;
  }
  me.record = record;
  const wantLines = me.ex.expect.lines;
  const matched = !!wantLines && linesEqual(snap.lines, wantLines);
  me.result = {
    ok, tokens, keys, ms,
    band: band(keys, me.ex.par.count),
    hint: chooseHint(me.ex, tokens, ok),
    diff: !ok && wantLines && !matched ? diffLines(snap.lines, wantLines) : null,
    cursorAt: snap.cursor,
    note: !ok && me.ex.kind === "ex" && matched
      ? "a : command was required: the buffer already matched, but this drill counts only an Ex command (the par uses one)."
      : null,
    gateNote,
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
  } // warm-ups are not counted
  if (me.role !== "placement") {
    if (!me.retry) {
      session.count++; // a retry is another attempt at the same exercise
      if (ok) session.solved++;
      else session.skipped++;
      if (record.beatPar) session.beat++;
    }
    recordSession();
  }
  persist();

  setEscCue(false);
  me.editor.setLocked(true);
  if (!ok && me.ex.kind === "cursor" && me.ex.expect.cursor) me.editor.revealTarget(me.ex.expect.cursor);
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

/** Space / enter on the result strip: one advance per rendered exercise. */
function advance(): void {
  if (advancing) return;
  advancing = true;
  void nextExercise().finally(() => (advancing = false));
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
    // A saved placement keeps its queue: drop the entry that fails, or enter would load it again.
    if (role === "placement" && placement) {
      placement.queue.splice(placement.i, 1);
      persist();
    }
    showMessage("Could not load an exercise", `${esc(id)}: ${esc((err as Error).message)}. Press enter to try another.`);
  }
}

function startSession(): void {
  session = { startMs: Date.now(), sinceT: nowSec(), count: 0, solved: 0, skipped: 0, beat: 0, warmupsLeft: WARMUPS, seen: new Set(), recorded: false };
  summaryData = null;
  void nextExercise();
}

/**
 * A saved placement without the queue entries build/ no longer has (content rebuilt since
 * the save); `i` still points at the same next entry. Boot and import call it.
 */
function knownQueue(p: PlacementProgress): PlacementProgress {
  const skills = index.langs[p.lang]?.skills ?? {};
  const known = (q: { skill: string; id: string }) => skills[q.skill]?.ids.includes(q.id) ?? false;
  p.i = p.queue.slice(0, p.i).filter(known).length;
  p.queue = p.queue.filter(known);
  return p;
}

/** Enter on the placement intro: build the queue, save it (a reload resumes it) and go to #placement. */
function startPlacement(): void {
  placement = { lang: S().lang, queue: placementQueue(), i: 0, records: [] };
  if (!placement.queue.length) return finishPlacement();
  persist();
  redirect("placement");
}

/**
 * Applies the placement's first attempts, marks its language placed and drops the
 * progress. Returns the one-line outcome for the stats page. Called by finishPlacement
 * and by onLangChange (a language switch finishes the running placement early).
 */
function closePlacement(): string {
  // The x skip path has no placement object: the current language is the one skipped.
  const lang = placement?.lang ?? S().lang;
  const recs = (placement?.records ?? []).filter((r) => r.lang === lang);
  if (recs.length) {
    try {
      saved.model = M.applyPlacement(saved.model, recs, graph);
    } catch (err) {
      console.error("applyPlacement failed", err);
    }
  }
  saved.placementDone[lang] = true;
  placement = null;
  fromOnboarding = false;
  persist();
  if (!recs.length) return "placement skipped.";
  const skills = [...new Set(recs.map((r) => r.skill))];
  const mastered = skills.filter((s) => ["mastered", "review"].includes(skillState(s, lang)?.status ?? "")).length;
  return `placement complete: ${skills.length} skill${skills.length === 1 ? "" : "s"} placed, ${mastered} mastered.`;
}

/** End of placement (last exercise, q, or x on the intro): the outcome line, then stats. */
function finishPlacement(): void {
  placementMoment = closePlacement();
  cur?.editor.destroy();
  cur = null;
  afterPlacement = true;
  announced = focusSkill(); // computed once: the stats line and enter use the same skill (QA #4)
  redirect("stats");
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
    solved: session.solved,
    skipped: session.skipped,
    beat: session.beat,
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
  redirect("practice"); // #practice with no exercise and summaryData set shows the summary
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
    <p id="summary-counts">${d.solved} solved, ${d.skipped} skipped${d.beat ? ` &middot; ${d.beat} beat par` : ""}</p>
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

/** The skill the stats grid outlines: the announced one straight after placement, else the model's pick. */
function statsFocus(): string {
  if (afterPlacement && announced) return announced;
  return placed() ? focusSkill() : "";
}

/** The #stats route: select the focus row and draw the page; called by render. */
function openStats(): void {
  show("stats");
  const rows = statRows();
  const i = rows.findIndex((r) => r.id === (forced ?? statsFocus()));
  statsSel = i >= 0 ? i : 0;
  renderStats();
}

/** The stats page: a header and lead line from main, the grid / progress / sessions from stats/statsView.ts. */
function renderStats(): void {
  const lang = S().lang;
  const avail = available();
  const rows = statRows();
  const focus = statsFocus();
  const lead = afterPlacement && focus ? `We'll start with ${code(skillInfo(focus).keys)}. Press enter.` : "";
  const hidden = graphNodes(graph).filter((n) => n.tier <= 12 && !avail.has(n.id)).length;
  $("#page").innerHTML = `
    <h1>Stats <span class="dim" style="font-size:14px;font-weight:400">${esc(langName(lang))}</span></h1>
    ${afterPlacement && placementMoment ? `<p class="moment" id="placement-moment">${esc(placementMoment)}</p>` : ""}
    ${lead ? `<p class="lead">${lead}</p>` : ""}
    <div id="stats-view"></div>
    ${hidden ? `<p class="note">${hidden} more skills in the plan have no ${esc(langName(lang))} exercises yet.</p>` : ""}
    <div class="keysline"><span><kbd>,</kbd> settings</span><span><kbd>Esc</kbd> back</span></div>`;
  statsView?.destroy();
  statsView = renderStatsView($("#stats-view"), saved.model, graph, lang, {
    tab: statsTab,
    selected: statsSel,
    skills: rows.map((r) => r.id),
    focus,
    sessions: saved.sessions,
    onSelect: (i) => {
      statsSel = i;
      afterPlacement = false;
    },
    onTab: (t) => (statsTab = t),
    // "Drill this": the skill becomes the next exercise; the attempt goes through
    // M.applyAttempt, which activates a locked skill.
    onForce: (id) => {
      afterPlacement = false;
      forceSkill(id);
    },
  });
}

/** After placement: enter starts the session on the skill the stats line announced. */
function drillSelected(): void {
  afterPlacement = false;
  forceSkill(announced || focusSkill());
}

/** Make `id` the next exercise's skill and leave stats for practice; an open exercise stays (forced applies next). */
function forceSkill(id: string): void {
  if (id && available().has(id)) forced = id;
  if (!(cur && cur.phase === "solving")) {
    cur?.editor.destroy();
    cur = null;
    summaryData = null;
  }
  redirect("practice"); // render -> resumeExercise starts or continues the session
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
      <p class="note">Theme: dark (the only theme so far).</p>
      <p class="note">Exercise snippets are cut from open-source code under its licence; each result shows its source.
        <a href="${esc(contentBase())}ATTRIBUTION.md" target="_blank" rel="noopener" id="attribution-link">Sources &amp; attribution</a></p>
      <fieldset><legend>Your data (stored only in this browser)</legend>
        <button type="button" id="btn-export">export JSON</button>
        <button type="button" id="btn-import">import JSON</button>
        <input type="file" id="file-import" accept="application/json,.json" hidden>
        <button type="button" class="danger" id="btn-reset">${resetArmed ? "press again to erase everything" : "reset"}</button>
        <p class="note" id="your-data">Your progress lives only in this browser's storage. Nothing you do
          here is sent anywhere: there is no account, no server and no analytics (the page only downloads
          its fonts and exercises). Export and import move your
          progress between browsers. The <kbd>!</kbd> flag opens a GitHub issue form prefilled with the
          exercise, your keys, recent errors and the app version (${esc(VERSION)}); you can edit or discard
          it before submitting.</p>
        <p class="note" id="share-log">Share your log: export writes one JSON file with your settings, each skill's
          model state, your sessions and every attempt (exercise id, the keys you typed, time, par, hints, flags).
          It reaches us only if you attach that file to an issue at
          <a href="${ISSUES_URL}" target="_blank" rel="noopener" id="issues-link">github.com/${esc(REPO)}/issues</a>.</p>
      </fieldset>
      <div class="msg" id="settings-msg">${pendingImport ? importAskHtml(pendingImport) : esc(settingsMsg)}</div>
    </form>
    <div class="keysline"><span><kbd>tab</kbd> move between controls</span><span><kbd>Esc</kbd> back</span></div>
    <p class="note version" id="app-version">vim-trainer ${esc(VERSION)}</p>`;
  void checkAttribution($("#attribution-link") as HTMLAnchorElement);
  const form = $("#settings-form") as HTMLFormElement;
  form.addEventListener("change", (e) => {
    const t = e.target as HTMLInputElement;
    if (t.type === "file") return; // the import file has its own handler below
    if (t.name === "lang") s.lang = t.value;
    if (t.name === "profile") s.profile = t.value as EditorProfile;
    settingsMsg = "saved; applies from the next exercise.";
    pendingImport = null; // the question line is replaced below: the file is dropped
    if (t.name === "lang") onLangChange(); // may replace settingsMsg (a language with no placement yet)
    else if (t.name === "profile") refreshGraph();
    if (t.name === "rel") s.relativeNumbers = t.value === "yes";
    if (t.name === "escape") s.escape = t.value as EscapePref;
    persist();
    $("#settings-msg").textContent = settingsMsg;
    $("#settings-msg").classList.remove("fade");
    renderHeader();
  });
  $("#btn-export").addEventListener("click", () => {
    pendingImport = null; // the message below replaces the y / n question: drop the file so y cannot answer it blind
    flashSettingsMsg(`saved ${exportJson(saved)}`);
  });
  $("#btn-import").addEventListener("click", () => ($("#file-import") as HTMLInputElement).click());
  $("#file-import").addEventListener("change", async (e) => {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (!f) return;
    try {
      pendingImport = parseImport(await f.text(), LANGS.map(([k]) => k)); // checked now, saved only on y
    } catch (err) {
      settingsMsg = `import failed: ${(err as Error).message}`;
    }
    renderSettings();
    if (pendingImport) (document.activeElement as HTMLElement | null)?.blur(); // y / n reach onKey, not a button
  });
  document.getElementById("import-yes")?.addEventListener("click", () => answerImport(true));
  document.getElementById("import-no")?.addEventListener("click", () => answerImport(false));
  $("#btn-reset").addEventListener("click", () => {
    if (!resetArmed) {
      resetArmed = true;
      return renderSettings();
    }
    clear();
    history.replaceState(null, "", "#practice"); // reload into the first-visit questions, not settings
    location.reload();
  });
}

/** The y / n question an import file waits on; rendered by renderSettings while pendingImport is set. */
function importAskHtml(next: Saved): string {
  return `replace your ${saved.model.log.length} attempts with the file's ${next.model.log.length}?
    <button type="button" id="import-yes"><kbd>y</kbd> replace</button> <button type="button" id="import-no"><kbd>n</kbd> keep mine</button>`;
}

/** y / n (or the buttons) on the import question: save the checked file over everything, or drop it; called by onKey and the buttons. */
function answerImport(yes: boolean): void {
  if (!pendingImport) return;
  if (yes) {
    saved = pendingImport;
    saved.settings = { ...DEFAULTS, ...saved.settings };
    placement = saved.placement?.lang === saved.settings.lang && !placed() ? knownQueue(saved.placement) : null;
    onboarding = false; // an imported save answers the setup questions
    refreshGraph();
    persist();
    settingsMsg = `imported ${saved.model.log.length} attempts.`;
  } else settingsMsg = "import cancelled; nothing changed.";
  pendingImport = null;
  renderSettings();
  renderHeader();
}

/** A settings message that fades after a few seconds (the export confirmation, QA #42); called by the export button. */
function flashSettingsMsg(text: string): void {
  const el = $("#settings-msg");
  el.textContent = text;
  el.classList.remove("fade");
  setTimeout(() => el.textContent === text && el.classList.add("fade"), 2500);
}

/** Points the "Sources & attribution" link at GitHub when this host does not serve ATTRIBUTION.md; called by renderSettings. */
async function checkAttribution(a: HTMLAnchorElement): Promise<void> {
  try {
    const res = await fetch(a.href, { method: "HEAD", cache: "no-cache" });
    if (res.ok && !(res.headers.get("content-type") ?? "").includes("text/html")) return;
  } catch {
    /* offline or blocked: use the fallback */
  }
  a.href = SOURCES_URL;
}

/**
 * The language changed in settings. Model state is per (skill, language), so nothing is
 * lost; the open exercise is in the old language and is dropped unrecorded. A placement
 * in progress is finished with the samples it has (QA #15), so the new language gets its
 * own intro and counter. A language with no placement yet gets a settings message, and
 * Esc (goBack) opens its placement intro.
 */
function onLangChange(): void {
  const was = placement ? { lang: placement.lang, n: placement.records.length } : null;
  if (placement) closePlacement(); // before refreshGraph: its records are scored on the old graph
  refreshGraph();
  if (cur && cur.ex.lang !== S().lang) {
    cur.editor.destroy();
    cur = null;
  }
  langChanged = true;
  const ended = was ? `${langName(was.lang)} placement ended early with ${was.n} exercise${was.n === 1 ? "" : "s"}. ` : "";
  if (!placed()) settingsMsg = `${ended}${langName(S().lang)} is new here: Esc opens its placement (x skips it).`;
  else if (ended) settingsMsg = ended;
  statsSel = 0;
}

/** The #settings route: draw the page with no message; called by render. */
function openSettings(): void {
  show("settings");
  settingsMsg = "";
  resetArmed = false;
  pendingImport = null;
  renderSettings();
}

/**
 * Esc on stats / settings: the previous history entry when this one was pushed by the
 * app (so Esc and browser Back agree), else practice. After a language change it is
 * always practice, which shows the new language's intro if it has no placement (QA #16).
 */
function goBack(): void {
  afterPlacement = false;
  if (langChanged || !(history.state as { app?: boolean } | null)?.app) {
    langChanged = false;
    return redirect("practice");
  }
  history.back(); // hashchange -> render
}

// --- routing -----------------------------------------------------------------------
// The hash names the view. navigate() pushes a history entry (a key or link the player
// used), redirect() replaces the current one (an internal hop, so Back never lands on
// it), and hashchange (Back, Forward, an edited URL) re-renders. render() applies the
// guards, so every hash is safe to load directly.

/** The route location.hash names; "" and unknown hashes mean practice. */
function hashRoute(): Route {
  const h = location.hash.slice(1);
  return (ROUTES as string[]).includes(h) ? (h as Route) : "practice";
}

/** A route the player asked for (s, ",", the header links): a new history entry, then render. */
function navigate(r: Route): void {
  if (location.hash === `#${r}`) return;
  history.pushState({ app: true }, "", `#${r}`);
  render();
}

/** An internal hop: replace the current history entry, then render. */
function redirect(r: Route): void {
  history.replaceState(null, "", `#${r}`);
  render();
}

/** Show the view for the current hash, redirecting when it does not apply (no placement running, already placed...). */
function render(): void {
  // First visit: only settings (to import a save) is open before the setup questions are answered.
  if (onboarding && hashRoute() !== "settings") return show("onboarding"), renderOnboarding();
  switch (hashRoute()) {
    case "stats":
      return openStats();
    case "settings":
      return openSettings();
    case "placement-intro":
      if (placement) return redirect("placement");
      if (placed()) return redirect("practice"); // a skipped placement is not re-entered (QA #14)
      return show("placement-intro"), renderPlacementIntro();
    case "placement":
      if (!placement) return redirect(placed() ? "practice" : "placement-intro");
      return resumeExercise();
    case "practice":
      if (placement) return redirect("placement");
      if (!placed()) return redirect("placement-intro");
      return resumeExercise();
  }
}

/** The practice / placement routes: the open exercise, else the summary, else the next exercise. */
function resumeExercise(): void {
  if (cur) return show("practice");
  if (summaryData) return show("summary"), renderSummary();
  // A session in progress (no exercise open: dropped by a language change, a message, or
  // loading) continues; a placement resumes at placement.i; only a fresh session starts over.
  if (placement || session.count > 0 || session.recorded) return void nextExercise();
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
    { label: "Yes, relative line numbers", sub: "default; the count-and-jump drills (7j) use them", off: false, apply: () => (s.relativeNumbers = true) },
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
    onboarding = false;
    fromOnboarding = true;
    redirect("placement-intro");
  } else {
    renderOnboarding();
    renderHeader(); // the language shows in the header once it is chosen
  }
}

function renderPlacementIntro(): void {
  const n = placementQueue().length;
  // Another language already placed: this is a language switch, not the first visit.
  const second = Object.values(saved.placementDone).some(Boolean);
  // "first visit 4 of 4" only right after the three setup questions (QA #31).
  const steps = fromOnboarding ? "first visit &middot; 4 of 4" : second ? "new language" : "";
  const carry = masteredElsewhere(S().lang).size > 0;
  $("#page").innerHTML = `
    ${steps ? `<p class="steps">${steps}</p>` : ""}
    <h1>Let's see where you are${second ? ` in ${esc(langName(S().lang))}` : ""}</h1>
    <p class="lead">${n} short exercises in ${esc(langName(S().lang))}, about five minutes. There is no pass mark; the results seed your chart.</p>
    ${carry ? `<p class="note">This is a new language: skills you mastered in another language are skipped (they come back as reviews).</p>` : ""}
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
        // A double press or key repeat must not skip an exercise: the strip is inert
        // from the first advance until the next exercise has rendered.
        if (advancing || e.repeat) return handled();
        if (cur.flagging) {
          // The picker owns the strip: digits pick, tab goes to the note, enter sends, Esc cancels, the rest is ignored.
          const opt = FLAG_REASONS[Number(k) - 1];
          if (/^[1-4]$/.test(k) && opt) pickFlagReason(opt[0]);
          else if (k === "Tab") $("#flag-note").focus();
          else if (k === "Enter") confirmFlag();
          else if (k === "Escape") closeFlagPicker();
          return handled();
        }
        if (k === "!") handled(), openFlagPicker();
        else if (k === " "|| k === "Enter") handled(), advance();
        else if (k === "r") handled(), mountExercise(cur.ex, cur.skill, cur.role, true);
        else if (k === "q") handled(), endSession();
        else if (k === "?") handled(), (cur.showAllHints = !cur.showAllHints), renderResult();
        else if (k === "s") handled(), navigate("stats");
        else if (k === ",") handled(), navigate("settings");
      } else {
        // Focus left the editor mid-exercise (a click): header keys, enter returns.
        if (k === "s") handled(), navigate("stats");
        else if (k === ",") handled(), navigate("settings");
        else if (k === "Enter" || k === "Escape" || k === "i") handled(), cur.editor.view.focus();
      }
      return;
    case "stats": {
      // Straight after placement, enter starts the session (the lead line says so).
      if (afterPlacement && k === "Enter") return handled(), drillSelected();
      if (statsView?.handleKey(k, e.shiftKey)) return handled();
      if (k === "Escape") handled(), goBack();
      else if (k === ",") handled(), navigate("settings");
      return;
    }
    case "settings":
      if (pendingImport && (k === "y" || k === "n")) handled(), answerImport(k === "y");
      else if (k === "Escape") handled(), goBack();
      return;
    case "summary":
      if (k === "Enter") handled(), startSession();
      else if (k === "s") handled(), navigate("stats");
      else if (k === ",") handled(), navigate("settings");
      return;
    case "message":
      if (k === "Enter") handled(), void nextExercise();
      else if (k === ",") handled(), navigate("settings");
      return;
  }
}

// --- boot ------------------------------------------------------------------------

async function boot(): Promise<void> {
  index = await loadIndex();
  const prior = load();
  saved = prior ?? { version: 1, settings: { ...DEFAULTS }, model: M.newState(baseGraph()), placementDone: {}, sessions: [], errors: [] };
  saved.settings = { ...DEFAULTS, ...saved.settings };
  // An import from before validation may hold an unknown language; fall back to the default.
  if (!LANGS.some(([k]) => k === saved.settings.lang)) saved.settings.lang = DEFAULTS.lang;
  for (const e of pendingErrors.splice(0)) pushError(saved, e), (broke = "yes");
  // A placement saved mid-way resumes at the same index with its records (QA #18).
  if (saved.placement?.lang === saved.settings.lang && !placed()) placement = knownQueue(saved.placement);
  else delete saved.placement;
  onboarding = !prior;
  refreshGraph();
  document.addEventListener("keydown", onKey);
  $("#nav-stats").addEventListener("click", (e) => (e.preventDefault(), navigate("stats")));
  $("#nav-settings").addEventListener("click", (e) => (e.preventDefault(), navigate("settings")));
  $("#hdr-ctx").addEventListener("click", (e) => (e.preventDefault(), navigate("settings")));
  // Clicking the locked editor must not strand focus: send it back to the strip.
  $("#code").addEventListener("mousedown", (e) => {
    if (cur?.phase === "result") {
      e.preventDefault();
      $("#foot").focus();
    }
  });
  window.addEventListener("hashchange", () => render());
  history.replaceState(history.state, "", `#${hashRoute()}`); // "" or an unknown hash: name the route
  render(); // a first visit shows the setup questions whatever the hash says
}

declare global {
  interface Window {
    vimTrainer: {
      saved: () => Saved; model: () => ModelState; current: () => Current | null; placementSkills: () => string[];
      placement: () => PlacementProgress | null;
    };
  }
}
// Test hook for the e2e suites; placementSkills lists the open placement's queued skills.
window.vimTrainer = {
  saved: () => saved, model: () => saved.model, current: () => cur, placementSkills: () => placement?.queue.map((q) => q.skill) ?? [],
  placement: () => placement,
};

boot().catch((err) => {
  console.error(err);
  document.body.insertAdjacentHTML("afterbegin", `<p style="padding:16px;color:#d98a7a">vim-trainer failed to start: ${esc(String(err))}</p>`);
});
