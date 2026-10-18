// Unit tests for grading. Run: npm test (node --test, native TS type stripping).
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  tokenize, displayKeys, replayKeys, splitKeys, checkPass, band, isGiveUp, armsGiveUp, PausableClock, tabSpaces, chooseHint, diffLines, usedExCommand, targetRange, targetRanges, exerciseHints, placementPass, unrecoverable,
  type KeyEvent, type Mode,
} from "./grading.ts";
import type { Exercise } from "./types.ts";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const ev = (key: string, mode: Mode = "normal", cmdline = false, active = 0): KeyEvent => ({ key, mode, cmdline, active });

function typed(seq: [string, Mode, boolean?][]): KeyEvent[] {
  return seq.map(([k, m, c], i) => ev(k, m, !!c, i * 100));
}

const quote: Exercise = {
  id: "py/t.quote/0001", skill: "t.quote", lang: "python", kind: "edit",
  task: "Change the string passed to `logger.warn` to `retrying`",
  start: { lines: ["x = 1", '    logger.warn("timeout, trying again")'], cursor: [2, 4] },
  expect: { lines: ["x = 1", '    logger.warn("retrying")'] },
  par: { keys: 'ci"retrying<Esc>', count: 12 },
  hints: [{ trigger: '^f"', text: "ci\" works from anywhere" }, "plain hint"],
};

// ci"retrying<Esc>: c i " in normal, text in insert, <Esc> pressed in insert.
const ciQuote = (): KeyEvent[] => [
  ev("c"), ev("i"), ev('"'),
  ..."retrying".split("").map((c) => ev(c, "insert")),
  ev("<Esc>", "insert"),
];

test("ci\"retrying<Esc> is 12 keys and displays as typed", () => {
  const t = tokenize(ciQuote(), "esc", "normal");
  assert.equal(t.length, 12);
  assert.equal(displayKeys(t), 'ci"retrying<Esc>');
});

test("the jk escape displays as jk but is logged for replay as <Esc>", () => {
  const t = tokenize([ev("c"), ev("w"), ev("x", "insert"), ev("j", "insert"), ev("k", "insert")], "jk", "normal");
  assert.equal(displayKeys(t), "cwxjk");
  assert.equal(replayKeys(t), "cwx<Esc>");
});

test("splitKeys counts notation tokens as one key", () => {
  assert.equal(splitKeys('ci"retrying<Esc>').length, 12);
  assert.equal(splitKeys(":g/print/d<CR>").length, 11);
  assert.deepEqual(splitKeys("<C-v>3jA;<C-[>"), ["<C-v>", "3", "j", "A", ";", "<C-[>"]);
});

test("insert-mode <Space> displays as a space but still counts once", () => {
  const t = tokenize([ev("i"), ev("a", "insert"), ev("<Space>", "insert"), ev("b", "insert"), ev("<Esc>", "insert")], "esc", "normal");
  assert.equal(displayKeys(t), "ia b<Esc>");
  assert.equal(t.length, 5);
});

test("jk escape counts as one key when it leaves insert mode", () => {
  const events = [ev("i"), ev("x", "insert"), ev("j", "insert"), ev("k", "insert"), ev("w", "normal")];
  assert.equal(tokenize(events, "jk", "normal").length, 4);
  assert.equal(tokenize(events, "esc", "normal").length, 5);
  // a literal "jk" typed while staying in insert mode is two keys
  const lit = [ev("i"), ev("j", "insert"), ev("k", "insert"), ev("x", "insert")];
  assert.equal(tokenize(lit, "jk", "insert").length, 4);
});

test("edit passes on matching buffer in normal mode, trailing whitespace ignored", () => {
  const t = tokenize(ciQuote(), "esc", "normal");
  assert.ok(checkPass(quote, { lines: ["x = 1  ", '    logger.warn("retrying")'], cursor: [2, 0], mode: "normal" }, t));
  assert.ok(!checkPass(quote, { lines: ["x = 1", '    logger.warn("retrying")'], cursor: [2, 0], mode: "insert" }, t));
  assert.ok(!checkPass(quote, { lines: ["x = 1", '    logger.warn("retry")'], cursor: [2, 0], mode: "normal" }, t));
});

