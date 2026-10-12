// Attempt recorder: keys, mode, completed commands, undo count and an active
// clock, on top of CodeMirror 6 + @replit/codemirror-vim. Production version of
// the M1 spike (src/spike/keylogger.ts; findings in src/spike/README.md):
//   keys          capture-phase keydown on a wrapper around view.dom, normalised
//                 with Vim.vimKeyFromEvent (what Vim itself sees);
//   mode          read from vim state, never from the vim-mode-change payload;
//   command done  signals + CM6 updates + command-line blur schedule one microtask
//                 check that fires only when no insert/replace mode, no pending
//                 command, no open command line, and buffer or cursor changed;
//   undo          CM6 transactions with userEvent "undo" (covers u, :undo, 3u);
//   clock         performance.now(), paused while the tab is hidden.

import { EditorView, type ViewUpdate } from "@codemirror/view";
import type { Extension, Text } from "@codemirror/state";
import { Vim, getCM } from "@replit/codemirror-vim";
import type { KeyEvent, Mode, Snapshot } from "./grading.ts";

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
  off(type: string, f: (...args: any[]) => void): void;
  getCursor(which?: string): { line: number; ch: number };
}

/** Wall clock that stops while the tab is hidden. */
export class ActiveClock {
  private startedAt = performance.now();
  private pausedTotal = 0;
  private pausedAt: number | null = document.visibilityState === "hidden" ? this.startedAt : null;
  private readonly onVis = () => this.sync();

  constructor() {
    document.addEventListener("visibilitychange", this.onVis);
  }

  /** Milliseconds of visible time since construction. */
  active(at = performance.now()): number {
    const pausedNow = this.pausedAt === null ? 0 : at - this.pausedAt;
    return at - this.startedAt - this.pausedTotal - pausedNow;
  }

  dispose(): void {
    document.removeEventListener("visibilitychange", this.onVis);
  }

