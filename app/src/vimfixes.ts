// Where codemirror-vim differs from Neovim on commands the shipped pars use, found by
// e2e/emulator.mjs (every build/ par replayed in the browser) and by difftest
// (content/difftest/known.jsonl, class a). Installed once, through the public Vim API
// (defineMotion / defineOperator / defineAction / _mapCommand / defineEx) plus wrappers
// around codemirror-vim's own motions, operators and actions (grabTable), so the
// vendored package is untouched. Every expected behaviour was checked against
// nvim --clean; the regression cases are in e2e/editor.mjs.
//
// 1. Exclusive motions (:help exclusive, :help exclusive-linewise): an operator whose
//    exclusive motion ends in column 0 of a later line stops at the end of the line
//    before, and becomes linewise when it started at or before the first non-blank
//    (d} c} y} gU} d/pat d* dB). codemirror-vim instead strips a trailing line break and
//    indent from every forward motion, which is right only for `w`. vimRange().
// 2. A linewise delete that reaches the last line (`dG`, `d2j` at the end) must remove
//    the line break before the range; codemirror-vim only special-cases `dd`.
// 3. `:move` / `:m`, `:copy` / `:co` / `:t` do not exist in codemirror-vim. Its ex
//    parser also reads `:m8` as a command named "m8", so a space is inserted between
//    those command names and a numeric address when the command line is submitted.
// 4. Searches, :s and :g are hard-coded to ignorecase + smartcase in codemirror-vim
//    (and * / # to ignorecase); the oracle runs `nvim --clean`, which is case-sensitive.
//    caseSensitiveSearch() strips the `i` flag from every stored query.
// 5. `i(` `i[` `i{` `i<` (and `ib` `iB`) after an operator follow Vim's current_block():
//    when the opening bracket is the last character of its line the object starts on the
//    next line, and when the closing bracket has only blanks before it the object stops
//    at the end of the previous line. Both together make it linewise. A count selects
//    the count-th enclosing block; outside any block Neovim takes the next one forward.
//    Visual mode (`vi{`) keeps codemirror-vim's behaviour.
// 6. A motion or text object that fails aborts its operator and stays in Normal mode
//    (dfz, ci' with no quotes, g~; , 3a[ with two levels, 9iw past the end, 2D / 2dd /
//    2>> / j / <CR> / _ on the last line, k / - on the first, gE at the start of the
//    buffer, dx). codemirror-vim returns the cursor instead, so the operator still runs.
// 7. > and < skip empty lines and rewrite the indent with spaces (:help shift-left-right).
// 8. y, g~, gu and gU leave the cursor at the start of the operated text (:help y), and
//    Visual-line u / U / ~ / c / s act like their linewise Normal-mode forms.
// 9. + - _ <CR> are linewise motions (:help linewise); <CR> also works after an operator.
// 10. Smaller ones, each named after the Vim function it follows: J / gJ (do_join), r{c}
//    with a count (fails past the end; `.` takes a new count), } { (findpar), quote
//    objects (current_quote), ip / ap (current_par), it / at (fail: no tags in code),
//    N%, p P gp gP ]p [p (do_put), `.` never repeats a yank or a failed operator, j / k
//    keep the display column over tabs, gj / gk are j / k with 'nowrap', text objects
//    switch Visual-line mode to charwise, and a Normal-mode cursor never rests past the
//    last character (V$<Esc>).

import { Vim, getCM } from "@replit/codemirror-vim";
import { EditorView } from "@codemirror/view";
import { countedOpenAbove, installMacroIndentFixes, shiftSkipsHash } from "./vimfixes-macros-indent.ts";

interface P {
  line: number;
  ch: number;
}
interface Range {
  anchor: P;
  head: P;
}
// codemirror-vim's per-editor state (the parts read here).
interface VimState {
  visualMode?: boolean;
  visualLine?: boolean;
  visualBlock?: boolean;
  insertMode?: boolean;
  sel: Range;
  lastMotion?: unknown;
  lastHPos?: number;
  lastEditInputState?: InputState & { repeatOverride?: number };
  lastEditActionCommand?: unknown;
}
// The CodeMirror 5 style adapter codemirror-vim passes to operators and ex commands.
interface CM {
  state: { vim: VimState };
  firstLine(): number;
  lastLine(): number;
  getLine(n: number): string;
  getRange(a: P, b: P): string;
  getSelection(): string;
  replaceRange(text: string, from: P, to?: P): void;
  replaceSelections(texts: string[]): void;
  setSelections(ranges: Range[], primary?: number): void;
  getCursor(which?: string): P;
  setCursor(p: P): void;
}
interface MotionArgs {
  selectedCharacter?: string;
  linewise?: boolean;
  inclusive?: boolean;
  forward?: boolean;
  wordEnd?: boolean;
  bigWord?: boolean;
  repeat?: number;
  repeatOffset?: number;
  repeatIsExplicit?: boolean;
  toFirstChar?: boolean;
  textObjectInner?: boolean;
}
interface InputState {
  operator?: string | null;
  operatorArgs?: OperatorArgs | null;
}
interface ScanCM extends CM {
  scanForBracket(from: P, dir: 1 | -1, style?: unknown, config?: { bracketRegex: RegExp }): { pos: P } | null | false | undefined;
}
interface OperatorArgs {
  linewise?: boolean;
  registerName?: string;
  repeat?: number;
  indentRight?: boolean;
  shouldMoveCursor?: boolean;
  fullLine?: boolean;
  // Set by evalInput for a Visual-mode operator (and kept for its `.`): the selection it ran on.
  lastSel?: { anchor: P; head: P; visualLine?: boolean; visualBlock?: boolean };
}
interface ActionArgs {
  repeat?: number;
  after?: boolean;
  matchIndent?: boolean;
  cursorAfterText?: boolean; // gp / gP (vimfixes' own mapping)
  registerName?: string;
  repeatIsExplicit?: boolean;
  selectedCharacter?: string;
  keepSpaces?: boolean;
  head?: P;
}
interface ExParams {
  line?: number;
  lineEnd?: number;
  selectionLine?: number;
  selectionLineEnd?: number;
  argString?: string;
}
type ExFn = (this: unknown, cm: CM, params: ExParams) => void;
type MotionResult = P | [P, P] | null | undefined;
type MotionFn = (this: unknown, cm: CM, head: P, args: MotionArgs, vim: VimState, input: InputState) => MotionResult;
type OperatorFn = (this: unknown, cm: CM, args: OperatorArgs, ranges: Range[], oldAnchor: P, newHead: P) => P | undefined | void;
type ActionFn = (this: unknown, cm: CM, args: ActionArgs, vim: VimState) => void;

// The oracle's 'shiftwidth' and 'tabstop' (content/.../oracle.py ORACLE_OPTIONS) and the editor's indentUnit / tabSize.
const SHIFTWIDTH = 4;
const TABSTOP = 4;

const firstNonBlank = (text: string): number => {
  const i = text.search(/\S/);
  return i < 0 ? text.length : i;
};
const isBefore = (a: P, b: P): boolean => a.line < b.line || (a.line === b.line && a.ch < b.ch);
const minPos = (a: P, b: P): P => (isBefore(b, a) ? b : a);
const samePos = (a: P, b: P): boolean => a.line === b.line && a.ch === b.ch;