test("cursor passes only on the target with the buffer unchanged", () => {
  const ex: Exercise = { ...quote, kind: "cursor", expect: { cursor: [2, 4] } };
  assert.ok(checkPass(ex, { lines: quote.start.lines, cursor: [2, 4], mode: "normal" }, []));
  assert.ok(!checkPass(ex, { lines: quote.start.lines, cursor: [2, 5], mode: "normal" }, []));
  assert.ok(!checkPass(ex, { lines: ["changed", quote.start.lines[1]], cursor: [2, 4], mode: "normal" }, []));
});

test("ex kind needs an executed : command", () => {
  const ex: Exercise = { ...quote, kind: "ex", expect: { lines: ["x = 1"] } };
  const snap = { lines: ["x = 1"], cursor: [1, 0] as [number, number], mode: "normal" as Mode };
  const viaDd = tokenize(typed([["j", "normal"], ["d", "normal"], ["d", "normal"]]), "esc", "normal");
  assert.ok(!checkPass(ex, snap, viaDd));
  const viaG = tokenize(typed([[":", "normal"], ["g", "normal", true], ["<CR>", "normal", true]]), "esc", "normal");
  assert.ok(usedExCommand(viaG));
  assert.ok(checkPass(ex, snap, viaG));
});

test("efficiency bands", () => {
  assert.equal(band(9, 11), "beat");
  assert.equal(band(0, 1), "beat");
  assert.equal(band(12, 12), "par");
  assert.equal(band(15, 12), "close");
  assert.equal(band(16, 12), "pass");
  assert.equal(band(25, 12), "over");
});

test("give-up needs two escapes pressed in normal mode", () => {
  assert.ok(isGiveUp([ev("<Esc>", "normal", false, 0), ev("<Esc>", "normal", false, 200)]));
  assert.ok(!isGiveUp([ev("<Esc>", "insert", false, 0), ev("<Esc>", "normal", false, 200)]));
  assert.ok(!isGiveUp([ev("<Esc>", "normal", false, 0), ev("<Esc>", "normal", false, 2000)]));
  assert.ok(isGiveUp([ev("<C-[>", "normal", false, 0), ev("<Esc>", "normal", false, 100)]));
});

test("an <Esc> that cancels a pending operator or count does not start the give-up", () => {
  const pend = (k: string, active: number): KeyEvent => ({ ...ev(k, "normal", false, active), pending: true });
  // d<Esc><Esc>: the first <Esc> cancels `d`, so this is not a give-up...
  assert.ok(!isGiveUp([ev("d"), pend("<Esc>", 100), ev("<Esc>", "normal", false, 200)]));
  assert.ok(!armsGiveUp(pend("<Esc>", 0)));
  // ...but a further <Esc> pair is.
  assert.ok(isGiveUp([ev("d"), pend("<Esc>", 100), ev("<Esc>", "normal", false, 200), ev("<Esc>", "normal", false, 300)]));
  assert.ok(armsGiveUp(ev("<Esc>")));
  assert.ok(!armsGiveUp(ev("<Esc>", "normal", true)));
  assert.ok(!armsGiveUp(ev("<Esc>", "insert")));
  assert.ok(!armsGiveUp(undefined));
});

test("attempt clock subtracts paused stretches, overlapping reasons included", () => {
  let t = 1000;
  const c = new PausableClock(() => t);
  t = 1500;
  assert.equal(c.active(), 500);
  c.setPaused("away", true); // stats opened
  t = 4500;
  assert.equal(c.active(), 500);
  c.setPaused("hidden", true); // tab hidden while stats is open
  t = 5000;
  c.setPaused("away", false); // still hidden: clock stays stopped
  t = 6000;
  assert.equal(c.active(), 500);
  assert.ok(c.paused());
  c.setPaused("hidden", false);
  t = 6250;
  assert.equal(c.active(), 750);
  c.setPaused("away", false); // releasing a reason that is not held changes nothing
  assert.equal(c.active(), 750);
  assert.ok(!c.paused());
});

test("insert-mode <Tab> fills to the next 4-column stop like nvim (expandtab, ts=sw=4, sts=0)", () => {
  // Expected values observed in nvim 0.12 --clean with the oracle's options.
  assert.equal(tabSpaces(""), 4);
  assert.equal(tabSpaces("ab"), 2);
  assert.equal(tabSpaces("abcd"), 4);
  assert.equal(tabSpaces("  "), 2);
  assert.equal(tabSpaces("a\tb"), 3); // the tab occupies columns 1-3
  assert.equal(tabSpaces("        x = 1"), 3);
});

