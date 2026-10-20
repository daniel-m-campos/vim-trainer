// @ts-nocheck -- node:test / node:fs types are not installed in the app (no @types/node), and
// tsc would reject the '.ts' import; Node runs this file directly with type stripping.
//
// Run (Node >= 23, zero install):   node --test app/src/model/model.test.ts
//
// Replays every model/.cache/vectors/*.json scenario (generated, not committed: `make vectors`)
// through the TypeScript mirror and compares each output with the Python-generated
// expectation (relative tolerance 1e-9).

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  Mulberry32,
  applyAttempt,
  applyPlacement,
  applyProfile,
  chooseExercise,
  chooseFocus,
  chooseWarmup,
  deriveSeed,
  diagnose,
  exercisePool,
  newState,
  projection,
  rebuild,
  sessionSummary,
} from './model.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const MODEL_DIR = join(HERE, '..', '..', '..', 'model');
const VECTOR_DIR = join(MODEL_DIR, '.cache', 'vectors');
const DEFAULT_GRAPH = JSON.parse(readFileSync(join(MODEL_DIR, 'skill-graph.json'), 'utf8'));
const DIGEST_TAIL = 5;
const REL_TOL = 1e-9;

function vectorGraph(vector) {
  let graph = vector.graph || DEFAULT_GRAPH;
  if (vector.profile) graph = applyProfile(graph, vector.profile.profile || 'neovim', vector.profile.extraTiers || []);
  return graph;
}

function digest(state) {
  const skills = {};
  for (const [id, langs] of Object.entries(state.skills)) {
    const kept = {};
    for (const [lang, st] of Object.entries(langs)) {
      if (st.status !== 'locked' || st.n > 0) kept[lang] = { ...st };
    }
    if (Object.keys(kept).length) skills[id] = kept;
  }
  return {
    skills,
    logLen: state.log.length,
    recentLen: state.recent.length,
    recentTail: state.recent.slice(-DIGEST_TAIL),
    focusTail: state.focusHistory.slice(-DIGEST_TAIL),
  };
}

function compare(expected, actual, path = '$') {
  if (typeof expected === 'boolean' || typeof actual === 'boolean' || expected === null || actual === null ||
      expected === undefined || actual === undefined) {
    return (expected ?? null) === (actual ?? null) ? [] : [`${path}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`];
  }
  if (typeof expected === 'number' && typeof actual === 'number') {
    const scale = Math.max(1, Math.abs(expected), Math.abs(actual));
    return Math.abs(expected - actual) <= REL_TOL * scale ? [] : [`${path}: expected ${expected}, got ${actual}`];
  }
  if (Array.isArray(expected) && Array.isArray(actual)) {
    if (expected.length !== actual.length) return [`${path}: length ${expected.length} != ${actual.length}`];
    return expected.flatMap((value, i) => compare(value, actual[i], `${path}[${i}]`));
  }
  if (typeof expected === 'object' && typeof actual === 'object') {
    const a = Object.keys(expected).sort();
    const b = Object.keys(actual).sort();
    const problems = JSON.stringify(a) === JSON.stringify(b) ? [] : [`${path}: keys ${a} != ${b}`];
    for (const key of a) if (key in actual) problems.push(...compare(expected[key], actual[key], `${path}.${key}`));
    return problems;
  }
  return expected === actual ? [] : [`${path}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`];
}

function runOp(op, state, graph, index) {
  switch (op.op) {
    case 'applyAttempt': return [applyAttempt(state, op.record, graph), undefined];
    case 'applyPlacement': return [applyPlacement(state, op.records, graph), undefined];
    case 'chooseFocus': return [state, chooseFocus(state, op.lang, graph, op.now, op.seed)];
    case 'chooseWarmup': return [state, chooseWarmup(state, op.lang, graph)];
    case 'chooseExercise':
      return [state, chooseExercise(state, op.skill, op.lang, index, op.seed, op.useGraph === false ? null : graph)];
    case 'projection': return [state, projection(state, op.skill, op.lang, graph)];
    case 'sessionSummary': return [state, sessionSummary(state, op.since, graph)];
    case 'diagnose': return [state, diagnose(state, op.skill, op.lang, graph)];
    case 'digest': return [state, digest(state)];
    case 'rebuildMatches': return [state, compare(digest(state), digest(rebuild(state.log, graph))).length === 0];
    case 'rng': {
      const rng = new Mulberry32(op.seed);
      return [state, Array.from({ length: op.count }, () => rng.next())];
    }
    case 'deriveSeed': return [state, deriveSeed(op.n, op.now)];
    default: throw new Error(`unknown op ${op.op}`);
  }
}