// Clamp p to a Normal-mode cursor position (on a character, or column 0 of an empty line).
function clip(cm: CM, p: P): P {
  const line = Math.min(Math.max(cm.firstLine(), p.line), cm.lastLine());
  const len = cm.getLine(line).length;
  return { line, ch: Math.min(Math.max(0, p.ch), Math.max(0, len - 1)) };
}

// Every line of the buffer, for the pure helpers below.
function allLines(cm: CM): string[] {
  const out: string[] = [];
  for (let i = cm.firstLine(); i <= cm.lastLine(); i++) out.push(cm.getLine(i));
  return out;
}

// ---------------------------------------------------------------------------------------
// Pure helpers (unit-tested in vimfixes.test.ts). Lines are 0-based.

/** Display width of one character at display column `col` (tabs to the next TABSTOP, CJK and emoji 2). */
export function charWidth(ch: string, col: number): number {
  if (ch === "\t") return TABSTOP - (col % TABSTOP);
  const cp = ch.codePointAt(0) ?? 0;
  const wide = cp >= 0x1100 && (cp <= 0x115f || (cp >= 0x2e80 && cp <= 0xa4cf) || (cp >= 0xac00 && cp <= 0xd7a3) ||
    (cp >= 0xf900 && cp <= 0xfaff) || (cp >= 0xfe30 && cp <= 0xfe4f) || (cp >= 0xff00 && cp <= 0xff60) ||
    (cp >= 0xffe0 && cp <= 0xffe6) || cp >= 0x1f000);
  return wide ? 2 : 1;
}

/** Display column where the character at UTF-16 index `ch` of `text` starts. */
export function displayCol(text: string, ch: number): number {
  let col = 0;
  for (let i = 0; i < ch && i < text.length; ) {
    const c = String.fromCodePoint(text.codePointAt(i) ?? 0);
    col += charWidth(c, col);
    i += c.length;
  }
  return col;
}

/** Vim's Normal-mode cursor column (curswant) on the character at `ch`: a tab's last column, any other character's first. */
export function cursorCol(text: string, ch: number): number {
  const start = displayCol(text, ch);
  return text[ch] === "\t" ? start + charWidth("\t", start) - 1 : start;
}

/** UTF-16 index of the character that covers display column `want` (Vim's coladvance(); last character if the line is shorter). */
export function charAtDisplayCol(text: string, want: number): number {
  let col = 0;
  let last = 0;
  for (let i = 0; i < text.length; ) {
    const c = String.fromCodePoint(text.codePointAt(i) ?? 0);
    const w = charWidth(c, col);
    if (col + w > want) return i;
    col += w;
    last = i;
    i += c.length;
  }
  return last;
}

/** Line `text` shifted by `steps` shiftwidths (negative: left), as Vim's shift_line() with expandtab; empty lines stay empty. */
export function shiftLine(text: string, steps: number): string {
  if (text === "") return text;
  const ws = /^[ \t]*/.exec(text)?.[0] ?? "";
  const width = displayCol(ws, ws.length);
  return " ".repeat(Math.max(0, width + steps * SHIFTWIDTH)) + text.slice(ws.length);
}

/** Vim's do_join() on `lines`: the joined text and the cursor column (the inserted space, or where the last line's text starts). */
export function joinLinesText(lines: string[], insertSpace: boolean): { text: string; col: number } {
  let text = lines[0] ?? "";
  let col = 0;
  for (const raw of lines.slice(1)) {
    const next = insertSpace ? raw.replace(/^[ \t]+/, "") : raw;
    const end = text.slice(-1);
    const space = insertSpace && next !== "" && !next.startsWith(")") && text !== "" && end !== " " && end !== "\t";
    col = text.length;
    text += (space ? " " : "") + next;
  }
  return { text, col };
}

/**
 * Vim's findpar() for `}` (forward) and `{`: the line and column it moves to, and whether
 * the motion became inclusive (it ends on the last character of the buffer); null when a
 * count runs past the buffer edge.
 */
export function paragraphMotion(lines: string[], line: number, count: number, forward: boolean): { line: number; ch: number; inclusive: boolean } | null {
  const dir = forward ? 1 : -1;
  let curr = line;
  for (let n = Math.max(1, count); n > 0; n--) {
    let didSkip = false;
    for (let first = true; ; first = false) {
      if (lines[curr] !== "") didSkip = true;
      if (!first && didSkip && lines[curr] === "") break;
      const next = curr + dir;
      if (next < 0 || next >= lines.length) {
        if (n > 1) return null;
        break;
      }
      curr = next;
    }
  }
  const len = lines[curr].length;
  if (forward && curr === lines.length - 1 && len > 0) return { line: curr, ch: len - 1, inclusive: true };
  return { line: curr, ch: 0, inclusive: false };
}

/** Vim's current_par() for `ip` / `ap` with a count: the first and last line, or null when it runs past the end. */
export function paragraphObject(lines: string[], line: number, count: number, include: boolean): [number, number] | null {
  const white = (n: number): boolean => /^[ \t]*$/.test(lines[n]);
  const last = lines.length - 1;
  let start = line;
  const whiteInFront = white(start);
  while (start > 0) {
    if (whiteInFront ? !white(start - 1) : white(start - 1)) break;
    start--;
  }
  let end = start;
  while (end <= last && white(end)) end++;
  end--;
  let i = Math.max(1, count);
  if (!include && whiteInFront) i--;
  while (i-- > 0) {
    if (end === last) return null;
    const doWhite = !include && white(end + 1);
    if (include || !doWhite) {
      end++;
      while (end < last && !white(end + 1)) end++;
    }
    if (i === 0 && whiteInFront && include) break;
    if (include || doWhite) while (end < last && white(end + 1)) end++;
  }
  if (!whiteInFront && !white(end) && include) while (start > 0 && white(start - 1)) start--;
  return [start, end];
}

/** Vim's current_quote() on one line: [start, end) of `i'` / `a'` (with `count`), or null when there is no quoted string. */
export function quoteObject(line: string, col: number, quote: string, include: boolean, count = 1): [number, number] | null {
  // find_next_quote / find_prev_quote with 'quoteescape' = backslash.
  const next = (from: number, escape: boolean): number => {
    for (let i = from; i < line.length; i++) {
      if (escape && line[i] === "\\") i++;
      else if (line[i] === quote) return i;
    }
    return -1;
  };
  const prev = (from: number): number => {
    let i = from;
    while (i > 0) {
      i--;
      let n = 0;
      while (i - n > 0 && line[i - n - 1] === "\\") n++;
      if (n % 2) i -= n;
      else if (line[i] === quote) break;
    }
    return i;
  };
  let start: number;
  let end: number;
  if (line[col] === quote) {
    // On a quote: pair the quotes from the start of the line to know which one it is.
    start = 0;
    for (;;) {
      start = next(start, false);
      if (start < 0 || start > col) return null;
      end = next(start + 1, true);
      if (end < 0) return null;
      if (start <= col && col <= end) break;
      start = end + 1;
    }
  } else {
    start = prev(col);
    if (line[start] !== quote) {
      start = next(start, false);
      if (start < 0) return null;
    }
    end = next(start + 1, true);
    if (end < 0) return null;
  }
  if (include) {
    if (/[ \t]/.test(line[end + 1] ?? "")) while (/[ \t]/.test(line[end + 1] ?? "")) end++;
    else while (start > 0 && /[ \t]/.test(line[start - 1])) start--;
  }
  const inner = !include && count < 2;
  return [inner ? start + 1 : start, inner ? end : end + 1];
}

