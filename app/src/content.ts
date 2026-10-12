// Content loading: build/index.json and per-exercise JSON, fetched lazily from
// /build/ (served from the repo's build/ directory by vite.config.ts). When the
// pipeline output is missing, falls back to the hand-written sample shipped in
// app/public/build-sample/ and says so in the console.

import type { ContentIndex, Exercise } from "./types.ts";

let base = "build/";
let index: ContentIndex | null = null;
const cache = new Map<string, Promise<Exercise>>();

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  const type = res.headers.get("content-type") ?? "";
  // A dev server's SPA fallback answers unknown paths with index.html.
  if (type.includes("text/html")) throw new Error(`${url}: got HTML, not JSON`);
  return (await res.json()) as T;
}

export async function loadIndex(): Promise<ContentIndex> {
  if (index) return index;
  try {
    index = await fetchJson<ContentIndex>(`${base}index.json`);
  } catch (err) {
    console.warn(`vim-trainer: build/index.json not available (${(err as Error).message}); using the bundled sample content in build-sample/.`);
    base = "build-sample/";
    index = await fetchJson<ContentIndex>(`${base}index.json`);
  }
  return index;
}

export function contentBase(): string {
  return base;
}

/** build/exercises/<lang>/<skill>/<last id segment>.json */
export function exercisePath(id: string, skill: string, lang: string): string {
  const leaf = id.split("/").pop() ?? id;
  return `${base}exercises/${lang}/${skill}/${leaf}.json`;
}

export function loadExercise(id: string, skill: string, lang: string): Promise<Exercise> {
  const key = `${lang}:${id}`;
  let p = cache.get(key);
  if (!p) {
    p = fetchJson<Exercise>(exercisePath(id, skill, lang));
    p.catch(() => cache.delete(key));
    cache.set(key, p);
  }
  return p;
}

/** Skill id that owns an exercise id in the index (ids are unique per language). */
export function skillOf(idx: ContentIndex, lang: string, id: string): string | null {
  for (const [skill, s] of Object.entries(idx.langs[lang]?.skills ?? {})) if (s.ids.includes(id)) return skill;
  return null;
}

export function skillsWithContent(idx: ContentIndex, lang: string): string[] {
  return Object.entries(idx.langs[lang]?.skills ?? {})
    .filter(([, s]) => s.ids.length > 0)
    .map(([k]) => k);
}
