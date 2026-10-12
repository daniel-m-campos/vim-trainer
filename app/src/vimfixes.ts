// Where codemirror-vim differs from Neovim on commands the shipped pars use, found by
// e2e/emulator.mjs (every build/ par replayed in the browser). Installed once, through
// the public Vim API (defineOperator / defineEx), so the vendored package is untouched.
//
// 1. `d}` / `d)` whose motion ends in column 0 must follow :help exclusive-linewise:
//    if the start is at or before the first non-blank the delete is linewise.
//    codemirror-vim moves the end back a line but stays charwise, leaving the
//    indentation behind as a whitespace-only line.
// 2. A linewise delete that reaches the last line (`dG`, `d2j` at the end) must remove
//    the line break before the range; codemirror-vim only special-cases `dd`, so it
//    leaves an empty last line.
// 3. `:move` / `:m`, `:copy` / `:co` / `:t` do not exist in codemirror-vim. Its ex
//    parser also reads `:m8` as a command named "m8", so a space is inserted between
//    those command names and a numeric address when the command line is submitted.
//
// 4. Searches, :s and :g are hard-coded to ignorecase + smartcase in codemirror-vim
//    (and * / # to ignorecase); the oracle runs `nvim --clean`, which is case-sensitive.
//    caseSensitiveSearch() strips the `i` flag from every stored query.
//
// 5. `i(` `i[` `i{` `i<` (and `ib` `iB`) after an operator follow Vim's current_block():
//    when the opening bracket is the last character of its line the object starts on the
//    next line, and when the closing bracket has only blanks before it the object stops
//    at the end of the previous line. Both together make it linewise, so `di{` on a
//    multi-line dict leaves `{` and `}` on their own lines and `>i{` indents only the
//    body. codemirror-vim takes the brackets' inner text as is (joining the lines).
//    Visual mode (`vi{`) keeps codemirror-vim's behaviour: TODO(mvp) if a par needs it.
//
// TODO(mvp): the same exclusive-linewise rule applies to c, y, gU, > and the other
// operators and to every exclusive motion (searches, `w` aside); only `d` with `}` / `)`
// is patched because only those pars hit it in the current content.

import { Vim } from "@replit/codemirror-vim";

interface P {
  line: number;
  ch: number;
}
interface Range {
  anchor: P;
  head: P;
}
// The CodeMirror 5 style adapter codemirror-vim passes to operators and ex commands.
interface CM {
  state: { vim: { visualMode?: boolean; visualBlock?: boolean } };
  firstLine(): number;
  lastLine(): number;
  getLine(n: number): string;
  getRange(a: P, b: P): string;
  getSelection(): string;
  replaceRange(text: string, from: P, to?: P): void;
  replaceSelections(texts: string[]): void;
  getCursor(): P;
  setCursor(p: P): void;
}
interface MotionArgs {
  selectedCharacter?: string;
  linewise?: boolean;
}
interface VimState {
  inputState: { operatorArgs?: OperatorArgs | null };
}
interface ScanCM extends CM {
  scanForBracket(from: P, dir: 1 | -1, style?: unknown, config?: { bracketRegex: RegExp }): { pos: P } | null | undefined;
}
interface OperatorArgs {
  linewise?: boolean;
  registerName?: string;
}
interface ExParams {
  line?: number;
  lineEnd?: number;
  argString?: string;
}

const firstNonBlank = (text: string): number => {
  const i = text.search(/\S/);
  return i < 0 ? text.length : i;
};

function clip(cm: CM, p: P): P {
  const line = Math.min(Math.max(cm.firstLine(), p.line), cm.lastLine());
  const len = cm.getLine(line).length;
  return { line, ch: Math.min(Math.max(0, p.ch), Math.max(0, len - 1)) };
}

// Last key pressed in an editor, recorded before codemirror-vim sees it, so the delete
// operator knows which motion it is running for (the operator API does not say).
let lastKey = "";
// Exclusive forward motions that the exclusive-linewise rule is applied to. Not `w`:
// Vim's `dw` special case keeps the end on the last word of the line.
const PARAGRAPH_KEYS = new Set(["}", ")"]);