// The generated vector files, sorted; stops the run with "run make vectors" when there are none.
function vectorFiles() {
  const found = existsSync(VECTOR_DIR) ? readdirSync(VECTOR_DIR).filter((name) => name.endsWith('.json')).sort() : [];
  if (found.length === 0) throw new Error(`no vectors in ${VECTOR_DIR}: run make vectors`);
  return found;
}

const files = vectorFiles();

test('at least 12 shared vectors exist', () => {
  assert.ok(files.length >= 12, `only ${files.length} vectors`);
});

test('app copy of skill-graph.json matches model/skill-graph.json', () => {
  const appCopy = readFileSync(join(HERE, 'skill-graph.json'), 'utf8');
  assert.equal(appCopy, readFileSync(join(MODEL_DIR, 'skill-graph.json'), 'utf8'));
});

for (const file of files) {
  test(`vector ${file}`, () => {
    const vector = JSON.parse(readFileSync(join(VECTOR_DIR, file), 'utf8'));
    const graph = vectorGraph(vector);
    const index = vector.index || {};
    let state = newState(graph);
    const problems = [];
    vector.ops.forEach((op, i) => {
      let output;
      [state, output] = runOp(op, state, graph, index);
      if ('expect' in op) problems.push(...compare(op.expect, output, `ops[${i}].${op.op}`));
    });
    assert.deepEqual(problems.slice(0, 20), []);
  });
}

test('model functions do not mutate their input state', () => {
  const graph = DEFAULT_GRAPH;
  const state = newState(graph);
  const snapshot = JSON.stringify(state);
  const record = { t: 1, ex: 'py/f.hjkl/0001', skill: 'f.hjkl', lang: 'python', ok: true, ms: 2000, keys: 6, par: 6,
    hint: false, retry: false, undo: 0 };
  applyAttempt(state, record, graph);
  applyPlacement(state, [record], graph);
  chooseFocus(state, 'python', graph, 10);
  sessionSummary(state, 0, graph);
  assert.equal(JSON.stringify(state), snapshot);
});

test('app-only record fields (seq, beatPar, flag) are logged unchanged and do not change the state', () => {
  const graph = DEFAULT_GRAPH;
  const plain = { t: 1, ex: 'py/f.hjkl/0001', skill: 'f.hjkl', lang: 'python', ok: true, ms: 2000, keys: 4, par: 6,
    hint: false, retry: false, undo: 0 };
  const extra = { seq: 'jjll', beatPar: true, flag: { reason: 'wrong-par', note: '4 keys is enough' } };
  const record = { ...plain, ...extra };
  const state = applyAttempt(newState(graph), record, graph);
  assert.deepEqual(state.log.at(-1), record);
  assert.deepEqual(digest(state), digest(applyAttempt(newState(graph), plain, graph)));
});

test('exercisePool reads the build/index.json shape (langs.<lang>.skills.<skill>.ids)', () => {
  const build = { version: 1, langs: { python: { skills: { 't.quote': { ids: ['a'], count: 1 } } } } };
  assert.deepEqual(exercisePool(build as any, 'python', 't.quote'), [{ id: 'a', skills: ['t.quote'] }]);
  assert.deepEqual(exercisePool(build as any, 'cpp', 't.quote'), []);
});

function focusPicks(file) {
  const vector = JSON.parse(readFileSync(join(VECTOR_DIR, file), 'utf8'));
  const graph = vectorGraph(vector);
  let state = newState(graph);
  const picks = [];
  for (const op of vector.ops) {
    let output;
    [state, output] = runOp(op, state, graph, vector.index || {});
    if (op.op === 'chooseFocus') picks.push(output);
  }
  return picks;
}

function maxWindowCount(picks, window) {
  let worst = 0;
  for (let i = 0; i + window <= picks.length; i++) {
    const counts = new Map();
    for (const id of picks.slice(i, i + window)) counts.set(id, (counts.get(id) ?? 0) + 1);
    worst = Math.max(worst, ...counts.values());
  }
  return worst;
}

test('share cap: no skill takes more than 4 of any 10 consecutive picks', () => {
  const picks = focusPicks('24_share_cap.json');
  assert.ok(maxWindowCount(picks, 10) <= 4, picks.join(' '));
});

test('starvation guard: the weight-0.2 skill appears in every 12 consecutive picks', () => {
  const picks = focusPicks('25_starvation_guard.json');
  for (let i = 0; i + 12 <= picks.length; i++) assert.ok(picks.slice(i, i + 12).includes('d0'), `window at ${i}`);
});
