// Tiny DOM helpers. No framework (tech-stack.md): the screens are a few regions and a key handler.

export function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

/** `code` -> <code>code</code>, escaped. */
export const code = (s: string) => `<code>${esc(s)}</code>`;

/** Task sentence: text in backticks becomes a literal span so what to type is unambiguous. */
export function taskHtml(task: string): string {
  return task
    .split(/(`[^`]*`)/)
    .map((part) => (part.startsWith("`") && part.endsWith("`") && part.length >= 2 ? `<span class="lit">${esc(part.slice(1, -1))}</span>` : esc(part)))
    .join("");
}

export function $(sel: string, root: ParentNode = document): HTMLElement {
  const el = root.querySelector<HTMLElement>(sel);
  if (!el) throw new Error(`missing ${sel}`);
  return el;
}

export function confidenceBar(c: number): string {
  const pct = Math.round(Math.max(0, Math.min(1, c)) * 100);
  return `<span class="bar" aria-label="confidence ${c.toFixed(2)}"><i style="width:${pct}%"></i></span>`;
}

export function fmtSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`;
}
