// Adaptive model (docs/plan/04-adaptive-model.md), TypeScript mirror of model/vimtrainer_model.
//
// Pure functions, no dependencies, no clock or global randomness: time and seeds are
// arguments. Both mirrors are checked against the shared vectors in model/vectors/*.json
// (see app/src/model/model.test.ts). Keep operation order identical to the Python side so
// floating-point results match bit for bit.
//
// Erasable TypeScript only (no enums, namespaces or parameter properties), so Node can run
// it directly with type stripping.

// Types ===========================================================================================

export type Status = 'locked' | 'active' | 'introduced' | 'mastered' | 'review';

export interface AttemptRecord {
  t: number;
  ex: string;
  /** Skill id; composites join several ids with '+', e.g. "m.find+o.change". */
  skill: string;
  lang: string;
  ok: boolean;
  ms: number;
  keys: number;
  par: number;
  hint: boolean;
  retry: boolean;
  undo: number;
  /** Set by applyPlacement on the records it logs, so rebuild() can replay them. */
  placement?: boolean;
  /** The keys the player typed, normalised (grading displayKeys); the model ignores it. */
  seq?: string;
  /** ok and fewer keys than par; the model ignores it. */
  beatPar?: boolean;
  /** Set by the "!" flag on the result strip; the model ignores it. */
  flag?: { reason: 'wrong-par' | 'wording' | 'emulator' | 'other'; note?: string };
}

export interface SkillState {
  timeEma: number | null;
  effEma: number | null;
  /** EMA of par on correct attempts; target_ms = targetBase + perKey * parEma. */
  parEma: number | null;
  acc: number;
  n: number;
  confidence: number;
  lastSeen: number;
  status: Status;
  reviewsPassed: number;
  nextReview: number | null;
}

export interface ModelState {
  skills: Record<string, Record<string, SkillState>>;
  log: AttemptRecord[];
  /** Last 50 exercise ids. */
  recent: string[];
  /** Primary skill of recent attempts (last 20), for the interleave rule. */
  focusHistory: string[];
}

export type EmulatorFlag = 'full' | 'partial' | 'none' | 'verify';

export interface SkillNode {
  id: string;
  tier: number;
  tierName?: string;
  keys?: string;
  what?: string;
  prereqs: string[];
  order: number;
  targetBase: number;
  perKey: number;
  enabled?: boolean;
  emulator: { neovim?: EmulatorFlag; vscodevim?: EmulatorFlag; ideavim?: EmulatorFlag; note?: string };
  langWeights: Record<string, number>;
}

export interface SkillGraph {
  version?: number;
  targetBase?: number;
  perKey?: number;
  langs?: string[];
  skills: Record<string, SkillNode>;
  tips?: Record<string, string>;
}

export type IndexItem = string | { id: string; skills?: string[] };
export type IndexEntry = IndexItem[] | { ids?: IndexItem[]; exercises?: IndexItem[] };
/** build/index.json: {langs: {lang: {skills: {skill: {ids: [...]}}}}}; {langs: {lang: {skill: ...}}} and {lang: {skill: ...}} also accepted. */
export type ExerciseIndex =
  | { langs: Record<string, Record<string, IndexEntry>> }
  | Record<string, Record<string, IndexEntry>>;

export interface PoolEntry {
  id: string;
  skills: string[];
}

export interface Projection {
  fit: 'none' | 'linear' | 'quadratic';
  attemptsToTarget: number | null;
  r2: number;
}

export interface SessionSummary {
  improved: { skill: string; delta: number }[];
  mastered: string[];
  unlocked: string[];
  tip: string | null;
}

export type Gate = 'samples' | 'accuracy' | 'efficiency' | 'speed';

export interface Diagnosis {
  status: Status | null;
  failing: Gate[];
  speed: number;
  efficiency: number | null;
  acc: number;
  n: number;
}

// Constants (mirror model/vimtrainer_model/constants.py) ==========================================

export const ALPHA = 0.1;
export const ACC_WINDOW = 20;
export const RECENT_MAX = 50;
export const FOCUS_HISTORY_MAX = 20;
export const MAX_STREAK = 3;
export const FOCUS_CANDIDATES = 3;
export const FOCUS_FLOOR = 0.1;
export const SHARE_WINDOW = 10;
export const SHARE_MAX = 4;
export const LOW_WEIGHT = 0.3;
export const STARVE_WINDOW = 12;
export const MASTER_N = 8;
export const MASTER_ACC = 0.9;
export const MASTER_EFF = 1.25;
export const EFF_FLOOR = 0.5;
export const MIN_ACTIVE = 4;
export const MAX_ACTIVE = 7;
export const REVIEW_P = 0.2;
export const REVIEW_KEYS = 1.5;
export const REVIEW_TIME = 1.3;
export const REVIEW_FAIL_FACTOR = 0.8;
export const MAX_INTERVAL_DAYS = 60;
export const DAY = 86400;
export const COMPOSITE_P = 0.2;
export const COMPOSITE_CONF = 0.8;
export const PLACEMENT_ACTIVE_CONF = 0.6;
export const PLACEMENT_INFERRED_CONF = 0.5;
export const PLACEMENT_INFERRED_REVIEWS = 2;
export const PLACEMENT_FOUNDATION_TIER = 3;
export const IMPROVED_DELTA = 0.1;
export const PROJECTION_WINDOW = 30;
export const PROJECTION_AHEAD = 30;
export const PROJECTION_QUADRATIC_N = 15;
export const PROJECTION_MIN_N = 3;
export const PROJECTION_MIN_R2 = 0.5;
export const DEFAULT_TARGET_BASE = 1200;
export const DEFAULT_PER_KEY = 180;

