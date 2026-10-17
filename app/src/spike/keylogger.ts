// Spike: attempt recorder on top of CodeMirror 6 + @replit/codemirror-vim.
//
// Throwaway code. It exists to find out which codemirror-vim hooks are usable
// for grading (docs/design/grading.md). Findings are in ./README.md.
//
// Design under test:
//   keys          capture-phase `keydown` on a wrapper element around the
//                 editor, normalised with Vim.vimKeyFromEvent (the same
//                 function the emulator uses), so the log always agrees with
//                 what Vim saw. Covers normal, insert, visual and the ":" / "/"
//                 command-line <input>, which lives inside the editor DOM.
//   mode          derived from vim state after every key/signal; the
//                 "vim-mode-change" signal is recorded too, only for comparison.
//   command done  "vim-command-done" signal OR a CM6 doc/selection update OR
//                 the command-line <input> losing focus, coalesced in a
//                 microtask, then filtered: not in insert mode,
//                 no pending keys/operator, no open command line, and buffer
//                 or cursor actually changed since the last command-done.
//   clock         performance.now(), paused while document.hidden.
//   browser keys  <Esc> and <Tab> that Vim leaves unhandled are prevented so
//                 they never blur the editor.

import { EditorView, type ViewUpdate } from "@codemirror/view";
import type { Extension, Text } from "@codemirror/state";
import { insertTab } from "@codemirror/commands";
import { Vim, getCM } from "@replit/codemirror-vim";

export type Mode = "normal" | "insert" | "replace" | "visual" | "visual-line" | "visual-block";

export interface Cursor {
  line: number; // 0-based
  ch: number; // 0-based
}

export type LogEvent =
  | { type: "key"; t: number; active: number; key: string; mode: Mode; cmdline: boolean; repeat: boolean }
  | { type: "mode"; t: number; active: number; from: Mode; to: Mode }
  | { type: "mode-signal"; t: number; active: number; mode: string; subMode?: string }
  | { type: "command-done"; t: number; active: number; keyIndex: number; source: string; doc: string; cursor: Cursor; docChanged: boolean }
  | { type: "cmdline"; t: number; active: number; open: boolean }
  | { type: "focus-lost"; t: number; active: number; after: string }
  | { type: "clock"; t: number; active: number; running: boolean }
  | { type: "raw-signal"; t: number; active: number; name: string; detail: string };

/** Minimal view of the CM5-style adapter object that codemirror-vim exposes. */
interface VimState {
  insertMode: boolean;
  visualMode: boolean;
  visualLine: boolean;
  visualBlock: boolean;
  inputState: { keyBuffer: string[]; operator?: string | null; prefixRepeat: string[]; motionRepeat: string[] };
}
interface CMAdapter {
  state: { vim?: VimState | null; overwrite?: boolean };
  on(type: string, f: (...args: any[]) => void): void;
  getCursor(which?: string): Cursor;
}

/** Wall clock that stops while the tab is hidden. */
export class ActiveClock {
  private startedAt = 0;
  private pausedTotal = 0;
  private pausedAt: number | null = null;

  constructor(private onChange: (running: boolean) => void = () => {}) {
    document.addEventListener("visibilitychange", () => this.sync());
  }

  start(): void {
    this.startedAt = performance.now();
    this.pausedTotal = 0;
    this.pausedAt = document.visibilityState === "hidden" ? this.startedAt : null;
  }

  /** Milliseconds of visible time since start(). */
  active(at = performance.now()): number {
    const pausedNow = this.pausedAt === null ? 0 : at - this.pausedAt;
    return at - this.startedAt - this.pausedTotal - pausedNow;
  }

  private sync(): void {
    const now = performance.now();
    if (document.visibilityState === "hidden" && this.pausedAt === null) {
      this.pausedAt = now;
      this.onChange(false);
    } else if (document.visibilityState !== "hidden" && this.pausedAt !== null) {
      this.pausedTotal += now - this.pausedAt;
      this.pausedAt = null;
      this.onChange(true);
    }
  }
}

