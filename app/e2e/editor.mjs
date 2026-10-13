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
];
// Known gap, not a case yet: <NL> (Ctrl-J) in Normal mode moves down like j in nvim
// ("abc"/"def", cursor [1, 1], "<NL>x" -> "abc"/"df"), but codemirror-vim ignores it
// ("ac"/"def"). No shipped par uses it; vimfixes.ts patches only what pars need.
//
// Open emulator bugs found by difftest (seed 20261012, docs/plan/12), accepted in
// content/difftest/known.jsonl as class a. Expected values are Neovim's (with
// startofline, as in Vim). They run on every pass and print XFAIL; one that starts
// passing prints XPASS and fails the run, so its fix gets moved into CASES.
// Today the browser gives the result after "web:".
const KNOWN_FAILING = [
  { name: "a failing f{c} aborts the operator (web: deletes one character)",
    lines: ["abc def"], cursor: [1, 0], keys: "dfz", expect: ["abc def"], cursorAfter: [1, 0] },
  { name: "ci' with no quotes on the line aborts, x then deletes (web: Insert mode, types x)",
    lines: ["abc def"], cursor: [1, 0], keys: "ci'x", expect: ["bc def"], cursorAfter: [1, 0] },
  { name: "S<Esc> drops the unused auto-indent (web: keeps 4 spaces, cursor [2, 3])",
    lines: ["def f():", "    x = 1"], cursor: [2, 4], keys: "S<Esc>", expect: ["def f():", ""], cursorAfter: [2, 0] },
  { name: "o<Esc> drops the unused auto-indent (web: keeps 4 spaces)",
    lines: ["def f():", "    x = 1"], cursor: [2, 4], keys: "o<Esc>", expect: ["def f():", "    x = 1", ""], cursorAfter: [3, 0] },
  { name: "<CR> in Insert mode keeps the indent (web: new line at column 0)",
    lines: ["def f():", "    x = 1"], cursor: [2, 4], keys: "A<CR>y = 2<Esc>",
    expect: ["def f():", "    x = 1", "    y = 2"], cursorAfter: [3, 8] },
  { name: "yb moves the cursor to the start of the yanked text (web: stays at [1, 4])",
    lines: ["foo bar"], cursor: [1, 4], keys: "yb", expect: ["foo bar"], cursorAfter: [1, 0] },
  { name: ">G leaves empty lines empty (web: indents the empty line)",
    lines: ["a", "", "b"], cursor: [1, 0], keys: ">G", expect: ["    a", "", "    b"], cursorAfter: [1, 4] },
  { name: "J adds no space after trailing whitespace (web: adds one)",
    lines: ["abc  ", "def"], cursor: [1, 0], keys: "J", expect: ["abc  def"], cursorAfter: [1, 5] },
  { name: ":%norm A; leaves the cursor on the ; (web: one past it)",
    lines: ["abc", "def"], cursor: [1, 0], keys: ":%norm A;<CR>", expect: ["abc;", "def;"], cursorAfter: [2, 3] },
];
// Also open: ":m<CR>" (no address) throws "E14: Invalid address" from vimfixes.ts
// parseAddress as an uncaught page error; Neovim reports E16 and changes nothing.
// Smoke: Playwright must accept the key name each of these tokens maps to (keys.mjs);
// a bad name would otherwise throw only when a real exercise first uses the token.
const SMOKE_KEYS = "<Nul><C-@><NL><F12><C-Space><C-Bslash><C-->";

// Mount case `c` in the emulator page, type its keys and compare with nvim's result; called per case by the loops below.
async function runCase(page, c) {
  const ex = {
    id: "e2e/editor", skill: "e2e", lang: "python", kind: "edit", task: c.name,
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
