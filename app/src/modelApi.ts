// Single import point for the adaptive model (app/src/model/model.ts, the TypeScript
// mirror of model/vimtrainer_model; both are checked against model/vectors/*.json).
// Thin wrappers only: null "no choice" results become "" so callers can test truthiness.

import * as model from "./model/model.ts";
import type { ExerciseIndex, ModelState, SkillGraph } from "./model/model.ts";

export type { AttemptRecord, ModelState, SkillGraph, SkillState, Status as SkillStatus, SessionSummary } from "./model/model.ts";
export { applyAttempt, applyPlacement, applyProfile, chooseWarmup, newState, projection, sessionSummary } from "./model/model.ts";

export const chooseFocus = (s: ModelState, lang: string, g: SkillGraph, nowSec: number): string =>
  model.chooseFocus(s, lang, g, nowSec) ?? "";

export const chooseExercise = (s: ModelState, skill: string, lang: string, index: unknown, seed: number, g: SkillGraph): string =>
  model.chooseExercise(s, skill, lang, index as ExerciseIndex, seed, g) ?? "";
