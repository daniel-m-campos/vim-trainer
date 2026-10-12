// The practice editor: CodeMirror 6 + codemirror-vim configured to match the
// par oracle (nvim --clean with expandtab, sw=4, ts=4; see content/oracle.lua).
// No basicSetup: closeBrackets / autocompletion / indent-on-input would make
// insert mode diverge from the oracle. A fresh view is built per exercise so
// marks, registers and undo history never leak between exercises.

import { EditorState, Compartment, StateField, RangeSetBuilder, type Extension } from "@codemirror/state";
import { EditorView, Decoration, type DecorationSet, drawSelection, gutter, GutterMarker, lineNumbers } from "@codemirror/view";
import { indentUnit, syntaxHighlighting, HighlightStyle } from "@codemirror/language";
import { history } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { tags as t } from "@lezer/highlight";
import { vim, Vim, getCM } from "@replit/codemirror-vim";
import { attachRecorder, recorderExtension, type Recorder } from "./recorder.ts";
import { targetRanges } from "./grading.ts";
import { caseSensitiveSearch, installVimFixes } from "./vimfixes.ts";
import type { EscapePref, Exercise } from "./types.ts";

// Mock palette (docs/mocks/practice-screen.html).
const highlight = HighlightStyle.define([
  { tag: [t.keyword, t.controlKeyword, t.definitionKeyword, t.moduleKeyword, t.operatorKeyword, t.bool, t.null, t.self], color: "#c792ea" },
  { tag: [t.function(t.variableName), t.function(t.propertyName), t.function(t.definition(t.variableName))], color: "#82aaff" },
  { tag: [t.string, t.special(t.string)], color: "#c3e88d" },
  { tag: [t.number], color: "#f78c6c" },
  { tag: [t.comment, t.lineComment], color: "#7d8794", fontStyle: "italic" },
]);

const theme = EditorView.theme(
  {
    "&": { backgroundColor: "transparent", color: "var(--fg)", fontSize: "14.5px" },
    ".cm-scroller": { fontFamily: "var(--mono)", lineHeight: "1.6", padding: "14px 0" },
    ".cm-content": { caretColor: "var(--fg)" },
    ".cm-gutters": { backgroundColor: "transparent", border: "none", color: "var(--muted)" },
    ".cm-lineNumbers .cm-gutterElement, .cm-relnums .cm-gutterElement": {
      minWidth: "3.2em", textAlign: "right", paddingRight: "1.2em", fontVariantNumeric: "tabular-nums",
    },
    ".cm-activeLineGutter": { color: "var(--fg)" },
    ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": { backgroundColor: "rgba(111,179,201,.28) !important" },
    ".cm-panels": { backgroundColor: "var(--panel)", color: "var(--fg)", borderTop: "1px solid var(--rule)" },
    ".cm-vim-panel input": { color: "var(--fg)", fontFamily: "var(--mono)" },
  },
  { dark: true },
);

// --- relative line numbers (current line shows its absolute number, like nu+rnu) --
class NumMarker extends GutterMarker {
  constructor(readonly text: string, readonly cur: boolean) { super(); }
  eq(o: NumMarker) { return o.text === this.text && o.cur === this.cur; }
  toDOM() {
    const el = document.createElement("span");
    el.textContent = this.text;
    if (this.cur) el.className = "cur";
    return el;
  }
}

const relativeNumbers = gutter({
  class: "cm-relnums",
  lineMarker(view, line) {
    const doc = view.state.doc;
    const cur = doc.lineAt(view.state.selection.main.head).number;
    const n = doc.lineAt(line.from).number;
    return new NumMarker(n === cur ? String(n) : String(Math.abs(n - cur)), n === cur);
  },
  lineMarkerChange: (u) => u.selectionSet || u.docChanged,
  initialSpacer: () => new NumMarker("999", false),
});

