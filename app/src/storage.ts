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
  /** Per language: true once that language's placement ran or was skipped. */
  placementDone: Record<string, boolean>;
  sessions: SessionRecord[];
}

export function load(): Saved | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as Saved;
    return data && data.version === 1 && data.model && Array.isArray(data.model.log) && data.settings ? normalize(data) : null;
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

// Checks an export file and returns it upgraded. Throws a message naming the first bad
// field, so nothing is saved. `langs` lists the language ids the app knows.
export function parseImport(text: string, langs: string[] = []): Saved {
  let data: Saved;
  try {
    data = JSON.parse(text) as Saved;
  } catch {
    throw new Error("that file is not valid JSON (it may be cut off)");
  }
  if (!isObj(data)) throw new Error("not a vim-trainer export");
  if (data.version !== 1) throw new Error(`export is version ${String(data.version)}, this app reads version 1`);
  if (!isObj(data.model)) throw new Error("missing field: model");
  if (!Array.isArray(data.model.log)) throw new Error("missing field: model.log");
  if (!isObj(data.model.skills)) throw new Error("missing field: model.skills");
  if (!isObj(data.settings)) throw new Error("missing field: settings");
  const lang = data.settings.lang;
  if (lang !== undefined && langs.length && !langs.includes(lang)) throw new Error(`unknown language in settings.lang: ${String(lang)}`);
  const pd = data.placementDone as unknown;
  if (typeof pd !== "boolean" && !isObj(pd)) throw new Error("missing field: placementDone");
  data.sessions ??= [];
  return normalize(data);
}

// True for a plain JSON object (not null, not an array).
const isObj = (v: unknown): boolean => !!v && typeof v === "object" && !Array.isArray(v);

// Upgrades older saves in place; called by load() and parseImport(). placementDone was
// one boolean before placement went per language: true meant the saved language's.
// A save without model.skills (an import from before validation) gets empty maps, which
// the model fills in again, so it no longer throws on every load.
function normalize(data: Saved): Saved {
  const old = data.placementDone as unknown;
  if (typeof old === "boolean") data.placementDone = old ? { [data.settings.lang ?? "python"]: true } : {};
  else if (!isObj(old)) data.placementDone = {};
  const m = data.model;
  if (!isObj(m.skills)) m.skills = {};
  if (!Array.isArray(m.recent)) m.recent = [];
  if (!Array.isArray(m.focusHistory)) m.focusHistory = [];
  return data;
}
