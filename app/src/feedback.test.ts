// Unit tests for the flag's issue URL (feedback.ts). Run: npm test.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { issueUrl, REPO, VERSION, type FlagReport } from "./feedback.ts";
import type { Exercise } from "./types.ts";

const ex = {
  id: "py/t.quote/0001", skill: "t.quote", lang: "python", kind: "edit", task: "Change the string to `retrying`",
  start: { lines: [""], cursor: [1, 0] }, expect: { lines: [""] }, par: { keys: 'ci"retrying<Esc>', count: 12 },
} as Exercise;
const report = (over: Partial<FlagReport> = {}): FlagReport =>
  ({ ex, seq: 'ci"retry<Esc>', keys: 9, ok: true, reason: "wrong-par", note: "par & more", profile: "neovim", ...over });

test("issue URL targets the repo with the feedback label and an encoded title and body", () => {
  const url = issueUrl(report());
  assert.ok(url.startsWith(`https://github.com/${REPO}/issues/new?labels=feedback&title=`), url);
  const q = new URL(url).searchParams;
  assert.equal(q.get("title"), "[wrong-par] py/t.quote/0001");
  const body = q.get("body") ?? "";
  for (const s of ["par & more", 'ci"retry<Esc>', 'ci"retrying<Esc>', "python", "kind edit", "Change the string", `app version: ${VERSION}`])
    assert.ok(body.includes(s), s);
});

test("a worst-case seq, task and note keep the URL under GitHub's 8k limit", () => {
  // Each of these characters encodes to 3 or more: space, `<`, `>`, backtick, newline, emoji.
  const nasty = "<Esc> `\n😀".repeat(3000);
  const url = issueUrl(report({ seq: nasty, note: nasty, ex: { ...ex, task: nasty } }));
  assert.ok(url.length < 8000, String(url.length));
  const body = new URL(url).searchParams.get("body") ?? "";
  assert.ok(body.includes("par keys") && body.includes(`app version: ${VERSION}`), body.slice(-200));
});

test("a body too long even after clipping is cut on code points and marked", () => {
  const url = issueUrl(report({ ex: { ...ex, id: "😀".repeat(3000) } })); // throws on a lone surrogate
  assert.ok(url.length < 8000, String(url.length));
  assert.ok((new URL(url).searchParams.get("body") ?? "").endsWith("(truncated)"));
});

test("VERSION matches app/package.json", () => {
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8"));
  assert.equal(VERSION, pkg.version);
});

test("the newest errors go at the end of the body, never pushing out the version", () => {
  const errors = [{ t: 0, version: "v", route: "practice", message: "boom", stack: "at x" }];
  const body = new URL(issueUrl(report({ errors }))).searchParams.get("body") ?? "";
  assert.ok(body.includes("recent errors") && body.includes("boom"), body);
  const nasty = "<Esc> `\n😀".repeat(3000);
  const worst = new URL(issueUrl(report({ seq: nasty, note: nasty, ex: { ...ex, task: nasty }, errors }))).searchParams.get("body") ?? "";
  assert.ok(worst.includes(`app version: ${VERSION}`), worst.slice(-200));
});
