// Grading (docs/plan/05-grading.md). Pure functions only: the recorder produces
// KeyEvents, this module turns them into pass/fail, key counts, display strings,
// efficiency bands and the one hint shown on the result strip.

import type { EscapePref, Exercise, Pos } from "./types.ts";

export type Mode = "normal" | "insert" | "replace" | "visual" | "visual-line" | "visual-block";

/** One keydown as Vim saw it. `mode` is the mode *before* the key was handled. */
export interface KeyEvent {
  key: string; // Vim angle-bracket notation from Vim.vimKeyFromEvent
  mode: Mode;
  cmdline: boolean; // typed into the : or / command line
  active: number; // active-clock ms since the exercise rendered
  /** A count, operator, register or partial command was pending when the key arrived. */
  pending?: boolean;
}

/** A counted keystroke. A `jk` escape collapses two events into one token. */
export interface Token {
  key: string;
  mode: Mode;
  cmdline: boolean;
}

const ESCAPES = new Set(["<Esc>", "<C-[>", "<C-c>"]);
const isInsertish = (m: Mode) => m === "insert" || m === "replace";

/**
 * Turn raw key events into counted tokens. Each Vim notation token is one key
 * (05: Shift is not separate; <C-v> is one). With the `jk` escape preference, a
 * `j` `k` pair typed in insert mode that leaves insert mode counts as one key.
 */
export function tokenize(events: KeyEvent[], escape: EscapePref, finalMode: Mode): Token[] {
  const out: Token[] = [];
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    if (escape === "jk" && e.key === "j" && isInsertish(e.mode) && !e.cmdline) {
      const k = events[i + 1];
      const after = events[i + 2]?.mode ?? finalMode;
      if (k && k.key === "k" && isInsertish(k.mode) && !isInsertish(after)) {
        out.push({ key: "jk", mode: e.mode, cmdline: false });
        i++;
        continue;
      }
    }
    out.push({ key: e.key, mode: e.mode, cmdline: e.cmdline });
  }
  return out;
}

/** Display form: insert-mode spaces render as spaces, everything else as logged. */
export function displayKeys(tokens: Token[]): string {
  return tokens.map((t) => (t.key === "<Space>" && isInsertish(t.mode) ? " " : t.key)).join("");
}

/** Replayable form for the logged `seq` (main.ts finish and the flag issue): a `jk` escape becomes <Esc>, so Neovim replays it. */
export function replayKeys(tokens: Token[]): string {
  return displayKeys(tokens.map((t) => (t.key === "jk" ? { ...t, key: "<Esc>" } : t)));
}

/** Split a par/alternate key string ("ci\"x<Esc>") into notation tokens. */
export function splitKeys(keys: string): string[] {
  return keys.match(/<(?:[A-Za-z]+-)*(?:[A-Za-z0-9]+|[^\s<>])>|./gs) ?? [];
}

export function normLines(lines: string[]): string[] {
  return lines.map((l) => l.replace(/\s+$/, ""));
}

export function linesEqual(a: string[], b: string[]): boolean {
  const x = normLines(a), y = normLines(b);
  return x.length === y.length && x.every((l, i) => l === y[i]);
}

/** True when the key log contains an executed ":" command (a ":" then <CR> in the command line). */
export function usedExCommand(tokens: Token[]): boolean {
  let open = false;
  for (const t of tokens) {
    if (!t.cmdline && t.key === ":" && !isInsertish(t.mode)) open = true;
    else if (open && t.cmdline && t.key === "<CR>") return true;
    else if (!t.cmdline && open) open = false;
  }
  return false;
}

export interface Snapshot {
  lines: string[];
  cursor: Pos; // [line 1-based, col 0-based]
  mode: Mode;
}

/** Pass conditions by kind (05). Called after each completed command. */
export function checkPass(ex: Exercise, snap: Snapshot, tokens: Token[]): boolean {
  if (snap.mode !== "normal") return false;
  switch (ex.kind) {
    case "edit":
      return !!ex.expect.lines && linesEqual(snap.lines, ex.expect.lines);
    case "cursor": {
      const c = ex.expect.cursor;
      if (!c) return false;
      // TODO(mvp): expect.cursor is a byte column (nvim); equal to the char column for ASCII only.
      return c[0] === snap.cursor[0] && c[1] === snap.cursor[1] && linesEqual(snap.lines, ex.start.lines);
    }
    case "ex":
      return !!ex.expect.lines && linesEqual(snap.lines, ex.expect.lines) && usedExCommand(tokens);
  }
  return false;
}

export type Band = "beat" | "par" | "close" | "pass" | "over";

