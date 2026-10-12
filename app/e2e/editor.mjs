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
const { typeKeys } = await import("./keys.mjs");

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
    if (!ok) failures++;
    console.log(`${ok ? "PASS" : "FAIL"}  [${engine}] ${c.name}${ok ? "" : `\n        got ${JSON.stringify(snap.lines)} cursor ${JSON.stringify(snap.cursor)}`}`);
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