// ---------------------------------------------------------------------------------------
// Access to codemirror-vim's private command tables.

// Reach a private command table (motions, operators, actions or ex commands): its define* function runs
// `table[name] = fn`, which calls this one-shot Object.prototype setter with `this` = the table.
function grabTable<T>(define: (name: string, fn: never) => void): Record<string, T> {
  const key = "__vimfixesGrab";
  let table: Record<string, T> | undefined;
  Object.defineProperty(Object.prototype, key, {
    configurable: true,
    set(this: Record<string, T>) {
      table ??= this; // the first assignment: defineEx also writes its prefix into a second table
    },
  });
  try {
    define(key, null as never);
  } finally {
    delete (Object.prototype as Record<string, unknown>)[key];
  }
  if (!table) throw new Error("vimfixes: codemirror-vim's command tables are not reachable");
  return table;
}

// The outermost motion of the command being run, recorded so the operator after it knows
// the motion's name, args and raw endpoints (evalInput only passes the operator a range).
interface MotionRun {
  name: string;
  args: MotionArgs;
  head: P;
  result: P | [P, P];
}
let lastRun: MotionRun | null = null;
let motionDepth = 0;

// Wrap every motion so the outermost call records a MotionRun; installVimFixes calls it last.
function recordMotions(motions: Record<string, MotionFn>): void {
  for (const name of Object.keys(motions)) {
    const orig = motions[name];
    motions[name] = function (cm, head, args, vim, input) {
      const start = { line: head.line, ch: head.ch };
      motionDepth++;
      let result: MotionResult;
      try {
        result = orig.call(this, cm, head, args, vim, input);
      } finally {
        motionDepth--;
      }
      if (motionDepth === 0) lastRun = result ? { name, args, head: start, result } : null;
      if (motionDepth === 0 && !result && input?.operator) restoreLastEdit(vim, input); // a failed `dfz` is not repeated by `.`
      return result;
    };
  }
}

/** The recorded motion of the operator now running (its result is the operator's newHead), or null. */
function runFor(newHead: P): MotionRun | null {
  if (!lastRun) return null;
  const r = lastRun.result;
  return (Array.isArray(r) ? r[1] : r) === newHead ? lastRun : null;
}

/** Where y / g~ / gu / gU leave the cursor: the start of the operated text (Vim's oap->start). */
function operatorStart(cm: CM, run: MotionRun, lineopToFirstNonBlank: boolean): P {
  const r = run.result;
  if (Array.isArray(r)) return minPos(r[0], r[1]);
  if (run.name === "expandToLine") {
    // nv_lineop moves to the last line's first non-blank for gUU / g~~ (yy keeps the column); the start is the earlier end.
    const last = Math.min(r.line, cm.lastLine());
    return lineopToFirstNonBlank ? minPos(run.head, { line: last, ch: firstNonBlank(cm.getLine(last)) }) : run.head;
  }
  return minPos(run.head, { line: Math.min(r.line, cm.lastLine()), ch: r.ch });
}

// What codemirror-vim's recordLastEdit() replaced when it stored the command now running.
interface EditSnapshot {
  next: unknown;
  input: unknown;
  action: unknown;
  changes: unknown;
  visualBlock: unknown;
}
const snapshots = new WeakMap<VimState, EditSnapshot>();
const watched = new WeakSet<VimState>();
let restoring = false;
type InsertChanges = { changes: unknown; visualBlock: unknown };
const insertChanges = (): InsertChanges =>
  (Vim.getVimGlobalState_() as unknown as { macroModeState: { lastInsertModeChanges: InsertChanges } }).macroModeState.lastInsertModeChanges;

// Fix 10: snapshot the `.` state each time recordLastEdit() replaces it (it sets lastEditInputState first); called per editor before its first key.
function watchLastEdit(vim: VimState): void {
  if (watched.has(vim)) return;
  watched.add(vim);
  let value = vim.lastEditInputState;
  Object.defineProperty(vim, "lastEditInputState", {
    configurable: true,
    enumerable: true,
    get: () => value,
    set(next) {
      if (!restoring) {
        const ic = insertChanges();
        snapshots.set(vim, { next, input: value, action: vim.lastEditActionCommand, changes: ic.changes, visualBlock: ic.visualBlock });
      }
      value = next;
    },
  });
}

// Fix 10: put back the `.` state from before `next` was recorded (a yank, or an operator whose motion failed: Vim repeats neither).
function restoreLastEdit(vim: VimState, next: unknown): void {
  const snap = snapshots.get(vim);
  if (!snap || snap.next !== next) return;
  snapshots.delete(vim);
  restoring = true;
  try {
    vim.lastEditInputState = snap.input as VimState["lastEditInputState"];
  } finally {
    restoring = false;
  }
  vim.lastEditActionCommand = snap.action;
  const ic = insertChanges();
  ic.changes = snap.changes;
  ic.visualBlock = snap.visualBlock;
}

// ---------------------------------------------------------------------------------------
// Fix 1 (:help exclusive-linewise) and the motion-failure fixes of fix 6.

/**
 * Fix 1: the range Vim gives an operator after a charwise motion (:help exclusive,
 * :help exclusive-linewise), or null to keep codemirror-vim's. `w` / `W` keep
 * codemirror-vim's line-break clipping (it stands in for Vim's stop at the end of line).
 */
function vimRange(cm: CM, run: MotionRun): { from: P; to: P; linewise: boolean } | null {
  const r = run.result;
  if (Array.isArray(r) || run.args.linewise) return null;
  if (run.name === "moveByWords" && run.args.forward && !run.args.wordEnd) {
    if (cm.getLine(run.head.line) !== "") return null;
    // From an empty line Vim's w (fwd_word with eol) stops at the next line's column 0, so exclusive-linewise
    // makes it the empty line alone: cw keeps the line, dw deletes it.
    if ((run.args.repeat ?? 1) === 1 && run.head.line < cm.lastLine()) {
      return { from: { line: run.head.line, ch: 0 }, to: { line: run.head.line + 1, ch: 0 }, linewise: true };
    }
  }
  const at = (p: P): P => {
    const line = Math.min(Math.max(p.line, cm.firstLine()), cm.lastLine());
    return { line, ch: Math.min(Math.max(p.ch, 0), cm.getLine(line).length) };
  };
  const from = at(minPos(run.head, r));
  let to = at(isBefore(run.head, r) ? r : run.head);
  if (run.args.inclusive) return { from, to: { line: to.line, ch: Math.min(to.ch + 1, cm.getLine(to.line).length) }, linewise: false };
  if (to.ch === 0 && to.line > from.line) {
    if (from.ch <= firstNonBlank(cm.getLine(from.line))) return { from: { line: from.line, ch: 0 }, to, linewise: true };
    to = { line: to.line - 1, ch: cm.getLine(to.line - 1).length };
  }
  return { from, to, linewise: false };
}

