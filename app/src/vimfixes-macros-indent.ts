// Round 4 emulator fixes: macros, auto-indent, Insert-mode <C-w> and ex commands, where
// codemirror-vim 6.4.0 differs from Neovim (the class a entries of content/difftest/known.jsonl). Every expected result was taken
// from nvim 0.12; the cases live in e2e/cases/macros-indent.json and js-indent.json, checked against nvim.
// Installed once by installVimFixes() (vimfixes.ts), through the public Vim API and the
// CodeMirror adapter's prototype, so the vendored package is untouched.
//
// Family 1  :help @, :help :normal. A command that fails (beeps) inside a macro aborts
//           the rest of the register and the remaining count; recursive macros stop at
//           the first failure (run as a loop, not nested), and a key/time guard stops
//           one that never fails. <Space> and <BS> wrap across lines ('whichwrap' b,s).
// Family 2  :help 'autoindent', 'indentexpr', 'cindent', 'cinkeys'. <CR> in Insert/Replace
//           mode, o, O and r<CR> indent the new line like Neovim's python, cpp, javascript
//           and typescript indent;
//           an indent left unused (o<Esc>, S<Esc>, cc<Esc>, <CR><CR>) is dropped; typing
//           } { ) ] # or : re-indents the line where Neovim's indent keys would.
// Family 3  :help i_CTRL-W. Insert/Replace-mode <C-w> deletes Vim's span.
// Family 4  :help :move, :normal, :join, <NL>. Ex errors thrown as "E123: ..." are
//           reported instead of escaping as page errors; :normal ends with Vim's
//           implicit <Esc>; :join takes a count and leaves Vim's cursor; <NL> is j.
// Family 5  :help gi, CTRL-W. gi inserts where Insert mode last stopped; a normal-mode
//           <C-w>{char} (window command) does nothing instead of running {char}.
// Family 6  :help undo-blocks. An insert and the command that started it (o, cw, S ...)
//           are one undo step; Insert-mode <C-w> and arrow keys start a new one.

import { Vim, CodeMirror } from "@replit/codemirror-vim";
import { language } from "@codemirror/language";
import { isolateHistory, undoDepth } from "@codemirror/commands";
import { EditorState, Transaction } from "@codemirror/state";
import type { EditorView } from "@codemirror/view";

interface P {
  line: number;
  ch: number;
}
interface InputState {
  keyBuffer: string[];
  prefixRepeat: string[];
  motionRepeat: string[];
  operator?: string | null;
  registerName?: string | null;
}
interface VimState {
  insertMode?: boolean;
  visualMode?: boolean;
  inputState: InputState;
  lastEditActionCommand?: { action?: string; actionArgs?: { after?: boolean } };
  lastEditInputState?: { operator?: string; motion?: string };
}
// The CodeMirror 5 style adapter codemirror-vim passes around (cm6 is the real view).
/** One change in the adapter's batch for its "change" listeners (a linked list per operation). */
interface ChangeObj {
  next?: ChangeObj;
}
interface CM {
  cm6: EditorView;
  curOp?: { change?: ChangeObj; lastChange?: ChangeObj } | null;
  state: { vim?: VimState | null; overwrite?: boolean };
  firstLine(): number;
  lastLine(): number;
  getLine(n: number): string;
  getCursor(): P;
  setCursor(p: P): void;
  replaceRange(text: string, from: P, to?: P): void;
  replaceSelection(text: string): void;
  on(type: string, f: (e: { mode: string }) => void): void;
  openNotification(template: Node, options?: { bottom?: boolean; duration?: number }): () => void;
}
interface ExParams {
  line?: number;
  lineEnd?: number;
  selectionLine?: number;
  argString?: string;
}
interface InsertChanges {
  changes: unknown[];
  maybeReset?: boolean;
  ignoreCount?: number;
}
interface VimGlobals {
  macroModeState: { isPlaying: boolean; lastInsertModeChanges: InsertChanges };
  lastCharacterSearch: { increment: number; forward: boolean; selectedCharacter: string };
}
// The parts of the Vim API this module calls (vimfixes.ts casts the same way).
interface VimApi {
  handleKey(cm: CM, key: string, origin: string): boolean | undefined;
  exitInsertMode(cm: CM, keepCursor?: boolean): void;
  getVimGlobalState_(): VimGlobals;
  getRegisterController(): { getRegister(name?: string): { toString(): string } };
  InsertModeKey: new (keyName: string, e: object) => unknown;
}
const api = Vim as unknown as VimApi;
const SW = 4; // shiftwidth and tabstop of the oracle (oracle.lua M.OPTIONS)

// ---------------------------------------------------------------- shared helpers

/** Width in columns of the leading whitespace of `text` (tabs to the next multiple of 4). */
function indentWidth(text: string): number {
  let w = 0;
  for (const c of text) {
    if (c === " ") w++;
    else if (c === "\t") w += SW - (w % SW);
    else break;
  }
  return w;
}

/** The editor's language name ("python", "cpp", "javascript", "typescript") as its CodeMirror language reports it. */
function langOf(cm: CM): string {
  return cm.cm6.state.facet(language)?.name ?? "";
}

/** True when > and < leave a line starting with # alone: C++, where 'cindent' and the # in 'cinkeys' make Vim's preprocs_left() true. */
export function shiftSkipsHash(cm: unknown): boolean {
  return langOf(cm as CM) === "cpp";
}

/** True when no command is half-typed (no count, register, operator or key prefix pending). */
function idle(vim: VimState): boolean {
  const s = vim.inputState;
  return !s.keyBuffer.length && !s.operator && !s.registerName && !s.prefixRepeat.length && !s.motionRepeat.length;
}

/** Show a Vim error message under the editor, as codemirror-vim's showConfirm does. */
function reportError(cm: CM, message: string): void {
  const el = document.createElement("div");
  el.className = "cm-vim-message";
  el.style.color = "red";
  el.textContent = message;
  cm.openNotification(el, { bottom: true, duration: 15000 });
}

// ---------------------------------------------------------------- family 1: macros

// Guards against a macro that never fails (Vim would run until CTRL-C). Exercise buffers
// have at most ~40 lines, and a macro over all of them replays in well under a second.
const MAX_REPLAY_KEYS = 100000; // keys one top-level @ / :normal may replay
const MAX_REPLAY_DEPTH = 500; // nested @ that is not the register's last key; JS stack: ~600 in Chromium
const MAX_REPLAY_MS = 30000; // wall time of one replay; only stops a frozen tab (slow machines: ~20 ms per replayed line)

/** One normal-mode command being typed or replayed, at one replay nesting depth. */
interface Cmd {
  keys: string;
  at: P;
  doc: EditorView["state"]["doc"];
  errors: number;
  visual: boolean; // typed in Visual mode
}
// depth: nested replays (@ inside @); nest: nested handleKey calls of any origin.
const replay = { aborted: false, keys: 0, depth: 0, normal: 0, nest: 0, started: 0 };
const cmdStack: (Cmd | null)[] = []; // the command being typed at each nest level
let errorCount = 0; // error messages shown so far (openNotification wrapper)
let currentKeys = ""; // keys of the innermost command in progress (o vs O, cc / S)

/**
 * Family 1 (:help @): run every key through codemirror-vim, but during a macro or :normal
 * stop at the first failing command: the remaining keys of the register and the count
 * are swallowed, as Neovim flushes them. Also feeds the per-editor trackers below.
 */
function guardedHandleKey(orig: VimApi["handleKey"]): VimApi["handleKey"] {
  return function (this: unknown, cm, key, origin) {
    attachEditor(cm);
    if (windowCommand?.cm === cm) {
      if (!cm.state.vim?.insertMode) {
        windowCommandKey(key);
        return true;
      }
      windowCommand = null;
    }
    const replaying = origin === "macro" || (origin === "mapping" && replay.normal > 0);
    const run = () => orig.call(this, cm, key, origin);
    const feed = (k: string) => void orig.call(this, cm, k, "macro"); // untracked: re-types a deferred @
    if (origin === "macro" && playing.length) playing[playing.length - 1].left--;
    if (!replaying) {
      if (origin === "user") {
        Object.assign(replay, { aborted: false, keys: 0, started: Date.now() });
        cmdStack.length = Math.min(cmdStack.length, 1); // forget commands a past replay left half-typed
      }
      return nested(() => trackKey(cm, key, run, feed, false));
    }
    if (replay.aborted) return true;
    const ms = Date.now() - replay.started;
    if (++replay.keys > MAX_REPLAY_KEYS || replay.depth >= MAX_REPLAY_DEPTH || ms > MAX_REPLAY_MS) {
      replay.aborted = true;
      reportError(cm, `macro stopped: ${replay.keys} keys, ${replay.depth} nested @, ${ms} ms and no command failed`);
      return true;
    }
    replay.depth++;
    try {
      return nested(() => trackKey(cm, key, run, feed, true, origin === "macro"));
    } catch (e) {
      replay.aborted = true; // e.g. a stack overflow deep inside codemirror-vim
      console.warn("macro aborted:", e);
      return true;
    } finally {
      replay.depth--;
    }
  };
}

