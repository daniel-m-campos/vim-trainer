// Type a key string in Vim notation into a Playwright page, one keystroke per token,
// as oracle.tokenize_keys splits it: <Esc>, <CR>, <Tab>, <BS>, <C-x> chords, else literal
// characters ("<" not followed by a known name is a literal "<").
const NAMED = { Esc: "Escape", CR: "Enter", Tab: "Tab", BS: "Backspace" };
const TOKEN = /<(?:Esc|CR|Tab|BS|C-[a-z\[\]])>|./gs;

export async function typeKeys(page, keys) {
  for (const tok of keys.match(TOKEN) ?? []) {
    if (tok.length > 1 && tok.startsWith("<C-")) await page.keyboard.press(`Control+${tok[3] === "[" ? "BracketLeft" : tok[3] === "]" ? "BracketRight" : tok[3]}`);
    else if (tok.length > 1) await page.keyboard.press(NAMED[tok.slice(1, -1)]);
    else await page.keyboard.type(tok);
  }
}