// Wrap every operator: replace codemirror-vim's range by vimRange() before it runs (fix 1).
function exclusiveRanges(operators: Record<string, OperatorFn>): void {
  for (const name of Object.keys(operators)) {
    const orig = operators[name];
    operators[name] = function (cm, args, ranges, oldAnchor, newHead) {
      const run = args.lastSel ? null : runFor(newHead);
      const fixed = run && !args.linewise ? vimRange(cm, run) : null;
      const call = (r: Range[]) => {
        // A search motion runs from the prompt's callback, outside a Vim key operation, so a
        // selection set for the operator flips codemirror-vim into Visual mode: undo that.
        if (!args.lastSel && cm.state.vim.visualMode) Vim.exitVisualMode(cm as never, false);
        return orig.call(this, cm, args, r, oldAnchor, newHead);
      };
      if (!fixed || (samePos(fixed.from, ranges[0].anchor) && samePos(fixed.to, ranges[0].head) && !fixed.linewise)) {
        return call(ranges);
      }
      const saved = args.linewise;
      const mine = [{ anchor: fixed.from, head: fixed.to }];
      args.linewise = fixed.linewise;
      cm.setSelections(mine, 0);
      try {
        return call(mine);
      } finally {
        args.linewise = saved; // `.` replays these args: the next motion decides again
      }
    };
  }
}

// Fix 6 and 9: j k + - _ <CR> fail at the first / last line instead of moving to the line's
// start or end (cursor_down / cursor_up); + - _ <CR> are linewise; j / k keep the display column.
function lineMotion(motions: Record<string, MotionFn>): MotionFn {
  const orig = motions.moveByLines;
  const want = new WeakMap<VimState, number>();
  return function (cm, head, args, vim, input) {
    const n = (args.repeat ?? 1) + (args.repeatOffset ?? 0);
    if (n > 0 && (args.forward ? head.line >= cm.lastLine() : head.line <= cm.firstLine())) return null;
    if (args.toFirstChar) {
      args.linewise = true;
      const to = orig.call(this, cm, head, args, vim, input);
      if (!to || Array.isArray(to) || to.line <= cm.lastLine()) return to;
      return { line: cm.lastLine(), ch: firstNonBlank(cm.getLine(cm.lastLine())) }; // 5_ / 5+ past the end: the last line's first non-blank
    }
    // The table entries, read now: recordMotions() wraps them after this is installed.
    const vertical = [motions.moveByLines, motions.moveByDisplayLines, motions.moveByScroll].includes(vim.lastMotion as MotionFn);
    const continuing = vertical && want.has(vim);
    const atEol = vim.lastMotion === motions.moveToEol || (vertical && vim.lastHPos === Infinity);
    const result = orig.call(this, cm, head, args, vim, input);
    if (atEol || !result || Array.isArray(result)) return result;
    const col = continuing ? (want.get(vim) as number) : cursorCol(cm.getLine(head.line), head.ch);
    want.set(vim, col);
    const line = Math.min(Math.max(result.line, cm.firstLine()), cm.lastLine());
    return { line, ch: charAtDisplayCol(cm.getLine(line), col) };
  };
}

// Fix 10: with 'nowrap' (the oracle's and the editor's) gj / gk are j / k, linewise after an operator (nv_g_cmd).
function displayLineMotion(motions: Record<string, MotionFn>): MotionFn {
  const orig = motions.moveByDisplayLines;
  return function (cm, head, args, vim, input) {
    if (!input) return orig.call(this, cm, head, args, vim, input); // <C-d> / <C-u> call it without an input state
    args.linewise = true;
    return motions.moveByLines.call(this, cm, head, args, vim, input);
  };
}

// Fix 6: `dd` / `>>` / `cc` / `yy` with a count fail on the last line (nv_lineop: cursor_down(count - 1)).
function lineOperatorMotion(orig: MotionFn): MotionFn {
  return function (cm, head, args, vim, input) {
    if ((args.repeat ?? 1) > 1 && head.line >= cm.lastLine()) return null;
    return orig.call(this, cm, head, args, vim, input);
  };
}

// Fix 6: f / F / ; / , / ]) [( ... fail when codemirror-vim reports "not found" by returning the cursor.
function failWhenStill(orig: MotionFn): MotionFn {
  return function (cm, head, args, vim, input) {
    const start = { line: head.line, ch: head.ch };
    const result = orig.call(this, cm, head, args, vim, input);
    return result && !Array.isArray(result) && samePos(result, start) ? null : result;
  };
}

// Fix 6: backward word motions after an operator fail at the start of the buffer, as Neovim does:
// b / B only when they cannot move at all, ge / gE when any step starts there (the cursor stays where it got).
function backwardWord(orig: MotionFn): MotionFn {
  return function (cm, head, args, vim, input) {
    if (args.forward || !input?.operator) return orig.call(this, cm, head, args, vim, input);
    const atStart = (p: P): boolean => p.line === cm.firstLine() && p.ch === 0;
    if (atStart(head)) return null;
    if (!args.wordEnd) return orig.call(this, cm, head, args, vim, input);
    let at: P = head;
    for (let i = 0; i < (args.repeat ?? 1); i++) {
      if (atStart(at)) {
        cm.setCursor(at);
        return null;
      }
      const step = orig.call(this, cm, at, { ...args, repeat: 1 }, vim, input);
      if (!step || Array.isArray(step)) return orig.call(this, cm, head, args, vim, input);
      at = step;
    }
    return orig.call(this, cm, head, args, vim, input);
  };
}

// Fix 6: `2$` / `2D` / `2C` fail on the last line (nv_dollar: cursor_down(count - 1)).
function eolMotion(orig: MotionFn): MotionFn {
  return function (cm, head, args, vim, input) {
    if ((args.repeat ?? 1) > 1 && head.line >= cm.lastLine()) return null;
    return orig.call(this, cm, head, args, vim, input);
  };
}

// Fix 10: } and { as Vim's findpar(): stop on the buffer's last character (inclusive), fail on a count past the edge.
function paragraphMove(): MotionFn {
  return function (cm, head, args) {
    const to = paragraphMotion(allLines(cm), head.line - cm.firstLine(), args.repeat ?? 1, !!args.forward);
    if (!to) return null;
    args.inclusive = to.inclusive; // the args object is replayed by `.`: set both ways
    return { line: to.line + cm.firstLine(), ch: to.ch };
  };
}

/** The next `open` after `from` that is not balanced by a `close` before it (findmatchlimit() with FM_FORWARD). */
function nextOpen(cm: CM, from: P, open: string, close: string): P | null {
  let depth = 0;
  for (let line = from.line; line <= cm.lastLine(); line++) {
    const text = cm.getLine(line);
    for (let ch = line === from.line ? from.ch + 1 : 0; ch < text.length; ch++) {
      if (text[ch] === close) depth++;
      else if (text[ch] === open) {
        if (depth === 0) return { line, ch };
        depth--;
      }
    }
  }
  return null;
}

/** Fix 5 (and 6): the count-th enclosing bracket pair around the cursor, as [open, close] positions. */
function enclosingPair(cm: ScanCM, head: P, open: string, close: string, count: number): [P, P] | null {
  const re = new RegExp(`[\\${open}\\${close}]`);
  let at: P = { line: head.line, ch: head.ch + (cm.getLine(head.line).charAt(head.ch) === open ? 1 : 0) };
  // Neovim's current_block(): with no enclosing block, the count-th next block forward instead.
  const inside = !!cm.scanForBracket(at, -1, undefined, { bracketRegex: re });
  for (let n = Math.max(1, count); n > 0; n--) {
    const o = inside ? cm.scanForBracket(at, -1, undefined, { bracketRegex: re }) : { pos: nextOpen(cm, at, open, close) };
    if (!o || !o.pos) return null;
    at = o.pos;
  }
  const c = cm.scanForBracket({ line: at.line, ch: at.ch + 1 }, 1, undefined, { bracketRegex: re });
  return c ? [at, c.pos] : null;
}