const IN_ROTATION: readonly Status[] = ['active', 'introduced'];
const MASTERED_LIKE: readonly Status[] = ['mastered', 'review'];
const EPSILON = 1e-12;

// RNG =============================================================================================

/** Mulberry32, bit-identical to model/vimtrainer_model/rng.py. */
export class Mulberry32 {
  state: number;

  constructor(seed: number) {
    this.state = seed >>> 0;
  }

  next(): number {
    this.state = (this.state + 0x6d2b79f5) >>> 0;
    const a = this.state;
    let t = Math.imul(a ^ (a >>> 15), 1 | a) >>> 0;
    t = (((t + (Math.imul(t ^ (t >>> 7), 61 | t) >>> 0)) >>> 0) ^ t) >>> 0;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
}

/** Seed derived from the log length and the clock, for calls that take no seed. */
export function deriveSeed(n: number, now: number): number {
  return ((Math.imul(n, 0x9e3779b1) >>> 0) ^ (Math.floor(now) >>> 0)) >>> 0;
}

// Graph ===========================================================================================

const orderCache = new WeakMap<SkillGraph, string[]>();

/** Skill ids sorted by (tier, document order). */
export function skillIds(graph: SkillGraph): string[] {
  const cached = orderCache.get(graph);
  if (cached) return cached;
  const ids = Object.keys(graph.skills).sort((x, y) => {
    const a = graph.skills[x];
    const b = graph.skills[y];
    return a.tier - b.tier || a.order - b.order;
  });
  orderCache.set(graph, ids);
  return ids;
}

function orderOf(graph: SkillGraph, skillId: string): number {
  return graph.skills[skillId].order;
}

function isEnabled(graph: SkillGraph, skillId: string): boolean {
  return graph.skills[skillId].enabled !== false;
}

export function langWeight(graph: SkillGraph | null | undefined, skillId: string, lang: string): number {
  if (!graph) return 1.0;
  const node = graph.skills[skillId];
  if (!node) return 1.0;
  const weight = node.langWeights?.[lang];
  return weight === undefined ? 1.0 : weight;
}

/** target_ms = targetBase + perKey * par. */
export function targetMs(graph: SkillGraph | null | undefined, skillId: string, par: number | null): number {
  const node = graph?.skills[skillId];
  const base = node?.targetBase ?? DEFAULT_TARGET_BASE;
  const perKey = node?.perKey ?? DEFAULT_PER_KEY;
  return base + perKey * (par || 0);
}

/** Skills credited by a record: `skill` split on '+', unknown ids dropped. */
export function recordSkills(graph: SkillGraph, record: AttemptRecord): string[] {
  const seen: string[] = [];
  for (const id of record.skill.split('+')) {
    if (graph.skills[id] && !seen.includes(id)) seen.push(id);
  }
  return seen;
}

/**
 * Copy of the graph with `enabled` set for an editor profile: skills flagged `none` for
 * the profile are disabled; tiers above 10 only when listed in extraTiers.
 */
export function applyProfile(
  graph: SkillGraph,
  profile: 'neovim' | 'vscodevim' | 'ideavim' = 'neovim',
  extraTiers: number[] = [],
): SkillGraph {
  const result: SkillGraph = JSON.parse(JSON.stringify(graph));
  for (const node of Object.values(result.skills)) {
    const tierOn = node.tier <= 10 || extraTiers.includes(node.tier);
    const supported = (node.emulator[profile] ?? 'full') !== 'none';
    node.enabled = tierOn && supported;
  }
  return result;
}

// State ===========================================================================================

export function newState(graph: SkillGraph): ModelState {
  const skills: Record<string, Record<string, SkillState>> = {};
  for (const id of skillIds(graph)) skills[id] = {};
  return { skills, log: [], recent: [], focusHistory: [] };
}

export function newSkillState(status: Status): SkillState {
  return {
    timeEma: null,
    effEma: null,
    parEma: null,
    acc: 0,
    n: 0,
    confidence: 0,
    lastSeen: 0,
    status,
    reviewsPassed: 0,
    nextReview: null,
  };
}

/** Copy a state; skill states are copied, log records are shared (treated as immutable). */
export function cloneState(state: ModelState): ModelState {
  const skills: Record<string, Record<string, SkillState>> = {};
  for (const [id, langs] of Object.entries(state.skills)) {
    const copy: Record<string, SkillState> = {};
    for (const [lang, st] of Object.entries(langs)) copy[lang] = { ...st };
    skills[id] = copy;
  }
  return {
    skills,
    log: state.log.slice(),
    recent: state.recent.slice(),
    focusHistory: state.focusHistory.slice(),
  };
}

function getSkill(state: ModelState, skillId: string, lang: string): SkillState | undefined {
  return state.skills[skillId]?.[lang];
}

function ensureSkill(state: ModelState, graph: SkillGraph, skillId: string, lang: string): SkillState {
  const langs = (state.skills[skillId] ??= {});
  const existing = langs[lang];
  if (existing) return existing;
  // Unlocking uses the max across languages (04). A skill mastered elsewhere starts
  // mastered with its first review due at once (not re-locked, not crowding the 4-7
  // active skills); one unlocked elsewhere is carried over only while a slot is free.
  if (isMasteredAnywhere(state, skillId)) {
    const st = newSkillState('mastered');
    st.nextReview = 0;
    langs[lang] = st;
    return st;
  }
  const tierZero = graph.skills[skillId].tier === 0;
  const carried = isUnlockedAnywhere(state, skillId) && activeCount(state, graph, lang) < MAX_ACTIVE;
  const st = newSkillState(tierZero || carried ? 'active' : 'locked');
  langs[lang] = st;
  return st;
}

function isUnlockedAnywhere(state: ModelState, skillId: string): boolean {
  return Object.values(state.skills[skillId] ?? {}).some((st) => st.status !== 'locked');
}

function isMasteredAnywhere(state: ModelState, skillId: string): boolean {
  return Object.values(state.skills[skillId] ?? {}).some((st) => MASTERED_LIKE.includes(st.status));
}

function isEligible(graph: SkillGraph, skillId: string, lang: string): boolean {
  return isEnabled(graph, skillId) && langWeight(graph, skillId, lang) > 0;
}

function prereqSatisfied(state: ModelState, graph: SkillGraph, prereq: string, lang: string): boolean {
  return isMasteredAnywhere(state, prereq) || !isEligible(graph, prereq, lang);
}

function prereqsSatisfied(state: ModelState, graph: SkillGraph, skillId: string, lang: string): boolean {
  return graph.skills[skillId].prereqs.every((p) => prereqSatisfied(state, graph, p, lang));
}

function speedOf(graph: SkillGraph | null | undefined, skillId: string, st: SkillState): number {
  if (st.timeEma === null) return 0;
  if (st.timeEma <= 0) return Infinity;
  return targetMs(graph, skillId, st.parEma) / st.timeEma;
}

function efficiencyFactor(st: SkillState): number {
  if (st.effEma === null) return EFF_FLOOR;
  if (st.effEma <= 0) return 1.0;
  return Math.min(Math.max(1.0 / st.effEma, EFF_FLOOR), 1.0);
}

/** min(speed, 1) * clamp(1 / effEma, 0.5, 1). */
export function confidenceOf(graph: SkillGraph | null | undefined, skillId: string, st: SkillState): number {
  if (st.timeEma === null) return 0;
  return Math.min(speedOf(graph, skillId, st), 1.0) * efficiencyFactor(st);
}

function failingGates(graph: SkillGraph, skillId: string, st: SkillState | undefined): Gate[] {
  if (!st) return ['samples', 'accuracy', 'efficiency', 'speed'];
  const failing: Gate[] = [];
  if (st.n < MASTER_N) failing.push('samples');
  if (st.acc < MASTER_ACC) failing.push('accuracy');
  if (st.effEma === null || st.effEma > MASTER_EFF) failing.push('efficiency');
  if (speedOf(graph, skillId, st) < 1.0) failing.push('speed');
  return failing;
}

/** Why a skill is not mastered yet (gates in order samples, accuracy, efficiency, speed). */
export function diagnose(state: ModelState, skillId: string, lang: string, graph: SkillGraph): Diagnosis {
  const st = getSkill(state, skillId, lang);
  if (!st) {
    return { status: null, failing: failingGates(graph, skillId, undefined), speed: 0, efficiency: null, acc: 0, n: 0 };
  }
  const efficiency = st.effEma === null || st.effEma <= 0 ? null : 1.0 / st.effEma;
  return {
    status: st.status,
    failing: failingGates(graph, skillId, st),
    speed: Math.min(speedOf(graph, skillId, st), 10.0),
    efficiency,
    acc: st.acc,
    n: st.n,
  };
}

function intervalDays(reviewsPassed: number): number {
  if (reviewsPassed >= 6) return MAX_INTERVAL_DAYS;
  return Math.min(1 << reviewsPassed, MAX_INTERVAL_DAYS);
}

function isCounted(record: AttemptRecord): boolean {
  return !record.retry && !record.hint;
}

function recentAccuracy(state: ModelState, graph: SkillGraph, skillId: string, lang: string): number {
  let total = 0;
  let correct = 0;
  for (let i = state.log.length - 1; i >= 0; i--) {
    if (total >= ACC_WINDOW) break;
    const record = state.log[i];
    if (record.lang !== lang || !isCounted(record)) continue;
    if (!recordSkills(graph, record).includes(skillId)) continue;
    total += 1;
    correct += record.ok ? 1 : 0;
  }
  return total ? correct / total : 0;
}

function logRecord(state: ModelState, record: AttemptRecord): void {
  state.log.push(record);
  state.recent = state.recent.concat([record.ex]).slice(-RECENT_MAX);
}

function ema(previous: number | null, value: number): number {
  if (previous === null) return value;
  return previous + ALPHA * (value - previous);
}

function updateStats(state: ModelState, graph: SkillGraph, skillId: string, record: AttemptRecord, st: SkillState): void {
  st.n += 1;
  st.lastSeen = record.t;
  if (record.ok) {
    const par = record.par;
    st.timeEma = ema(st.timeEma, record.ms);
    st.effEma = ema(st.effEma, par > 0 ? record.keys / par : 1.0);
    st.parEma = ema(st.parEma, par);
  }
  st.acc = recentAccuracy(state, graph, skillId, record.lang);
  st.confidence = confidenceOf(graph, skillId, st);
}

function markMastered(st: SkillState, now: number): void {
  st.status = 'mastered';
  st.reviewsPassed = 0;
  st.nextReview = now + intervalDays(0) * DAY;
}

function markDueReviews(state: ModelState, now: number): void {
  for (const langs of Object.values(state.skills)) {
    for (const st of Object.values(langs)) {
      if (st.status !== 'mastered' || st.nextReview === null) continue;
      if (st.nextReview <= now) st.status = 'review';
    }
  }
}

function ensureLang(state: ModelState, graph: SkillGraph, lang: string): void {
  for (const id of skillIds(graph)) {
    if (isEnabled(graph, id)) ensureSkill(state, graph, id, lang);
  }
}

function prepare(state: ModelState, graph: SkillGraph, lang: string, now: number): void {
  ensureLang(state, graph, lang);
  markDueReviews(state, now);
  updateUnlocks(state, graph, lang);
}

function activeCount(state: ModelState, graph: SkillGraph, lang: string): number {
  let count = 0;
  for (const id of skillIds(graph)) {
    if (!isEligible(graph, id, lang)) continue;
    const st = getSkill(state, id, lang);
    if (st && IN_ROTATION.includes(st.status)) count += 1;
  }
  return count;
}

/** Unlock skills whose prerequisites are mastered (up to 7 active), then pull in
 *  `introduced` skills while fewer than 4 are active. */
function updateUnlocks(state: ModelState, graph: SkillGraph, lang: string): void {
  const candidates = skillIds(graph).filter((id) => isEligible(graph, id, lang));
  let count = activeCount(state, graph, lang);
  for (const id of candidates) {
    if (count >= MAX_ACTIVE) break;
    const st = ensureSkill(state, graph, id, lang);
    if (st.status !== 'locked' || !prereqsSatisfied(state, graph, id, lang)) continue;
    st.status = 'active';
    count += 1;
  }
  while (count < MIN_ACTIVE) {
    const id = introduceCandidate(state, graph, lang, candidates);
    if (id === null) break;
    state.skills[id][lang].status = 'introduced';
    count += 1;
  }
}

function introduceCandidate(state: ModelState, graph: SkillGraph, lang: string, candidates: string[]): string | null {
  const locked = candidates.filter((id) => ensureSkill(state, graph, id, lang).status === 'locked');
  if (locked.length === 0) return null;
  let tier = Infinity;
  for (const id of locked) tier = Math.min(tier, graph.skills[id].tier);
  let best: string | null = null;
  let bestKey: number[] = [];
  for (const id of locked) {
    if (graph.skills[id].tier !== tier) continue;
    const prereqs = graph.skills[id].prereqs;
    const unmet = prereqs.filter((p) => !prereqSatisfied(state, graph, p, lang)).length;
    const key = [unmet, prereqs.length, graph.skills[id].order];
    if (best === null || lexLess(key, bestKey)) {
      best = id;
      bestKey = key;
    }
  }
  return best;
}

function lexLess(a: number[], b: number[]): boolean {
  for (let i = 0; i < a.length; i++) {
    if (a[i] < b[i]) return true;
    if (a[i] > b[i]) return false;
  }
  return false;
}

// Attempts ========================================================================================

/** New state with one attempt applied. Composite records credit every '+'-joined skill. */
export function applyAttempt(state: ModelState, record: AttemptRecord, graph: SkillGraph): ModelState {
  const result = cloneState(state);
  const skills = recordSkills(graph, record);
  logRecord(result, record);
  if (!record.retry) {
    // A retry repeats the exercise just shown; it is not another pick of the skill,
    // so it must not count toward the 3-in-a-row interleave limit.
    const primary = skills.length ? skills[0] : record.skill;
    result.focusHistory = result.focusHistory.concat([primary]).slice(-FOCUS_HISTORY_MAX);
  }
  prepare(result, graph, record.lang, record.t);
  if (!isCounted(record)) return result;
  for (const id of skills) credit(result, graph, id, record);
  updateUnlocks(result, graph, record.lang);
  return result;
}

/** Recompute a state from its log (records flagged `placement` are replayed as placement).
 *  Consecutive placement records form one applyPlacement batch; a language change closes it. */
export function rebuild(log: AttemptRecord[], graph: SkillGraph): ModelState {
  let state = newState(graph);
  let batch: AttemptRecord[] = [];
  for (const record of log) {
    if (batch.length && (!record.placement || record.lang !== batch[0].lang)) {
      state = applyPlacement(state, batch, graph);
      batch = [];
    }
    if (record.placement) {
      batch.push(record);
      continue;
    }
    state = applyAttempt(state, record, graph);
  }
  if (batch.length) state = applyPlacement(state, batch, graph);
  return state;
}

/** A review passes when ok, keys <= 1.5 x par and ms <= 1.3 x target time. */
export function reviewPassed(graph: SkillGraph, skillId: string, record: AttemptRecord): boolean {
  if (!record.ok) return false;
  if (record.keys > REVIEW_KEYS * record.par) return false;
  return record.ms <= REVIEW_TIME * targetMs(graph, skillId, record.par);
}

function credit(state: ModelState, graph: SkillGraph, skillId: string, record: AttemptRecord): void {
  const st = ensureSkill(state, graph, skillId, record.lang);
  // Only a skill the user forced from the stats screen is drilled while locked;
  // forcing a skill makes it active (04, Unlocking).
  if (st.status === 'locked') st.status = 'active';
  const wasReview = st.status === 'review';
  updateStats(state, graph, skillId, record, st);
  if (wasReview) {
    gradeReview(graph, skillId, st, record);
    return;
  }
  if (IN_ROTATION.includes(st.status) && failingGates(graph, skillId, st).length === 0) {
    markMastered(st, record.t);
  }
}

function gradeReview(graph: SkillGraph, skillId: string, st: SkillState, record: AttemptRecord): void {
  if (reviewPassed(graph, skillId, record)) {
    st.reviewsPassed += 1;
    st.status = 'mastered';
    st.nextReview = record.t + intervalDays(st.reviewsPassed) * DAY;
    return;
  }
  st.reviewsPassed = 0;
  st.nextReview = null;
  st.status = 'active';
  dropConfidence(graph, skillId, st);
}

function dropConfidence(graph: SkillGraph, skillId: string, st: SkillState): void {
  if (st.timeEma === null || st.confidence <= 0) return;
  const cappedSpeed = REVIEW_FAIL_FACTOR * Math.min(speedOf(graph, skillId, st), 1.0);
  st.timeEma = targetMs(graph, skillId, st.parEma) / cappedSpeed;
  st.confidence = confidenceOf(graph, skillId, st);
}

// Placement =======================================================================================

/** All prerequisites of a skill, nearest first, without duplicates. */
export function transitivePrereqs(graph: SkillGraph, skillId: string): string[] {
  const found: string[] = [];
  const queue = graph.skills[skillId].prereqs.slice();
  while (queue.length) {
    const prereq = queue.shift() as string;
    if (found.includes(prereq)) continue;
    found.push(prereq);
    queue.push(...graph.skills[prereq].prereqs);
  }
  return found;
}

/** Skills a placement pass proves: transitive prerequisites, plus tier 0 for tier >= 3. */
export function inferredFromPass(graph: SkillGraph, skillId: string): string[] {
  const found = transitivePrereqs(graph, skillId);
  if (graph.skills[skillId].tier < PLACEMENT_FOUNDATION_TIER) return found;
  const foundations = skillIds(graph).filter((id) => graph.skills[id].tier === 0 && !found.includes(id));
  return found.concat(foundations);
}

/** New state seeded from placement-test records (logged with `placement: true`). */
export function applyPlacement(state: ModelState, records: AttemptRecord[], graph: SkillGraph): ModelState {
  const result = cloneState(state);
  if (records.length === 0) return result;
  const langs: string[] = [];
  let tEnd = -Infinity;
  for (const record of records) {
    if (!langs.includes(record.lang)) langs.push(record.lang);
    tEnd = Math.max(tEnd, record.t);
  }
  for (const lang of langs) ensureLang(result, graph, lang);
  const sampled = seedPlacement(result, graph, records);
  const inferred = propagatePlacement(result, graph, sampled, tEnd);
  for (const lang of langs) {
    settlePlacement(result, graph, lang, sampled, inferred);
    updateUnlocks(result, graph, lang);
  }
  return result;
}

const keyOf = (skillId: string, lang: string): string => `${skillId}\u0000${lang}`;

function seedPlacement(state: ModelState, graph: SkillGraph, records: AttemptRecord[]): Map<string, boolean> {
  const sampled = new Map<string, boolean>();
  for (const record of records) {
    const flagged: AttemptRecord = { ...record, placement: true };
    logRecord(state, flagged);
    // A hinted or retried record is logged only, and is never a pass, so it cannot
    // propagate mastery to prerequisites.
    const counted = isCounted(flagged);
    for (const id of recordSkills(graph, flagged)) {
      const st = ensureSkill(state, graph, id, flagged.lang);
      const key = keyOf(id, flagged.lang);
      if (!counted) {
        sampled.set(key, sampled.get(key) ?? false);
        continue;
      }
      updateStats(state, graph, id, flagged, st);
      sampled.set(key, (sampled.get(key) ?? false) || Boolean(flagged.ok));
    }
  }
  return sampled;
}

function propagatePlacement(state: ModelState, graph: SkillGraph, sampled: Map<string, boolean>, now: number): Set<string> {
  const inferred = new Set<string>();
  for (const [key, passed] of sampled) {
    if (!passed) continue;
    const [skillId, lang] = key.split('\u0000');
    for (const prereq of inferredFromPass(graph, skillId)) {
      if (sampled.get(keyOf(prereq, lang)) === false) continue;
      inferMastered(ensureSkill(state, graph, prereq, lang), now);
      inferred.add(keyOf(prereq, lang));
    }
  }
  return inferred;
}

function inferMastered(st: SkillState, now: number): void {
  st.status = 'mastered';
  st.confidence = 1.0;
  st.n = Math.max(st.n, MASTER_N);
  st.acc = 1.0;
  st.reviewsPassed = PLACEMENT_INFERRED_REVIEWS;
  st.nextReview = now + intervalDays(PLACEMENT_INFERRED_REVIEWS) * DAY;
}

function settlePlacement(
  state: ModelState,
  graph: SkillGraph,
  lang: string,
  sampled: Map<string, boolean>,
  inferred: Set<string>,
): void {
  for (const key of sampled.keys()) {
    const [skillId, sampledLang] = key.split('\u0000');
    if (sampledLang !== lang || inferred.has(key)) continue;
    const st = state.skills[skillId][lang];
    if (MASTERED_LIKE.includes(st.status)) continue;
    const opens = st.confidence > PLACEMENT_ACTIVE_CONF || prereqsSatisfied(state, graph, skillId, lang);
    st.status = opens ? 'active' : 'locked';
  }
  let count = activeCount(state, graph, lang);
  for (const id of skillIds(graph)) {
    if (count >= MAX_ACTIVE) break;
    const key = keyOf(id, lang);
    if (sampled.has(key) || inferred.has(key) || !isEligible(graph, id, lang)) continue;
    const st = ensureSkill(state, graph, id, lang);
    if (st.status !== 'locked' || graph.skills[id].prereqs.length === 0) continue;
    if (!prereqsSatisfied(state, graph, id, lang)) continue;
    st.status = 'active';
    if (st.n === 0) st.confidence = PLACEMENT_INFERRED_CONF;
    count += 1;
  }
}

// Selection =======================================================================================

/**
 * Skill to drill next. With probability 0.2 the most overdue review skill. Otherwise a
 * low-weight skill (language weight <= 0.3) absent from the last 11 picks (starvation guard).
 * Otherwise the in-rotation skills are filtered (no 4th pick in a row; none with 4 of the last
 * 9 picks, so none exceeds 4 of any 10) and one of the 3 lowest by priority
 * 1 - (1 - confidence) * weight is drawn with weight (max priority of the three - priority) + 0.1.
 * Each filter is skipped when it would leave nothing. The first RNG draw is the review roll, the
 * second the weighted pick. `seed` defaults to deriveSeed(log.length, now).
 */
export function chooseFocus(
  state: ModelState,
  lang: string,
  graph: SkillGraph,
  nowSeconds: number,
  seed?: number | null,
): string | null {
  const view = cloneState(state);
  prepare(view, graph, lang, nowSeconds);
  const rng = new Mulberry32(seed === undefined || seed === null ? deriveSeed(state.log.length, nowSeconds) : seed);
  const roll = rng.next();
  const eligible = skillIds(graph).filter((id) => isEligible(graph, id, lang));
  const due = dueReviews(view, graph, lang, eligible);
  if (due.length && roll < REVIEW_P) return due[0];
  const rotation = eligible.filter((id) => IN_ROTATION.includes(view.skills[id][lang].status));
  if (rotation.length) return pickRotation(view, graph, lang, rotation, rng.next());
  if (due.length) return due[0];
  const mastered = eligible.filter((id) => view.skills[id][lang].status === 'mastered');
  if (mastered.length === 0) return null;
  return minBy(mastered, (id) => [view.skills[id][lang].confidence, orderOf(graph, id)]);
}

/** Mastered skill with the highest confidence (warm-ups are not counted). */
export function chooseWarmup(state: ModelState, lang: string, graph: SkillGraph): string | null {
  const mastered = skillIds(graph).filter(
    (id) => isEligible(graph, id, lang) && getSkill(state, id, lang)?.status === 'mastered',
  );
  if (mastered.length === 0) return null;
  return minBy(mastered, (id) => [-state.skills[id][lang].confidence, orderOf(graph, id)]);
}

/**
 * Exercise from the focus skill's pool: 1 in 5 composites when 2+ unlocked skills are above
 * 0.8 confidence, preferring ids not among the last 50, weighted by the product of the
 * tagged skills' language weights when a graph is given.
 */
export function chooseExercise(
  state: ModelState,
  skillId: string,
  lang: string,
  index: ExerciseIndex,
  rngSeed: number,
  graph?: SkillGraph | null,
): string | null {
  let pool = exercisePool(index, lang, skillId);
  if (pool.length === 0) return null;
  const rng = new Mulberry32(rngSeed);
  const compositeRoll = rng.next();
  const singles = pool.filter((entry) => entry.skills.length === 1);
  const composites = compositesOf(state, pool, skillId, lang);
  if (composites.length && compositeRoll < COMPOSITE_P && compositeReady(state, lang)) {
    pool = composites;
  } else if (singles.length) {
    pool = singles;
  } else if (composites.length) {
    pool = composites;
  }
  const candidates = freshOf(pool, state.recent);
  let weights = candidates.map((entry) => exerciseWeight(graph, entry, lang));
  let total = 0;
  for (const w of weights) total += w;
  if (total <= 0) {
    weights = candidates.map(() => 1.0);
    total = candidates.length;
  }
  const draw = rng.next() * total;
  let running = 0;
  for (let i = 0; i < candidates.length; i++) {
    running += weights[i];
    if (draw < running) return candidates[i].id;
  }
  return candidates[candidates.length - 1].id;
}

/** Normalised [{id, skills}] pool for (lang, skill) from an exercise index. */
export function exercisePool(index: ExerciseIndex, lang: string, skillId: string): PoolEntry[] {
  const root = ('langs' in index ? index.langs : index) as Record<string, Record<string, IndexEntry>>;
  let byLang: Record<string, IndexEntry> = root[lang] ?? {};
  const nested = (byLang as { skills?: unknown }).skills;
  // build/index.json: {langs: {lang: {skills: {skill: {...}}}}}
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) byLang = nested as Record<string, IndexEntry>;
  let raw: IndexEntry = byLang[skillId] ?? [];
  if (!Array.isArray(raw)) raw = raw.ids ?? raw.exercises ?? [];
  const pool: PoolEntry[] = [];
  for (const item of raw) {
    if (typeof item === 'string') {
      pool.push({ id: item, skills: [skillId] });
      continue;
    }
    const skills = item.skills && item.skills.length ? item.skills.slice() : [skillId];
    if (!skills.includes(skillId)) skills.unshift(skillId);
    pool.push({ id: item.id, skills });
  }
  return pool;
}

