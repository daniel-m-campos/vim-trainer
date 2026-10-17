// Editor-level regressions: key sequences typed into the practice editor (the
// emulator-check.html harness) whose results were checked against nvim --clean.
// Each case is a buffer, a start cursor, keys in Vim notation and the expected buffer
// (and cursor, [line 1-based, col 0-based]) after them.
//
//   npm run e2e:editor            # Chromium
//   npm run e2e:editor -- --all   # Chromium, Firefox, WebKit
process.env.PLAYWRIGHT_BROWSERS_PATH ??= "0";

const { createServer } = await import("vite");
const { chromium, firefox, webkit } = await import("playwright");
const { fileURLToPath } = await import("node:url");
const { typeKeys, tokenize } = await import("./keys.mjs");
const { CASES: MACRO_INDENT_CASES } = await import("./cases-macros-indent.mjs");

const CASES = [
  {
    name: "di{ then . on a single-line block stays charwise (vimfixes innerBlock resets linewise)",
    lines: ["a = {", "  1,", "}", "b = {1, 2}"],
    cursor: [2, 2],
    keys: "di{G$.",
    expect: ["a = {", "}", "b = {}"],
  },
  {
    name: "<C-v> I block insert: <Esc> leaves the cursor on the block's top-left corner",
    lines: ["abc def", "ghi jkl", "mno pqr"],
    cursor: [1, 0],
    keys: "<C-v>jjIXY<Esc>x",
    expect: ["Yabc def", "XYghi jkl", "XYmno pqr"],
    cursorAfter: [1, 0],
  },
  {
    name: "<C-v> A block append: <Esc> leaves the cursor on the block's top-left corner",
    lines: ["abc def", "ghi jkl", "mno pqr"],
    cursor: [1, 2],
    keys: "<C-v>jjlAXY<Esc>",
    expect: ["abc XYdef", "ghi XYjkl", "mno XYpqr"],
    cursorAfter: [1, 2],
  },
  {
    name: ". re-expands an insert-mode <Tab> at the new column (spaces to the next 4-column stop)",
    lines: ["ab", "abc"],
    cursor: [1, 0],
    keys: "A<Tab>x<Esc>j.",
    expect: ["ab  x", "abc x"],
    cursorAfter: [2, 4],
  },
  {
    name: ". re-expands a Replace-mode <Tab> (one character replaced by spaces to the stop)",
    lines: ["abcdef", "abcdef"],
    cursor: [1, 1],
    keys: "R<Tab><Esc>j.",
    expect: ["a   cdef", "abc ef"],
    cursorAfter: [2, 3],
  },
  // vimfixes fix 6: a failing motion or text object aborts its operator (Normal mode stays);
  // counts past the first / last line fail where Neovim's cursor_down / cursor_up fail.
  { name: "a failing f{c} aborts the operator",
    lines: ["abc def"], cursor: [1, 0], keys: "dfz", expect: ["abc def"], cursorAfter: [1, 0] },
  { name: "ci' with no quotes on the line aborts; x then deletes in Normal mode",
    lines: ["abc def"], cursor: [1, 0], keys: "ci'x", expect: ["bc def"], cursorAfter: [1, 0] },
  { name: "cf{c} with no match stays in Normal mode",
    lines: ["abc def"], cursor: [1, 0], keys: "cfzx", expect: ["bc def"], cursorAfter: [1, 0] },
  { name: "<F{c} with no match shifts nothing",
    lines: ["abc def"], cursor: [1, 4], keys: "<Fz", expect: ["abc def"], cursorAfter: [1, 4] },
  { name: ">a\" with no quotes shifts nothing",
    lines: ["abc def"], cursor: [1, 0], keys: ">a\"", expect: ["abc def"], cursorAfter: [1, 0] },
  { name: "3<a[ with one level of brackets shifts nothing",
    lines: ["  a [b] c"], cursor: [1, 5], keys: "3<a[", expect: ["  a [b] c"], cursorAfter: [1, 5] },
  { name: "3gua{ with two levels changes nothing",
    lines: ["x = {A {B} C}"], cursor: [1, 8], keys: "3gua{", expect: ["x = {A {B} C}"], cursorAfter: [1, 8] },
  { name: "2gua{ takes the second enclosing block",
    lines: ["x = {A {B} C}"], cursor: [1, 8], keys: "2gua{", expect: ["x = {a {b} c}"], cursorAfter: [1, 4] },
  { name: "9<iW past the end of the buffer fails and leaves the cursor at the end",
    lines: ["    a b", "    c d"], cursor: [1, 4], keys: "<<9<iW", expect: ["a b", "    c d"], cursorAfter: [2, 6] },
  { name: "c9iw past the end fails (x then deletes)",
    lines: ["a b c", "d e"], cursor: [1, 0], keys: "c9iwx", expect: ["a b c", "d "], cursorAfter: [2, 1] },
  { name: "g~; with no previous f/t fails",
    lines: ["abc def"], cursor: [1, 0], keys: "g~;", expect: ["abc def"], cursorAfter: [1, 0] },
  { name: "c; with no further match stays in Normal mode",
    lines: ["abc def"], cursor: [1, 0], keys: "fcc;x", expect: ["ab def"], cursorAfter: [1, 2] },
  { name: "2D on the last line fails",
    lines: ["abc", "def", "ghi"], cursor: [3, 1], keys: "2D", expect: ["abc", "def", "ghi"], cursorAfter: [3, 1] },
  { name: "2C on the last line fails (x then deletes)",
    lines: ["abc", "def"], cursor: [2, 1], keys: "2Cx", expect: ["abc", "df"], cursorAfter: [2, 1] },
  { name: "2cc on the last line fails (x then deletes)",
    lines: ["abc", "def", "ghi"], cursor: [3, 1], keys: "2ccx", expect: ["abc", "def", "gi"], cursorAfter: [3, 1] },
  { name: "2dd on the last line does nothing",
    lines: ["abc", "def", "ghi"], cursor: [3, 1], keys: "2dd", expect: ["abc", "def", "ghi"], cursorAfter: [3, 1] },
  { name: "2>> on the last line does nothing",
    lines: ["abc", "def", "ghi"], cursor: [3, 1], keys: "2>>", expect: ["abc", "def", "ghi"], cursorAfter: [3, 1] },
  { name: "9dd in the middle deletes to the end (the count is clamped)",
    lines: ["abc", "def", "ghi"], cursor: [2, 1], keys: "9dd", expect: ["abc"], cursorAfter: [1, 0] },
  { name: "<CR> on the last line does not move",
    lines: ["abc", "def"], cursor: [2, 1], keys: "<CR>", expect: ["abc", "def"], cursorAfter: [2, 1] },
  { name: "j on the last line does not move",
    lines: ["abc", "def"], cursor: [2, 1], keys: "j", expect: ["abc", "def"], cursorAfter: [2, 1] },
  { name: "5k on the first line does not move",
    lines: ["abc", "def"], cursor: [1, 1], keys: "5k", expect: ["abc", "def"], cursorAfter: [1, 1] },
  { name: "t{c} onto the next character stays, then j on a one-line buffer does not move",
    lines: ["a=b c=d"], cursor: [1, 0], keys: "t=j", expect: ["a=b c=d"], cursorAfter: [1, 0] },
  { name: "5_ past the end goes to the last line's first non-blank",
    lines: ["abc", "  def"], cursor: [1, 1], keys: "5_", expect: ["abc", "  def"], cursorAfter: [2, 2] },
  { name: "dj on the last line does nothing",
    lines: ["abc", "def", "ghi"], cursor: [3, 1], keys: "dj", expect: ["abc", "def", "ghi"], cursorAfter: [3, 1] },
  { name: "dk on the first line does nothing",
    lines: ["abc", "def"], cursor: [1, 1], keys: "dk", expect: ["abc", "def"], cursorAfter: [1, 1] },
  { name: "d<CR> is a linewise motion, not a typed line break",
    lines: ["abc", "def"], cursor: [2, 1], keys: "d<CR>", expect: ["abc", "def"], cursorAfter: [2, 1] },
  { name: "d5<CR> deletes to the end of the buffer",
    lines: ["abc", "def"], cursor: [1, 1], keys: "d5<CR>", expect: [""], cursorAfter: [1, 0] },
  { name: "d_ is linewise (last line)",
    lines: ["abc", "def", "ghi"], cursor: [3, 1], keys: "d_", expect: ["abc", "def"], cursorAfter: [2, 0] },
  { name: "d2_ on the last line does nothing",
    lines: ["abc", "def", "ghi"], cursor: [3, 1], keys: "d2_", expect: ["abc", "def", "ghi"], cursorAfter: [3, 1] },
  { name: "d- deletes this line and the one above",
    lines: ["abcd", "abcd", "abcd"], cursor: [3, 2], keys: "d-", expect: ["abcd"], cursorAfter: [1, 0] },
  { name: "d- on the first line does nothing",
    lines: ["abcd", "abcd", "abcd"], cursor: [1, 2], keys: "d-", expect: ["abcd", "abcd", "abcd"], cursorAfter: [1, 2] },
  { name: "y- leaves the cursor on the upper line's first non-blank",
    lines: ["abcd", "abcd", "abcd"], cursor: [3, 2], keys: "y-", expect: ["abcd", "abcd", "abcd"], cursorAfter: [2, 0] },
  { name: "dx: x is not a motion, the operator is cancelled",
    lines: ["abc def"], cursor: [1, 4], keys: "dx", expect: ["abc def"], cursorAfter: [1, 4] },
  { name: "dgE at the start of the buffer does nothing",
    lines: ["a b", "c d"], cursor: [1, 0], keys: "dgE", expect: ["a b", "c d"], cursorAfter: [1, 0] },
  { name: "d3ge past the start fails and leaves the cursor at the start",
    lines: ["a b c"], cursor: [1, 4], keys: "d3ge", expect: ["a b c"], cursorAfter: [1, 0] },
  { name: "d5b past the start deletes to the start (b does not fail)",
    lines: ["a b"], cursor: [1, 2], keys: "d5b", expect: ["b"], cursorAfter: [1, 0] },
  { name: "d7ap past the end does nothing",
    lines: ["a", "", "b", "", "c"], cursor: [1, 0], keys: "d7ap", expect: ["a", "", "b", "", "c"], cursorAfter: [1, 0] },
  { name: "d3ip takes three paragraph / blank blocks",
    lines: ["a", "", "b", "", "c"], cursor: [1, 0], keys: "d3ip", expect: ["", "c"], cursorAfter: [1, 0] },
  { name: "5rx past the end of the line does nothing",
    lines: ["abc"], cursor: [1, 1], keys: "5rx", expect: ["abc"], cursorAfter: [1, 1] },
  { name: "rx then 3. replaces three characters",
    lines: ["abcdef"], cursor: [1, 0], keys: "rx3.", expect: ["xxxdef"], cursorAfter: [1, 2] },
  { name: "2rx, l, 3. uses the new count",
    lines: ["abcdef"], cursor: [1, 0], keys: "2rxl3.", expect: ["xxxxxf"], cursorAfter: [1, 4] },
  { name: "dit with no tag does nothing",
    lines: ["a b"], cursor: [1, 0], keys: "dit", expect: ["a b"], cursorAfter: [1, 0] },
  // vimfixes fix 7: > and < skip empty lines and rewrite the indent with spaces.
  { name: ">G leaves empty lines empty",
    lines: ["a", "", "b"], cursor: [1, 0], keys: ">G", expect: ["    a", "", "    b"], cursorAfter: [1, 4] },
  { name: "<G empties a white-space-only line",
    lines: ["    a", "  ", "    b"], cursor: [1, 0], keys: "<G", expect: ["a", "", "b"], cursorAfter: [1, 0] },
  { name: ">ap leaves the blank line after the paragraph unindented",
    lines: ["x", "a", "", "b", "", "c"], cursor: [2, 0], keys: ">ap", expect: ["    x", "    a", "", "b", "", "c"], cursorAfter: [1, 4] },
  { name: ">* shifts the lines up to the match but not the empty one",
    lines: ["foo", "", "x", "foo"], cursor: [1, 0], keys: ">*", expect: ["    foo", "", "    x", "foo"], cursorAfter: [1, 4] },
    // Was flaky in Firefox (cursor jumped to [1, 0] ~300 ms later): a stale DOM selection read
    // by CodeMirror's DOM observer; editor.ts keepVimCursor now drops it outside Insert mode.
  { name: ">> rewrites a tab indent with spaces",
    lines: ["\ta", "b"], cursor: [1, 0], keys: ">>", expect: ["        a", "b"], cursorAfter: [1, 8] },
  { name: "Vjj> skips the empty line",
    lines: ["a", "", "c"], cursor: [1, 0], keys: "Vjj>", expect: ["    a", "", "    c"], cursorAfter: [1, 4] },
  // vimfixes fix 8: y leaves the cursor at the start of the yanked text.
  { name: "yb moves the cursor to the start of the yanked text",
    lines: ["foo bar"], cursor: [1, 4], keys: "yb", expect: ["foo bar"], cursorAfter: [1, 0] },
  { name: "yiw moves the cursor to the start of the word",
    lines: ["foo bar"], cursor: [1, 5], keys: "yiw", expect: ["foo bar"], cursorAfter: [1, 4] },
  { name: "yB moves the cursor back",
    lines: ["foo b.r x"], cursor: [1, 6], keys: "yB", expect: ["foo b.r x"], cursorAfter: [1, 4] },
  { name: "ygE moves the cursor back",
    lines: ["foo b.r x"], cursor: [1, 8], keys: "ygE", expect: ["foo b.r x"], cursorAfter: [1, 6] },
  { name: "yk keeps the column on the upper line",
    lines: ["abcd", "abcd", "abcd"], cursor: [3, 2], keys: "yk", expect: ["abcd", "abcd", "abcd"], cursorAfter: [2, 2] },
  { name: "ygg goes to the first line",
    lines: ["abcd", "abcd", "abcd"], cursor: [3, 2], keys: "ygg", expect: ["abcd", "abcd", "abcd"], cursorAfter: [1, 0] },
  { name: "yip goes to the paragraph's first line",
    lines: ["abcd", "abcd", "", "x"], cursor: [2, 2], keys: "yip", expect: ["abcd", "abcd", "", "x"], cursorAfter: [1, 0] },
  { name: "Vky leaves the cursor where it is above the anchor",
    lines: ["abc def", "  ghi jkl"], cursor: [2, 6], keys: "Vky", expect: ["abc def", "  ghi jkl"], cursorAfter: [1, 6] },
  { name: "y} from column 0 is linewise (exclusive-linewise)",
    lines: ["a b", "  c d", "", "e"], cursor: [1, 0], keys: "y}P", expect: ["a b", "  c d", "a b", "  c d", "", "e"], cursorAfter: [1, 0] },
  // vimfixes fix 1: :help exclusive-linewise for every operator and charwise motion but w / W;
  // op_delete's linewise rule (d2$, 5D, 4dW).
  { name: "c} from column 0 is linewise",
    lines: ["a b", "  c d", "", "e"], cursor: [1, 0], keys: "c}x", expect: ["x", "", "e"], cursorAfter: [1, 1] },
  { name: "d* from column 0 deletes whole lines",
    lines: ["foo x", "bar", "foo"], cursor: [1, 0], keys: "d*", expect: ["foo"], cursorAfter: [1, 0] },
  { name: "d* from the indent deletes whole lines",
    lines: ["  foo x", "bar", "foo"], cursor: [1, 2], keys: "d*", expect: ["foo"], cursorAfter: [1, 0] },
  { name: "d/pat<CR> ending in column 0 deletes whole lines",
    lines: ["foo x", "bar", "foo"], cursor: [1, 0], keys: "d/foo<CR>", expect: ["foo"], cursorAfter: [1, 0] },
  { name: "d/pat<CR> keeps the next line's indent text when the match is not in column 0",
    lines: ["a", "  b"], cursor: [1, 0], keys: "d/b<CR>", expect: ["b"], cursorAfter: [1, 0] },
  { name: "y/pat<CR> to column 0 yanks linewise",
    lines: ["a", "b"], cursor: [1, 0], keys: "y/b<CR>P", expect: ["a", "a", "b"], cursorAfter: [1, 0] },
  { name: "c/pat<CR> to column 0 changes the line (x typed)",
    lines: ["a", "b"], cursor: [1, 0], keys: "c/b<CR>x", expect: ["x", "b"], cursorAfter: [1, 1] },
  { name: "dB from column 0 stops at the end of the line above",
    lines: ["a b", "c d"], cursor: [2, 0], keys: "dB", expect: ["a ", "c d"], cursorAfter: [1, 1] },
  { name: "cB from column 0 keeps the line break",
    lines: ["a b", "c d"], cursor: [2, 0], keys: "cBx", expect: ["a x", "c d"], cursorAfter: [1, 3] },
  { name: "db onto an empty line keeps it",
    lines: ["a b", ""], cursor: [2, 0], keys: "db", expect: ["a ", ""], cursorAfter: [1, 1] },
  { name: "d{ from column 0 is linewise",
    lines: ["a", "", "b c", "d"], cursor: [4, 1], keys: "d{", expect: ["a", "d"], cursorAfter: [2, 0] },
  { name: "de crosses the line break (inclusive, no clipping)",
    lines: ["abc def", "  x y"], cursor: [1, 6], keys: "de", expect: ["abc de y"], cursorAfter: [1, 6] },
  { name: "d2$ from the indent to the end of a line is linewise (op_delete)",
    lines: ["  ab", "cd", "ef"], cursor: [1, 2], keys: "d2$", expect: ["ef"], cursorAfter: [1, 0] },
  { name: "d% from the indent stays charwise",
    lines: ["  (b", "c)"], cursor: [1, 2], keys: "d%", expect: ["  "], cursorAfter: [1, 1] },
  // vimfixes fixes 8-10: J, Visual-line c / s / u / U / ~, ~, } {, quote objects, display
  // columns over tabs, gj / gk with nowrap, g~ / gu / gU cursor.
  { name: "J adds no space after trailing whitespace",
    lines: ["abc  ", "def"], cursor: [1, 0], keys: "J", expect: ["abc  def"], cursorAfter: [1, 5] },
  { name: "J adds no space before )",
    lines: ["abc(", "  )def"], cursor: [1, 0], keys: "J", expect: ["abc()def"], cursorAfter: [1, 4] },
  { name: "J onto an empty line adds no space",
    lines: ["", "abc"], cursor: [1, 0], keys: "J", expect: ["abc"], cursorAfter: [1, 0] },
  { name: "J after a trailing tab adds no space",
    lines: ["abc\t", "def"], cursor: [1, 0], keys: "J", expect: ["abc\tdef"], cursorAfter: [1, 4] },
  { name: "VJ on one line joins two lines",
    lines: ["abc", "def", "ghi"], cursor: [1, 0], keys: "VJ", expect: ["abc def", "ghi"], cursorAfter: [1, 3] },
  { name: "2J on the last line does nothing",
    lines: ["abc", "def", "ghi"], cursor: [3, 1], keys: "2J", expect: ["abc", "def", "ghi"], cursorAfter: [3, 1] },
  { name: "gJ keeps the next line's indent",
    lines: ["abc", "  def"], cursor: [1, 1], keys: "gJ", expect: ["abc  def"], cursorAfter: [1, 3] },
  { name: "Vc on one line leaves an empty line",
    lines: ["x = 1", "y"], cursor: [1, 2], keys: "Vcz<Esc>", expect: ["z", "y"], cursorAfter: [1, 0] },
  { name: "Vs on one line leaves an empty line",
    lines: ["x = 1", "y"], cursor: [1, 2], keys: "Vsz<Esc>", expect: ["z", "y"], cursorAfter: [1, 0] },
  { name: "~ on the last character keeps the cursor on it",
    lines: ["abc"], cursor: [1, 2], keys: "~", expect: ["abC"], cursorAfter: [1, 2] },
  { name: "5~ past the end keeps the cursor on the last character",
    lines: ["abc"], cursor: [1, 1], keys: "5~", expect: ["aBC"], cursorAfter: [1, 2] },
  { name: "} on a one-line buffer goes to the last character",
    lines: ["abc def"], cursor: [1, 0], keys: "}", expect: ["abc def"], cursorAfter: [1, 6] },
  { name: "} with no blank line ahead goes to the last character",
    lines: ["abc", "def"], cursor: [1, 1], keys: "}", expect: ["abc", "def"], cursorAfter: [2, 2] },
  { name: "d} to the end of the buffer is inclusive",
    lines: ["abc", "def"], cursor: [2, 2], keys: "d}", expect: ["abc", "de"], cursorAfter: [2, 1] },
  { name: "3} past the end does not move",
    lines: ["abc", "", "def"], cursor: [1, 1], keys: "3}", expect: ["abc", "", "def"], cursorAfter: [1, 1] },
  { name: "3{ past the start does not move",
    lines: ["abc", "", "def"], cursor: [3, 1], keys: "3{", expect: ["abc", "", "def"], cursorAfter: [3, 1] },
  { name: "va' before the first string selects it with the trailing space",
    lines: ["x = 'ab' + 'cd'"], cursor: [1, 0], keys: "va'<Esc>", expect: ["x = 'ab' + 'cd'"], cursorAfter: [1, 8] },
  { name: "vi\" after the last quote fails and keeps the cursor",
    lines: ["x = \"ab\" + y"], cursor: [1, 11], keys: "vi\"<Esc>", expect: ["x = \"ab\" + y"], cursorAfter: [1, 11] },
  { name: "di\" skips an escaped quote",
    lines: ["x = \"a\\\"b\" + y"], cursor: [1, 5], keys: "di\"", expect: ["x = \"\" + y"], cursorAfter: [1, 5] },
  { name: "da' takes the trailing white space",
    lines: ["x = 'ab'  + y"], cursor: [1, 5], keys: "da'", expect: ["x = + y"], cursorAfter: [1, 4] },
  { name: "da' with nothing after takes the leading white space",
    lines: ["x = 'ab'"], cursor: [1, 5], keys: "da'", expect: ["x ="], cursorAfter: [1, 2] },
  { name: "2di' includes the quotes",
    lines: ["x = 'ab' 'cd'"], cursor: [1, 5], keys: "2di'", expect: ["x =  'cd'"], cursorAfter: [1, 4] },
  { name: "j from a tab keeps the display column (end of the tab)",
    lines: ["\tabc", "abcdefgh"], cursor: [1, 0], keys: "j", expect: ["\tabc", "abcdefgh"], cursorAfter: [2, 3] },
  { name: "j over a tab-indented line keeps the display column",
    lines: ["\tabcdef", "        abc", "\tabc"], cursor: [1, 3], keys: "j", expect: ["\tabcdef", "        abc", "\tabc"], cursorAfter: [2, 6] },
  { name: "gk with nowrap keeps the wanted column",
    lines: ["abcdefgh", "\tab", "abcdefgh"], cursor: [1, 5], keys: "jgk", expect: ["abcdefgh", "\tab", "abcdefgh"], cursorAfter: [1, 5] },
  { name: "dgk with nowrap is linewise",
    lines: ["abcdefgh", "ab", "abcdefgh"], cursor: [3, 6], keys: "dgk", expect: ["abcdefgh"], cursorAfter: [1, 0] },
  { name: "Vu leaves the cursor in column 0",
    lines: ["  abc def", "x"], cursor: [1, 6], keys: "Vu", expect: ["  abc def", "x"], cursorAfter: [1, 0] },
  { name: "V~ leaves the cursor in column 0",
    lines: ["  abc def", "x"], cursor: [1, 6], keys: "V~", expect: ["  ABC DEF", "x"], cursorAfter: [1, 0] },
  { name: "VkU leaves the cursor where it is (above the anchor)",
    lines: ["abc def", "  ghi jkl"], cursor: [2, 6], keys: "VkU", expect: ["ABC DEF", "  GHI JKL"], cursorAfter: [1, 6] },
  { name: "V$<Esc> leaves the cursor on the last character",
    lines: ["  abc def", "x"], cursor: [1, 6], keys: "V$<Esc>", expect: ["  abc def", "x"], cursorAfter: [1, 8] },
  { name: "g~ap leaves the cursor on the paragraph's first line",
    lines: ["abc", "", "Def", "ghi", "", "x"], cursor: [4, 1], keys: "g~ap", expect: ["abc", "", "dEF", "GHI", "", "x"], cursorAfter: [3, 0] },
  { name: "g~k leaves the cursor on the upper line, same column",
    lines: ["abc", "def", "ghi"], cursor: [3, 2], keys: "g~k", expect: ["abc", "DEF", "GHI"], cursorAfter: [2, 2] },
  { name: "g~- is linewise",
    lines: ["abc", "def", "ghi"], cursor: [3, 2], keys: "g~-", expect: ["abc", "DEF", "GHI"], cursorAfter: [2, 0] },
  { name: "gu2G goes to line 2",
    lines: ["abc", "def", "ghi"], cursor: [3, 2], keys: "gu2G", expect: ["abc", "def", "ghi"], cursorAfter: [2, 0] },
  { name: "g~~ goes to the first non-blank",
    lines: ["abc", "  def", "ghi"], cursor: [2, 4], keys: "g~~", expect: ["abc", "  DEF", "ghi"], cursorAfter: [2, 2] },
  { name: "2g~~ keeps the column",
    lines: ["  abcdef", "  xyz", "q"], cursor: [1, 5], keys: "2g~~", expect: ["  ABCDEF", "  XYZ", "q"], cursorAfter: [1, 5] },
  // vimfixes fix 10: put (p P gp gP ]p [p) cursor and text, as Vim's do_put().
  { name: "ddp on the last line puts the line back without an empty line (fix 2's register)",
    lines: ["abc", "def", "ghi"], cursor: [3, 1], keys: "ddp", expect: ["abc", "def", "ghi"], cursorAfter: [3, 0] },
  { name: "2ddp at the end puts the lines back below",
    lines: ["abc", "def", "ghi"], cursor: [2, 1], keys: "2ddp", expect: ["abc", "def", "ghi"], cursorAfter: [2, 0] },
  { name: "ddP on the last line",
    lines: ["abc", "def", "ghi"], cursor: [3, 1], keys: "ddP", expect: ["abc", "ghi", "def"], cursorAfter: [2, 0] },
  { name: "xP ends on the last pasted character",
    lines: ["abc", "def"], cursor: [1, 1], keys: "xP", expect: ["abc", "def"], cursorAfter: [1, 1] },
  { name: "x2P ends on the last pasted character",
    lines: ["abc", "def"], cursor: [1, 1], keys: "x2P", expect: ["abbc", "def"], cursorAfter: [1, 2] },
  { name: "xgp leaves the cursor just after the text",
    lines: ["abc", "def"], cursor: [1, 1], keys: "xgp", expect: ["acb", "def"], cursorAfter: [1, 2] },
  { name: "xgP leaves the cursor just after the text",
    lines: ["abc", "def"], cursor: [1, 1], keys: "xgP", expect: ["abc", "def"], cursorAfter: [1, 2] },
  { name: "ywgp leaves the cursor just after the text",
    lines: ["abc", "def"], cursor: [1, 0], keys: "ywgp", expect: ["aabcbc", "def"], cursorAfter: [1, 4] },
  { name: "yyjgp leaves the cursor on the line below the pasted line",
    lines: ["abc", "def", "ghi"], cursor: [1, 0], keys: "yyjgp", expect: ["abc", "def", "abc", "ghi"], cursorAfter: [4, 0] },
  { name: "yyGgp at the end leaves the cursor on the pasted last line",
    lines: ["abc", "def", "ghi"], cursor: [1, 0], keys: "yyGgp", expect: ["abc", "def", "ghi", "abc"], cursorAfter: [4, 0] },
  { name: "yyjgP leaves the cursor on the line below the pasted line",
    lines: ["abc", "def", "ghi"], cursor: [1, 0], keys: "yyjgP", expect: ["abc", "abc", "def", "ghi"], cursorAfter: [3, 0] },
  { name: "gp of a multi-line charwise register ends after the text",
    lines: ["ab cd", "ef"], cursor: [1, 1], keys: "d/f<CR>gp", expect: ["afb cd", "e"], cursorAfter: [2, 0] },
  { name: "gP of a multi-line charwise register ends after the text",
    lines: ["ab cd", "ef"], cursor: [1, 1], keys: "d/f<CR>gP", expect: ["ab cd", "ef"], cursorAfter: [2, 1] },
  { name: "]p with a charwise register is p (no indent change)",
    lines: ["  abc", "def"], cursor: [1, 3], keys: "x]p", expect: ["  acb", "def"], cursorAfter: [1, 4] },
  { name: "[p with a charwise register is P",
    lines: ["  abc", "def"], cursor: [1, 3], keys: "x[p", expect: ["  abc", "def"], cursorAfter: [1, 3] },
  { name: "yiwP ends on the last pasted character",
    lines: ["abc def"], cursor: [1, 4], keys: "yiwP", expect: ["abc defdef"], cursorAfter: [1, 6] },
  { name: "VdP on the last line",
    lines: ["abc", "def", "ghi"], cursor: [3, 0], keys: "VdP", expect: ["abc", "ghi", "def"], cursorAfter: [2, 0] },
  { name: "Vkdp at the end puts the lines back below",
    lines: ["abc", "def", "ghi"], cursor: [3, 1], keys: "Vkdp", expect: ["abc", "def", "ghi"], cursorAfter: [2, 0] },
  // vimfixes fix 10: `.` never repeats a yank or an operator whose motion failed.
  { name: ". after yy repeats the x before it (a yank is not repeatable)",
    lines: ["abc def"], cursor: [1, 3], keys: "xyy.", expect: ["abcef"], cursorAfter: [1, 3] },
  { name: ". after a Visual y repeats the x before it",
    lines: ["abc def"], cursor: [1, 0], keys: "xvly.", expect: ["c def"], cursorAfter: [1, 0] },
  { name: ". after yiw repeats the cw before it, with its text",
    lines: ["abc def ghi"], cursor: [1, 0], keys: "cwX<Esc>wyiww.", expect: ["X def X"], cursorAfter: [1, 6] },
  { name: ". after a failed dfz repeats the dw before it",
    lines: ["abc def ghi"], cursor: [1, 0], keys: "dwdfz.", expect: ["ghi"], cursorAfter: [1, 0] },
  { name: ". after a failed c; repeats the cgg before it",
    lines: ["abc", "def", "ghi"], cursor: [1, 0], keys: "cggx<Esc>c;j.", expect: ["x", "ghi"], cursorAfter: [1, 0] },
  { name: ". after yl repeats the insert before it",
    lines: ["abc def ghi"], cursor: [1, 0], keys: "ix<Esc>yl.", expect: ["xxabc def ghi"], cursorAfter: [1, 0] },
  // vimfixes fixes 5, 6, 10: block objects (Neovim's forward search), Visual-line text objects go charwise, N%, g<CR>.
  { name: "ci( before a block on the line takes the next block (Neovim's current_block)",
    lines: ["abc (def)"], cursor: [1, 0], keys: "ci(x", expect: ["abc (x)"], cursorAfter: [1, 6] },
  { name: "di( outside any block skips a balanced ) and takes the next block",
    lines: ["x) (a (b) c) (d)"], cursor: [1, 0], keys: "di(", expect: ["x) (a () c) (d)"], cursorAfter: [1, 7] },
  { name: "d2a( outside any block takes the second next block forward",
    lines: ["x (a (b) c) (d)"], cursor: [1, 0], keys: "d2a(", expect: ["x (a  c) (d)"], cursorAfter: [1, 5] },
  { name: "di{ before a { at the end of the line takes that block, linewise",
    lines: ["f() {", "  a;", "}"], cursor: [1, 0], keys: "di{", expect: ["f() {", "}"], cursorAfter: [2, 0] },
  { name: "<i{ before a { at the end of the line shifts the block's body",
    lines: ["f() {", "  a;", "}"], cursor: [1, 0], keys: "<i{", expect: ["f() {", "a;", "}"], cursorAfter: [2, 0] },
  { name: "da( with no block anywhere does nothing",
    lines: ["abc def"], cursor: [1, 0], keys: "da(", expect: ["abc def"], cursorAfter: [1, 0] },
  { name: "Vaw switches to charwise Visual and selects the word with its space",
    lines: ["a b c", "d e"], cursor: [1, 2], keys: "Vaw<Esc>", expect: ["a b c", "d e"], cursorAfter: [1, 3] },
  { name: "Viwd deletes the word only (charwise)",
    lines: ["a b c", "d e"], cursor: [1, 2], keys: "Viwd", expect: ["a  c", "d e"], cursorAfter: [1, 2] },
  { name: "Vi(d deletes the block's inside only (charwise)",
    lines: ["a (b c)", "d e"], cursor: [1, 4], keys: "Vi(d", expect: ["a ()", "d e"], cursorAfter: [1, 3] },
  { name: "Va[d deletes the block only (charwise)",
    lines: ["a [b c]", "d e"], cursor: [1, 4], keys: "Va[d", expect: ["a ", "d e"], cursorAfter: [1, 1] },
  { name: "Vi'd deletes the string's inside only (charwise)",
    lines: ["a 'b c'", "d e"], cursor: [1, 4], keys: "Vi'd", expect: ["a ''", "d e"], cursorAfter: [1, 3] },
  { name: "50% goes to the middle line",
    lines: ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"], cursor: [1, 0], keys: "50%", expect: ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"], cursorAfter: [5, 0] },
  { name: "d30% from column 0 deletes the lines before the target (exclusive-linewise)",
    lines: ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"], cursor: [1, 0], keys: "d30%", expect: ["c", "d", "e", "f", "g", "h", "i", "j"], cursorAfter: [1, 0] },
  { name: "101% fails",
    lines: ["a", "b", "c"], cursor: [1, 0], keys: "101%", expect: ["a", "b", "c"], cursorAfter: [1, 0] },
  { name: "g<CR> does nothing (x then deletes)",
    lines: ["abc", "def"], cursor: [1, 1], keys: "g<CR>x", expect: ["ac", "def"], cursorAfter: [1, 1] },
  // Passes since vimfixes clamps a Normal-mode cursor past the end of the line after each key
  // (fix 10); :normal itself belongs to vimfixes-macros-indent.ts.
  { name: ":%norm A; leaves the cursor on the ;",
    lines: ["abc", "def"], cursor: [1, 0], keys: ":%norm A;<CR>", expect: ["abc;", "def;"], cursorAfter: [2, 3] },
  // Backwards ex ranges: Neovim swaps them (`:.,1d` used to throw "Invalid change range"
  // in replaceRange; difftest seed 20261015, `fl=,:.,3d<CR>` minimised). A bare range
  // `:4,2<CR>` is not swapped: it goes to line 2.
  { name: ":.,1d deletes lines 1 to the cursor line; cursor on the first non-blank",
    lines: ["def f():", "    a = 1", "    b = 2", "    c = 3"], cursor: [3, 4], keys: ":.,1d<CR>", expect: ["    c = 3"], cursorAfter: [1, 4] },
  { name: ":.,2d from the last line (cpp)", lang: "cpp",
    lines: ["int f() {", "    int a;", "    return a;", "}"], cursor: [4, 0], keys: ":.,2d<CR>", expect: ["int f() {"], cursorAfter: [1, 0] },
  { name: ":4,2j joins lines 2-4",
    lines: ["a1", "b2", "c3", "d4", "e5"], cursor: [5, 0], keys: ":4,2j<CR>", expect: ["a1", "b2 c3 d4", "e5"], cursorAfter: [2, 0] },
  { name: ":4,2normal Ax appends to lines 2-4",
    lines: ["a1", "b2", "c3", "d4", "e5"], cursor: [5, 0], keys: ":4,2normal Ax<CR>", expect: ["a1", "b2x", "c3x", "d4x", "e5"], cursorAfter: [4, 2] },
  { name: ":4,2g/./d deletes lines 2-4",
    lines: ["a1", "b2", "c3", "d4", "e5"], cursor: [5, 0], keys: ":4,2g/./d<CR>", expect: ["a1", "e5"], cursorAfter: [2, 0] },
  { name: ":4,2<CR> goes to line 2 (a bare range is not swapped)",
    lines: ["a1", "b2", "c3", "d4", "e5"], cursor: [5, 0], keys: ":4,2<CR>", expect: ["a1", "b2", "c3", "d4", "e5"], cursorAfter: [2, 0] },
  // :s with an empty pattern and no previous search: E35, nothing changes, Normal mode
  // (codemirror-vim threw a TypeError reading the missing query).
  { name: ":s//x/ with no previous search changes nothing (E35); x then deletes",
    lines: ["abc def", "def ghi"], cursor: [1, 0], keys: ":s//x/<CR>x", expect: ["bc def", "def ghi"], cursorAfter: [1, 0] },
  { name: ":%s///g with no previous search changes nothing (E35)",
    lines: ["abc def", "def ghi"], cursor: [1, 0], keys: ":%s///g<CR>x", expect: ["bc def", "def ghi"], cursorAfter: [1, 0] },
  // Cursor not checked: codemirror-vim leaves it on the replacement, Neovim on column 0 (an open :s cursor divergence, difftest `(cursor)` findings).
  { name: "/def then :s//x/ substitutes the last search pattern",
    lines: ["abc def", "def ghi"], cursor: [1, 0], keys: "/def<CR>:s//x/<CR>", expect: ["abc x", "def ghi"] },
  // Ends in Insert mode with `<` waiting 200 ms for a <C-…> key; the next case's mount
  // destroys the editor first, which used to make that timer throw (a page error at the end).
  { name: "a< then remount: no page error from the pending Insert-mode key",
    lines: ["ab"], cursor: [1, 0], keys: "a<", expect: ["a<b"], cursorAfter: [1, 2] },
  ...MACRO_INDENT_CASES, // macros, :normal, auto-indent, Insert <C-w>, :j (vimfixes-macros-indent.ts)
];
// Open emulator bugs found by difftest (seed 20261012, docs/plan/12), accepted in
// content/difftest/known.jsonl as class a. Expected values are Neovim's (with
// startofline, as in Vim). They run on every pass and print XFAIL; one that starts
// passing prints XPASS and fails the run, so its fix gets moved into CASES.
// Today the browser gives the result after "web:". Empty since round 4: <NL>, :m<CR>
// and the auto-indent cases moved into cases-macros-indent.mjs.
const KNOWN_FAILING = [
];
// Smoke: Playwright must accept the key name each of these tokens maps to (keys.mjs);
// a bad name would otherwise throw only when a real exercise first uses the token.
const SMOKE_KEYS = "<Nul><C-@><NL><F12><C-Space><C-Bslash><C-->";