export function band(keys: number, par: number): Band {
  if (keys < par) return "beat"; // fewer keys than the oracle's par: worth a look (ingest)
  const eff = keys / Math.max(1, par);
  if (eff <= 1.0) return "par";
  if (eff <= 1.25) return "close";
  if (eff <= 2.0) return "pass";
  return "over";
}

/**
 * Placement gate (QA #8): a placement sample counts as passed only when it reached
 * the target within max(2 * par, par + 6) keys. Without the key cap, eleven presses
 * of l on a par-2 cursor exercise marked the skill (and its prerequisites) mastered.
 * The + 6 keeps very short pars (1 to 6 keys) from failing on one detour. For the
 * placement flow in main.ts.
 */
export function placementPass(ok: boolean, keys: number, par: number): boolean {
  return ok && keys <= Math.max(2 * par, par + 6);
}

// Lines as a count map (trailing whitespace ignored), for unrecoverable().
function lineCounts(lines: string[]): Map<string, number> {
  const m = new Map<string, number>();
  for (const l of normLines(lines)) m.set(l, (m.get(l) ?? 0) + 1);
  return m;
}

// Lines of `a` not matched by a line of `b` (multiset difference), for unrecoverable().
function minus(a: Map<string, number>, b: Map<string, number>): Map<string, number> {
  const out = new Map<string, number>();
  for (const [l, n] of a) if (n > (b.get(l) ?? 0)) out.set(l, n - (b.get(l) ?? 0));
  return out;
}

/**
 * Cheap check that the buffer can no longer reach the target without retyping
 * deleted text, so the player should undo. Returns the reason to show, or null.
 * False alarms are worse than misses, so it stays quiet unless something was
 * deleted that a single put could not bring back:
 *  - nothing deleted (only typing added): null, the rest can still be typed;
 *  - every deleted line is one the target still needs: null, `p`/`P` may restore
 *    it (the dd half of ddp, a line move);
 * and then fires on (a) fewer lines than both start and expect while a line the
 * target needs from start is gone (a line only expect has is new text still to type:
 * dG then oX is fine), (b) a non-blank line common to start and expect gone from the
 * buffer, (c) whole lines deleted, the text under half of expect's length, and over
 * half of expect's text was on the deleted lines (shared prefix + suffix with a missing
 * line: a deleted line the target only edits, not new text).
 * Mid-insert typing never deletes lines, so (a) and (c) cannot fire on it. Meant for
 * normal mode between commands; main.ts (the exercise view) is the intended caller.
 */
export function unrecoverable(start: string[], now: string[], expect: string[]): string | null {
  const nowC = lineCounts(now);
  const startC = lineCounts(start);
  const deleted = minus(startC, nowC);
  const missing = minus(lineCounts(expect), nowC);
  if (deleted.size === 0) return null;
  if ([...deleted].every(([l, n]) => (missing.get(l) ?? 0) >= n)) return null;

  const lostFromStart = [...missing.keys()].some((l) => startC.has(l));
  if (now.length < expect.length && now.length < start.length && lostFromStart) {
    const n = expect.length - now.length;
    return `the target keeps ${n} more line${n === 1 ? "" : "s"}`;
  }
  const kept = normLines(start).filter((l) => l.trim() !== "" && normLines(expect).includes(l));
  if (kept.some((l) => !nowC.has(l))) return "a line that should stay was removed";
  const len = (ls: string[]) => normLines(ls).join("\n").length;
  const fromDeleted = [...missing.keys()].reduce((sum, m) => sum + Math.max(0, ...[...deleted.keys()].map((d) => shared(d, m))), 0);
  if (now.length < start.length && len(now) < 0.5 * len(expect) && fromDeleted > 0.5 * len(expect)) return "too much was deleted";
  return null;
}

// Characters two lines share as a common prefix plus a common suffix, for unrecoverable().
function shared(a: string, b: string): number {
  let p = 0;
  while (p < a.length && p < b.length && a[p] === b[p]) p++;
  let s = 0;
  while (s < a.length - p && s < b.length - p && a[a.length - 1 - s] === b[b.length - 1 - s]) s++;
  return p + s;
}

export const BAND_LABEL: Record<Band, string> = { beat: "beat par", par: "at par", close: "close", pass: "passed", over: "over par" };

export const GIVE_UP_MS = 800;

/**
 * An escape that can start the give-up gesture: pressed in normal mode, outside the
 * command line, with nothing pending. An <Esc> that cancels a pending operator,
 * count or register (`d<Esc>`, `3<Esc>`, `"a<Esc>`) is Vim's cancel, not a give-up.
 */
export function armsGiveUp(e: KeyEvent | undefined): boolean {
  return !!e && ESCAPES.has(e.key) && e.mode === "normal" && !e.cmdline && !e.pending;
}

