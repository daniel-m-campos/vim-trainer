// Unit tests for vimfixes.ts's pure helpers. Expected values come from nvim --clean (the
// oracle, with the oracle's tabstop=4 shiftwidth=4 expandtab); lines are 0-based. Run: npm test.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  charAtDisplayCol, cursorCol, displayCol, joinLinesText, paragraphMotion, paragraphObject, quoteObject, shiftLine, spaceExAddress,
} from "./vimfixes.ts";

test("J joins like do_join(): no space after trailing white space, before ')' or onto an empty line", () => {
  assert.deepEqual(joinLinesText(["abc", "def"], true), { text: "abc def", col: 3 });
  assert.deepEqual(joinLinesText(["abc  ", "def"], true), { text: "abc  def", col: 5 });
  assert.deepEqual(joinLinesText(["abc\t", "def"], true), { text: "abc\tdef", col: 4 });
  assert.deepEqual(joinLinesText(["abc", "  )def"], true), { text: "abc)def", col: 3 });
  assert.deepEqual(joinLinesText(["abc(", "  )def"], true), { text: "abc()def", col: 4 });
  assert.deepEqual(joinLinesText(["abc", "\tdef"], true), { text: "abc def", col: 3 });
  assert.deepEqual(joinLinesText(["", "abc"], true), { text: "abc", col: 0 });
  assert.deepEqual(joinLinesText(["abc", ""], true), { text: "abc", col: 3 }); // J then clamps the cursor to [1, 2]
  assert.deepEqual(joinLinesText(["abc", "", "def"], true), { text: "abc def", col: 3 }); // 3J
});

test("gJ keeps the lines' white space and adds none", () => {
  assert.deepEqual(joinLinesText(["abc", "  def"], false), { text: "abc  def", col: 3 });
});

test("> and < shift by shiftwidth with spaces and leave empty lines alone", () => {
  assert.equal(shiftLine("a", 1), "    a");
  assert.equal(shiftLine("", 1), ""); // >G on ["a", "", "b"]
  assert.equal(shiftLine("  ", 1), "      "); // >G on ["a", "  ", "b"]
  assert.equal(shiftLine("  ", -1), ""); // <G on ["    a", "  ", "    b"]
  assert.equal(shiftLine("\ta", 1), "        a"); // >> on "\ta"
  assert.equal(shiftLine("\ta", -1), "a");
  assert.equal(shiftLine("  a", -1), "a");
  assert.equal(shiftLine("a", 3), "            a"); // Vj3>
});

test("} and { follow findpar(): last character of the buffer, or fail on a count past the edge", () => {
  assert.deepEqual(paragraphMotion(["abc def"], 0, 1, true), { line: 0, ch: 6, inclusive: true });
  assert.deepEqual(paragraphMotion(["abc", "def"], 0, 1, true), { line: 1, ch: 2, inclusive: true });
  assert.deepEqual(paragraphMotion(["abc", "def"], 1, 1, true), { line: 1, ch: 2, inclusive: true });
  assert.deepEqual(paragraphMotion(["abc", "def", ""], 2, 1, true), { line: 2, ch: 0, inclusive: false });
  assert.deepEqual(paragraphMotion(["abc", "", "def"], 0, 1, true), { line: 1, ch: 0, inclusive: false });
  assert.deepEqual(paragraphMotion(["abc", "", "def"], 0, 2, true), { line: 2, ch: 2, inclusive: true });
  assert.equal(paragraphMotion(["abc", "", "def"], 0, 3, true), null);
  assert.equal(paragraphMotion(["abc", "", "def"], 2, 3, false), null);
  assert.deepEqual(paragraphMotion(["abc", "def"], 1, 1, false), { line: 0, ch: 0, inclusive: false });
});