const BLOCKS: Record<string, [string, string]> = {
  "(": ["(", ")"], ")": ["(", ")"], b: ["(", ")"],
  "[": ["[", "]"], "]": ["[", "]"],
  "{": ["{", "}"], "}": ["{", "}"], B: ["{", "}"],
  "<": ["<", ">"], ">": ["<", ">"],
};

// Fix 6 and 10: text objects that fail like Vim (quotes, it/at, counts on w/W/p/blocks) and Vim's quote and paragraph rules.
function textObject(orig: MotionFn): MotionFn {
  return function (cm, head, args, vim, input) {
    const ch = args.selectedCharacter ?? "";
    const count = args.repeat ?? 1;
    const include = !args.textObjectInner;
    const call = (a: MotionArgs) => orig.call(this, cm, head, a, vim, input);
    if (ch === "t") return null; // no tags in code buffers: Vim's current_tagblock() fails
    if (vim.visualMode && vim.visualLine && ch !== "p") {
      // Word, quote and block objects switch Visual-line mode to charwise (current_word() etc.).
      vim.visualLine = false;
      (cm as unknown as { signal(type: string, e: unknown): void }).signal("vim-mode-change", { mode: "visual", subMode: "" });
    }
    const visualEmpty = !vim.visualMode || (!vim.visualLine && !vim.visualBlock && samePos(vim.sel.anchor, vim.sel.head));
    if ((ch === "'" || ch === '"' || ch === "`") && visualEmpty) {
      const q = quoteObject(cm.getLine(head.line), head.ch, ch, include, count);
      if (!q) return null;
      const from = { line: head.line, ch: q[0] };
      return vim.visualMode ? [from, { line: head.line, ch: Math.max(q[1] - 1, 0) }] : [from, { line: head.line, ch: q[1] }];
    }
    if (ch === "p" && !vim.visualMode) {
      const p = paragraphObject(allLines(cm), head.line - cm.firstLine(), count, include);
      if (!p) return null;
      args.linewise = true;
      return [{ line: p[0] + cm.firstLine(), ch: 0 }, { line: p[1] + cm.firstLine(), ch: 0 }];
    }
    if (BLOCKS[ch] && !vim.visualMode) {
      const pair = enclosingPair(cm as ScanCM, head, BLOCKS[ch][0], BLOCKS[ch][1], count);
      if (!pair) return null;
      return include ? [pair[0], { line: pair[1].line, ch: pair[1].ch + 1 }] : [{ line: pair[0].line, ch: pair[0].ch + 1 }, pair[1]];
    }
    if ((ch === "w" || ch === "W") && vim.visualMode && visualEmpty) {
      // A fresh Visual selection: the object as after an operator, the cursor on its last character
      // (codemirror-vim would read the word from the CodeMirror selection, a whole line in V mode).
      vim.visualMode = false;
      cm.setCursor(head);
      let r: MotionResult;
      try {
        r = call(args);
      } finally {
        vim.visualMode = true;
      }
      return Array.isArray(r) ? [r[0], { line: r[1].line, ch: Math.max(r[1].ch - 1, 0) }] : r;
    }
    if ((ch === "w" || ch === "W") && count > 1 && !vim.visualMode) {
      // current_word() fails when the count runs out of buffer; the cursor is left at the end.
      const all = call(args);
      const fewer = call({ ...args, repeat: count - 1 });
      if (Array.isArray(all) && Array.isArray(fewer) && samePos(all[1], fewer[1])) {
        cm.setCursor(clip(cm, { line: all[1].line, ch: all[1].ch - 1 }));
        return null;
      }
      return all;
    }
    return call(args);
  };
}

/** Fix 5: the inner block object as Vim's current_block() cuts it (operator-pending only). */
// `input` is the command's own input state: codemirror-vim has already replaced
// vim.inputState with a fresh one when the motion runs, and `.` replays this object.
function innerBlock(cm: ScanCM, head: P, motionArgs: MotionArgs, _vim: unknown, input: InputState): [P, P] | null {
  const pair = BLOCKS[motionArgs.selectedCharacter ?? ""];
  if (!pair) return null;
  // `.` replays these same args objects (evalInput also stores the final linewise in
  // operatorArgs): reset what a previous multi-line cut set.
  motionArgs.linewise = false;
  if (input?.operatorArgs) input.operatorArgs.linewise = false;
  const found = enclosingPair(cm, head, pair[0], pair[1], motionArgs.repeat ?? 1);
  if (!found) return null;
  const [o, c] = found;
  const openAtEol = o.ch + 1 >= cm.getLine(o.line).length;
  const start: P = openAtEol && c.line > o.line ? { line: o.line + 1, ch: 0 } : { line: o.line, ch: o.ch + 1 };
  const closeAtSol = c.line > o.line && /^\s*$/.test(cm.getLine(c.line).slice(0, c.ch));
  if (!closeAtSol) return [start, c];
  if (c.line - 1 < start.line) return [start, start]; // `{` and `}` on adjacent lines: nothing inside
  if (openAtEol) {
    motionArgs.linewise = true;
    return [start, { line: c.line - 1, ch: 0 }];
  }
  return [start, { line: c.line - 1, ch: cm.getLine(c.line - 1).length }];
}

// Fix 10: N% goes to N percent of the buffer (first non-blank; over 100 fails). Neovim treats it as an
// exclusive charwise motion there (d30% from column 0 then follows exclusive-linewise); plain % keeps codemirror-vim's.
function percentMotion(orig: MotionFn): MotionFn {
  return function (cm, head, args, vim, input) {
    args.inclusive = !args.repeatIsExplicit; // the args object is replayed by `.`: set both ways
    if (!args.repeatIsExplicit) return orig.call(this, cm, head, args, vim, input);
    const n = args.repeat ?? 0;
    if (n > 100) return null;
    const line = cm.firstLine() + Math.floor((n * (cm.lastLine() - cm.firstLine() + 1) + 99) / 100) - 1;
    return { line, ch: firstNonBlank(cm.getLine(line)) };
  };
}

// Fix 6: in operator-pending mode these keys are not motions; Vim cancels the operator.
const failMotion: MotionFn = () => null;
const NOT_MOTIONS = ["x", "X", "D", "C", "Y", "~", "s", "S", "<Del>"];

// ---------------------------------------------------------------------------------------
// Operators (fixes 2, 7, 8).

