// localStorage persistence of the model state, settings and sessions, with JSON
// export / import. Every access is wrapped: private windows and blocked storage
// must still give a working (if forgetful) trainer.

import type { ModelState } from "./modelApi.ts";
import type { SessionRecord, Settings } from "./types.ts";

const KEY = "vim-trainer.v1";

export interface Saved {
  version: 1;
  settings: Settings;
  model: ModelState;
  placementDone: boolean;
  sessions: SessionRecord[];
}

export function load(): Saved | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as Saved;
    return data && data.version === 1 && data.model && data.settings ? data : null;
  } catch {
    return null;
  }
}

export function save(data: Saved): boolean {
  try {
    localStorage.setItem(KEY, JSON.stringify(data));
    return true;
  } catch {
    return false;
  }
}

export function clear(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable */
  }
}

export function exportJson(data: Saved): void {
  const blob = new Blob([JSON.stringify(data, null, 1)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `vim-trainer-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function parseImport(text: string): Saved {
  const data = JSON.parse(text) as Saved;
  if (!data || data.version !== 1 || !data.model || !Array.isArray(data.model.log) || !data.settings)
    throw new Error("not a vim-trainer export (version 1)");
  data.sessions ??= [];
  return data;
}