/** Starvation guard, then streak and share-cap filters, then a weighted draw among the weakest. */
function pickRotation(state: ModelState, graph: SkillGraph, lang: string, rotation: string[], draw: number): string {
  const history = state.focusHistory;
  const starved = starvedOf(graph, lang, rotation, history);
  if (starved.length) return minBy(starved, (id) => [orderOf(graph, id)]);
  const streak = streakSkill(history);
  let candidates = without(rotation, new Set(streak === null ? [] : [streak]));
  candidates = without(candidates, cappedOf(history));
  const ranked = candidates
    .map((id) => ({ id, p: priority(state, graph, id, lang), o: orderOf(graph, id) }))
    .sort((a, b) => (a.p < b.p ? -1 : a.p > b.p ? 1 : a.o - b.o))
    .slice(0, FOCUS_CANDIDATES);
  let top = ranked[0].p;
  for (const r of ranked) if (r.p > top) top = r.p;
  const weights = ranked.map((r) => top - r.p + FOCUS_FLOOR);
  let total = 0;
  for (const w of weights) total += w;
  const target = draw * total;
  let running = 0;
  for (let i = 0; i < ranked.length; i++) {
    running += weights[i];
    if (target < running) return ranked[i].id;
  }
  return ranked[ranked.length - 1].id;
}

