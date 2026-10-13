// Player feedback (docs/plan/11-feedback-loop.md): the "!" flag on the result strip
// opens a prefilled GitHub issue. No server: the player's browser opens the
// new-issue form and the player decides whether to submit it. REPO is the single
// place that names the tracker, so moving it (09: revisit at soft launch) is one line.

import type { AttemptRecord } from "./modelApi.ts";
import type { Exercise } from "./types.ts";

export const REPO = "daniel-m-campos/vim-trainer";
export const ISSUES_URL = `https://github.com/${REPO}/issues`;
/** Keep equal to "version" in app/package.json (the app has no build-time version). */
export const VERSION = "0.0.0";
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
  // Backstop for a body still too long once encoded: drop a tenth of it per round.
  let cps = Array.from(body); // code points, so a cut never leaves half a surrogate pair
  while (encodeURIComponent(cps.join("")).length > ENCODED_BODY_MAX) cps = cps.slice(0, Math.floor(cps.length * 0.9));
  if (cps.length < Array.from(body).length) body = cps.join("") + "\n(truncated)";
  return `${ISSUES_URL}/new?labels=feedback&title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}

/** The first n code points of s, with "..." when cut; called by issueUrl. */
function clip(s: string, n: number): string {
  const cps = Array.from(s);
  return cps.length > n ? cps.slice(0, n).join("") + "..." : s;
}
