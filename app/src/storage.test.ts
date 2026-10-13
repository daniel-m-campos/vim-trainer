// Unit tests for import validation and the save migration in storage.ts. Run: npm test.
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseImport } from "./storage.ts";

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
