// Skill graph. model/gen_graph.py generates it from model/skill-graph.md and
// writes an identical copy to app/src/model/skill-graph.json, which is bundled here
// (no fetch, so the model always gets a well-formed graph).

import rawGraph from "./model/skill-graph.json";
import { applyProfile, type SkillGraph } from "./modelApi.ts";
import type { EditorProfile } from "./types.ts";

export interface NodeView {
  id: string;
  tier: number;
  prereqs: string[];
}

export function baseGraph(): SkillGraph {
  return rawGraph as unknown as SkillGraph;
}

/**
 * The graph the model runs on: the editor profile applied (skills the editor does not
 * support are disabled), then every skill with no exercises in `withContent` disabled.
 *
 * Note: content exists for 26 Python and 16 C++ skills (tiers 1-8) only. Disabling the rest makes the
 * model treat them as satisfied prerequisites (disabled prereqs count as met), so the
 * drillable skills unlock and focus never lands on a skill with nothing to practise.
 * Drop the second step once tier 0 and the other skills have content.
 */
export function drillGraph(profile: EditorProfile, withContent: Set<string>): SkillGraph {
  const g = applyProfile(baseGraph(), profile);
  for (const [id, node] of Object.entries(g.skills)) if (!withContent.has(id)) node.enabled = false;
  return g;
}

export function graphNodes(graph: SkillGraph): NodeView[] {
  return Object.values(graph.skills).map((n) => ({ id: n.id, tier: n.tier, prereqs: n.prereqs ?? [] }));
}