/** Run `f` one handleKey level deeper (keys a mapping such as <CR> -> j^ sends itself). */
function nested<T>(f: () => T): T {
  replay.nest++;
  try {
    return f();
  } finally {
    replay.nest--;
  }
}

/** Run one key, keeping the command's keys and start state; on a replayed failure abort. */
function trackKey(cm: CM, key: string, run: () => boolean | undefined, feed: (k: string) => void,
  replaying: boolean, fromMacro = false): boolean | undefined {
  const vim = cm.state.vim;
  const d = replay.nest - 1;
  if (!vim || vim.insertMode) {
    insertCursor = cm.getCursor(); // typed text moved it without an adapter edit
    if (/^<(?:[CS]-)?(?:Left|Right|Up|Down|Home|End|PageUp|PageDown)>$/.test(key)) markUndoStep(cm);
    if (/^(?: |<Space>|<Tab>)$/.test(key)) blankTypedOn = { cm, line: cm.getCursor().line };
    const result = run();
    noteInsertKey(cm, key);
    return result;
  }
  if (!cmdStack[d]) markUndoStep(cm); // a new command: its changes are a new undo step
  const cmd = (cmdStack[d] ??= { keys: "", at: cm.getCursor(), doc: cm.cm6.state.doc, errors: errorCount, visual: !!vim.visualMode });
  cmd.keys += key;
  currentKeys = cmd.keys;
  let result = playMacro(cmd.keys, () => withOldRecording(cmd.keys, run), feed, fromMacro);
  resolveInsertEntry(cm);
  const after = cm.state.vim;
  if (!after || after.insertMode || idle(after)) {
    cmdStack[d] = null;
    if (replaying && commandFailed(cm, cmd)) {
      replay.aborted = true;
      if (after?.insertMode) api.exitInsertMode(cm, true); // a failed c{motion}: no insert
    }
  }
  if (!result && !after?.insertMode && /^<(?:[CSMA]-)*CR>$/.test(key)) result = true; // g<CR>: no line break
  return result;
}

/** Macro playbacks in progress, innermost last: how many of the register's keys are left. */
const playing: { left: number }[] = [];
let tailCall: string | null = null; // an @ command deferred until its playback returns
let suppressPlay: string | null = null; // getRegister() hands an empty register for this name

/**
 * Family 1 (:help @): a recursive macro (qaq qa...@aq) nests one playback per line, and
 * the JS stack overflows near 600 of them in Chromium. An @ that is the last key of the
 * playing register is instead run when that playback returns: the same keys in the same
 * order, as a loop. trackKey runs every finished command through here.
 */