function deleteOperator(cm: CM, args: OperatorArgs, ranges: Range[], oldAnchor?: P, newHead?: P): P {
  const vim = cm.state.vim;
  let text: string;
  let finalHead: P;
  let linewise = !!args.linewise;
  if (!vim.visualBlock) {
    let anchor = { ...ranges[0].anchor };
    let head = { ...ranges[0].head };
    // Fix 1: the motion ended in column 0 of a later line (codemirror-vim's clipToLine
    // has already moved the end to the previous line's end); start at or before the
    // first non-blank makes the delete linewise.
    if (
      !linewise && !vim.visualMode && PARAGRAPH_KEYS.has(lastKey) && oldAnchor && newHead &&
      newHead.ch === 0 && newHead.line > oldAnchor.line && anchor.ch <= firstNonBlank(cm.getLine(anchor.line))
    ) {
      linewise = true;
      anchor = { line: anchor.line, ch: 0 };
      head = { line: newHead.line, ch: 0 }; // lines anchor..newHead-1 with their line breaks
    }
    if (linewise && head.line > cm.lastLine()) {
      // Fix 2 (also covers the original dd-on-the-last-line case).
      if (anchor.line > cm.firstLine()) anchor = { line: anchor.line - 1, ch: cm.getLine(anchor.line - 1).length };
      else anchor = { line: anchor.line, ch: 0 };
    }
    text = cm.getRange(anchor, head);
    cm.replaceRange("", anchor, head);
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

const BLOCKS: Record<string, [string, string]> = {
  "(": ["(", ")"], ")": ["(", ")"], b: ["(", ")"],
  "[": ["[", "]"], "]": ["[", "]"],
  "{": ["{", "}"], "}": ["{", "}"], B: ["{", "}"],
  "<": ["<", ">"], ">": ["<", ">"],
};

/** Fix 5: the inner block object as Vim's current_block() cuts it (operator-pending only). */
function innerBlock(cm: ScanCM, head: P, motionArgs: MotionArgs, vim: VimState): [P, P] | null {
  const pair = BLOCKS[motionArgs.selectedCharacter ?? ""];
  if (!pair) return null;
  const [open, close] = pair;
  const re = new RegExp(`[\\${open}\\${close}]`);
  const from = { line: head.line, ch: head.ch + (cm.getLine(head.line).charAt(head.ch) === open ? 1 : 0) };
  const a = cm.scanForBracket(from, -1, undefined, { bracketRegex: re });
  const b = cm.scanForBracket(from, 1, undefined, { bracketRegex: re });
  if (!a || !b) return null;
  let [o, c] = [a.pos, b.pos];
  if (o.line > c.line || (o.line === c.line && o.ch > c.ch)) [o, c] = [c, o];
  const openAtEol = o.ch + 1 >= cm.getLine(o.line).length;
  const start: P = openAtEol && c.line > o.line ? { line: o.line + 1, ch: 0 } : { line: o.line, ch: o.ch + 1 };
  const closeAtSol = c.line > o.line && /^\s*$/.test(cm.getLine(c.line).slice(0, c.ch));
  if (!closeAtSol) return [start, c];
  if (c.line - 1 < start.line) return [start, start]; // `{` and `}` on adjacent lines: nothing inside
  if (openAtEol) {
    motionArgs.linewise = true;
    if (vim.inputState.operatorArgs) vim.inputState.operatorArgs.linewise = true;
    return [start, { line: c.line - 1, ch: 0 }];
  }
  return [start, { line: c.line - 1, ch: cm.getLine(c.line - 1).length }];
}

/** An ex address as the 1-based line after which to put text (0 = above line 1). */
function parseAddress(cm: CM, raw: string | undefined): number {
  const s = (raw ?? "").trim();
  const m = /^(\d+|\.|\$)?((?:\s*[+-]\s*\d*)*)$/.exec(s);
  if (!s || !m) throw new Error(`E14: Invalid address`);
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

function allLines(cm: CM): string[] {
  const out: string[] = [];
  for (let i = cm.firstLine(); i <= cm.lastLine(); i++) out.push(cm.getLine(i));
  return out;
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

/** `:m8` -> `:m 8`, `:t.` -> `:t .` (codemirror-vim reads \w+ as the command name). */
export function spaceExAddress(input: string): string {
  return input.replace(/^(\s*:*(?:[^a-zA-Z']|'[a-zA-Z<>])*?)(move|mov|mo|m|copy|cop|co|t)(?=[\d.$+-])/, "$1$2 ");
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

let installed = false;

export function installVimFixes(): void {
  if (installed) return;
  installed = true;
  Vim.defineOperator("delete", deleteOperator as never);
  Vim.defineMotion("innerBlockVim", innerBlock as never);
  for (const ch of Object.keys(BLOCKS)) {
    // Unshifted onto the keymap, so it wins over the built-in `i<register>` entry.
    Vim._mapCommand({ keys: `i${ch}`, type: "motion", motion: "innerBlockVim", motionArgs: { textObjectInner: true, selectedCharacter: ch }, context: "operatorPending" } as never);
  }
  // Names differ from the built-in "move" (the bare `:15` line jump), which must stay.
  Vim.defineEx("movelines", "m", exMove as never);
  Vim.defineEx("copylines", "co", exCopy as never);
  Vim.defineEx("t", "t", exCopy as never);
  document.addEventListener(
    "keydown",
    (e) => {
      const t = e.target as HTMLInputElement | null;
      if (t?.closest?.(".cm-content")) lastKey = e.key;
      if (e.key === "Enter" && t?.tagName === "INPUT" && t.closest(".cm-vim-panel")) t.value = spaceExAddress(t.value);
    },
    true,
  );
}
