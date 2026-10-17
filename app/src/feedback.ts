// Player feedback (docs/plan/11-feedback-loop.md): the "!" flag on the result strip
// opens a prefilled GitHub issue. No server: the player's browser opens the
// new-issue form and the player decides whether to submit it. REPO is the single
// place that names the tracker, so moving it (09: revisit at soft launch) is one line.

import type { AttemptRecord } from "./modelApi.ts";
import type { ErrorEntry } from "./storage.ts";
import type { Exercise } from "./types.ts";
import pkg from "../package.json" with { type: "json" };

export const REPO = "daniel-m-campos/vim-trainer";
export const ISSUES_URL = `https://github.com/${REPO}/issues`;
/** Fallback for the settings "Sources & attribution" link on a host that does not serve
 * build/ATTRIBUTION.md (the single-file bundle): the committed source allowlist. */
export const SOURCES_URL = `https://github.com/${REPO}/blob/main/content/sources.toml`;
/** Defined by vite.config.ts: package.json "version", plus "+<short commit sha>" when known. */
declare const __APP_VERSION__: string | undefined;
/** The app version; under node --test (no Vite define) it is package.json's "version". */
export const VERSION: string = typeof __APP_VERSION__ === "string" ? __APP_VERSION__ : pkg.version;
/** GitHub rejects new-issue URLs of about 8k characters. The cap is on the encoded body,
 * because encodeURIComponent turns one character into 3 to 12 (space, `<`, newline, emoji). */
const ENCODED_BODY_MAX = 6000;
/** The free-text fields are clipped first, so the par and version lines usually survive. */
const FIELD_MAX = 400;

/** The reason union lives on AttemptRecord.flag (model.ts); this names it. */
export type FlagReason = NonNullable<AttemptRecord["flag"]>["reason"];

/** Picker order: key 1 is the first entry. */
export const FLAG_REASONS: [FlagReason, string][] = [
  ["wrong-par", "wrong par"],
  ["wording", "wording"],
  ["emulator", "emulator"],
  ["other", "other"],
];

export interface FlagReport {
  ex: Exercise;
  seq: string; // the player's keys, replayKeys form (jk escape written as <Esc>)
  keys: number;
  ok: boolean;
  reason: FlagReason;
  note: string;
  profile: string;
  /** saved.errors; the newest few go at the end of the body while they fit. */
  errors?: ErrorEntry[];
}

/** The new-issue URL with title and body filled in; called by confirmFlag in main.ts. */
export function issueUrl(r: FlagReport): string {
  const title = `[${r.reason}] ${clip(r.ex.id, 100)}`;
  let body = [
    `**reason:** ${r.reason}`,
    `**note:** ${clip(r.note, FIELD_MAX) || "(none)"}`,
    "",
    `- exercise: \`${r.ex.id}\` (${r.ex.lang}, kind ${r.ex.kind}, skill ${r.ex.skill})`,
    `- task: ${clip(r.ex.task, FIELD_MAX)}`,
    `- player keys (${r.keys}, ${r.ok ? "correct" : "gave up"}): \`${clip(r.seq, FIELD_MAX)}\``,
    `- par keys (${r.ex.par.count}): \`${r.ex.par.keys}\``,
    `- editor profile: ${r.profile}`,
    `- app version: ${VERSION}`,
  ].join("\n");
  // Errors last, one line at a time, only while the encoded body stays under the cap.
  for (const line of errorLines(r.errors ?? [])) {
    if (encodeURIComponent(`${body}\n${line}`).length > ENCODED_BODY_MAX) break;
    body += `\n${line}`;
  }
  // Backstop for a body still too long once encoded: drop a tenth of it per round.
  let cps = Array.from(body); // code points, so a cut never leaves half a surrogate pair
  while (encodeURIComponent(cps.join("")).length > ENCODED_BODY_MAX) cps = cps.slice(0, Math.floor(cps.length * 0.9));
  if (cps.length < Array.from(body).length) body = cps.join("") + "\n(truncated)";
  return `${ISSUES_URL}/new?labels=feedback&title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}

/** The newest 3 errors as markdown list lines, stack lines indented; called by issueUrl. */
function errorLines(errors: ErrorEntry[]): string[] {
  if (!errors.length) return [];
  const out = ["- recent errors (newest first):"];
  for (const e of errors.slice(-3).reverse()) {
    out.push(`  - ${new Date(e.t * 1000).toISOString()} ${e.version} #${e.route}: ${clip(e.message, 200)}`);
    for (const l of e.stack.split("\n").filter(Boolean)) out.push(`    ${clip(l.trim(), 160)}`);
  }
  return out;
}

/** The first n code points of s, with "..." when cut; called by issueUrl. */
function clip(s: string, n: number): string {
  const cps = Array.from(s);
  return cps.length > n ? cps.slice(0, n).join("") + "..." : s;
}