function playMacro(keys: string, run: () => boolean | undefined, feed: (k: string) => void,
  fromMacro: boolean): boolean | undefined {
  if (!/^(?:"[\s\S])?\d*@[\s\S]$/.test(keys)) return run();
  const top = playing[playing.length - 1];
  if (fromMacro && top && top.left <= 0) {
    tailCall = keys;
    suppressPlay = macroRegister(keys);
    try {
      return run(); // consumes the keys and plays nothing
    } finally {
      suppressPlay = null;
    }
  }
  const play = <T>(k: string, f: () => T): T => {
    const count = Number(/(\d*)@/.exec(k)![1]) || 1;
    const reg = api.getRegisterController().getRegister(macroRegister(k)) as unknown as RegisterData;
    const left = reg.keyBuffer.join("").match(/<(?:[CSMA]-)*\w+>|./gi)?.length ?? 0; // as codemirror-vim splits it
    playing.push({ left: left * count });
    try {
      return f();
    } finally {
      playing.pop();
    }
  };
  const result = play(keys, run);
  while (tailCall && !replay.aborted) {
    const k = tailCall;
    tailCall = null;
    play(k, () => [...k].forEach(feed));
  }
  tailCall = null;
  return result;
}

/** The register an @ command plays ("@@": the last one played); used by playMacro. */
function macroRegister(keys: string): string {
  const name = keys[keys.length - 1];
  const g = api.getVimGlobalState_().macroModeState as { latestRegister?: string };
  return name === "@" ? g.latestRegister ?? "" : name;
}

interface RegisterData {
  keyBuffer: unknown[];
  insertModeChanges: unknown[];
  searchQueries: unknown[];
}
interface RegisterController {
  getRegister(name?: string): RegisterData & { toString(): string };
  r4Wrapped?: boolean;
}
/** What register `name` held when `q{name}` started recording into it. */
let beforeRecording: { name: string; data: RegisterData } | null = null;
let playOld: { name: string; skip: number } | null = null;

/**
 * Family 1 (:help q, :help @): Vim fills the register only when recording stops, so `@a`
 * typed while recording into a (the qaq qa...@aq recursion idiom) runs the old content,
 * usually nothing. codemirror-vim records into the live register and so recursed at once.
 */
function withOldRecording(keys: string, run: () => boolean | undefined): boolean | undefined {
  const g = api.getVimGlobalState_().macroModeState as { isRecording?: boolean; latestRegister?: string };
  const ctrl = api.getRegisterController() as unknown as RegisterController;
  if (!ctrl.r4Wrapped) {
    const get = ctrl.getRegister.bind(ctrl);
    ctrl.getRegister = (name) => {
      if (suppressPlay !== null && name === suppressPlay) { // playMacro's deferred @
        return Object.assign(Object.create(Object.getPrototypeOf(get(name))), { keyBuffer: [], insertModeChanges: [], searchQueries: [] });
      }
      if (!playOld || name !== playOld.name || !beforeRecording) return get(name);
      if (playOld.skip-- > 0) return get(name); // the first call logs the "a" of "@a"
      return Object.assign(Object.create(Object.getPrototypeOf(get(name))), beforeRecording.data);
    };
    ctrl.r4Wrapped = true;
  }
  const q = /^q([a-z0-9"])$/.exec(keys);
  if (q && !g.isRecording) {
    const reg = ctrl.getRegister(q[1]);
    beforeRecording = { name: q[1], data: { keyBuffer: reg.keyBuffer, insertModeChanges: reg.insertModeChanges, searchQueries: reg.searchQueries } };
  }
  const at = /^\d*@([a-z0-9"@])$/.exec(keys);
  const name = at?.[1] === "@" ? g.latestRegister : at?.[1];
  if (!g.isRecording || !name || name !== beforeRecording?.name || name !== g.latestRegister) return run();
  playOld = { name, skip: 1 };
  try {
    return run();
  } finally {
    playOld = null;
  }
}

/**
 * Family 1: does this finished command fail in Vim (beep, which aborts a macro)? Decided
 * from the state before the command, since codemirror-vim moves or edits anyway.
 */
function commandFailed(cm: CM, cmd: Cmd): boolean {
  if (errorCount > cmd.errors) return true; // E486 pattern not found, ex errors, ...
  // register, count, operator (a "<" that starts a key name like <CR> is not one), count, motion
  const m = /^(?:"[\s\S])?(\d*)((?:[dcy>=!]|<(?!(?:[CSMA]-)*\w+>)|g[~uU?qw]|zf)?)(\d*)([\s\S]*)$/.exec(cmd.keys);
  if (!m) return false;
  const count = (Number(m[1]) || 1) * (Number(m[3]) || 1);
  const [op, motion] = [m[2], m[4]];
  const doc = cmd.doc;
  const { line, ch } = cmd.at;
  const last = doc.lines - 1;
  const text = doc.line(line + 1).text;
  if (op && (motion === op.slice(-1) || motion === op)) return count > 1 && line >= last; // 2dd on the last line
  if (/^(?:j|\+|<CR>|<C-[jn]>|<Down>)$/.test(motion)) return line >= last;
  if (/^(?:k|-|<C-p>|<Up>)$/.test(motion)) return line <= 0;
  if (/^(?:h|<Left>)$/.test(motion) || (motion === "X" && !op)) return !op && ch === 0; // dh in column 0 does not beep
  if (/^(?:<BS>|<C-h>)$/.test(motion)) return !op && line === 0 && ch === 0; // wraps to the line above
  // Visual l may go onto the line break; <Space> wraps to the next line.
  if (/^(?:l|<Right>)$/.test(motion)) return !op && !cmd.visual && ch >= text.length - 1;
  if (motion === "<Space>") return !op && line === last && ch >= text.length - (cmd.visual ? 0 : 1);
  if (/^[wW]$/.test(motion)) return !op && line === last && ch >= text.length - 1;
  if (/^(?:[bB]|g[eE])$/.test(motion)) return line === 0 && ch === 0;
  if (/^[eE]$/.test(motion)) return !op && !/\S/.test(doc.sliceString(doc.line(line + 1).from + ch + 1));
  if (/^[fFtT].$/.test(motion)) return charSearchFails(text, ch, motion[0], motion[1], count, false);
  if (/^[;,]$/.test(motion)) {
    const s = api.getVimGlobalState_().lastCharacterSearch;
    const dir = (s.forward === (motion === ";")) ? (s.increment ? "t" : "f") : (s.increment ? "T" : "F");
    return !!s.selectedCharacter && charSearchFails(text, ch, dir, s.selectedCharacter, count, true);
  }
  if (motion === "J" && !op) return line >= last && count <= 2;
  if (/^r.$/.test(motion) && !op) return ch + count > text.length;
  if (/^g?[pP]$/.test(motion) && !op) {
    const reg = /^"([\s\S])/.exec(cmd.keys)?.[1];
    return api.getRegisterController().getRegister(reg).toString() === "";
  }
  const unchanged = cm.cm6.state.doc === doc && cm.getCursor().line === line && cm.getCursor().ch === ch;
  return op === "d" && /^[ia]./.test(motion) && unchanged; // di( with no ( around the cursor
}

/**
 * Family 1 (:help <Space>, 'whichwrap' b,s): <Space> moves right like l but goes on to the
 * next line. With an operator or in Visual mode it first stops just past the line's last
 * character (the line break counts as one position). A motion; installed by install below.
 */
function spaceRight(cm: CM, head: P, args: { repeat?: number }, vim: VimState, input: InputState): P {
  const past = !!input.operator || !!vim.visualMode;
  let { line, ch } = head;
  for (let n = args.repeat ?? 1; n > 0; n--) {
    const len = cm.getLine(line).length;
    if (ch < (past && len ? len : Math.max(0, len - 1))) ch++;
    else if (line < cm.lastLine()) [line, ch] = [line + 1, 0];
    else break;
  }
  return { line, ch };
}

/**
 * Family 1 (:help <BS>, 'whichwrap' b): <BS> / <C-h> move left like h but go on to the end
 * of the line above (past its last character in Visual mode or for d / c, which then
 * delete the line break). A motion; installed by install below.
 */
function backspaceLeft(cm: CM, head: P, args: { repeat?: number }, vim: VimState, input: InputState): P | [P, P] {
  const op = input.operator; // vim.inputState is already cleared when a motion runs
  let { line, ch } = head;
  let joined = false;
  for (let n = args.repeat ?? 1; n > 0; n--) {
    if (ch > 0) {
      ch--;
      continue;
    }
    if (line === 0) break;
    line--;
    const len = cm.getLine(line).length;
    joined = (op === "delete" || op === "change") && len > 0;
    ch = vim.visualMode || joined ? len : Math.max(0, len - 1);
  }
  // Neovim skips the exclusive-linewise adjustment here (CA_NO_ADJ_OP_END): a range keeps it.
  return joined ? [{ line, ch }, head] : { line, ch };
}

/** Family 1: would f/F/t/T{c} (or ; and , repeating it) find no target on the line? */
function charSearchFails(text: string, ch: number, kind: string, c: string, count: number, repeat: boolean): boolean {
  const forward = kind === "f" || kind === "t";
  // t/T repeated with ; skip a target right next to the cursor (:help cpo-;).
  let i = forward ? ch + (repeat && kind === "t" ? 2 : 1) : ch - (repeat && kind === "T" ? 2 : 1);
  for (let n = 0; i >= 0 && i < text.length; i += forward ? 1 : -1) {
    if (text[i] === c && ++n === count) return false;
  }
  return true;
}

/** Count error messages (not "3 lines yanked", shown for 1.5 s) for commandFailed(). */
function countErrorMessages(): void {
  const proto = CodeMirror.prototype as unknown as CM;
  const orig = proto.openNotification;
  proto.openNotification = function (this: CM, template, options) {
    if (options?.duration !== 1500) errorCount++;
    return orig.call(this, template, options);
  };
}

/**
 * Family 1c + 4 (:help :normal): run {commands} on each line of the range as typed keys.
 * A failing command ends that line (the next line still runs, as in Neovim); an
 * unfinished command is ended by Vim's implicit <Esc>, which in Insert mode moves the
 * cursor left (codemirror-vim kept it). Keys are literal: ":norm i<CR>" types "<CR>".
 */
function exNormal(cm: CM, params: ExParams): void {
  let keys = params.argString ?? "";
  if (keys.startsWith("!")) keys = keys.slice(1); // TODO: :normal! still applies the jk map
  keys = keys.trimStart();
  if (!keys) return reportError(cm, "E471: Argument required");
  if (params.line === undefined) return runNormalKeys(cm, keys);
  const end = Math.min(params.lineEnd ?? params.line, cm.lastLine());
  // Neovim's ex_normal steps a line number and clamps it to the buffer: after :%norm dd
  // deleted lines, the last line is used again (every line is deleted).
  for (let l = params.line; l <= end; l++) {
    const before = cm.curOp?.lastChange;
    cm.setCursor({ line: Math.min(l, cm.lastLine()), ch: 0 });
    runNormalKeys(cm, keys);
    // codemirror-vim hands the whole ex command's changes to its Insert-mode recorder (the
    // text `.` repeats) when the command ends; keep only this line's, as Neovim repeats.
    const op = cm.curOp;
    if (op && before?.next && op.lastChange !== before) op.change = before.next;
  }
}

/** Feed one :normal string as keys, then end Insert mode or a pending command like <Esc>. */
function runNormalKeys(cm: CM, keys: string): void {
  if (!replay.normal && !replay.depth) Object.assign(replay, { keys: 0, started: Date.now() });
  cmdStack.length = Math.min(cmdStack.length, replay.depth + 1);
  replay.normal++;
  replay.aborted = false;
  const proto = CodeMirror.prototype as unknown as { openDialog: (...a: unknown[]) => () => void };
  const openDialog = proto.openDialog;
  let prompt = false; // ":" or "/" can never be finished inside :normal (no <CR> in it)
  proto.openDialog = () => ((prompt = true), () => {});
  try {
    for (const c of keys) {
      if (replay.aborted || prompt) break;
      const vim = cm.state.vim!;
      // In Insert mode a literal "<" would start matching key names such as <CR>.
      const key = c === " " ? "<Space>" : c === "<" && vim.insertMode ? "<lt>" : c;
      const handled = api.handleKey(cm, key, "mapping");
      if (!handled && vim.insertMode) typeInsertChar(cm, c);
    }
  } finally {
    proto.openDialog = openDialog;
    replay.normal--;
  }
  replay.aborted = false; // the implicit <Esc> below must run
  const vim = cm.state.vim!;
  if (vim.insertMode) api.exitInsertMode(cm);
  else if (!idle(vim)) api.handleKey(cm, "<Esc>", "mapping");
}

/** Insert (or in Replace mode overwrite) one character typed by :normal in Insert mode. */
function typeInsertChar(cm: CM, c: string): void {
  const cur = cm.getCursor();
  const over = cm.state.overwrite && cur.ch < cm.getLine(cur.line).length;
  cm.replaceRange(c, cur, over ? { line: cur.line, ch: cur.ch + 1 } : cur);
  cm.setCursor({ line: cur.line, ch: cur.ch + 1 });
}

// ---------------------------------------------------------------- family 2: indent

/** Per-line code with strings and comments blanked, and where a comment starts (-1: none). */
interface CodeLine {
  code: string;
  comment: number;
  inString: boolean; // the line starts inside a (python triple-quoted / C block / JS template) string or comment
}

/**
 * Blank out strings and comments so brackets and colons in them are ignored. C++,
 * javascript and typescript share // and /* *\/; javascript `templates` are strings that
 * span lines. typescript's are left as code: Neovim's typescript indent does not treat
 * them as strings (their syntax group, typescriptTemplate, misses its string pattern).
 */
function maskCode(lines: string[], lang: string): CodeLine[] {
  const py = lang === "python";
  const js = lang === "javascript" || lang === "typescript";
  const quotes = py ? /^(?:'''|"""|'|")/ : lang === "javascript" ? /^(?:\/\*|'|"|`)/ : /^(?:\/\*|'|")/;
  let open: string | null = null; // the open multi-line string / block comment delimiter
  return lines.map((text) => {
    const inString = open !== null;
    let code = "";
    let comment = -1;
    let operand = false; // the last code token is an operand (a / after it divides)
    for (let i = 0; i < text.length; ) {
      if (open) {
        if (text[i] === "\\" && open !== "*/") { code += "  "; i += 2; continue; }
        if (text.startsWith(open, i)) {
          code += " ".repeat(open.length);
          i += open.length;
          operand ||= open !== "*/"; // a string is an operand; a comment changes nothing
          open = null;
          continue;
        }
        code += " "; i++; continue;
      }
      const rest = text.slice(i);
      if (py ? rest[0] === "#" : rest.startsWith("//")) { comment = i; code += " ".repeat(text.length - i); break; }
      const delim = quotes.exec(rest)?.[0];
      if (delim) {
        if (delim === "/*" && comment < 0) comment = i;
        open = delim === "/*" ? "*/" : delim;
        code += " ".repeat(delim.length);
        i += delim.length;
        continue;
      }
      const regex = js && rest[0] === "/" && !operand ? regexLength(rest) : 0;
      if (regex) { code += " ".repeat(regex); i += regex; operand = true; continue; }
      if (/\S/.test(text[i])) operand = !/[=(,:[!?&|{;]/.test(text[i]) && !/\breturn$/.test(code + text[i]);
      code += text[i++];
    }
    if (open && open.length === 1 && open !== "`") open = null; // an unterminated '...' ends at the line end
    return { code, comment, inString };
  });
}

/** Length of the /regex/flags literal `rest` starts with, or 0 when its / closes nowhere on the line. */
function regexLength(rest: string): number {
  let inClass = false;
  for (let i = 1; i < rest.length; i++) {
    const c = rest[i];
    if (c === "\\") i++;
    else if (c === "[") inClass = true;
    else if (c === "]") inClass = false;
    else if (c === "/" && !inClass) return i + 1 + /^[a-z]*/.exec(rest.slice(i + 1))![0].length;
  }
  return 0;
}

/** The innermost unclosed ( [ { (only "(" when `parens`) before (line, ch), searching back to line `stop` (Vim's searchpair). */
function openBracketBefore(code: CodeLine[], line: number, ch: number, stop: number, parens = false): P | null {
  const [opens, closes] = parens ? ["(", ")"] : ["([{", ")]}"];
  let depth = 0;
  for (let l = line; l >= Math.max(0, stop); l--) {
    const t = code[l].code;
    for (let i = (l === line ? ch : t.length) - 1; i >= 0; i--) {
      if (closes.includes(t[i])) depth++;
      else if (opens.includes(t[i]) && depth-- === 0) return { line: l, ch: i };
    }
  }
  return null;
}

/**
 * Family 2: Neovim's python indentexpr (runtime/autoload/python.vim, python#GetIndent)
 * for line n of `lines`; -1 keeps the autoindent `cur`. Ported line by line.
 */
function pythonIndent(lines: string[], n: number, cur: number): number {
  const ind = (i: number) => indentWidth(lines[i]);
  if (n > 0 && lines[n - 1].endsWith("\\")) return n > 1 && lines[n - 2].endsWith("\\") ? ind(n - 1) : ind(n - 1) + 2 * SW;
  const code = maskCode(lines.slice(0, n + 1), "python");
  if (code[n].inString) return -1;
  let plnum = n - 1;
  while (plnum >= 0 && !/\S/.test(lines[plnum])) plnum--;
  if (plnum < 0) return 0;
  const p = openBracketBefore(code, n, 0, n - 50); // align with an open bracket not at the line end
  if (p && p.ch !== lines[p.line].length - 1) return p.ch + 1;
  const outer = openBracketBefore(code, plnum, 0, plnum - 50); // is plnum inside brackets?
  const plindent = outer ? ind(outer.line) : ind(plnum);
  const plnumstart = outer ? outer.line : plnum;
  if (p) {
    if (p.line === plnum) return ind(plnum) + (openBracketBefore(code, p.line, p.ch, n - 50) ? SW : 2 * SW);
    return plnumstart === p.line ? ind(plnum) : plindent;
  }
  const pline = code[plnum].comment >= 0 ? lines[plnum].slice(0, code[plnum].comment) : lines[plnum];
  if (/:\s*$/.test(pline)) return plindent + SW;
  const dedented = (expected: number) => cur <= expected - SW;
  if (/^\s*(?:break|continue|raise|return|pass)\b/.test(lines[plnum])) return dedented(ind(plnum)) ? -1 : ind(plnum) - SW;
  if (/^\s*(?:except|finally)\b/.test(lines[n])) {
    for (let l = n - 1; l >= 0; l--) if (/^\s*(?:try|except)\b/.test(lines[l])) return ind(l) >= cur ? -1 : ind(l);
    return -1;
  }
  if (/^\s*(?:elif|else)\b/.test(lines[n])) {
    if (/^\s*(?:for|if|elif|try)\b/.test(lines[plnumstart])) return plindent;
    return dedented(plindent) ? -1 : plindent - SW;
  }
  if (outer) return dedented(plindent) ? -1 : plindent;
  return -1;
}

/**
 * Family 2: the common cases of Neovim's cindent for line n (C++ has no indentexpr to
 * port). Checked against nvim: blocks, closing braces, unbraced if/for/else bodies,
 * case labels, continuation lines and open parentheses. -1 keeps the autoindent.
 */
function cppIndent(lines: string[], n: number): number {
  const ind = (i: number) => indentWidth(lines[i]);
  const code = maskCode(lines.slice(0, n + 1), "cpp");
  const t = (i: number) => code[i].code.trim();
  const skip = (i: number) => !t(i) || t(i).startsWith("#");
  // The line where the statement on line l starts: back over a ( it closes (if (a &&\n b) {).
  const start = (l: number) => {
    let depth = 0;
    for (let i = 0; i < code[l].code.length; i++) {
      const c = code[l].code[i];
      if (c === "(") depth++;
      else if (c === ")" && --depth < 0) return openBracketBefore(code, l, i, 0)?.line ?? l;
    }
    return l;
  };
  // A closing brace lines up with the statement of its {, or column 0 without one; a { inside
  // an open ( continues the ( (two levels in).
  const closing = (l: number) => {
    const m = openBracketBefore(code, l, code[l].code.indexOf("}"), 0);
    const paren = m && openBracketBefore(code, m.line, m.ch, 0);
    if (paren && code[paren.line].code[paren.ch] !== "{") return ind(paren.line) + 2 * SW;
    return m ? ind(start(m.line)) : 0;
  };
  const tn = t(n);
  if (tn.startsWith("}")) return closing(n);
  if (tn.startsWith("#")) return 0; // preprocessor lines start in column 0
  const open = openBracketBefore(code, n, 0, 0);
  const opener = open ? code[open.line].code[open.ch] : "";
  if ((tn.startsWith(")") && opener === "(") || (tn.startsWith("]") && opener === "[")) return open!.ch; // under its ( or [
  if (/^(?:case\b|default\s*:)/.test(tn) && open) return ind(start(open.line)); // with the switch
  if (/^(?:public|private|protected)\s*:/.test(tn) && open) return ind(start(open.line)) + SW;
  if (/^[A-Za-z_]\w*\s*:(?!:)/.test(tn)) return 0; // a goto label
  let p = n - 1;
  while (p >= 0 && skip(p)) p--;
  if (p < 0) return 0;
  if (open && code[open.line].code[open.ch] !== "{") return ind(open.line) + 2 * SW; // ( or [
  const pt = t(p);
  if (tn.startsWith("{") && !/[;{}]$/.test(pt)) return ind(start(p)); // a block's { under its header
  if (pt.endsWith("{")) return ind(start(p)) + SW; // a block opened on line p
  if (open?.line === p) return ind(p) + SW; // a brace list opened on line p
  if (/^(?:case\b.*|default\s*):$/.test(pt)) return ind(p) + SW;
  if (/^(?:public|private|protected)\s*:$/.test(pt)) return open ? ind(open.line) + SW : ind(p) + SW;
  // An unbraced if / for / while / else / do body is one level in (top level: column 4).
  if (/^(?:}\s*)?(?:(?:if|for|while|switch)\b.*\)|else(?:\s+if\b.*\))?|do)$/.test(pt)) return open ? ind(p) + SW : SW;
  if (pt.startsWith("}")) return closing(p);
  // The first line of the statement that ends (or continues) on line p.
  let s = p;
  for (let q = s - 1; q >= 0 && !(open && q <= open.line); q--) {
    if (skip(q)) continue;
    if (/[;{}:]$/.test(t(q))) break;
    s = q;
  }
  if (/[;,]$/.test(pt)) return ind(s);
  return open ? ind(s) + SW : -1; // continuation line; top level keeps the autoindent
}

/** The last token before (line, ch) in masked code (a word or one other character) and where it starts; null at the top. */
function tokenBefore(code: CodeLine[], line: number, ch: number): (P & { tok: string }) | null {
  for (let l = line; l >= 0; l--) {
    const t = code[l].code;
    let i = (l === line ? ch : t.length) - 1;
    while (i >= 0 && /\s/.test(t[i])) i--;
    if (i < 0) continue;
    let s = i;
    if (/[\w$]/.test(t[i])) while (s > 0 && /[\w$]/.test(t[s - 1])) s--;
    return { line: l, ch: s, tok: t.slice(s, i + 1) };
  }
  return null;
}

/** Words after which a { opens an object literal, not a block (javascript.vim s:IsBlock). */
const JS_EXPR_WORDS = "return const let import export extends yield default delete var await void typeof throw case new in instanceof".split(" ");
/** A line starting with one of these continues the statement above (javascript.vim s:opfirst). */
const JS_OPFIRST = /^(?:[<>=,.?^%|/&]|([-:+])(?!\1)|\*+|!=|in(?:stanceof)?\b)/;
/** A line ending with one of these continues on the next line (javascript.vim s:continuation). */
const JS_CONTINUATION = /(?:[<=,.~!?/*^%|&:]|(?<!\+)\+|(?<!-)-|(?<!=)>|\b(?:typeof|new|delete|void|in|instanceof|await))$/;

/** True when the { at `brace` opens a block rather than an object literal (javascript.vim s:IsBlock). */
function jsIsBlock(code: CodeLine[], brace: P): boolean {
  const prev = tokenBefore(code, brace.line, brace.ch);
  if (!prev) return true;
  const before = tokenBefore(code, prev.line, prev.ch)?.tok ?? "";
  if (/^[\w$]/.test(prev.tok)) return JS_EXPR_WORDS.indexOf(prev.tok) < (prev.line !== brace.line ? 1 : 0) || before === ".";
  if (prev.tok === ">") return code[prev.line].code[prev.ch - 1] === "="; // =>
  if (prev.tok === ":") return /^[A-Za-z_$][\w$]*$/.test(before) && !jsExprCol(code, prev); // a label
  return !/[=~!<,.?^%|&([*+/-]/.test(prev.tok);
}

/** True when the : at `colon` is part of an expression (a ternary or an object key), not a label or case (javascript.vim s:ExprCol). */
function jsExprCol(code: CodeLine[], colon: P): boolean {
  if (code[colon.line].code[colon.ch - 1] === ":") return true;
  let bal = 0;
  let q: P | null = colon;
  while ((q = tokenBefore(code, q.line, q.ch))) {
    const t = code[q.line].code;
    const c = t[q.ch];
    if (c === ":") {
      if (t[q.ch - 1] === ":") q = { line: q.line, ch: q.ch - 1 };
      else bal--;
    } else if (c === "?") {
      if (/^\.(?!\d)/.test(t.slice(q.ch + 1, q.ch + 3))) continue; // ?. optional chaining
      if (!bal) return true;
      bal++;
    } else if (c === "{") return !jsIsBlock(code, q);
    else if (c === "}") {
      q = openBracketBefore(code, q.line, q.ch, 0);
      if (!q) return false;
    }
  }
  return false;
}

/** True when the first code after the { at `brace` is a case or default label (javascript.vim s:IsSwitch). */
function jsIsSwitch(code: CodeLine[], brace: P): boolean {
  const rest = [code[brace.line].code.slice(brace.ch + 1), ...code.slice(brace.line + 1).map((c) => c.code)].join("\n");
  return /^\s*(?:case|default)\b/.test(rest);
}

/** If the token `at` ends an unbraced if/for/while/with (...), else, do or => head, where to look further back; else null (javascript.vim s:OneScope). */
function jsOneScope(code: CodeLine[], at: P & { tok: string }): (P & { tok: string }) | null {
  const prev = (q: P) => tokenBefore(code, q.line, q.ch);
  if (at.tok === ")") {
    const paren = openBracketBefore(code, at.line, at.ch, 0);
    const kw = paren && prev(paren);
    if (!kw) return null;
    const head = ["for", "if", "let", "while", "with"].includes(kw.tok) || (/^(?:await|each)$/.test(kw.tok) && prev(kw)?.tok === "for");
    return head && prev(kw)?.tok !== "." ? kw : null;
  }
  if (at.tok === "else" || at.tok === "do") return prev(at)?.tok !== "." ? at : null;
  if (at.tok !== ">" || code[at.line].code[at.ch - 1] !== "=") return null;
  const param = tokenBefore(code, at.line, at.ch - 1); // => : back over the parameters
  if (param?.tok !== ")") return param ?? at;
  const paren = openBracketBefore(code, param.line, param.ch, 0);
  return paren && { ...paren, tok: "(" };
}

/** How many unbraced scopes (if (a), else, x =>) line p and the lines above it leave open (javascript.vim s:IsContOne). */
function jsBraceless(code: CodeLine[], lines: string[], p: number, open: P | null, cont: boolean): number {
  const ind = (i: number) => indentWidth(lines[i]);
  const top = open ? open.line : 0;
  const pind = open ? ind(open.line) + SW : 0;
  let at = tokenBefore(code, p, code[p].code.length);
  let level = ind(p) + (cont ? 0 : 1);
  let count = 0;
  while (at && ((at.line > top && level > pind) || at.line === top)) {
    const scope = ind(at.line) < level ? jsOneScope(code, at) : null;
    if (scope) {
      count++;
      at = scope;
    } else if (!cont || count || level < ind(p)) break;
    else at = { line: at.line, ch: 0, tok: "" };
    level = Math.min(level, ind(at.line));
    at = tokenBefore(code, at.line, at.ch);
  }
  return count;
}

/**
 * Family 2: Neovim's javascript indentexpr (runtime/indent/javascript.vim,
 * GetJavascriptIndent) for line n, the common cases: the enclosing ( [ { sets the base
 * (a block after `if (...)` measures from the `(` line), a switch body adds a level for
 * its labels, and a statement left open (a trailing operator, `=>`, an unbraced if /
 * for / while / else body) one more. A closing bracket goes back to its opener's line.
 * -1 keeps the autoindent.
 */
function jsIndent(lines: string[], n: number): number {
  const ind = (i: number) => indentWidth(lines[i]);
  const code = maskCode(lines, "javascript");
  if (code[n].inString) return -1; // inside a template literal or a block comment
  // A line holding only a string literal is code (s:PrevCodeLine skips blank and comment lines only).
  const noCode = (l: number) => !code[l].code.trim() && (code[l].inString || code[l].comment === lines[l].length - lines[l].trimStart().length || !lines[l].trim());
  let p = n - 1;
  while (p >= 0 && noCode(p)) p--;
  if (p < 0) return 0;
  const pline = (code[p].comment >= 0 ? lines[p].slice(0, code[p].comment) : lines[p]).trimEnd();
  const lead = lines[n].length - lines[n].trimStart().length;
  const line = code[n].comment === lead ? "" : lines[n].trimStart(); // a comment line counts as empty
  const closer = /^[\])}]/.test(line);
  const open = openBracketBefore(code, n, closer ? lead : 0, 0);
  let numInd = open ? ind(open.line) : 0;
  let isOp = 0, braceless = 0, switchOffset = 0;
  if (!open || (code[open.line].code[open.ch] === "{" && jsIsBlock(code, open))) {
    const close = open && tokenBefore(code, open.line, open.ch);
    const paren = close?.tok === ")" ? openBracketBefore(code, close.line, close.ch, 0) : null;
    if (open && close && paren) {
      if (close.line === open.line) numInd = ind(paren.line);
      if (!closer && tokenBefore(code, paren.line, paren.ch)?.tok === "switch" && jsIsSwitch(code, open)) {
        switchOffset = SW;
        if (!pline.endsWith(".") && /^(?:default|case)\b/.test(line)) return numInd + SW;
      }
    }
    if (!closer && !/[{;]$/.test(pline)) {
      if (JS_OPFIRST.test(line) || jsContinues(code, pline, p)) isOp = SW;
      braceless = Math.max(0, jsBraceless(code, lines, p, open, isOp > 0) - (!isOp && line.startsWith("{") ? 1 : 0)) * SW;
    }
  }
  if (closer) return numInd;
  return (open ? numInd + SW + switchOffset : 0) + braceless + isOp;
}

/** True when `pline` (line p without its comment) ends with an operator that continues the statement (javascript.vim s:Continues). */
function jsContinues(code: CodeLine[], pline: string, p: number): boolean {
  const tok = JS_CONTINUATION.exec(pline.slice(-15))?.[0] ?? "";
  if (tok === ":") return jsExprCol(code, { line: p, ch: pline.length - 1 });
  if (/^[a-z]/.test(tok)) return tokenBefore(code, p, pline.length - tok.length)?.tok !== ".";
  return tok !== "";
}

/** typescript.vim's patterns; a match may be followed by blanks and a // comment. */
const TS_END = String.raw`\s*(?:\/\/.*)?$`;
const TS_CONTINUATION = new RegExp(String.raw`(?:[\\*+/.:]|(?<!<%)[=-]|\W[|&?]|\|\||&&|[^=]=[^=].*,)` + TS_END);
const TS_ONE_LINE_SCOPE = new RegExp(String.raw`\b(?:if|else|for|while)\b[^{;]*` + TS_END);
const TS_BLOCK = new RegExp(String.raw`[{[]` + TS_END);

/**
 * Family 2: Neovim's typescript indentexpr (runtime/indent/typescript.vim,
 * GetTypescriptIndent). Unlike javascript's it follows the previous code line: a line
 * ending in { or [ indents, an unclosed ( aligns after it, a trailing operator starts a
 * continuation, an unbraced if / else / for / while body indents one line, and a
 * closing bracket goes back to its opener's line. -1 keeps the autoindent.
 */
function tsIndent(lines: string[], n: number): number {
  const ind = (i: number) => indentWidth(lines[i]);
  const code = maskCode(lines, "typescript");
  const masked = (l: number, i: number) => (code[l].comment >= 0 && i >= code[l].comment) || code[l].code[i] !== lines[l][i];
  // s:Match: the pattern matches line l outside strings and comments.
  const matches = (l: number, re: RegExp) => {
    const m = l >= 0 ? re.exec(lines[l]) : null;
    return m !== null && !masked(l, m.index);
  };
  const prevNonBlank = (l: number) => {
    while (l >= 0 && !lines[l].trim()) l--;
    return l;
  };
  // s:PrevNonBlankNonString: the code line at or above `from`, skipping // and /* */ comment lines.
  const prevCode = (from: number) => {
    let inBlock = false;
    let l = prevNonBlank(from);
    for (; l >= 0; l = prevNonBlank(l - 1)) {
      if (lines[l].includes("/*")) {
        if (!inBlock) break;
        inBlock = false;
      } else if (!inBlock && lines[l].includes("*/")) inBlock = true;
      else if (!inBlock && !/^\s*\/\//.test(lines[l])) break;
    }
    return l;
  };
  // s:GetMSL: the first line of the continued statement line l belongs to.
  const msl = (l: number, inScope: boolean) => {
    let found = l;
    for (let q = prevCode(l - 1); q >= 0; q = prevCode(q - 1)) {
      if (matches(q, TS_CONTINUATION)) found = q;
      else if (inScope || !matches(q, TS_ONE_LINE_SCOPE)) break;
    }
    return found;
  };
  const line = lines[n];
  const prevline = prevNonBlank(n - 1);
  const close = /^\s*[\],})]/.exec(line);
  if (close && !masked(n, close[0].length - 1)) {
    const at = close[0].length - 1;
    if (line[at] === ",") return -1;
    const open = openBracketBefore(code, n, at, 0, line[at] === ")");
    if (!open) return -1;
    if (line[at] === ")" && open.ch !== lines[open.line].length - 1) return open.ch;
    return ind(msl(open.line, false));
  }
  if (prevline >= 0 && /^\s*,/.test(lines[prevline])) return ind(prevline) - SW;
  if (prevline >= 0 && /^\s+[?|:]/.test(line)) return ind(prevline) + (/^\s+\?/.test(lines[prevline]) ? 0 : SW);
  if (code[n].inString) return -1; // in a block comment
  if (!line.trim() && prevline >= 0 && code[prevline].inString) return ind(prevline) - 1;
  const lnum = prevCode(n - 1);
  if (!line.trim() && lnum !== prevline) return ind(prevline);
  if (lnum < 0) return 0;
  if (matches(lnum, TS_BLOCK)) return ind(msl(lnum, false)) + SW;
  if (/[[({]/.test(lines[lnum])) {
    const net = (o: string, c: string) => [...code[lnum].code].reduce((d, ch) => d + (ch === o ? 1 : ch === c ? -1 : 0), 0);
    const paren = net("(", ")") > 0 ? openBracketBefore(code, n, 0, 0, true) : null;
    if (paren) return paren.ch === lines[paren.line].length - 1 ? ind(lnum) + SW : paren.ch + 1;
    if (net("[", "]") > 0 || net("{", "}") > 0) return ind(lnum) + SW;
  }
  // s:IndentWithContinuation
  let res = ind(lnum);
  const start = msl(lnum, true);
  if (!(start !== lnum && matches(lnum, TS_CONTINUATION)) && matches(start, TS_CONTINUATION))
    res = start === lnum ? ind(start) + SW : ind(start);
  // s:InOneLineScope / s:ExitingOneLineScope
  const inScope = (l: number) => {
    const s = msl(l, true);
    return matches(s, TS_ONE_LINE_SCOPE) ? s : -1;
  };
  if (inScope(lnum) >= 0) return res + SW;
  const prevStart = matches(start, TS_ONE_LINE_SCOPE) ? -1 : msl(start - 1, true);
  let ols = matches(prevStart, TS_ONE_LINE_SCOPE) ? prevStart : -1;
  while (ols >= 0 && res > 0) {
    res -= SW;
    ols = inScope(ols - 1);
  }
  return res;
}

/** Neovim's indent for line n of `lines` in `lang`, or -1 (keep the autoindent); `cur` is the indent autoindent would give. */
function langIndent(lang: string, lines: string[], n: number, cur: number): number {
  switch (lang) {
    case "python": return pythonIndent(lines, n, cur);
    case "cpp": return cppIndent(lines, n);
    case "javascript": return jsIndent(lines, n);
    case "typescript": return tsIndent(lines, n);
    default: return -1;
  }
}

/** Languages with C comments: //, /* *\/ and the leaders Neovim's formatoptions add. */
const C_COMMENTS = ["cpp", "javascript", "typescript"];

/** Family 2: comment leader Neovim's C formatoptions add on a new line ("// ", " * "), or "". */
function commentLeader(lang: string, above: string): string {
  if (!C_COMMENTS.includes(lang)) return "";
  const masked = maskCode([above], lang)[0];
  if (masked.comment < 0) return /^\s*\*(?!\/)/.test(above) ? " ".repeat(above.indexOf("*")) + "* " : "";
  const rest = above.slice(masked.comment);
  if (rest.startsWith("//")) return " ".repeat(masked.comment) + /^\/\/\s*/.exec(rest)![0];
  return rest.includes("*/") ? "" : " ".repeat(masked.comment + 1) + "* ";
}

/** The new line's leading text (indent, maybe a comment leader) for line n of `lines`. */
function newLineIndent(cm: CM, lines: string[], n: number, autoindent: string): string {
  const lang = langOf(cm);
  const leader = commentLeader(lang, lines[n - 1] ?? "");
  // javascript and typescript indent a // line with their indentexpr (cindent keeps it under the one above).
  if (leader && !(lang !== "cpp" && leader.trimStart().startsWith("//"))) return leader;
  if (leader) lines[n] = leader.trimStart() + lines[n];
  const cols = langIndent(lang, lines, n, indentWidth(autoindent));
  if (leader) return cols < 0 ? leader : " ".repeat(cols) + leader.trimStart();
  return cols < 0 ? autoindent : " ".repeat(cols);
}

/** A line opened by o/O/S/cc/<CR> whose indent is dropped if nothing is typed on it. */
let pendingIndent: { cm: CM; line: number; text: string } | null = null;

/** Family 2: drop the pending auto-indent of `line` if nothing was typed on it. */
function dropUnusedIndent(cm: CM, line: number): void {
  const p = pendingIndent;
  pendingIndent = null;
  if (!p || p.cm !== cm || p.line !== line || line > cm.lastLine()) return;
  const text = cm.getLine(line);
  if (text && text === p.text) cm.replaceRange("", { line, ch: 0 }, { line, ch: text.length });
}

/** True while the command being run is O (the new line goes above the cursor line). */
function openingAbove(cm: CM): boolean {
  if (/^(?:"[\s\S])?\d*O$/.test(currentKeys)) return true;
  const last = cm.state.vim?.lastEditActionCommand;
  return currentKeys === "." && last?.action === "newLineAndEnterInsertMode" && last.actionArgs?.after === false;
}

/**
 * Family 2 (:help i_<CR>, o, O, r<CR>): split the line at the cursor and indent the new
 * line like Neovim. Blanks after the cursor are dropped (autoindent), an unused indent
 * on the line left behind is removed, and the new line's indent becomes the pending one.
 */
function breakLine(cm: CM, openLine = false): void {
  resolveInsertEntry(cm);
  const cur = cm.getCursor();
  const lines = cm.cm6.state.doc.toString().split("\n");
  const text = lines[cur.line];
  const rest = text.slice(cur.ch);
  const skip = rest.length - rest.trimStart().length;
  const above = openLine && openingAbove(cm);
  // O: codemirror-vim breaks at the end of the line above; autoindent copies the line below.
  const source = above && cur.line + 1 < lines.length ? lines[cur.line + 1] : text;
  const autoindent = /^\s*/.exec(source)![0];
  lines.splice(cur.line, 1, text.slice(0, cur.ch), rest.slice(skip));
  const indent = newLineIndent(cm, lines, cur.line + 1, autoindent);
  cm.replaceRange("\n" + indent, cur, { line: cur.line, ch: cur.ch + skip });
  dropUnusedIndent(cm, cur.line);
  const replaced = /r<CR>$/.test(currentKeys) || (currentKeys === "." && cm.state.vim?.lastEditActionCommand?.action === "replace");
  const at = { line: cur.line + 1, ch: indent.length };
  cm.setCursor(replaced ? { ...at, ch: Math.max(0, at.ch - 1) } : at); // r<CR> ends on the indent's last blank
  pendingIndent = /^\s+$/.test(indent) && !rest.trim() ? { cm, line: at.line, text: indent } : null;
}

type OpenLineAction = (this: unknown, cm: CM, args: { after?: boolean }, vim: VimState) => void;

/**
 * Family 2 (:help O): 3Oz repeats the insert by typing a line break and the text again at
 * the end of the insert, so the copies go below the first one and the cursor ends on the
 * last. codemirror-vim reopened a line above each time. installVimFixes() (vimfixes.ts)
 * wraps the newLineAndEnterInsertMode action with this.
 */
export function countedOpenAbove(orig: OpenLineAction): OpenLineAction {
  return function (cm, args, vim) {
    if (vim.insertMode && args.after === false) return breakLine(cm); // a repeat: already inserting
    return orig.call(this, cm, args, vim);
  };
}

/** Family 2: Insert/Replace-mode <CR>, recorded as a key so . and @ re-indent like Vim. */
function insertModeNewline(cm: CM): void {
  recordInsertKey(cm, "r4Newline", () => breakLine(cm));
}

/** Keys that re-indent the line they are typed on (Neovim's cinkeys / indentkeys, word triggers left out). */
const ELECTRIC_KEYS = ["{", "}", ")", "]", "#", ":"];
/** The line a blank was last typed on in this insert (trackKey sets it, resolveInsertEntry clears it). */
let blankTypedOn: { cm: CM; line: number } | null = null;

/**
 * Family 2 (:help cinkeys, indentkeys): type `ch` (over a character in Replace mode), then
 * re-indent the line where Neovim would: { } ) ] or (C++, javascript) # typed as the line's
 * first character, and : after a case / default / access specifier / label (C++,
 * javascript) or any : (python's <:>). Installed as an Insert-mode action and as a key . and @ replay.
 */
function typeElectric(cm: CM, ch: string): void {
  if (cm.cm6.state.selection.ranges.length > 1) return cm.replaceSelection(ch); // a block insert: no re-indent
  typeInsertChar(cm, ch);
  const lang = langOf(cm);
  const cur = cm.getCursor();
  const text = cm.getLine(cur.line);
  const before = text.slice(0, cur.ch).trim();
  // "0}": only when } is the first character typed on the line (typed blanks before it count).
  const first = before === ch && ch !== ":" && !(blankTypedOn?.cm === cm && blankTypedOn.line === cur.line);
  // A case / label / access specifier; for "::" Vim tests the line with the second : as a blank (in_cinkeys).
  const label = (s: string) => /^(?:case\b.*|[A-Za-z_]\w*\s*):$/.test(s);
  // typescript's indentkeys have no : or #; javascript keeps the default ones, as C++'s cinkeys.
  const go = lang === "python" ? ch === ":" || (first && ch !== "#")
    : lang === "typescript" ? first && ch !== "#"
    : (lang === "cpp" || lang === "javascript") && (first || (ch === ":" && (label(before) || (before.endsWith("::") && label(before.slice(0, -1).trimEnd())))));
  if (!go) return;
  const lines = cm.cm6.state.doc.toString().split("\n");
  const cols = langIndent(lang, lines, cur.line, indentWidth(text));
  const lead = /^\s*/.exec(text)![0];
  if (cols < 0 || lead === " ".repeat(cols)) return;
  cm.replaceRange(" ".repeat(cols), { line: cur.line, ch: 0 }, { line: cur.line, ch: lead.length });
  cm.setCursor({ line: cur.line, ch: cur.ch - lead.length + cols });
}

/**
 * Run an Insert-mode edit and record it as InsertModeKey(name) instead of the text it
 * changed, so `.` and macros replay the edit (codemirror-vim replays keys through
 * CodeMirror.keys[name], which install() points at the same function).
 */
function recordInsertKey(cm: CM, name: string, edit: () => void): void {
  const g = api.getVimGlobalState_().macroModeState;
  if (g.isPlaying) return edit();
  const last = g.lastInsertModeChanges;
  if (last.maybeReset) {
    last.changes = [];
    last.maybeReset = false;
  }
  last.ignoreCount = 2; // codemirror-vim's change listener then skips this edit's text
  const before = cm.curOp?.lastChange;
  edit();
  // The listener reads the key's changes when its operation ends: skip all this edit made.
  let made = 0;
  for (let c = before ? before.next : cm.curOp?.change; c; c = c.next) made++;
  if (cm.curOp) last.ignoreCount = made + 1;
  last.changes.push(new api.InsertModeKey(name, { key: "" }));
}

// ---------------------------------------------------------------- family 3: <C-w>

/** Where the current Insert/Replace session started, and the line's text before Replace. */
let insertStart: { cm: CM; at: P; replaced: string | null } | null = null;

/**
 * Family 3 (:help i_CTRL-W): delete the white space and then the word (one character
 * class, as `b` sees it) before the cursor. It stops first at the insert start, joins
 * with the previous line at column 0, and in Replace mode restores replaced characters
 * and only moves over the ones before the insert start.
 */
function insertCtrlW(cm: CM): void {
  resolveInsertEntry(cm);
  const cur = cm.getCursor();
  const start = insertStart?.cm === cm ? insertStart : null;
  if (cur.ch === 0) {
    if (cur.line > 0 && !start?.replaced) cm.replaceRange("", { line: cur.line - 1, ch: cm.getLine(cur.line - 1).length }, cur);
    return;
  }
  const text = cm.getLine(cur.line);
  const stop = start && start.at.line === cur.line && start.at.ch < cur.ch ? start.at.ch : 0;
  const cls = (c: string) => (/\s/.test(c) ? 0 : /\w/.test(c) ? 1 : 2);
  let i = cur.ch;
  while (i > stop && cls(text[i - 1]) === 0) i--;
  const word = i > stop ? cls(text[i - 1]) : -1;
  while (i > stop && cls(text[i - 1]) === word) i--;
  const from = { line: cur.line, ch: i };
  if (start?.replaced != null && start.at.line === cur.line) {
    const keep = Math.max(i, start.at.ch); // replaced characters come back, the rest is skipped
    const orig = start.replaced.slice(keep, cur.ch);
    if (keep < cur.ch) cm.replaceRange(orig, { line: cur.line, ch: keep }, cur);
  } else {
    cm.replaceRange("", from, cur);
  }
  cm.setCursor(from);
  if (start && start.at.line === cur.line && i < start.at.ch) start.at = { ...from };
}

/** Insert-mode <C-w> through recordInsertKey(), so . and @ replay it; it starts a new undo step. */
function insertModeCtrlW(cm: CM): void {
  markUndoStep(cm);
  recordInsertKey(cm, "r4CtrlW", () => insertCtrlW(cm));
}

// ---------------------------------------------------------------- family 6: undo steps

/** Where the current undo step started: the history depth before its first change. */
let undoStep: { cm: CM; depth: number; isolate: boolean } | null = null;

/** Start a new undo step at the next change of `cm`; trackKey calls it per command, <C-w> and arrow key. */
function markUndoStep(cm: CM): void {
  // Inside :normal every change joins the ex command's single step (:help undo-blocks).
  undoStep = { cm, depth: undoDepth(cm.cm6.state), isolate: replay.normal === 0 };
}

/**
 * Family 6 (:help undo-blocks): in Insert mode, the first change of a step is kept apart
 * from the change before it, and every later change joins it, however long the typing
 * takes and wherever <CR>, o or <C-w> moved the cursor. CodeMirror's history joins only
 * quick, adjacent edits with no cursor move between them, but always joins a change
 * tagged "input.type.compose". Added next to history() by editor.ts.
 */
export const insertUndoSteps = EditorState.transactionExtender.of((tr) => {
  const s = undoStep;
  if (!s || !tr.docChanged || s.cm.cm6.state !== tr.startState || !s.cm.state.vim?.insertMode) return null;
  if (tr.isUserEvent("undo") || tr.isUserEvent("redo")) return null;
  if (undoDepth(tr.startState) <= s.depth) return s.isolate ? { annotations: isolateHistory.of("before") } : null;
  // The transaction's own userEvent comes first and wins, so retag it (as codemirror-vim's dispatchChange does).
  const notes = (tr as unknown as { annotations: { type: unknown; value: unknown }[] }).annotations;
  const note = notes.find((a) => a.type === Transaction.userEvent);
  if (!note) return { annotations: Transaction.userEvent.of("input.type.compose") };
  note.value = "input.type.compose";
  return null;
});

// ---------------------------------------------------------------- per-editor tracking

const attached = new WeakSet<object>();

/** Listen to one editor's mode changes once (first key it receives). */
function attachEditor(cm: CM): void {
  if (attached.has(cm)) return;
  attached.add(cm);
  cm.on("vim-mode-change", (e) => onModeChange(cm, e.mode));
}

/** Insert or Replace mode was just entered; resolved once the cursor is in place. */
let entering: { cm: CM; mode: string } | null = null;

/** Insert entered: note it (codemirror-vim signals before it places the cursor). Normal: drop an unused indent. */
function onModeChange(cm: CM, mode: string): void {
  if (mode === "insert" || mode === "replace") {
    entering = { cm, mode };
  } else if (mode === "normal") {
    resolveInsertEntry(cm);
    if (insertStart?.cm === cm) lastInsertStop.set(cm, insertCursor ?? cm.getCursor());
    insertStart = null;
    if (pendingIndent?.cm === cm) {
      const line = pendingIndent.line;
      dropUnusedIndent(cm, line);
      if (cm.getLine(line) === "") cm.setCursor({ line, ch: 0 });
    }
  }
}

/**
 * Called after the key that entered Insert mode, and before the first edit or <C-w> in
 * it (whichever comes first, so `.` and macro replays are covered): remember the insert
 * start, and the indent of a line that S / cc emptied.
 */
function resolveInsertEntry(cm: CM): void {
  if (!entering || entering.cm !== cm) return;
  const { mode } = entering;
  entering = null;
  const cur = cm.getCursor();
  const text = cm.getLine(cur.line);
  insertStart = { cm, at: cur, replaced: mode === "replace" ? text : null };
  insertCursor = cur;
  blankTypedOn = null;
  const ed = cm.state.vim?.lastEditInputState;
  const changeLine = /^(?:"[\s\S])?\d*(?:S|c\d*c)$/.test(currentKeys) ||
    (currentKeys === "." && ed?.operator === "change" && ed.motion === "expandToLine");
  if (changeLine && /^\s+$/.test(text)) pendingIndent = { cm, line: cur.line, text };
  else if (pendingIndent?.line !== cur.line) pendingIndent = null;
}

/** Resolve a pending Insert-mode entry before any adapter edit (replays edit through these). */
function resolveBeforeEdits(): void {
  const proto = CodeMirror.prototype as unknown as Record<"replaceRange" | "replaceSelection", (...a: unknown[]) => unknown>;
  for (const name of ["replaceRange", "replaceSelection"] as const) {
    const orig = proto[name];
    proto[name] = function (this: CM, ...args: unknown[]) {
      resolveInsertEntry(this);
      const result = orig.apply(this, args);
      if (this.state.vim?.insertMode) insertCursor = this.getCursor();
      return result;
    };
  }
}

/** A key typed in Insert mode means the auto-indent is used (o<Space><Esc> keeps it). */
function noteInsertKey(cm: CM, key: string): void {
  if (key !== "<Esc>" && key !== "<CR>" && !cm.state.vim?.inputState.keyBuffer.length) pendingIndent = null;
}

// ---------------------------------------------------------------- family 5: gi, CTRL-W

/** Cursor in Insert mode as last seen, and where Insert mode was last stopped (the '^ mark). */
let insertCursor: P | null = null;
const lastInsertStop = new WeakMap<object, P>();

/** Family 5 (:help gi): insert where Insert mode last stopped, or at the cursor if it never did; 3gi inserts 3 times. */
function insertAtLastStop(cm: CM, args: { repeat?: number }): void {
  const count = (args.repeat ?? 1) > 1 ? [...String(args.repeat)] : [];
  const p = lastInsertStop.get(cm);
  let key = "i";
  if (p && p.line <= cm.lastLine()) {
    const len = cm.getLine(p.line).length;
    if (len && p.ch >= len) {
      cm.setCursor({ line: p.line, ch: len - 1 });
      key = "a"; // '^ at the end of the line: append
    } else {
      cm.setCursor(p);
    }
  }
  for (const k of [...count, key]) api.handleKey(cm, k, "mapping");
}

/** Set by <C-w> in Normal / Visual mode: the keys after it are a window command, a no-op in one window. */
let windowCommand: { cm: CM; g: boolean } | null = null;

/** Family 5 (:help CTRL-W): <C-w>{char} does nothing here; codemirror-vim ran {char} as a command. */
function startWindowCommand(cm: CM): void {
  windowCommand = { cm, g: false };
}

/** Swallow one key of a window command: a count (<C-w>12j) and g{char} take more keys; guardedHandleKey calls it. */
function windowCommandKey(key: string): void {
  if (/^\d$/.test(key) && !windowCommand!.g) return; // [count]
  if (key === "g" && !windowCommand!.g) windowCommand!.g = true; // g{char}: one more key
  else windowCommand = null;
}

// ---------------------------------------------------------------- family 4: ex

/**
 * Family 4 (:help E16): an ex command that throws "E123: ..." (vimfixes :m / :t on a bad
 * or missing address) has had its message shown by codemirror-vim; the throw itself
 * escaped as a page error and left a stray line break. Stop it at the operation.
 */
function catchExErrors(): void {
  const proto = CodeMirror.prototype as unknown as { operation: (fn: () => unknown, force?: boolean) => unknown };
  const orig = proto.operation;
  proto.operation = function (this: unknown, fn, force) {
    try {
      return orig.call(this, fn, force);
    } catch (e) {
      if (e instanceof Error && /^E\d+: /.test(e.message)) return undefined;
      throw e;
    }
  };
}

/**
 * Family 4 (:help :join): join the range (at least two lines), or {count} lines from the
 * range's last line, with J / gJ; the cursor ends on the first non-blank like Neovim.
 */
function exJoin(cm: CM, params: ExParams & { argString?: string }): void {
  const arg = (params.argString ?? "").trim();
  const bang = arg.startsWith("!");
  const count = Number(/\d+/.exec(arg)?.[0] ?? 0);
  const first = params.line ?? params.selectionLine ?? cm.getCursor().line;
  const lastInRange = params.lineEnd ?? first;
  if (Math.max(first, lastInRange) > cm.lastLine()) return reportError(cm, "E16: Invalid range"); // :.,+3j near the end
  const from = count ? lastInRange : first;
  let n = count ? count : Math.max(2, lastInRange - first + 1);
  n = Math.min(n, cm.lastLine() - from + 1);
  if (n < 2) return;
  cm.setCursor({ line: from, ch: 0 });
  const vim = cm.state.vim!;
  const dot = [vim.lastEditActionCommand, vim.lastEditInputState] as const; // an ex command is not repeated by `.`
  for (const key of [...String(n), ...(bang ? ["g", "J"] : ["J"])]) api.handleKey(cm, key, "mapping");
  [vim.lastEditActionCommand, vim.lastEditInputState] = dot;
  const text = cm.getLine(from);
  cm.setCursor({ line: from, ch: Math.max(0, text.search(/\S|$/)) });
}

// ---------------------------------------------------------------- install

let installed = false;

/** Install every fix in this module once; called by installVimFixes() in vimfixes.ts. */
export function installMacroIndentFixes(): void {
  if (installed) return;
  installed = true;
  const v = Vim as unknown as VimApi & {
    defineAction(name: string, fn: unknown): void;
    defineEx(name: string, prefix: string, fn: unknown): void;
    defineMotion(name: string, fn: unknown): void;
    _mapCommand(command: object): void;
  };
  v.handleKey = guardedHandleKey(v.handleKey);
  countErrorMessages();
  catchExErrors();
  resolveBeforeEdits();
  v.defineEx("normal", "norm", exNormal);
  v.defineEx("join", "j", exJoin);
  const keys = CodeMirror.keys as Record<string, (cm: CM) => void>;
  keys.r4Newline = (cm) => breakLine(cm);
  keys.r4CtrlW = insertCtrlW;
  v.defineAction("r4Electric", (cm: CM, args: { ch: string }) => recordInsertKey(cm, `r4Electric${args.ch}`, () => typeElectric(cm, args.ch)));
  for (const ch of ELECTRIC_KEYS) {
    keys[`r4Electric${ch}`] = (cm) => typeElectric(cm, ch);
    v._mapCommand({ keys: ch, type: "action", action: "r4Electric", actionArgs: { ch }, context: "insert" });
  }
  const commands = CodeMirror.commands as unknown as Record<string, (cm: CM) => void>;
  commands.newlineAndIndent = (cm) => breakLine(cm, true); // o, O and r<CR> call it
  v.defineAction("r4InsertNewline", insertModeNewline);
  v.defineAction("r4InsertCtrlW", insertModeCtrlW);
  v._mapCommand({ keys: "<CR>", type: "action", action: "r4InsertNewline", context: "insert" });
  v._mapCommand({ keys: "<C-w>", type: "action", action: "r4InsertCtrlW", context: "insert" });
  v._mapCommand({ keys: "<C-j>", type: "keyToKey", toKeys: "j" }); // <NL> is j (:help <NL>)
  v._mapCommand({ keys: "<C-j>", type: "action", action: "r4InsertNewline", context: "insert" }); // i_<NL> is <CR>
  v.defineMotion("r4SpaceRight", spaceRight);
  v.defineMotion("r4BackspaceLeft", backspaceLeft);
  for (const context of ["normal", "visual", "operatorPending"]) {
    v._mapCommand({ keys: "<Space>", type: "motion", motion: "r4SpaceRight", context });
    for (const keys of ["<BS>", "<C-h>"]) v._mapCommand({ keys, type: "motion", motion: "r4BackspaceLeft", context });
  }
  v.defineAction("r4InsertAtLastStop", insertAtLastStop);
  v._mapCommand({ keys: "gi", type: "action", action: "r4InsertAtLastStop", context: "normal" });
  v.defineAction("r4WindowCommand", startWindowCommand);
  v._mapCommand({ keys: "<C-w>", type: "action", action: "r4WindowCommand", context: "normal" });
  v._mapCommand({ keys: "<C-w>", type: "action", action: "r4WindowCommand", context: "visual" });
}