// Fix 2: codemirror-vim's delete with the line break before a linewise range that reaches the last line removed.
function deleteOperator(cm: CM, args: OperatorArgs, ranges: Range[], _oldAnchor: P, newHead: P): P {
  const vim = cm.state.vim;
  let text: string;
  let finalHead: P;
  let linewise = !!args.linewise;
  if (!vim.visualBlock) {
    let anchor = { ...ranges[0].anchor };
    let head = { ...ranges[0].head };
    if (!linewise && !args.lastSel && runFor(newHead)?.name !== "moveToMatchedSymbol" && // Neovim leaves d% charwise
        head.line > anchor.line && anchor.ch <= firstNonBlank(cm.getLine(anchor.line)) &&
        /^\s*$/.test(cm.getLine(head.line).slice(head.ch))) {
      // Fix 1 (op_delete): a charwise delete over several lines from the indent to the end of a line is linewise (5D, 4dW).
      linewise = true;
      anchor = { line: anchor.line, ch: 0 };
      head = { line: head.line + 1, ch: 0 };
    }
    let register: string | null = null;
    if (linewise && head.line > cm.lastLine()) {
      // Fix 2 (also covers the original dd-on-the-last-line case). The register still gets
      // the lines themselves, not the line break before them (ddp on the last line).
      if (anchor.line > cm.firstLine()) {
        register = cm.getRange({ line: anchor.line, ch: 0 }, head);
        anchor = { line: anchor.line - 1, ch: cm.getLine(anchor.line - 1).length };
      } else anchor = { line: anchor.line, ch: 0 };
    }
    text = cm.getRange(anchor, head);
    cm.replaceRange("", anchor, head);
    if (register !== null) text = register;
    finalHead = anchor;
    if (linewise) {
      // The line that moved up into the deleted range's place (or the new last line).
      const line = Math.min(anchor.line, cm.lastLine());
      finalHead = { line, ch: firstNonBlank(cm.getLine(line)) };
    }
  } else {
    text = cm.getSelection();
    cm.replaceSelections(ranges.map(() => ""));
    const a = ranges[0].anchor, h = ranges[0].head;
    finalHead = a.line < h.line || (a.line === h.line && a.ch <= h.ch) ? a : h;
  }
  Vim.getRegisterController().pushText(args.registerName, "delete", text, linewise, !!vim.visualBlock);
  return clip(cm, finalHead);
}

// Fix 7: > and < as Vim's op_shift(): every non-empty line of the range, indent rewritten with spaces, cursor on the first line's first non-blank.
function shiftOperator(orig: OperatorFn): OperatorFn {
  return function (cm, args, ranges, oldAnchor, newHead) {
    if (args.lastSel?.visualBlock) return orig.call(this, cm, args, ranges, oldAnchor, newHead);
    const { anchor, head } = ranges[0];
    const first = Math.min(anchor.line, head.line);
    let last = Math.max(anchor.line, head.line) - (args.linewise ? 1 : 0);
    last = Math.max(first, Math.min(last, cm.lastLine()));
    const steps = (args.lastSel ? args.repeat || 1 : 1) * (args.indentRight ? 1 : -1);
    const skipHash = shiftSkipsHash(cm);
    for (let line = first; line <= last; line++) {
      const text = cm.getLine(line);
      if (skipHash && text.startsWith("#")) continue; // Vim's op_shift: a preprocessor line stays in column 0
      const next = shiftLine(text, steps);
      if (next !== text) cm.replaceRange(next, { line, ch: 0 }, { line, ch: text.length });
    }
    return { line: first, ch: firstNonBlank(cm.getLine(first)) };
  };
}

/** Fix 8: where a Visual-line y / u / U / ~ leaves the cursor: column 0 of the anchor's line, or the cursor if it is above that. */
function visualLineStart(sel: { anchor: P; head: P }): P {
  const top = { line: sel.anchor.line, ch: 0 };
  return isBefore(top, sel.head) ? top : sel.head;
}

// Fix 8: y leaves the cursor at the start of the yanked text (yb, yiw, yk, ygg).
function yankOperator(orig: OperatorFn): OperatorFn {
  return function (cm, args, ranges, oldAnchor, newHead) {
    const run = args.lastSel ? null : runFor(newHead);
    const result = orig.call(this, cm, args, ranges, oldAnchor, newHead);
    const vim = cm.state.vim;
    if (vim.lastEditInputState?.operator === "yank") restoreLastEdit(vim, vim.lastEditInputState); // `.` never repeats a yank
    if (args.lastSel?.visualLine) return clip(cm, visualLineStart(args.lastSel));
    return run ? clip(cm, operatorStart(cm, run, false)) : result;
  };
}

// Fix 8: g~ gu gU (and ~, Visual u U ~) leave the cursor where Vim does: start of the text, column 0 for Visual-line, never past the end.
function caseOperator(orig: OperatorFn): OperatorFn {
  return function (cm, args, ranges, oldAnchor, newHead) {
    const sel = args.lastSel;
    const run = sel || args.shouldMoveCursor ? null : runFor(newHead);
    const result = orig.call(this, cm, args, ranges, oldAnchor, newHead);
    if (sel?.visualLine) return clip(cm, visualLineStart(sel));
    if (run) return clip(cm, operatorStart(cm, run, true));
    return result ? clip(cm, result) : result;
  };
}

// Fix 8: Visual-line c / s change the lines like `cc` (one line left, its indent kept) instead of deleting them.
function changeOperator(orig: OperatorFn): OperatorFn {
  return function (cm, args, ranges, oldAnchor, newHead) {
    if (args.lastSel?.visualLine && !args.lastSel.visualBlock && !args.fullLine) {
      const first = Math.min(ranges[0].anchor.line, ranges[0].head.line);
      const last = Math.max(first, Math.max(ranges[0].anchor.line, ranges[0].head.line) - 1);
      ranges = [{ anchor: { line: first, ch: firstNonBlank(cm.getLine(first)) }, head: { line: last + 1, ch: 0 } }];
      args.fullLine = true; // codemirror-vim's Visual R path: delete up to the end of the last line
      try {
        return orig.call(this, cm, args, ranges, oldAnchor, newHead);
      } finally {
        args.fullLine = false;
      }
    }
    return orig.call(this, cm, args, ranges, oldAnchor, newHead);
  };
}

// ---------------------------------------------------------------------------------------
// Actions (fix 10).

// The count given to the `.` being replayed (repeatLastEdit), read by replaceAction.
let dotCount: number | undefined;

// Fix 10: remember `.`'s count while it replays, so r{c} can use it (codemirror-vim passes it only to operators).
function dotRepeat(orig: ActionFn): ActionFn {
  return function (cm, args, vim) {
    const saved = dotCount;
    dotCount = args.repeatIsExplicit ? args.repeat : vim.lastEditInputState?.repeatOverride;
    try {
      orig.call(this, cm, args, vim);
    } finally {
      dotCount = saved;
    }
  };
}

// Fix 10: r{c} fails when the count is longer than the rest of the line; `.` with a count replaces that many.
// Visual r<CR> puts a literal CR in place of each selected character (only Normal r<CR> breaks the line).
function replaceAction(orig: ActionFn): ActionFn {
  return function (cm, args, vim) {
    if (vim.visualMode && args.selectedCharacter === "\n") args = { ...args, selectedCharacter: "\r" };
    if (!vim.visualMode) {
      const repeat = dotCount ?? args.repeat ?? 1;
      const cur = cm.getCursor();
      if (cur.ch + repeat > cm.getLine(cur.line).length) return;
      args = { ...args, repeat };
    }
    orig.call(this, cm, args, vim);
  };
}