/** Low-weight rotation skills not picked in the last STARVE_WINDOW - 1 picks. */
function starvedOf(graph: SkillGraph, lang: string, rotation: string[], history: string[]): string[] {
  if (history.length < STARVE_WINDOW - 1) return [];
  const recent = new Set(history.slice(-(STARVE_WINDOW - 1)));
  return rotation.filter((id) => langWeight(graph, id, lang) <= LOW_WEIGHT && !recent.has(id));
}

/** Skills that would exceed SHARE_MAX of the last SHARE_WINDOW picks if picked again. */
function cappedOf(history: string[]): Set<string> {
  const counts = new Map<string, number>();
  for (const id of history.slice(-(SHARE_WINDOW - 1))) counts.set(id, (counts.get(id) ?? 0) + 1);
  return new Set([...counts].filter(([, n]) => n >= SHARE_MAX).map(([id]) => id));
}

/** Items not in `drop`, or all items when that would leave none. */
function without(items: string[], drop: Set<string>): string[] {
  const kept = items.filter((id) => !drop.has(id));
  return kept.length ? kept : items;
}

function priority(state: ModelState, graph: SkillGraph, skillId: string, lang: string): number {
  const conf = state.skills[skillId][lang].confidence;
  return 1.0 - (1.0 - conf) * langWeight(graph, skillId, lang);
}