  private sync(): void {
    const now = performance.now();
    if (document.visibilityState === "hidden" && this.pausedAt === null) this.pausedAt = now;
    else if (document.visibilityState !== "hidden" && this.pausedAt !== null) {
      this.pausedTotal += now - this.pausedAt;
      this.pausedAt = null;
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

function commandPending(cm: CMAdapter): boolean {
  const s = cm.state.vim?.inputState;
  if (!s) return false;
  return s.keyBuffer.length > 0 || !!s.operator || s.prefixRepeat.length > 0 || s.motionRepeat.length > 0;
}

const updateSinks = new WeakMap<EditorView, (u: ViewUpdate) => void>();

/** Add to the editor's extensions so the recorder sees CM6 doc/selection updates. */
export const recorderExtension: Extension = EditorView.updateListener.of((u) => updateSinks.get(u.view)?.(u));

export interface Recorder {
  readonly events: KeyEvent[];
  mode(): Mode;
  undoCount(): number;
  activeMs(): number;
  snapshot(): Snapshot;
  onCommandDone(fn: (s: Snapshot) => void): void;
  onKey(fn: (e: KeyEvent) => void): void;
  onChange(fn: () => void): void; // any mode / cursor change, for the mode line
  onHintKey(fn: () => void): void; // F1: the trainer's hint key, never delivered to Vim
  destroy(): void;
}

/** `wrapper` must contain view.dom. Attach right after the exercise renders: the clock starts now. */
export function attachRecorder(view: EditorView, wrapper: HTMLElement): Recorder {
  const cm = getCM(view) as unknown as CMAdapter | null;
  if (!cm) throw new Error("codemirror-vim is not active on this view");

  const events: KeyEvent[] = [];
  const doneFns: ((s: Snapshot) => void)[] = [];
  const keyFns: ((e: KeyEvent) => void)[] = [];
  const changeFns: (() => void)[] = [];
  const hintFns: (() => void)[] = [];
  const clock = new ActiveClock();
  let mode: Mode = modeFromState(cm);
  let lastDoc: Text = view.state.doc;
  let lastHead = view.state.selection.main.head;
  let undo = 0;
  let scheduled = false;

  const cmdlineOpen = () => {
    const a = document.activeElement;
    return a instanceof HTMLInputElement && wrapper.contains(a);
  };

  function snapshot(): Snapshot {
    const c = cm!.getCursor("head");
    return { lines: view.state.doc.toString().split("\n"), cursor: [c.line + 1, c.ch], mode };
  }

  function check(): void {
    scheduled = false;
    const next = modeFromState(cm!);
    if (next !== mode) mode = next;
    for (const fn of changeFns) fn();
    if (mode === "insert" || mode === "replace") return;
    if (commandPending(cm!)) return;
    if (cmdlineOpen()) return;
    const doc = view.state.doc;
    const head = view.state.selection.main.head;
    if (doc.eq(lastDoc) && head === lastHead) return;
    lastDoc = doc;
    lastHead = head;
    const snap = snapshot();
    for (const fn of doneFns) fn(snap);
  }
  const schedule = () => {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(check);
  };

  const onKeyCapture = (e: KeyboardEvent) => {
    // F1 is the trainer's mid-exercise hint key. Stop it here, before the contentDOM:
    // codemirror-vim treats an unmapped key as "no match" and clears a pending
    // command (`ci` then F1 would drop the `ci`), and the key log would no longer
    // match what Vim did.
    if (e.key === "F1") {
      e.preventDefault();
      e.stopPropagation();
      for (const fn of hintFns) fn();
      return;
    }
    // IME / dead keys: the emulator reads these via the text-input path.
    // TODO(mvp): log the composed text instead of skipping it.
    if (e.isComposing || e.keyCode === 229 || e.key === "Process" || e.key === "Unidentified") return;
    const key = Vim.vimKeyFromEvent(e, (cm.state.vim ?? undefined) as any);
    if (!key) return;
    const ev: KeyEvent = { key, mode, cmdline: cmdlineOpen(), active: clock.active() };
    events.push(ev);
    for (const fn of keyFns) fn(ev);
  };

  // Keys Vim leaves unhandled must not reach browser defaults (blur on Tab, etc.).
  // Tab in insert mode indents with the oracle's settings (expandtab, sw=4).
  const onKeyBubble = (e: KeyboardEvent) => {
    if (e.defaultPrevented) return;
    if (e.key === "Escape") e.preventDefault();
    if (e.key === "Tab" && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault();
      // TODO(mvp): align to the next shiftwidth stop like nvim; this inserts 4 spaces.
      if (mode === "insert" || mode === "replace") view.dispatch(view.state.replaceSelection("    "));
    }
  };

  const onFocusOut = (e: FocusEvent) => {
    if (e.target instanceof HTMLInputElement) schedule();
  };

  const onSignal = () => schedule();
  wrapper.addEventListener("keydown", onKeyCapture, { capture: true });
  wrapper.addEventListener("keydown", onKeyBubble);
  wrapper.addEventListener("focusout", onFocusOut);
  cm.on("vim-command-done", onSignal);
  cm.on("vim-mode-change", onSignal);
  updateSinks.set(view, (u) => {
    for (const tr of u.transactions) if (tr.isUserEvent("undo")) undo++;
    if (u.docChanged || u.selectionSet) schedule();
  });

  return {
    events,
    mode: () => mode,
    undoCount: () => undo,
    activeMs: () => clock.active(),
    snapshot,
    onCommandDone: (fn) => doneFns.push(fn),
    onKey: (fn) => keyFns.push(fn),
    onChange: (fn) => changeFns.push(fn),
    onHintKey: (fn) => hintFns.push(fn),
    destroy() {
      clock.dispose();
      wrapper.removeEventListener("keydown", onKeyCapture, { capture: true });
      wrapper.removeEventListener("keydown", onKeyBubble);
      wrapper.removeEventListener("focusout", onFocusOut);
      cm.off("vim-command-done", onSignal);
      cm.off("vim-mode-change", onSignal);
      updateSinks.delete(view);
    },
  };
}
