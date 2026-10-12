// x-axis labels of the stats charts never name an attempt that is not plotted.
import { test } from "node:test";
import assert from "node:assert/strict";
import { stepChart, timeChart } from "./charts.ts";

const xLabels = (svg: string): number[] =>
  [...svg.matchAll(/<text class="sv-tick" x="[^"]+" y="[^"]+" text-anchor="middle">(\d+)<\/text>/g)].map((m) => Number(m[1]));

test("one attempt: the step chart labels attempt 1 only", () => {
  assert.deepEqual(xLabels(stepChart({ ratios: [1.4], limit: 1.25, label: "t" })), [1]);
});

test("one attempt, no projection: the time chart labels attempt 1 only", () => {
  assert.deepEqual(xLabels(timeChart({ times: [4000], targetMs: 2000, projection: null, crossing: null, label: "t" })), [1]);
});

test("a projection extends the time chart's labels to its last point", () => {
  const projection = [{ x: 1, y: 3000 }, { x: 5, y: 2000 }];
  const labels = xLabels(timeChart({ times: [4000, 3500], targetMs: 2000, projection, crossing: 5, label: "t" }));
  assert.equal(Math.max(...labels), 6);
});