function dueReviews(state: ModelState, graph: SkillGraph, lang: string, eligible: string[]): string[] {
  const due = eligible.filter((id) => state.skills[id][lang].status === 'review');
  return due.sort((a, b) => {
    const ka = state.skills[a][lang].nextReview || 0;
    const kb = state.skills[b][lang].nextReview || 0;
    return ka - kb || orderOf(graph, a) - orderOf(graph, b);
  });
}

function streakSkill(history: string[]): string | null {
  const tail = history.slice(-MAX_STREAK);
  if (tail.length < MAX_STREAK || tail.some((id) => id !== tail[0])) return null;
  return tail[0];
}

function minBy(items: string[], key: (id: string) => number[]): string {
  let best = items[0];
  let bestKey = key(best);
  for (let i = 1; i < items.length; i++) {
    const k = key(items[i]);
    if (lexLess(k, bestKey)) {
      best = items[i];
      bestKey = k;
    }
  }
  return best;
}

function unlockedState(state: ModelState, skillId: string, lang: string): SkillState | null {
  const st = getSkill(state, skillId, lang);
  if (!st || st.status === 'locked') return null;
  return st;
}

function compositeReady(state: ModelState, lang: string): boolean {
  let count = 0;
  for (const id of Object.keys(state.skills)) {
    const st = unlockedState(state, id, lang);
    if (st && st.confidence > COMPOSITE_CONF) count += 1;
  }
  return count >= 2;
}

