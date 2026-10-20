// Pure tests for the e2e key-notation tokeniser (no browser): node --test e2e/keys.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { tokenize, keyAction } from "./keys.mjs";

test("tokenize matches the oracle docstring example", () => {
  assert.deepEqual(tokenize("3<C-a>:w<CR>"), ["3", "<C-a>", ":", "w", "<CR>"]);
});

test("tokenize keeps named keys and chords whole, any case", () => {
  assert.deepEqual(tokenize("<C-v>2j$A;<Esc>"), ["<C-v>", "2", "j", "$", "A", ";", "<Esc>"]);
  assert.deepEqual(tokenize("<space><Up><S-Tab><M-x><F12>"), ["<space>", "<Up>", "<S-Tab>", "<M-x>", "<F12>"]);
  assert.deepEqual(tokenize("<C-S-Left><lt><Bar><Bslash>"), ["<C-S-Left>", "<lt>", "<Bar>", "<Bslash>"]);
});

test("tokenize treats an unknown <...> as literal characters", () => {
  assert.deepEqual(tokenize("i<div><Esc>"), ["i", "<", "d", "i", "v", ">", "<Esc>"]);
  assert.deepEqual(tokenize("a< b<C- x>"), ["a", "<", " ", "b", "<", "C", "-", " ", "x", ">"]);
});

test("existing tokens map exactly as before", () => {
  assert.deepEqual(keyAction("<Esc>"), ["press", "Escape"]);
  assert.deepEqual(keyAction("<CR>"), ["press", "Enter"]);
  assert.deepEqual(keyAction("<Tab>"), ["press", "Tab"]);
  assert.deepEqual(keyAction("<BS>"), ["press", "Backspace"]);
  assert.deepEqual(keyAction("<C-x>"), ["press", "Control+x"]);
  assert.deepEqual(keyAction("<C-[>"), ["press", "Control+BracketLeft"]);
  assert.deepEqual(keyAction("<C-]>"), ["press", "Control+BracketRight"]);
  assert.deepEqual(keyAction("<"), ["type", "<"]);
  assert.deepEqual(keyAction("x"), ["type", "x"]);
});

test("new named keys map to Playwright names or typed characters", () => {
  const cases = {
    "<Up>": ["press", "ArrowUp"], "<Down>": ["press", "ArrowDown"],
    "<Left>": ["press", "ArrowLeft"], "<Right>": ["press", "ArrowRight"],
    "<Home>": ["press", "Home"], "<End>": ["press", "End"], "<Del>": ["press", "Delete"],
    "<PageUp>": ["press", "PageUp"], "<PageDown>": ["press", "PageDown"],
    "<Insert>": ["press", "Insert"], "<Enter>": ["press", "Enter"], "<Return>": ["press", "Enter"],
    "<F1>": ["press", "F1"], "<f10>": ["press", "F10"], "<esc>": ["press", "Escape"],
    "<Space>": ["type", " "], "<lt>": ["type", "<"], "<Bar>": ["type", "|"], "<Bslash>": ["type", "\\"],
    "<NL>": ["press", "Control+j"], "<Nul>": ["press", "Control+@"],
  };
  for (const [tok, want] of Object.entries(cases)) assert.deepEqual(keyAction(tok), want, tok);
});

test("modifier chords", () => {
  const cases = {
    "<C-v>": ["press", "Control+v"], "<C-r>": ["press", "Control+r"], "<C-a>": ["press", "Control+a"],
    "<C-o>": ["press", "Control+o"], "<C-w>": ["press", "Control+w"], "<C-u>": ["press", "Control+u"],
    "<C-d>": ["press", "Control+d"], "<C-V>": ["press", "Control+v"], "<c-v>": ["press", "Control+v"],
    "<S-Tab>": ["press", "Shift+Tab"], "<S-Up>": ["press", "Shift+ArrowUp"], "<S-a>": ["type", "A"],
    "<C-S-Left>": ["press", "Control+Shift+ArrowLeft"], "<M-x>": ["press", "Alt+x"],
    "<A-x>": ["press", "Alt+x"], "<D-s>": ["press", "Meta+s"], "<C-Space>": ["press", "Control+Space"],
    "<C-->": ["press", "Control+-"], "<C-Bslash>": ["press", "Control+\\"],
  };
  for (const [tok, want] of Object.entries(cases)) assert.deepEqual(keyAction(tok), want, tok);
});

test("every token tokenize emits maps to an action", () => {
  for (const tok of tokenize("<C-v>j<S-Right><Bar><lt><Nul><NL><F5>x<C-^><C-@>")) {
    const [how, what] = keyAction(tok);
    assert.ok((how === "press" || how === "type") && typeof what === "string" && what.length > 0, tok);
  }
});

test("F13 and above throw: Playwright has no key for them", () => {
  assert.deepEqual(keyAction("<F12>"), ["press", "F12"]);
  assert.throws(() => keyAction("<F13>"), /no key past F12/);
  assert.throws(() => keyAction("<C-F24>"), /no key past F12/);
});