// Fix 10: p / P / gp / gP / ]p / [p as Vim's do_put(): P of one line of text ends on its last character, gp / gP
// just after the text (the line below for lines), ]p / [p adjust the indent only for a linewise register.
function pasteAction(orig: ActionFn): ActionFn {
  return function (cm, args, vim) {
    if (dotCount !== undefined) args = { ...args, repeat: dotCount }; // 3. after p puts three times
    const reg = Vim.getRegisterController().getRegister(args.registerName) as unknown as { linewise?: boolean; blockwise?: boolean };
    const text = String(reg).repeat(Math.max(1, args.repeat ?? 1));
    if (vim.visualMode || args.registerName === "+" || reg.blockwise || !text) return orig.call(this, cm, args, vim);
    if (args.matchIndent && !reg.linewise) args = { ...args, matchIndent: false };
    const cur = cm.getCursor();
    const start = { line: cur.line, ch: Math.min(cur.ch + (args.after ? 1 : 0), cm.getLine(cur.line).length) };
    orig.call(this, cm, args, vim);
    const parts = text.split("\n");
    if (reg.linewise) {
      if (args.cursorAfterText) cm.setCursor(clip(cm, { line: cur.line + parts.length - 1 + (args.after ? 1 : 0), ch: 0 }));
    } else if (args.cursorAfterText) {
      const end = parts.length === 1 ? { line: start.line, ch: start.ch + text.length } : { line: start.line + parts.length - 1, ch: parts[parts.length - 1].length };
      cm.setCursor(clip(cm, end));
    } else if (parts.length === 1 && !args.after) {
      cm.setCursor({ line: start.line, ch: start.ch + text.length - 1 });
    }
  };
}

// Fix 10: J / gJ as Vim's do_join(); J fails on the last line, a one-line Visual J joins two lines.
function joinAction(exitVisual: (cm: CM, moveHead?: boolean) => void): ActionFn {
  return function (cm, args, vim) {
    let first: number;
    let count: number;
    if (vim.visualMode) {
      first = Math.min(vim.sel.anchor.line, vim.sel.head.line);
      count = Math.max(2, Math.abs(vim.sel.anchor.line - vim.sel.head.line) + 1);
      exitVisual(cm, false);
      if (first + count - 1 > cm.lastLine()) return;
    } else {
      first = cm.getCursor().line;
      count = Math.max(2, args.repeat ?? 1);
      if (first + count - 1 > cm.lastLine()) {
        if (count <= 2) return;
        count = cm.lastLine() - first + 1;
      }
    }
    const last = first + count - 1;
    const lines: string[] = [];
    for (let i = first; i <= last; i++) lines.push(cm.getLine(i));
    const { text, col } = joinLinesText(lines, !args.keepSpaces);
    if (last > first) cm.replaceRange(text, { line: first, ch: 0 }, { line: last, ch: cm.getLine(last).length });
    cm.setCursor(clip(cm, { line: first, ch: col }));
  };
}

// ---------------------------------------------------------------------------------------
// Ex commands (fix 3).

/** An ex address as the 1-based line after which to put text (0 = above line 1). */
function parseAddress(cm: CM, raw: string | undefined): number {
  const s = (raw ?? "").trim();
  const m = /^(\d+|\.|\$)?((?:\s*[+-]\s*\d*)*)$/.exec(s);
  if (!s || !m) throw new Error("E16: Invalid range"); // nvim: `:m`, `:m x` give E16
  const cur = cm.getCursor().line + 1;
  const last = cm.lastLine() + 1;
  let n = m[1] === undefined || m[1] === "." ? cur : m[1] === "$" ? last : Number(m[1]);
  for (const [, sign, digits] of m[2].matchAll(/([+-])\s*(\d*)/g)) n += (sign === "-" ? -1 : 1) * (digits ? Number(digits) : 1);
  if (n < 0 || n > last) throw new Error("E16: Invalid range");
  return n;
}

function lineRange(cm: CM, params: ExParams): [number, number] {
  const a = params.line ?? cm.getCursor().line;
  const b = params.lineEnd ?? a;
  const lo = Math.max(cm.firstLine(), Math.min(a, b));
  const hi = Math.min(cm.lastLine(), Math.max(a, b));
  return [lo, hi];
}

function exMove(cm: CM, params: ExParams): void {
  const [lo, hi] = lineRange(cm, params);
  const dest = parseAddress(cm, params.argString);
  if (dest >= lo + 1 && dest < hi + 1) throw new Error("E134: Cannot move a range of lines into itself");
  const lines = allLines(cm);
  const block = lines.slice(lo, hi + 1);
  if (dest === hi + 1 || dest === lo) {
    cm.setCursor({ line: hi, ch: firstNonBlank(lines[hi]) });
    return;
  }
  const rest = [...lines.slice(0, lo), ...lines.slice(hi + 1)];
  const at = dest > hi ? dest - block.length : dest;
  rest.splice(at, 0, ...block);
  // Replace only the lines that changed (a move keeps the line count).
  const from = Math.min(lo, at);
  const to = Math.max(hi, at + block.length - 1);
  cm.replaceRange(rest.slice(from, to + 1).join("\n"), { line: from, ch: 0 }, { line: to, ch: lines[to].length });
  const end = at + block.length - 1;
  cm.setCursor({ line: end, ch: firstNonBlank(rest[end]) });
}

function exCopy(cm: CM, params: ExParams): void {
  const [lo, hi] = lineRange(cm, params);
  const dest = parseAddress(cm, params.argString);
  const block = allLines(cm).slice(lo, hi + 1);
  if (dest === 0) cm.replaceRange(block.join("\n") + "\n", { line: 0, ch: 0 });
  else cm.replaceRange("\n" + block.join("\n"), { line: dest - 1, ch: cm.getLine(dest - 1).length });
  const end = dest + block.length - 1;
  cm.setCursor({ line: end, ch: firstNonBlank(cm.getLine(end)) });
}