function modeFromState(cm: CMAdapter): Mode {
  const vim = cm.state.vim;
  if (!vim) return "normal";
  if (vim.insertMode) return cm.state.overwrite ? "replace" : "insert";
  if (vim.visualMode) return vim.visualBlock ? "visual-block" : vim.visualLine ? "visual-line" : "visual";
  return "normal";
}

/** True while Vim is in the middle of a command (after `c`, `ci`, `3`, `"a`, ...). */
function commandPending(cm: CMAdapter): boolean {
  const s = cm.state.vim?.inputState;
  if (!s) return false;
  return s.keyBuffer.length > 0 || !!s.operator || s.prefixRepeat.length > 0 || s.motionRepeat.length > 0;
}

const updateSinks = new WeakMap<EditorView, (u: ViewUpdate) => void>();

/** Add to the editor's extensions; lets the recorder see CM6 doc/selection updates. */
export const recorderExtension: Extension = EditorView.updateListener.of((u) => updateSinks.get(u.view)?.(u));

export interface Recorder {
  readonly log: LogEvent[];
  readonly mode: () => Mode;
  readonly keys: () => string[];
  /** Restart the clock and clear the log (new attempt). */
  reset(): void;
  onEvent(fn: (e: LogEvent) => void): void;
}

/**
 * Attach the recorder. `wrapper` must contain `view.dom`; the key listener sits
 * on it in the capture phase so it sees every key before CodeMirror or Vim can
 * stopPropagation, including keys typed into the Vim command-line <input>.
 */
