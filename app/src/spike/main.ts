import { EditorState } from "@codemirror/state";
import { EditorView, lineNumbers, drawSelection } from "@codemirror/view";
import { indentUnit } from "@codemirror/language";
import { history } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { vim, getCM, Vim } from "@replit/codemirror-vim";
import { attachRecorder, recorderExtension, type LogEvent } from "./keylogger";

const BUFFER = `def fetch(url, attempts=3):
    for i in range(attempts):
        try:
            return get(url)
        except Timeout:
            logger.warn("timeout, trying again")
            sleep(2 ** i)
    raise GiveUp(url)
`;

// No basicSetup: closeBrackets, autocompletion and bracket auto-indent would
// make insert mode diverge from nvim --clean, which is the par oracle.
const view = new EditorView({
  parent: document.getElementById("editor")!,
  state: EditorState.create({
    doc: BUFFER,
    extensions: [
      vim(), // must come first so its keymap has precedence
      history(), // without it `u` is a silent no-op
      lineNumbers(),
      drawSelection(),
      python(),
      EditorState.tabSize.of(4),
      indentUnit.of("    "),
      recorderExtension,
    ],
  }),
});

// Vim regex semantics for :s and /, not JavaScript's (default is pcre=true).
Vim.setOption("pcre", false);

// Start on line 6, column 0 (inside the indent, before logger).
view.dispatch({ selection: { anchor: view.state.doc.line(6).from } });
view.focus();

const recorder = attachRecorder(view, document.getElementById("editor")!);

const logEl = document.getElementById("log")!;
const modeEl = document.getElementById("mode")!;
const keysEl = document.getElementById("keys")!;

function fmt(e: LogEvent): string {
  const t = e.active.toFixed(1).padStart(8);
  switch (e.type) {
    case "key": return `${t}  key   ${e.key}${e.cmdline ? "  (cmdline)" : ""}  [${e.mode}]`;
    case "mode": return `${t}  mode  ${e.from} -> ${e.to}`;
    case "mode-signal": return `${t}  raw   vim-mode-change ${e.mode}${e.subMode ? "/" + e.subMode : ""}`;
    case "command-done": return `${t}  DONE  after key #${e.keyIndex} via ${e.source}  cursor ${e.cursor.line}:${e.cursor.ch}${e.docChanged ? "  doc changed" : ""}`;
    case "cmdline": return `${t}  cmdl  ${e.open ? "open" : "close"}`;
    case "focus-lost": return `${t}  FOCUS LOST after ${e.after}`;
    case "clock": return `${t}  clock ${e.running ? "resumed" : "paused (tab hidden)"}`;
    case "raw-signal": return `${t}  raw   ${e.name} ${e.detail}`;
  }
}

recorder.onEvent((e) => {
  const line = document.createElement("div");
  line.textContent = fmt(e);
  line.className = e.type === "key" ? "key" : e.type === "command-done" ? "done" : e.type === "mode" ? "mode" : "";
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
  modeEl.textContent = recorder.mode().toUpperCase().replace("-", " ");
  keysEl.textContent = recorder.keys().join("");
});

// Handle for Playwright (src/spike/verify.mjs).
declare global {
  interface Window { spike: unknown }
}
window.spike = { view, cm: getCM(view), Vim, recorder };