// Mount case `c` in the emulator page, type its keys and compare with nvim's result; called per case by the loops below.
async function runCase(page, c) {
  const ex = {
    id: "e2e/editor", skill: "e2e", lang: c.lang ?? "python", kind: "edit", task: c.name,
    start: { lines: c.lines, cursor: c.cursor }, expect: { lines: c.expect }, par: { keys: c.keys, count: 0 },
  };
  await page.evaluate((ex) => window.emu.mount(ex), ex);
  await page.waitForFunction(() => !!document.activeElement?.closest(".cm-editor"), null, { timeout: 3000 });
  await typeKeys(page, c.keys);
  await page.waitForTimeout(50);
  const snap = (await page.evaluate(() => window.emu.status())).snap;
  const ok = JSON.stringify(snap.lines) === JSON.stringify(c.expect) &&
    (!c.cursorAfter || JSON.stringify(snap.cursor) === JSON.stringify(c.cursorAfter));
  return { ok, snap };
}

const root = fileURLToPath(new URL("..", import.meta.url));
const server = await createServer({ root, logLevel: "error", server: { port: 0 } });
await server.listen();
const url = server.resolvedUrls.local[0];
const engines = process.argv.includes("--all") ? { chromium, firefox, webkit } : { chromium };
let failures = 0;