function compositesOf(state: ModelState, pool: PoolEntry[], skillId: string, lang: string): PoolEntry[] {
  return pool.filter(
    (entry) =>
      entry.skills.length >= 2 &&
      entry.skills.every((other) => other === skillId || unlockedState(state, other, lang) !== null),
  );
}

function freshOf(pool: PoolEntry[], recent: string[]): PoolEntry[] {
  const seen = new Set(recent);
  const fresh = pool.filter((entry) => !seen.has(entry.id));
  if (fresh.length) return fresh;
  const lastSeen = new Map<string, number>();
  recent.forEach((id, position) => lastSeen.set(id, position));
  let best = pool[0];
  for (const entry of pool) {
    if ((lastSeen.get(entry.id) as number) < (lastSeen.get(best.id) as number)) best = entry;
  }
  return [best];
}

function exerciseWeight(graph: SkillGraph | null | undefined, entry: PoolEntry, lang: string): number {
  let weight = 1.0;
  for (const id of entry.skills) weight *= langWeight(graph, id, lang);
  return weight;
}

// Projection ======================================================================================

/**
 * Least-squares fit of the last 30 counted correct attempts' ms (linear below 15 points,
 * quadratic from 15); shown when R^2 >= 0.5; attemptsToTarget is the first step ahead
 * (<= 30) where the fit reaches target_ms, 0 if already there, null if not within 30.
 */