test("hint order: exercise trigger, then generic detectors, then nothing at par", () => {
  const fci = tokenize([ev("f"), ev('"'), ...ciQuote()], "esc", "normal");
  assert.equal(chooseHint(quote, fci, true), "ci\" works from anywhere");
  const atPar = tokenize(ciQuote(), "esc", "normal");
  assert.equal(chooseHint(quote, atPar, true), null);
  const jspam = tokenize([..."jjjjj".split("").map((k) => ev(k)), ...ciQuote()], "esc", "normal");
  assert.match(chooseHint(quote, jspam, true) ?? "", /5j/);
  const xspam = tokenize([..."xxxx".split("").map((k) => ev(k)), ...ciQuote()], "esc", "normal");
  assert.match(chooseHint(quote, xspam, true) ?? "", /^d with a motion/);
  // typed text never triggers detectors
  const insertX = tokenize([ev("c"), ev("i"), ev('"'), ..."xxxxjjjjjj".split("").map((c) => ev(c, "insert")), ev("<Esc>", "insert")], "esc", "normal");
  assert.equal(chooseHint(quote, insertX, true), "plain hint");
  // the 0 inside a count (10w) is not the 0 motion; a bare 0w is
  const dw: Exercise = { ...quote, hints: [], par: { keys: "dw", count: 2 } };
  const counted = tokenize([..."10wdw"].map((k) => ev(k)), "esc", "normal");
  assert.equal(chooseHint(dw, counted, true), null);
  const zero = tokenize([..."0wdw"].map((k) => ev(k)), "esc", "normal");
  assert.match(chooseHint(dw, zero, true) ?? "", /^\^ jumps/);
});

test("diffLines marks removed and added lines", () => {
  const d = diffLines(["a", "b", "c"], ["a", "B", "c"]);
  assert.deepEqual(d.map((x) => x.op + x.text), [" a", "-b", "+B", " c"]);
});

test("target range: explicit, cursor, derived from diff", () => {
  const explicit = targetRange({ ...quote, target: { from: [2, 16], to: [2, 39] } });
  assert.deepEqual(explicit, { from: 6 + 16, to: 6 + 39 });
  const cur = targetRange({ ...quote, kind: "cursor", expect: { cursor: [2, 4] } });
  assert.deepEqual(cur, { from: 10, to: 11 });
  const derived = targetRange(quote)!;
  const text = quote.start.lines.join("\n").slice(derived.from, derived.to);
  assert.equal(text, "timeout, trying again");
});

test("target range: the pipeline's list of inclusive {start, end} spans", () => {
  // line 2 is '    logger.warn("timeout, trying again")'; the string with quotes is cols 16..38.
  const spans = targetRanges({ ...quote, target: [{ start: [2, 16], end: [2, 38] }, { start: [1, 0], end: [1, 0] }] });
  const text = quote.start.lines.join("\n");
  assert.deepEqual(spans.map((r) => text.slice(r.from, r.to)), ['"timeout, trying again"', "x"]);
});

// Contract between the content pipeline (build/) and the app: every shipped exercise
// must be readable by the app. Skipped when build/ has not been generated.
const BUILD = join(import.meta.dirname, "..", "..", "build", "exercises");
test("build/ exercises match what the app reads", { skip: !existsSync(BUILD) && "build/ not generated" }, () => {
  let n = 0;
  const problems: string[] = [];
  for (const lang of readdirSync(BUILD))
    for (const skill of readdirSync(join(BUILD, lang)))
      for (const f of readdirSync(join(BUILD, lang, skill))) {
        const ex = JSON.parse(readFileSync(join(BUILD, lang, skill, f), "utf8")) as Exercise;
        n++;
        const where = `${ex.id}`;
        if (!["edit", "cursor", "ex"].includes(ex.kind)) problems.push(`${where}: kind ${ex.kind}`);
        if (ex.kind === "cursor" ? !ex.expect.cursor : !ex.expect.lines) problems.push(`${where}: expect does not fit kind`);
        if (splitKeys(ex.par.keys).length !== ex.par.count) problems.push(`${where}: par ${ex.par.keys} counts ${splitKeys(ex.par.keys).length}, not ${ex.par.count}`);
        if (targetRanges(ex).length === 0) problems.push(`${where}: no target range`);
        for (const h of ex.hints ?? []) if (typeof h !== "string" && h.trigger && !exerciseHints({ ...ex, hints: [h] })[0].trigger) problems.push(`${where}: bad trigger ${h.trigger}`);
        // A hint never fires at par (the pipeline drops triggers that match the canonical keys).
        if (chooseHint(ex, splitKeys(ex.par.keys).map((key) => ({ key, mode: "normal" as Mode, cmdline: false })), true) && exerciseHints(ex).some((h) => h.trigger?.test(ex.par.keys)))
          problems.push(`${where}: a hint fires at par`);
      }
  assert.ok(n > 0, "no exercises found");
  assert.deepEqual(problems.slice(0, 10), []);
});

