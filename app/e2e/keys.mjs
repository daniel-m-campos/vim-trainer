// Type a key string in Vim notation into a Playwright page, one keystroke per token,
// as oracle.tokenize_keys splits it: named keys (<Esc>, <CR>, <Space>, <Up>, <lt>, <F1>, ...)
// and modifier chords (<C-x>, <S-Tab>, <M-a>, ...), else literal characters ("<" not
// followed by a known name is a literal "<"). TOKEN mirrors oracle.py _KEY_TOKEN.
const NAMES = "Esc|CR|Enter|Return|NL|BS|Tab|Space|lt|Bar|Bslash|Del|Insert|Home|End|PageUp|PageDown"
  + "|Up|Down|Left|Right|Nul|F[0-9]{1,2}";
const TOKEN = new RegExp(`<(?:(?:[CSMAD]-)+(?:${NAMES}|[^<>\\s])|${NAMES})>|.`, "gis");

// Vim key name (lower-cased) -> Playwright key name, or the single character it stands for.
const NAMED = {
  esc: "Escape", cr: "Enter", enter: "Enter", return: "Enter", bs: "Backspace", tab: "Tab",
  del: "Delete", insert: "Insert", home: "Home", end: "End", pageup: "PageUp", pagedown: "PageDown",
  up: "ArrowUp", down: "ArrowDown", left: "ArrowLeft", right: "ArrowRight",
  space: " ", lt: "<", bar: "|", bslash: "\\",
};
const MODS = { c: "Control", s: "Shift", m: "Alt", a: "Alt", d: "Meta" };

// Split a key string into keystroke tokens, like oracle.tokenize_keys; used by typeKeys and tests.
export function tokenize(keys) {
  return keys.match(TOKEN) ?? [];
}

// Turn one token into ["type", text] or ["press", playwrightKey]; used by typeKeys and tests.
// Throws for <F13>..<F99>: Playwright knows only F1-F12 (editor.mjs smoke-tests the names).
export function keyAction(tok) {
  if (tok.length === 1 || !tok.startsWith("<")) return ["type", tok];
  const [, modStr, name] = tok.slice(1, -1).match(/^((?:[CSMAD]-)*)(.+)$/is);
  const mods = modStr.split("-").filter(Boolean).map((m) => MODS[m.toLowerCase()]);
  const lower = name.toLowerCase();
  let key = name.length === 1 ? name : NAMED[lower] ?? (/^f\d+$/.test(lower) ? lower.toUpperCase() : undefined);
  if (/^f\d+$/.test(lower) && Number(lower.slice(1)) > 12) throw new Error(`${tok}: Playwright has no key past F12`);
  if (lower === "nl") return ["press", [...mods, "Control", "j"].join("+")];  // <NL> is <C-j>
  if (lower === "nul") return ["press", [...mods, "Control", "@"].join("+")];  // <Nul> is <C-@>
  if (mods.length === 0) return key.length === 1 ? ["type", key] : ["press", key];
  if (key.length === 1 && mods.every((m) => m === "Shift")) return ["type", key.toUpperCase()];  // <S-a> is A
  if (key === "[") key = "BracketLeft";
  else if (key === "]") key = "BracketRight";
  else if (key === " ") key = "Space";
  else if (key.length === 1) key = key.toLowerCase();  // <C-V> is <C-v>
  return ["press", [...mods, key].join("+")];
}

export async function typeKeys(page, keys) {
  for (const tok of tokenize(keys)) {
    const [how, what] = keyAction(tok);
    if (how === "press") await page.keyboard.press(what);
    else await page.keyboard.type(what);
  }
}