// --- target highlight: tint + underline (shape, not colour alone) ---------------
const targetMark = Decoration.mark({ class: "cm-target" });

function targetField(ranges: { from: number; to: number }[]): Extension {
  return StateField.define<DecorationSet>({
    create(state) {
      const b = new RangeSetBuilder<Decoration>();
      const len = state.doc.length;
      let last = -1; // RangeSetBuilder needs sorted, non-decreasing starts
      for (const { from, to } of [...ranges].sort((x, y) => x.from - y.from)) {
        if (to > from && from < len && from >= last) {
          b.add(from, Math.min(to, len), targetMark);
          last = from;
        }
      }
      return b.finish();
    },
    update(deco, tr) {
      return deco.map(tr.changes);
    },
    provide: (f) => EditorView.decorations.from(f),
  });
}

function langExt(lang: string): Extension {
  switch (lang) {
    case "python":
      return python();
    default:
      return []; // TODO(mvp): grammars for cpp / typescript when their content exists.
  }
}

let globalsApplied: EscapePref | null = null;

/** Reset Vim's global state (registers, last search, f/t, macros) like the oracle does per exercise. */
function resetVimGlobals(escape: EscapePref): void {
  installVimFixes(); // once: Neovim behaviour the pars rely on (see vimfixes.ts)
  Vim.resetVimGlobalState_(); // also resets options to defaults
  Vim.setOption("pcre", false); // Vim regex semantics for :s and /
  caseSensitiveSearch(); // nvim --clean: noignorecase
  if (globalsApplied !== escape) {
    try {
      Vim.unmap("jk", "insert");
    } catch {
      /* not mapped */
    }
    if (escape === "jk") Vim.map("jk", "<Esc>", "insert");
    globalsApplied = escape;
  }
}

export interface EditorHandle {
  view: EditorView;
  recorder: Recorder;
  /** Lock the editor (result strip showing): not focusable, no edits. */
  setLocked(locked: boolean): void;
  destroy(): void;
}

export function mountEditor(parent: HTMLElement, ex: Exercise, opts: { relativeNumbers: boolean; escape: EscapePref }): EditorHandle {
  resetVimGlobals(opts.escape);
  const doc = ex.start.lines.join("\n");
  const [line, col] = ex.start.cursor;
  const lineCount = ex.start.lines.length;
  const l = Math.min(Math.max(line, 1), lineCount);
  let anchor = 0;
  for (let i = 0; i < l - 1; i++) anchor += ex.start.lines[i].length + 1;
  anchor += Math.min(col, Math.max(0, ex.start.lines[l - 1].length - 1));

  const ranges = targetRanges(ex);
  const editable = new Compartment();
  const state = EditorState.create({
    doc,
    selection: { anchor },
    extensions: [
      vim(), // first, so its keymap has precedence
      history(), // without it `u` is a silent no-op
      opts.relativeNumbers ? relativeNumbers : lineNumbers(),
      drawSelection(),
      langExt(ex.lang),
      syntaxHighlighting(highlight),
      EditorState.tabSize.of(4),
      indentUnit.of("    "),
      theme,
      ranges.length ? targetField(ranges) : [],
      editable.of([]),
      recorderExtension,
    ],
  });
  parent.replaceChildren();
  const view = new EditorView({ state, parent });
  // The cursor line must be visible; buffers are short so this is cheap.
  view.dispatch({ effects: EditorView.scrollIntoView(anchor, { y: "center" }) });
  const recorder = attachRecorder(view, parent);
  getCM(view); // ensure the vim adapter exists before the first key
  view.focus();

  return {
    view,
    recorder,
    setLocked(locked) {
      view.dispatch({ effects: editable.reconfigure(locked ? [EditorView.editable.of(false), EditorState.readOnly.of(true)] : []) });
      if (locked) view.contentDOM.blur();
      else view.focus();
    },
    destroy() {
      recorder.destroy();
      view.destroy();
    },
  };
}
