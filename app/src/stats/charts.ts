// Hand-rolled SVG charts for the stats screen; the projection fit is model.ts `projection`.
// No dependency: two small chart forms, returned as SVG strings.
//
// Dataviz rules applied: one y axis per chart (time and keys/par are separate charts),
// thin 2px lines, recessive grid, inline labels instead of a legend, values printed on
// the chart (last value, target, projection end) so nothing needs hover, and a native
// <title> tooltip per attempt for pointer users. Colours come from the app's CSS tokens
// through classes styled in stats.css (series --mode blue, projection --accent amber,
// references neutral); the blue/amber pair passes the CVD check, and the projection is
// also dashed so identity never rests on colour alone.

export interface Point {
  x: number;
  y: number;
}

export interface TimeChartInput {
  /** Time to solve (ms) of each counted correct attempt, oldest first. */
  times: number[];
  /** Target time (ms) for the skill, or null when there is no par estimate yet. */
  targetMs: number | null;
  /** Fitted projection in attempt-index space (x = index into `times`), or null. */
  projection: Point[] | null;
  /** Index where the projection reaches the target, if it does. */
  crossing: number | null;
  /** Accessible name for the chart. */
  label: string;
}

export interface StepChartInput {
  /** keys / par of each counted correct attempt, oldest first. */
  ratios: number[];
  /** Mastery limit on keys/par (MASTER_EFF). */
  limit: number;
  label: string;
}

const W = 460;
const H = 190;
const M = { top: 16, right: 54, bottom: 28, left: 40 };
const PW = W - M.left - M.right;
const PH = H - M.top - M.bottom;

let clipSeq = 0;

/** "Nice" tick values covering [lo, hi], about `count` of them. */
export function niceTicks(lo: number, hi: number, count = 4): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const ticks: number[] = [];
  for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + 1e-9; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks;
}

function scale(d0: number, d1: number, r0: number, r1: number): (v: number) => number {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (v) => r0 + (v - d0) * k;
}

const f1 = (v: number) => v.toFixed(1);
const f2 = (v: number) => v.toFixed(2);
const r = (v: number) => v.toFixed(1);

function frame(label: string, body: string): string {
  return `<svg class="sv-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${label}" preserveAspectRatio="xMidYMid meet">${body}</svg>`;
}

function yGrid(ticks: number[], y: (v: number) => number, fmt: (v: number) => string): string {
  return ticks
    .map((t) => {
      const py = r(y(t));
      return `<line class="sv-gridline" x1="${M.left}" x2="${M.left + PW}" y1="${py}" y2="${py}"/><text class="sv-tick" x="${M.left - 6}" y="${py}" dy="0.32em" text-anchor="end">${fmt(t)}</text>`;
    })
    .join("");
}

/**
 * x ticks at attempt numbers (1-based labels for 0-based indices), none past `lastIndex`
 * (the last attempt or projection point plotted), so no label names a missing attempt.
 */
function xAxis(maxIndex: number, lastIndex: number, x: (v: number) => number): string {
  const ticks = niceTicks(1, Math.max(2, maxIndex + 1), 5).filter((t) => Number.isInteger(t) && t >= 1 && t - 1 <= lastIndex);
  const base = `<line class="sv-axis" x1="${M.left}" x2="${M.left + PW}" y1="${M.top + PH}" y2="${M.top + PH}"/>`;
  const labels = ticks
    .map((t) => `<text class="sv-tick" x="${r(x(t - 1))}" y="${M.top + PH + 16}" text-anchor="middle">${t}</text>`)
    .join("");
  return base + labels;
}

/** Text with a surface-coloured halo so it stays legible over lines. */
function label(x: number, y: number, text: string, anchor: "start" | "middle" | "end", cls = "sv-label"): string {
  return `<text class="${cls}" x="${r(x)}" y="${r(y)}" text-anchor="${anchor}">${text}</text>`;
}

/** Reference line across the plot with its name in the right margin (above or below the line). */
function refLine(py: number, above: string, below: string): string {
  const x = M.left + PW + 6;
  let out = `<line class="sv-ref" x1="${M.left}" x2="${M.left + PW}" y1="${r(py)}" y2="${r(py)}"/>`;
  if (above) out += label(x, py - 4, above, "start", "sv-label sv-muted");
  if (below) out += label(x, py + 12, below, "start", "sv-label sv-muted");
  return out;
}

/** Clamp a label x so text anchored there stays inside the plot. */
function anchorFor(px: number): "start" | "middle" | "end" {
  if (px > M.left + PW - 40) return "end";
  if (px < M.left + 40) return "start";
  return "middle";
}

/**
 * Time-to-solve line over attempts, with the target as a dashed neutral reference and
 * the projection as a dashed amber continuation from the last attempt.
 */
