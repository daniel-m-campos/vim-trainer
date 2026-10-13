// Unit tests for the save migration in storage.ts (normalize, via parseImport). Run: npm test.
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseImport } from "./storage.ts";

// An export with the given placementDone and settings; parseImport normalizes it.
const migrate = (placementDone: unknown, settings: object = { lang: "cpp" }) =>
  parseImport(JSON.stringify({ version: 1, settings, model: { log: [] }, placementDone, sessions: [] })).placementDone;

test("old boolean placementDone migrates to the saved language", () => {
  assert.deepEqual(migrate(true), { cpp: true });
  assert.deepEqual(migrate(false), {});
});

test("old true save with no settings.lang is keyed python", () => {
  assert.deepEqual(migrate(true, {}), { python: true });
});

test("bad shapes reset to an empty map", () => {
  assert.deepEqual(migrate(null), {});
  assert.deepEqual(migrate(undefined), {});
  assert.deepEqual(migrate([]), {});
  assert.deepEqual(migrate([true]), {});
  assert.deepEqual(migrate("yes"), {});
});

test("a per-language map is kept as is", () => {
  assert.deepEqual(migrate({ python: true, cpp: true }), { python: true, cpp: true });
});