for (const [engine, type] of Object.entries(engines)) {
  const browser = await type.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`${url}emulator-check.html`);
  await page.waitForFunction(() => !!window.emu);
  for (const c of CASES) {
    const { ok, snap } = await runCase(page, c);
    if (c.xfailIn?.includes(engine)) {
      // A known engine-specific, timing-dependent failure: reported, never counted.
      console.log(`${ok ? "XPASS" : "XFAIL"}  [${engine}] ${c.name} (xfailIn ${engine}: does not count)`);
      continue;
    }
    if (!ok) failures++;
    console.log(`${ok ? "PASS" : "FAIL"}  [${engine}] ${c.name}${ok ? "" : `\n        got ${JSON.stringify(snap.lines)} cursor ${JSON.stringify(snap.cursor)}`}`);
  }
  for (const c of KNOWN_FAILING) {
    const { ok } = await runCase(page, c);
    if (ok) failures++;
    console.log(`${ok ? "XPASS (now passes: move it into CASES)" : "XFAIL"}  [${engine}] ${c.name}`);
  }
  for (const tok of tokenize(SMOKE_KEYS)) {
    const err = await typeKeys(page, tok).then(() => null, (e) => String(e));
    if (err) failures++;
    console.log(`${err ? "FAIL" : "PASS"}  [${engine}] Playwright accepts ${tok}${err ? `\n        ${err}` : ""}`);
  }
  if (errors.length) {
    failures++;
    console.log(`FAIL  [${engine}] page errors: ${errors.join(" | ")}`);
  }
  await browser.close();
}

await server.close();
console.log(failures ? `\n${failures} check(s) failed` : "\nall checks passed");
process.exit(failures ? 1 : 0);
