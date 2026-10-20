// Unit tests for import validation and the save migration in storage.ts. Run: npm test.
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseImport, pushError, ERRORS_MAX, type Saved } from "./storage.ts";

const LANGS = ["python", "cpp"];
// A minimal valid export; `patch` overrides top-level fields.
const exportText = (patch: object = {}) =>
  JSON.stringify({ version: 1, settings: { lang: "cpp" }, model: { log: [], skills: {} }, placementDone: {}, sessions: [], ...patch });
// An export with the given placementDone and settings; parseImport normalizes it.
const migrate = (placementDone: unknown, settings: object = { lang: "cpp" }) =>
  parseImport(exportText({ placementDone, settings }), LANGS).placementDone;

test("old boolean placementDone migrates to the saved language", () => {
  assert.deepEqual(migrate(true), { cpp: true });
  assert.deepEqual(migrate(false), {});
});

test("old true save with no settings.lang is keyed python", () => {
  assert.deepEqual(migrate(true, {}), { python: true });
});

test("a per-language map is kept as is", () => {
  assert.deepEqual(migrate({ python: true, cpp: true }), { python: true, cpp: true });
});

test("import rejects a missing or malformed placementDone", () => {
  for (const bad of [null, undefined, [], [true], "yes"]) assert.throws(() => migrate(bad), /placementDone/);
});

test("import rejects a file without model.skills", () => {
  assert.throws(() => parseImport(exportText({ model: { log: [] } }), LANGS), /model\.skills/);
});

test("import rejects an unknown language", () => {
  assert.throws(() => parseImport(exportText({ settings: { lang: "klingon" } }), LANGS), /klingon/);
});

test("import names the version and explains invalid JSON", () => {
  assert.throws(() => parseImport(exportText({ version: 2 }), LANGS), /version 2, this app reads version 1/);
  assert.throws(() => parseImport(exportText().slice(0, 40), LANGS), /not valid JSON/);
});

test("an export from before the error buffer gets errors: []", () => {
  assert.deepEqual(parseImport(exportText(), LANGS).errors, []);
});

test("a malformed placement in progress is dropped on import", () => {
  const data = parseImport(exportText({ placement: { lang: "python", queue: "x" } }), LANGS);
  assert.equal("placement" in data, false);
});

test("a placement with a bad queue entry or index is dropped on import", () => {
  const placement = (queue: unknown[], i: number) => ({ placement: { lang: "python", queue, i, records: [] } });
  const ok = { skill: "m.word", id: "abc" };
  for (const [queue, i] of [[[null], 0], [[{ skill: "m.word" }], 0], [[ok], -1], [[ok], 2]] as [unknown[], number][]) {
    assert.equal("placement" in parseImport(exportText(placement(queue, i)), LANGS), false, JSON.stringify([queue, i]));
  }
  assert.deepEqual(parseImport(exportText(placement([ok], 1)), LANGS).placement?.queue, [ok]);
});

test("imported error entries feedback.ts cannot format are dropped, the rest capped", () => {
  const good = { t: 1, version: "v", route: "practice", message: "m", stack: "s" };
  const bad = [null, { ...good, t: "x" }, { ...good, t: 1e20 }, { t: 1, message: "m" }, { ...good, stack: undefined }];
  assert.deepEqual(parseImport(exportText({ errors: [...bad, good] }), LANGS).errors, [good]);
  const many = Array.from({ length: 30 }, (_, i) => ({ ...good, t: i }));
  const kept = parseImport(exportText({ errors: many }), LANGS).errors;
  assert.equal(kept.length, ERRORS_MAX);
  assert.equal(kept[0].t, 10);
});

test("pushError keeps only the newest ERRORS_MAX entries", () => {
  const data = { errors: [] } as unknown as Saved;
  for (let i = 0; i < 25; i++) pushError(data, { t: i, version: "v", route: "practice", message: String(i), stack: "" });
  assert.equal(data.errors.length, ERRORS_MAX);
  assert.equal(data.errors[0].message, "5");
});