/** `:m8` -> `:m 8`, `:t.` -> `:t .`, `:j3` -> `:j 3` (codemirror-vim reads \w+ as the command name). */
export function spaceExAddress(input: string): string {
  return input
    .replace(/^(\s*:*(?:[^a-zA-Z']|'[a-zA-Z<>])*?)(move|mov|mo|m|copy|cop|co|t)(?=[\d.$+-])/, "$1$2 ")
    .replace(/^(\s*:*(?:[^a-zA-Z']|'[a-zA-Z<>])*?)(join|joi|jo|j)(?=\d)/, "$1$2 ");
}

// Fix 3: swap a backwards range (`:.,1d` threw in replaceRange) as nvim does, but `:4,2<CR>` goes to line 2; wraps every ex command, called by installVimFixes.
function orderExRanges(exCommands: Record<string, ExFn>): void {
  for (const [name, fn] of Object.entries(exCommands)) {
    exCommands[name] = function (this: unknown, cm: CM, params: ExParams) {
      const { line, lineEnd } = params;
      if (line !== undefined && lineEnd !== undefined && !isNaN(lineEnd)) {
        if (name === "move") params.line = lineEnd;
        else if (lineEnd < line) [params.line, params.lineEnd] = [lineEnd, line];
        params.selectionLine = params.line;
        params.selectionLineEnd = params.lineEnd;
      }
      return fn.call(this, cm, params);
    };
  }
}

// Fix 3: `:s//x/` with no last search gives E35 and changes nothing (codemirror-vim threw a TypeError); wraps exCommands.substitute in installVimFixes.
function substituteNeedsPattern(orig: ExFn): ExFn {
  return function (this: unknown, cm, params) {
    const arg = params.argString ?? "";
    const noPattern = arg.length < 2 || arg[1] === arg[0]; // `:s`, `:s/`, `:s//x/`
    if (noPattern && !(Vim.getVimGlobalState_() as { query?: RegExp | null }).query) {
      throw new Error("E35: No previous regular expression"); // shown by codemirror-vim, caught by catchExErrors
    }
    return orig.call(this, cm, params);
  };
}

// Fix 3: `:d` leaves the cursor on the first non-blank of the line now in the range's place (codemirror-vim: column 0); wraps exCommands.delete in installVimFixes.
function exDeleteCursor(orig: ExFn): ExFn {
  return function (this: unknown, cm, params) {
    orig.call(this, cm, params);
    const line = Math.min(params.selectionLine ?? cm.getCursor().line, cm.lastLine());
    cm.setCursor({ line, ch: firstNonBlank(cm.getLine(line)) });
  };
}

/**
 * Make the stored search query case-sensitive (Vim's default 'noignorecase'). The
 * global state is rebuilt by Vim.resetVimGlobalState_(), so call this after each reset.
 */
export function caseSensitiveSearch(): void {
  const g = Vim.getVimGlobalState_() as { query?: RegExp | null };
  let query: RegExp | null | undefined = g.query;
  Object.defineProperty(g, "query", {
    configurable: true,
    enumerable: true,
    get: () => query,
    set: (q: RegExp | null | undefined) => {
      query = q && q.flags.includes("i") ? new RegExp(q.source, q.flags.replace("i", "")) : q;
    },
  });
}

// Fix 10: after a key, a Normal-mode cursor past the last character (V$<Esc>) moves back onto it.
function clampNormalCursor(target: Element): void {
  const dom = target.closest(".cm-editor");
  const view = dom ? EditorView.findFromDOM(dom as HTMLElement) : null;
  const cm = view ? (getCM(view) as unknown as CM | null) : null;
  const vim = cm?.state.vim;
  if (vim) watchLastEdit(vim);
  if (!cm || !vim || vim.insertMode || vim.visualMode) return;
  const cur = cm.getCursor();
  const len = cm.getLine(cur.line).length;
  if (cur.ch > 0 && cur.ch >= len) cm.setCursor({ line: cur.line, ch: Math.max(0, len - 1) });
}

// Last key pressed in an editor, recorded before codemirror-vim sees it.
let lastKey = "";
/** The last key pressed in an editor (KeyboardEvent.key), before codemirror-vim handled it. */
export const lastEditorKey = (): string => lastKey;

let installed = false;

export function installVimFixes(): void {
  if (installed) return;
  installed = true;
  installMacroIndentFixes(); // macros, :normal, auto-indent, Insert <C-w>, :j (vimfixes-macros-indent.ts)
  const motions = grabTable<MotionFn>(Vim.defineMotion as never);
  const operators = grabTable<OperatorFn>(Vim.defineOperator as never);
  const actions = grabTable<ActionFn>(Vim.defineAction as never);

  motions.moveByLines = lineMotion(motions);
  motions.moveByDisplayLines = displayLineMotion(motions);
  motions.expandToLine = lineOperatorMotion(motions.expandToLine);
  motions.moveToEol = eolMotion(motions.moveToEol);
  motions.moveByWords = backwardWord(motions.moveByWords);
  motions.moveByParagraph = paragraphMove();
  motions.textObjectManipulation = textObject(motions.textObjectManipulation);
  for (const name of ["moveToCharacter", "repeatLastCharacterSearch", "moveToSymbol"]) motions[name] = failWhenStill(motions[name]);
  motions.moveToMatchedSymbol = percentMotion(motions.moveToMatchedSymbol);
  motions.innerBlockVim = innerBlock as unknown as MotionFn;
  motions.vimfixesFail = failMotion;

  operators.delete = deleteOperator as unknown as OperatorFn;
  operators.indent = shiftOperator(operators.indent);
  operators.yank = yankOperator(operators.yank);
  operators.changeCase = caseOperator(operators.changeCase);
  operators.change = changeOperator(operators.change);

  actions.replace = replaceAction(actions.replace);
  actions.paste = pasteAction(actions.paste);
  actions.repeatLastEdit = dotRepeat(actions.repeatLastEdit);
  actions.joinLines = joinAction(Vim.exitVisualMode as never);
  actions.newLineAndEnterInsertMode = countedOpenAbove(actions.newLineAndEnterInsertMode as never) as never; // 3O

  recordMotions(motions); // last: wraps everything above
  exclusiveRanges(operators);

  for (const ch of Object.keys(BLOCKS)) {
    // Unshifted onto the keymap, so it wins over the built-in `i<register>` entry.
    Vim._mapCommand({ keys: `i${ch}`, type: "motion", motion: "innerBlockVim", motionArgs: { textObjectInner: true, selectedCharacter: ch }, context: "operatorPending" } as never);
  }
  // <CR> is `+` (codemirror-vim maps it to `j^` in Normal mode only, so `d<CR>` typed a line break).
  Vim._mapCommand({ keys: "<CR>", type: "motion", motion: "moveByLines", motionArgs: { forward: true, toFirstChar: true } } as never);
  Vim._mapCommand({ keys: "g<CR>", type: "motion", motion: "vimfixesFail" } as never); // not a command: nothing happens
  // % with explicitRepeat, so percentMotion can tell `%` from `1%` (repeatIsExplicit).
  Vim._mapCommand({ keys: "%", type: "motion", motion: "moveToMatchedSymbol", motionArgs: { inclusive: true, toJumplist: true, explicitRepeat: true } } as never);
  for (const [keys, after] of [["gp", true], ["gP", false]] as const) {
    Vim._mapCommand({ keys, type: "action", action: "paste", isEdit: true, actionArgs: { after, isEdit: true, cursorAfterText: true } } as never);
  }
  for (const keys of NOT_MOTIONS) Vim._mapCommand({ keys, type: "motion", motion: "vimfixesFail", context: "operatorPending" } as never);
  // Names differ from the built-in "move" (the bare `:15` line jump), which must stay.
  Vim.defineEx("movelines", "m", exMove as never);
  Vim.defineEx("copylines", "co", exCopy as never);
  Vim.defineEx("t", "t", exCopy as never);
  const exCommands = grabTable<ExFn>(((name: string, fn: never) => Vim.defineEx(name, undefined as never, fn)) as never);
  exCommands.substitute = substituteNeedsPattern(exCommands.substitute);
  exCommands.delete = exDeleteCursor(exCommands.delete);
  orderExRanges(exCommands); // last: wraps every ex command defined so far
  document.addEventListener(
    "keydown",
    (e) => {
      const t = e.target as HTMLInputElement | null;
      if (t?.closest?.(".cm-content")) {
        lastKey = e.key;
        clampNormalCursor(t); // also starts watchLastEdit before the editor's first command
      }
      if (e.key === "Enter" && t?.tagName === "INPUT" && t.closest(".cm-vim-panel")) t.value = spaceExAddress(t.value);
    },
    true,
  );
  // keyup: codemirror-vim has finished with the key's keydown by then.
  document.addEventListener(
    "keyup",
    (e) => {
      const t = e.target as Element | null;
      if (t?.closest?.(".cm-content")) clampNormalCursor(t);
    },
    true,
  );
}