/**
 * Give-up gesture: <Esc><Esc> where both escapes were pressed in normal mode
 * (so leaving insert mode with one <Esc> and pressing another does not count),
 * outside the command line, within 800 ms, and the first one did not cancel a
 * pending command.
 */
export function isGiveUp(events: KeyEvent[]): boolean {
  const n = events.length;
  if (n < 2) return false;
  const a = events[n - 2], b = events[n - 1];
  return armsGiveUp(a) && armsGiveUp(b) && b.active - a.active <= GIVE_UP_MS;
}

// --- clock --------------------------------------------------------------------

/**
 * Attempt clock (05 "Time"): milliseconds since start minus every paused stretch.
 * Pauses are keyed by reason ("hidden" for visibilitychange, "away" while stats or
 * settings cover the exercise) and overlap freely; the clock runs only when no
 * reason holds. `now` is injectable for tests.
 */
export class PausableClock {
  private readonly startedAt: number;
  private pausedTotal = 0;
  private pausedAt: number | null = null;
  private readonly reasons = new Set<string>();
  private readonly now: () => number;

  constructor(now: () => number = () => performance.now()) {
    this.now = now;
    this.startedAt = now();
  }

  setPaused(reason: string, on: boolean): void {
    const was = this.reasons.size > 0;
    if (on) this.reasons.add(reason);
    else this.reasons.delete(reason);
    const is = this.reasons.size > 0;
    const t = this.now();
    if (!was && is) this.pausedAt = t;
    else if (was && !is && this.pausedAt !== null) {
      this.pausedTotal += t - this.pausedAt;
      this.pausedAt = null;
    }
  }

  paused(): boolean {
    return this.reasons.size > 0;
  }

  /** Active milliseconds since construction. */
  active(at = this.now()): number {
    const pausedNow = this.pausedAt === null ? 0 : at - this.pausedAt;
    return at - this.startedAt - this.pausedTotal - pausedNow;
  }
}

// --- insert-mode <Tab> ------------------------------------------------------------

/** The oracle's tab options (content/src/vimtrainer_content/oracle.lua M.OPTIONS). */
export const TAB_OPTIONS = { expandtab: true, shiftwidth: 4, tabstop: 4, softtabstop: 0 } as const;

/**
 * Spaces one insert-mode <Tab> adds after `before` (the line text left of the
 * cursor) under the oracle's options: expandtab, ts=sw=4, sts=0 and Neovim's
 * default smarttab. sts=0 means the tab stop is 'tabstop' and smarttab uses
 * 'shiftwidth' in leading whitespace; both are 4, so the result is "fill to the
 * next multiple of 4 virtual columns", with existing tab characters counted at
 * their display width. Checked against nvim 0.12: "ab" -> 2, "abcd" -> 4,
 * "a<Tab>b" -> 3.
 */
export function tabSpaces(before: string): number {
  const ts = TAB_OPTIONS.tabstop;
  const stop = /^[ \t]*$/.test(before) ? TAB_OPTIONS.shiftwidth : ts;
  let col = 0;
  for (const ch of before) col = ch === "\t" ? col + ts - (col % ts) : col + 1;
  return stop - (col % stop);
}

// --- hints ------------------------------------------------------------------

interface Detector {
  re: RegExp;
  text: string;
}

// Generic detectors (05), run over normal-mode keys only so typed text cannot trigger them.
const DETECTORS: Detector[] = [
  { re: /(?:j{4,}|k{4,})/, text: "relative numbers show the distance, so {count}j or {count}k reaches the line in two or three keys." },
  { re: /(?:l{5,}|h{5,})/, text: "f{char}, t{char} or w reach a spot on the line in fewer keys than repeated l or h." },
  { re: /x{3,}/, text: "d with a motion (dw, dt, or d$) deletes a stretch in one command instead of repeated x." },
  { re: /(?:dd.*){3,}/, text: ":g/pattern/d deletes every matching line in one command." },
  // A 0 preceded by a digit is part of a count (10w, 20l), not the 0 motion.
  { re: /(?<![0-9])0[wle]/, text: "^ jumps straight to the first non-blank character." },
  { re: /(.{3,}?)\1{2,}/, text: "when you repeat the same edit, . (dot) or a macro replays it for one key." },
];

const INSERT_ARROWS = new Set(["<Left>", "<Right>", "<Up>", "<Down>"]);

export function exerciseHints(ex: Exercise): { trigger?: RegExp; text: string }[] {
  return (ex.hints ?? []).map((h) => {
    if (typeof h === "string") return { text: h };
    let trigger: RegExp | undefined;
    try {
      // The pipeline checks every trigger compiles as a JS RegExp with the `u` flag.
      trigger = h.trigger ? new RegExp(h.trigger, "u") : undefined;
    } catch {
      trigger = undefined;
    }
    return { trigger, text: h.text };
  });
}

