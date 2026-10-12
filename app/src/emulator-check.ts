// Harness for e2e/emulator.mjs (the browser half of the par oracle, 03 "Emulator
// oracle"): mount an exercise exactly as the practice screen does, let Playwright type
// keys, and report whether the exercise passed. Loaded only by emulator-check.html.

import { mountEditor, type EditorHandle } from "./editor.ts";
import { checkPass, tokenize, type Snapshot } from "./grading.ts";
import type { Exercise } from "./types.ts";

let handle: EditorHandle | null = null;
let passed = false;

function mount(ex: Exercise): void {
  handle?.destroy();
  passed = false;
  const h = mountEditor(document.getElementById("code")!, ex, { relativeNumbers: true, escape: "esc" });
  handle = h;
  h.recorder.onCommandDone((snap: Snapshot) => {
    if (handle === h && !passed) passed = checkPass(ex, snap, tokenize(h.recorder.events, "esc", snap.mode));
  });
}

function status(): { passed: boolean; snap: Snapshot | null } {
  return { passed, snap: handle ? handle.recorder.snapshot() : null };
}

declare global {
  interface Window {
    emu: { mount: typeof mount; status: typeof status };
  }
}
window.emu = { mount, status };