export function projection(state: ModelState, skillId: string, lang: string, graph?: SkillGraph | null): Projection {
  const ys = recentTimes(state, skillId, lang, graph);
  if (ys.length < PROJECTION_MIN_N) return { fit: 'none', attemptsToTarget: null, r2: 0 };
  const degree = ys.length >= PROJECTION_QUADRATIC_N ? 2 : 1;
  const coeffs = fitPolynomial(ys, degree);
  const r2 = rSquared(ys, coeffs);
  if (r2 < PROJECTION_MIN_R2) return { fit: 'none', attemptsToTarget: null, r2 };
  const fit = degree === 2 ? 'quadratic' : 'linear';
  const st = getSkill(state, skillId, lang);
  if (!st || st.parEma === null) return { fit, attemptsToTarget: null, r2 };
  const target = targetMs(graph, skillId, st.parEma);
  return { fit, attemptsToTarget: attemptsToTarget(coeffs, ys.length, target), r2 };
}

export function recentTimes(state: ModelState, skillId: string, lang: string, graph?: SkillGraph | null): number[] {
  const times: number[] = [];
  for (let i = state.log.length - 1; i >= 0; i--) {
    if (times.length >= PROJECTION_WINDOW) break;
    const record = state.log[i];
    if (record.lang !== lang || !record.ok || !isCounted(record)) continue;
    const skills = graph ? recordSkills(graph, record) : record.skill.split('+');
    if (!skills.includes(skillId)) continue;
    times.push(record.ms);
  }
  return times.reverse();
}