test("ip and ap follow current_par(), failing when the count runs past the end", () => {
  const five = ["a", "", "b", "", "c"];
  assert.deepEqual(paragraphObject(five, 0, 2, true), [0, 3]); // d2ap -> ["c"]
  assert.deepEqual(paragraphObject(five, 0, 3, true), [0, 4]); // d3ap -> [""]
  assert.equal(paragraphObject(five, 0, 7, true), null); // d7ap: no change
  assert.deepEqual(paragraphObject(five, 0, 3, false), [0, 2]); // d3ip -> ["", "c"]
  assert.equal(paragraphObject(five, 0, 9, false), null);
  assert.deepEqual(paragraphObject(["abcd", "abcd", "", "x"], 1, 1, false), [0, 1]); // yip
  assert.deepEqual(paragraphObject(["abcd", "abcd", "", "x"], 1, 1, true), [0, 2]); // yap
  assert.deepEqual(paragraphObject(["x", "a", "", "b", "", "c"], 1, 1, true), [0, 2]); // >ap
  assert.deepEqual(paragraphObject(["abc", "", "Def", "ghi", "", "x"], 3, 1, true), [2, 4]); // g~ap
});

test("quote objects follow current_quote()", () => {
  const two = "x = 'ab' + 'cd'";
  assert.deepEqual(quoteObject(two, 9, "'", false), [8, 11]); // di' between strings -> "x = 'ab''cd'"
  assert.deepEqual(quoteObject(two, 0, "'", false), [5, 7]); // before the first string
  assert.deepEqual(quoteObject(two, 0, "'", true), [4, 9]); // va' takes the trailing space
  assert.equal(quoteObject('x = "ab" + y', 11, '"', false), null); // after the last quote: fails
  assert.equal(quoteObject("abc def", 0, "'", false), null);
  assert.deepEqual(quoteObject('x = "a\\"b" + y', 5, '"', false), [5, 9]); // escaped quote inside
  assert.deepEqual(quoteObject("x = 'ab'  + y", 5, "'", true), [4, 10]); // trailing white space
  assert.deepEqual(quoteObject("x = 'ab'", 5, "'", true), [3, 8]); // none after: leading white space
  assert.deepEqual(quoteObject("x = 'ab' 'cd'", 5, "'", false, 2), [4, 8]); // 2i' includes the quotes
  assert.deepEqual(quoteObject("x = 'ab'", 7, "'", false), [5, 7]); // on the closing quote
  assert.deepEqual(quoteObject("x = ''", 4, "'", false), [5, 5]); // empty string
});

test("display columns count a tab to the next tabstop and CJK / emoji as two", () => {
  assert.equal(displayCol("\tabcdef", 3), 6);
  assert.equal(charAtDisplayCol("        abc", 6), 6); // j from [1, 3] on "\tabcdef" lands on [2, 6]
  assert.equal(charAtDisplayCol("\tabc", 2), 0); // inside the tab
  assert.equal(charAtDisplayCol("ab", 9), 1); // past the end: last character
  assert.equal(displayCol("你好b", 2), 4);
  assert.equal(charAtDisplayCol("a🙂b", 3), 3);
});

test("the Normal-mode cursor on a tab sits on its last column (j from [1, 0] on \"\\tabc\" lands on [2, 3])", () => {
  assert.equal(cursorCol("\tabc", 0), 3);
  assert.equal(cursorCol("\tabc", 1), 4);
  assert.equal(charAtDisplayCol("abcdefgh", cursorCol("\tabc", 0)), 3);
});

test("ex addresses get a space after :m / :t / :co", () => {
  assert.equal(spaceExAddress(":m8"), ":m 8");
  assert.equal(spaceExAddress(":t."), ":t .");
  assert.equal(spaceExAddress(":move 3"), ":move 3");
});

test(":j{count} gets a space so the count is not read as part of the name", () => {
  assert.equal(spaceExAddress(":j3"), ":j 3");
  assert.equal(spaceExAddress(":2,3join5"), ":2,3join 5");
  assert.equal(spaceExAddress(":j"), ":j");
  assert.equal(spaceExAddress(":jumps"), ":jumps");
});