/**
 * The one hint for the result strip, in 05's order: exercise hint whose trigger
 * matches; then generic detectors; then (only if over par) the exercise's first
 * untriggered hint; otherwise null (the strip shows the par and nothing else).
 */
export function chooseHint(ex: Exercise, tokens: Token[], ok: boolean): string | null {
  const typed = displayKeys(tokens);
  const hints = exerciseHints(ex);
  for (const h of hints) if (h.trigger && h.trigger.test(typed)) return h.text;
  const firstPlain = hints.find((h) => !h.trigger)?.text ?? null;
  if (!ok) return firstPlain;
  if (tokens.length <= ex.par.count) return null;

  const normal = tokens.filter((t) => !isInsertish(t.mode) && !t.cmdline).map((t) => t.key).join("");
  const par = splitKeys(ex.par.keys).join("");
  if (tokens.some((t) => isInsertish(t.mode) && INSERT_ARROWS.has(t.key)))
    return "arrow keys in insert mode cost one key each; <Esc> and a motion is usually shorter.";
  for (const d of DETECTORS) {
    if (d.re.test(normal) && !d.re.test(par)) {
      if (d.text.includes("{count}")) {
        const run = normal.match(/j{4,}|k{4,}/)?.[0] ?? "";
        return d.text.replace("{count}", String(run.length)).replace("{count}", String(run.length));
      }
      return d.text;
    }
  }
  return firstPlain;
}

// --- diff (shown on a fail) -------------------------------------------------

export interface DiffLine {
  op: " " | "-" | "+";
  text: string;
}

/** Line diff from `a` (current buffer) to `b` (expected), via LCS. Buffers are tiny. */
export function diffLines(a: string[], b: string[]): DiffLine[] {
  const n = a.length, m = b.length;
  const L: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) L[i][j] = a[i] === b[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out: DiffLine[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { out.push({ op: " ", text: a[i] }); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) out.push({ op: "-", text: a[i++] });
    else out.push({ op: "+", text: b[j++] });
  }
  while (i < n) out.push({ op: "-", text: a[i++] });
  while (j < m) out.push({ op: "+", text: b[j++] });
  return out;
}

// --- target range -------------------------------------------------------------

/**
 * Ranges to highlight in the start buffer, as [from, to) document offsets.
 * Uses ex.target when present (a list of inclusive {start, end} spans from the
 * pipeline, or a single exclusive {from, to}); for cursor exercises the expected
 * cursor char; otherwise the span where start and expect differ (common
 * prefix/suffix trim), widened to at least one character.
 */
export function targetRanges(ex: Exercise): { from: number; to: number }[] {
  const text = ex.start.lines.join("\n");
  const off = (p: Pos) => {
    let o = 0;
    for (let i = 0; i < p[0] - 1 && i < ex.start.lines.length; i++) o += ex.start.lines[i].length + 1;
    const line = ex.start.lines[Math.min(p[0], ex.start.lines.length) - 1] ?? "";
    return Math.min(text.length, o + Math.min(p[1], line.length));
  };
  const t = ex.target;
  if (Array.isArray(t) && t.length) {
    const out: { from: number; to: number }[] = [];
    for (const span of t) {
      if (!span?.start || !span?.end) continue;
      const from = off(span.start);
      out.push({ from, to: Math.min(text.length, Math.max(from + 1, off(span.end) + 1)) });
    }
    if (out.length) return out;
  } else if (t && !Array.isArray(t) && t.from && t.to) {
    return [{ from: off(t.from), to: Math.max(off(t.from) + 1, off(t.to)) }];
  }
  if (ex.kind === "cursor" && ex.expect.cursor) {
    const from = off(ex.expect.cursor);
    return [{ from, to: Math.min(text.length, from + 1) }];
  }
  if (!ex.expect.lines) return [];
  const want = ex.expect.lines.join("\n");
  let p = 0;
  while (p < text.length && p < want.length && text[p] === want[p]) p++;
  let s = 0;
  while (s < text.length - p && s < want.length - p && text[text.length - 1 - s] === want[want.length - 1 - s]) s++;
  let from = p, to = text.length - s;
  if (to <= from) to = Math.min(text.length, from + 1);
  // Whole lines deleted: highlight the full line(s) rather than a newline.
  if (text.slice(from, to).startsWith("\n")) from += 1;
  return [{ from, to: Math.max(to, from + 1) }];
}

/** First highlight range, or null (kept for callers that want one span). */
export function targetRange(ex: Exercise): { from: number; to: number } | null {
  return targetRanges(ex)[0] ?? null;
}