export function fitPolynomial(ys: number[], degree: number): number[] {
  const size = degree + 1;
  const matrix: number[][] = [];
  for (let r = 0; r < size; r++) matrix.push(new Array(size).fill(0));
  const rhs: number[] = new Array(size).fill(0);
  for (let i = 0; i < ys.length; i++) {
    const powers = powersOf(i, 2 * degree);
    for (let row = 0; row < size; row++) {
      rhs[row] += powers[row] * ys[i];
      for (let col = 0; col < size; col++) matrix[row][col] += powers[row + col];
    }
  }
  return solve(matrix, rhs);
}

export function evaluatePolynomial(coeffs: number[], x: number): number {
  let total = 0;
  let power = 1;
  for (const coeff of coeffs) {
    total += coeff * power;
    power = power * x;
  }
  return total;
}

export function rSquared(ys: number[], coeffs: number[]): number {
  let mean = 0;
  for (const y of ys) mean += y;
  mean = mean / ys.length;
  let ssTot = 0;
  let ssRes = 0;
  for (let i = 0; i < ys.length; i++) {
    const residual = ys[i] - evaluatePolynomial(coeffs, i);
    ssRes += residual * residual;
    ssTot += (ys[i] - mean) * (ys[i] - mean);
  }
  if (ssTot <= 0) return 0;
  return 1.0 - ssRes / ssTot;
}

function powersOf(x: number, highest: number): number[] {
  const powers = [1.0];
  for (let i = 0; i < highest; i++) powers.push(powers[powers.length - 1] * x);
  return powers;
}

function solve(matrix: number[][], rhs: number[]): number[] {
  const size = rhs.length;
  const a = matrix.map((row, i) => row.concat([rhs[i]]));
  for (let col = 0; col < size; col++) {
    let pivot = col;
    for (let row = col + 1; row < size; row++) {
      if (Math.abs(a[row][col]) > Math.abs(a[pivot][col])) pivot = row;
    }
    const tmp = a[col];
    a[col] = a[pivot];
    a[pivot] = tmp;
    if (a[col][col] === 0) return new Array(size).fill(0);
    for (let row = col + 1; row < size; row++) {
      const factor = a[row][col] / a[col][col];
      for (let k = col; k <= size; k++) a[row][k] -= factor * a[col][k];
    }
  }
  const coeffs: number[] = new Array(size).fill(0);
  for (let row = size - 1; row >= 0; row--) {
    let total = a[row][size];
    for (let k = row + 1; k < size; k++) total -= a[row][k] * coeffs[k];
    coeffs[row] = total / a[row][row];
  }
  return coeffs;
}

function attemptsToTarget(coeffs: number[], n: number, target: number): number | null {
  const last = n - 1;
  if (evaluatePolynomial(coeffs, last) <= target) return 0;
  for (let step = 1; step <= PROJECTION_AHEAD; step++) {
    if (evaluatePolynomial(coeffs, last + step) <= target) return step;
  }
  return null;
}

// Session summary =================================================================================

/**
 * What changed since `sinceT`: confidence gains >= 0.1 (largest first), new masteries, new
 * unlocks, and the tip of the most-improved skill that has one (graph.tips). The state
 * before the session is rebuilt from the log, hence the graph argument.
 */
export function sessionSummary(state: ModelState, sinceT: number, graph: SkillGraph): SessionSummary {
  const langs: string[] = [];
  for (const record of state.log) {
    if (record.t >= sinceT && !langs.includes(record.lang)) langs.push(record.lang);
  }
  const before = rebuild(state.log.filter((record) => record.t < sinceT), graph);
  for (const lang of langs) ensureLang(before, graph, lang); // a language new this session starts as ensureSkill makes it
  const gains = new Map<string, number>();
  const mastered: string[] = [];
  const unlocked: string[] = [];
  for (const id of skillIds(graph)) {
    for (const lang of langs) {
      const oldView = viewOf(before, graph, id, lang);
      const newView = viewOf(state, graph, id, lang);
      const delta = newView.confidence - oldView.confidence;
      if (delta > (gains.get(id) ?? 0)) gains.set(id, delta);
      if (MASTERED_LIKE.includes(newView.status) && !MASTERED_LIKE.includes(oldView.status) && !mastered.includes(id)) {
        mastered.push(id);
      }
      if (IN_ROTATION.includes(newView.status) && oldView.status === 'locked' && !unlocked.includes(id)) {
        unlocked.push(id);
      }
    }
  }
  const ranked = [...gains.keys()].sort(
    (a, b) => (gains.get(b) as number) - (gains.get(a) as number) || orderOf(graph, a) - orderOf(graph, b),
  );
  const improved = ranked
    .filter((id) => (gains.get(id) as number) >= IMPROVED_DELTA - EPSILON)
    .map((id) => ({ skill: id, delta: gains.get(id) as number }));
  let tip: string | null = null;
  const tips = graph.tips ?? {};
  for (const id of ranked.concat(mastered)) {
    if (tips[id] !== undefined) {
      tip = tips[id];
      break;
    }
  }
  return { improved, mastered, unlocked, tip };
}

function viewOf(state: ModelState, graph: SkillGraph, skillId: string, lang: string): { status: Status; confidence: number } {
  const st = getSkill(state, skillId, lang);
  if (st) return { status: st.status, confidence: st.confidence };
  if (isMasteredAnywhere(state, skillId)) return { status: 'mastered', confidence: 0 };
  const opened = graph.skills[skillId].tier === 0 || isUnlockedAnywhere(state, skillId);
  return { status: opened ? 'active' : 'locked', confidence: 0 };
}