export function attachRecorder(view: EditorView, wrapper: HTMLElement): Recorder {
  const cm = getCM(view) as unknown as CMAdapter | null;
  if (!cm) throw new Error("codemirror-vim is not active on this view");

  const log: LogEvent[] = [];
  const listeners: ((e: LogEvent) => void)[] = [];
  const clock = new ActiveClock((running) => push({ type: "clock", ...stamp(), running }));

  let mode: Mode = modeFromState(cm);
  let lastDoc: Text = view.state.doc;
  let lastCursor: Cursor = cm.getCursor("head");
  let checkScheduled = false;
  let checkSources = new Set<string>();

  function stamp() {
    const t = performance.now();
    return { t, active: clock.active(t) };
  }
  function push(e: LogEvent): void {
    log.push(e);
    for (const fn of listeners) fn(e);
  }
  function keyIndex(): number {
    let n = -1;
    for (const e of log) if (e.type === "key") n++;
    return n;
  }

  function cmdlineOpen(): boolean {
    const a = document.activeElement;
    return a instanceof HTMLInputElement && wrapper.contains(a);
  }

  function syncMode(): void {
    const next = modeFromState(cm!);
    if (next !== mode) {
      push({ type: "mode", ...stamp(), from: mode, to: next });
      mode = next;
    }
  }

  function scheduleCheck(source: string): void {
    checkSources.add(source);
    if (checkScheduled) return;
    checkScheduled = true;
    queueMicrotask(() => {
      checkScheduled = false;
      const sources = [...checkSources].sort().join("+");
      checkSources = new Set();
      syncMode();
      if (mode === "insert" || mode === "replace") return; // mid-edit: ci"ret is not done
      if (commandPending(cm!)) return; // operator / count / register pending
      if (cmdlineOpen()) return; // typing a : or / command line
      const doc = view.state.doc;
      const cursor = cm!.getCursor("head");
      const docChanged = !doc.eq(lastDoc);
      const cursorChanged = cursor.line !== lastCursor.line || cursor.ch !== lastCursor.ch;
      if (!docChanged && !cursorChanged) return;
      lastDoc = doc;
      lastCursor = cursor;
      push({
        type: "command-done",
        ...stamp(),
        keyIndex: keyIndex(),
        source: sources,
        doc: doc.toString(),
        cursor,
        docChanged,
      });
    });
  }

  // --- keys -----------------------------------------------------------------
  wrapper.addEventListener(
    "keydown",
    (e) => {
      // IME composition and dead keys: the emulator re-reads these from the
      // text input path; skip here. TODO: log the composed text instead.
      if (e.isComposing || e.keyCode === 229 || e.key === "Process" || e.key === "Unidentified") return;
      const key = Vim.vimKeyFromEvent(e, (cm.state.vim ?? undefined) as any);
      if (!key) return; // bare modifier
      push({
        type: "key",
        ...stamp(),
        key,
        mode,
        cmdline: cmdlineOpen(),
        repeat: e.repeat,
      });
      // No scheduleCheck here: in Chromium/WebKit the microtask checkpoint runs
      // right after this listener, i.e. *before* Vim sees the key. The
      // signal/doc/selection triggers below cover every state change.
    },
    { capture: true },
  );

  // Keys Vim did not consume must not reach browser defaults. Bubble phase, so
  // Vim/CM see the key first (when Vim consumes a key it already called
  // preventDefault + stopPropagation, so this never runs for those).
  //   <Esc> in normal mode: Vim returns "unhandled"; prevent it anyway.
  //   <Tab>: CM6 deliberately leaves Tab to the browser, which moves focus out
  //          of the editor (Chromium, WebKit). Insert a tab in insert mode.
  //          TODO: follow the oracle's option set (expandtab/sw) instead
  //          of a literal tab, which is what `nvim --clean` inserts.
  wrapper.addEventListener("keydown", (e) => {
    if (e.defaultPrevented) return;
    if (e.key === "Escape") e.preventDefault();
    if (e.key === "Tab" && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      if (mode === "insert" || mode === "replace") insertTab(view);
    }
  });

  // Focus watchdog: record any blur that happens right after a key.
  wrapper.addEventListener("focusout", (e) => {
    const to = e.relatedTarget as Node | null;
    if (to && wrapper.contains(to)) return; // editor <-> command-line input
    queueMicrotask(() => {
      if (wrapper.contains(document.activeElement)) return;
      const lastKey = [...log].reverse().find((x) => x.type === "key");
      push({ type: "focus-lost", ...stamp(), after: lastKey && lastKey.type === "key" ? lastKey.key : "" });
    });
  });

  // --- codemirror-vim signals -------------------------------------------------
  cm.on("vim-command-done", (reason?: string) => {
    push({ type: "raw-signal", ...stamp(), name: "vim-command-done", detail: reason ?? "" });
    scheduleCheck("signal");
  });
  cm.on("vim-mode-change", (e: { mode: string; subMode?: string }) => {
    push({ type: "mode-signal", ...stamp(), mode: e.mode, subMode: e.subMode });
    scheduleCheck("mode-signal");
  });
  cm.on("vim-keypress", (key: string) => {
    push({ type: "raw-signal", ...stamp(), name: "vim-keypress", detail: key });
  });
  // ":" and "/" prompts are an <input> inside the editor's panel. Its focus is
  // the reliable "command line open" signal; cm.state.dialog is not (after
  // :s it holds the "Found N matches" notification for 5 s).
  wrapper.addEventListener("focusin", (e) => {
    if (e.target instanceof HTMLInputElement) push({ type: "cmdline", ...stamp(), open: true });
  });
  wrapper.addEventListener("focusout", (e) => {
    if (!(e.target instanceof HTMLInputElement)) return;
    push({ type: "cmdline", ...stamp(), open: false });
    scheduleCheck("cmdline-close");
  });

  // CM6 updates catch edits that do not go through clearInputState (ex
  // commands, undo via :undo, external dispatches).
  updateSinks.set(view, (u) => {
    if (u.docChanged) scheduleCheck("doc");
    else if (u.selectionSet) scheduleCheck("sel");
  });

  clock.start();
  return {
    log,
    mode: () => mode,
    keys: () => log.flatMap((e) => (e.type === "key" ? [e.key] : [])),
    reset() {
      log.length = 0;
      mode = modeFromState(cm);
      lastDoc = view.state.doc;
      lastCursor = cm.getCursor("head");
      clock.start();
    },
    onEvent(fn) {
      listeners.push(fn);
    },
  };
}