export function timeChart(input: TimeChartInput): string {
  const { times, targetMs, projection, crossing } = input;
  const n = times.length;
  const projEnd = projection && projection.length ? projection[projection.length - 1].x : n - 1;
  const xMax = Math.max(n - 1, projEnd, 1);
  const dataMax = Math.max(...times, targetMs ?? 0);
  // The y range comes from the data and target only; a projection that leaves it is clipped
  // rather than allowed to squash the chart.
  const yMax = dataMax * 1.12;
  const yTicks = niceTicks(0, yMax / 1000, 4);
  const yTop = Math.max(yMax, (yTicks[yTicks.length - 1] ?? 0) * 1000);
  const x = scale(0, xMax, M.left, M.left + PW);
  const y = scale(0, yTop, M.top + PH, M.top);
  const clip = `sv-clip-${++clipSeq}`;
  let body = `<defs><clipPath id="${clip}"><rect x="${M.left}" y="${M.top - 4}" width="${PW + 4}" height="${PH + 4}"/></clipPath></defs>`;
  body += yGrid(yTicks, (t) => y(t * 1000), f1);
  body += `<text class="sv-unit" x="${M.left - 6}" y="${M.top - 6}" text-anchor="end">s</text>`;
  body += xAxis(xMax, Math.max(n - 1, projEnd, 0), x);

  if (targetMs !== null) {
    body += refLine(y(targetMs), "target", `${f1(targetMs / 1000)} s`);
  }

  if (projection && projection.length > 1) {
    const d = projection.map((p, i) => `${i ? "L" : "M"}${r(x(p.x))},${r(y(Math.max(0, p.y)))}`).join("");
    body += `<path class="sv-proj" clip-path="url(#${clip})" d="${d}"/>`;
    if (crossing !== null && targetMs !== null && crossing > n - 1) {
      const cx = x(crossing);
      const cy = y(targetMs);
      body += `<circle class="sv-proj-dot" cx="${r(cx)}" cy="${r(cy)}" r="4"/>`;
      body += label(cx, cy + 16, `+${crossing - (n - 1)}`, anchorFor(cx), "sv-label");
    } else {
      const last = projection[projection.length - 1];
      const px = x(last.x);
      const py = Math.min(Math.max(y(Math.max(0, last.y)), M.top + 10), M.top + PH - 4);
      const above = targetMs === null || py < y(targetMs);
      body += label(px, above ? py - 7 : py + 15, "projected", "end", "sv-label sv-muted");
    }
  }

  if (n) {
    const d = times.map((t, i) => `${i ? "L" : "M"}${r(x(i))},${r(y(t))}`).join("");
    body += `<path class="sv-line" d="${d}"/>`;
    const lx = x(n - 1);
    const ly = y(times[n - 1]);
    body += `<circle class="sv-dot" cx="${r(lx)}" cy="${r(ly)}" r="4"/>`;
    body += label(lx, ly - 9, `${f1(times[n - 1] / 1000)} s`, anchorFor(lx), "sv-label sv-value");
    // Hover layer: one column per attempt, bigger than the mark.
    const col = PW / Math.max(1, xMax);
    body += times
      .map((t, i) => `<rect class="sv-hit" x="${r(x(i) - col / 2)}" y="${M.top}" width="${r(col)}" height="${PH}"><title>attempt ${i + 1}: ${f1(t / 1000)} s</title></rect>`)
      .join("");
  }
  return frame(input.label, body);
}

/**
 * keys/par as a step chart (discrete, so no fit): each attempt holds its value until
 * the next one. References at 1.0 (par) and the mastery limit.
 */
export function stepChart(input: StepChartInput): string {
  const { ratios, limit } = input;
  const n = ratios.length;
  const lo = Math.min(1, ...ratios);
  const hi = Math.max(limit + 0.25, ...ratios);
  const yTicks = niceTicks(Math.max(0, Math.floor(lo * 4) / 4 - 0.25), hi, 4);
  const y0 = Math.min(yTicks[0], lo);
  const y1 = Math.max(yTicks[yTicks.length - 1], hi);
  const xMax = Math.max(n, 2);
  const x = scale(0, xMax, M.left, M.left + PW);
  const y = scale(y0, y1, M.top + PH, M.top);
  let body = yGrid(yTicks, y, f2);
  body += `<text class="sv-unit" x="${M.left - 6}" y="${M.top - 6}" text-anchor="end">x par</text>`;
  // Steps span [i, i + 1); tick k labels attempt k at the step's left edge.
  const ticks = niceTicks(1, Math.max(2, n), 5).filter((t) => Number.isInteger(t) && t >= 1 && t <= n);
  body += `<line class="sv-axis" x1="${M.left}" x2="${M.left + PW}" y1="${M.top + PH}" y2="${M.top + PH}"/>`;
  body += ticks.map((t) => `<text class="sv-tick" x="${r(x(t - 0.5))}" y="${M.top + PH + 16}" text-anchor="middle">${t}</text>`).join("");

  // par is labelled below its line and the limit above, so the two never collide.
  body += refLine(y(1), "", "par");
  body += refLine(y(limit), "limit", "");

  if (n) {
    let d = `M${r(x(0))},${r(y(ratios[0]))}`;
    for (let i = 0; i < n; i++) {
      if (i) d += `V${r(y(ratios[i]))}`;
      d += `H${r(x(i + 1))}`;
    }
    body += `<path class="sv-line" d="${d}"/>`;
    const lx = x(n - 0.5);
    const ly = y(ratios[n - 1]);
    body += label(lx, ly - 7, `${f2(ratios[n - 1])}x`, anchorFor(lx), "sv-label sv-value");
    body += ratios
      .map((v, i) => `<rect class="sv-hit" x="${r(x(i))}" y="${M.top}" width="${r(x(i + 1) - x(i))}" height="${PH}"><title>attempt ${i + 1}: ${f2(v)} x par</title></rect>`)
      .join("");
  }
  return frame(input.label, body);
}