test("placementPass: ok within max(2 * par, par + 6) keys (QA #8)", () => {
  assert.equal(placementPass(true, 8, 2), true); // short par: par + 6 = 8
  assert.equal(placementPass(true, 9, 2), false);
  assert.equal(placementPass(true, 11, 2), false); // 11 presses of l on a par-2 exercise
  assert.equal(placementPass(true, 20, 10), true); // long par: 2 * par = 20
  assert.equal(placementPass(true, 21, 10), false);
  assert.equal(placementPass(true, 12, 6), true); // the two caps meet at par 6
  assert.equal(placementPass(true, 13, 6), false);
  assert.equal(placementPass(false, 1, 2), false);
});

// py/o.delete/0a6154fe41 (QA #3): "Delete the function `__init__` (4 lines)", par d}.
// Every `now` below is Neovim 0.12.5's buffer after the named keys (oracle.verify_many).
const INIT = ["def __init__(self):", "    self.current_frame_idx = 0", "    self.bonus_throws = []", "    self.frames = [Frame(idx) for idx in range(MAX_FRAME)]"];
const REST = ["@property", "def current_frame(self):", "    return self.frames[self.current_frame_idx]", "", "def next_throws(self, frame_idx):", '    """Return a frame\'s next throws in the form of a list."""', "    throws = []", "    for idx in range(frame_idx + 1, MAX_FRAME):", "        throws.extend(self.frames[idx].throws)", "    throws.extend(self.bonus_throws)", "    return throws"];
const START = [...INIT, "", ...REST];
const EXPECT = ["", ...REST];

test("unrecoverable: dap removes the blank line the target keeps (QA #3)", () => {
  assert.equal(unrecoverable(START, REST, EXPECT), "the target keeps 1 more line");
});

test("unrecoverable: a kept line deleted along with other lines", () => {
  // 3jd2j: deletes self.frames, the blank and @property; 13 lines, still >= 12.
  const now = [...INIT.slice(0, 3), ...REST.slice(1)];
  assert.equal(unrecoverable(START, now, EXPECT), "a line that should stay was removed");
});

test("unrecoverable: whole lines deleted and less than half the text left", () => {
  const start = ["total = compute(alpha, beta, gamma)", "", "", "print(total)"];
  const expect = ["total = compute(alpha, beta)", "", "print(total)"];
  assert.equal(unrecoverable(start, ["", "", "print(total)"], expect), "too much was deleted"); // dd
});

test("unrecoverable: stays quiet on states that can still reach the target", () => {
  const cases: [string, string[], string[], string[]][] = [
    ["untouched", START, START, EXPECT],
    ["d} (the pass)", START, EXPECT, EXPECT],
    ["dd, part way", START, START.slice(1), EXPECT],
    ["3dd, part way", START, START.slice(3), EXPECT],
    ["cwfoo, insert still open", START, ["foo __init__(self):", ...START.slice(1)], EXPECT],
    ["o# note<Esc>, an extra line", START, [INIT[0], "    # note", ...START.slice(1)], EXPECT],
    ["ddp, lines reordered", START, [INIT[1], INIT[0], ...START.slice(2)], EXPECT],
    ["6jdd, a kept line in the register (P restores it)", START, [...START.slice(0, 6), ...START.slice(7)], EXPECT],
    ["dd of a line move, before the p", ["import os", "import sys", "x = 1"], ["import sys", "x = 1"], ["import sys", "import os", "x = 1"]],
    ["f,;Dx, a charwise delete", ["total = compute(alpha, beta, gamma)", "", "", "print(total)"], ["total = compute(alpha, bet", "", "", "print(total)"], ["total = compute(alpha, beta)", "", "print(total)"]],
    // Fewer lines than start and expect, but the missing line is new text still to type.
    ["dG, then oX to come", ["a", "b", "c", "d"], ["a"], ["a", "X"]],
    ["jdd, then obaz to come", ["foo", "bar"], ["foo"], ["foo", "baz"]],
  ];
  for (const [name, start, now, expect] of cases) assert.equal(unrecoverable(start, now, expect), null, name);
});
