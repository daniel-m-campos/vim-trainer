// Browser check of the stats screen demo (stats-demo.html, src/stats/statsView.ts).
//
//   node e2e/stats-demo.mjs                 # Chromium
//   node e2e/stats-demo.mjs --all           # Chromium, Firefox, WebKit
//   node e2e/stats-demo.mjs --shots <dir>   # also save a screenshot per tab
//
// Asserts the three tabs render (grid cells, charts with a projection caption, the
// sessions table), the keyboard works (h j k l, enter, f, esc, tab) and the page logs no
// console errors. Browsers live in node_modules (PLAYWRIGHT_BROWSERS_PATH=0).
process.env.PLAYWRIGHT_BROWSERS_PATH ??= "0";

const { createServer } = await import("vite");
const { chromium, firefox, webkit } = await import("playwright");
const { fileURLToPath } = await import("node:url");
const { join } = await import("node:path");
const { mkdirSync } = await import("node:fs");
const { tmpdir } = await import("node:os");

const root = fileURLToPath(new URL("..", import.meta.url));
const server = await createServer({ root, logLevel: "error", server: { port: 0 } });
await server.listen();
const url = new URL("stats-demo.html", server.resolvedUrls.local[0]).href;

const shotsAt = process.argv.indexOf("--shots");
const shots = shotsAt > 0 ? process.argv[shotsAt + 1] : null;
if (shots) mkdirSync(shots, { recursive: true });
const engines = process.argv.includes("--all") ? { chromium, firefox, webkit } : { chromium };
let failures = 0;
function check(engine, name, ok, detail) {
  if (!ok) failures++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${engine}] ${name}${detail && !ok ? `\n        ${detail}` : ""}`);
}

for (const [engine, type] of Object.entries(engines)) {
  const browser = await type.launch();
  const page = await browser.newPage({ viewport: { width: 1100, height: 900 } });
  const errors = [];
  page.on("console", (m) => (m.type() === "error" && !m.text().startsWith("Failed to load resource") ? errors.push(m.text()) : null));
  page.on("pageerror", (e) => errors.push(String(e)));
  const status = () => page.locator("#demo-status").innerText();
  const shot = async (name) => shots && page.screenshot({ path: join(shots, `${engine}-${name}.png`), fullPage: true });

  try {
    await page.goto(url);
    await page.waitForSelector(".sv-cell", { timeout: 10000 });

    // Skills
    const cells = await page.locator(".sv-cell").count();
    check(engine, "skills grid renders cells grouped by tier", cells > 20 && (await page.locator(".sv-tier").count()) > 3, `${cells} cells`);
    check(engine, "a focus skill is outlined", (await page.locator(".sv-cell.sv-focus").count()) === 1);
    check(engine, "locked skills are dimmed", (await page.locator(".sv-cell.sv-locked").count()) > 0);
    check(engine, "some skills are mastered", (await page.locator(".sv-cell.sv-mastered").count()) > 0);
    check(engine, "the first cell is selected", (await page.locator('.sv-cell.sv-sel[data-i="0"]').count()) === 1);
    await shot("skills");

    await page.keyboard.press("l");
    check(engine, "l selects the next cell", (await page.locator('.sv-cell.sv-sel[data-i="1"]').count()) === 1 && (await status()).startsWith("selected 1"), await status());
    await page.keyboard.press("j");
    const afterJ = Number(await page.locator(".sv-cell.sv-sel").getAttribute("data-i"));
    check(engine, "j moves down a row", afterJ > 1, `selected ${afterJ}`);
    await page.keyboard.press("k");
    const afterK = Number(await page.locator(".sv-cell.sv-sel").getAttribute("data-i"));
    check(engine, "k moves back up", afterK < afterJ, `selected ${afterK}`);
    await page.keyboard.press("h");

    // Open the focus skill's history: click it, then enter.
    await page.locator(".sv-cell.sv-focus").click();
    await page.keyboard.press("Enter");
    await page.waitForSelector(".sv-detail", { timeout: 3000 });
    check(engine, "enter opens the history chart", (await page.locator(".sv-detail svg.sv-chart").count()) === 2);
    check(engine, "history shows the diagnosis", (await page.locator(".sv-detail .sv-diag").innerText()).includes("speed"));
    await shot("history");
    await page.keyboard.press("f");
    check(engine, "f forces the selected skill", (await status()).startsWith("forced next focus:"), await status());
    await page.keyboard.press("Escape");
    check(engine, "esc closes the history chart", (await page.locator(".sv-detail").count()) === 0);

    // Progress
    await page.keyboard.press("Tab");
    await page.waitForSelector('.sv[data-tab="progress"]', { timeout: 3000 });
    const cards = await page.locator(".sv-card").count();
    check(engine, "progress shows the focus skill and the 3 weakest", cards === 4, `${cards} cards`);
    const charts = await page.locator(".sv-card svg.sv-chart").count();
    check(engine, "each card has a time chart and a keys/par chart", charts >= 2 && charts % 2 === 0, `${charts} charts`);
    check(engine, "time charts draw a target line", (await page.locator(".sv-card .sv-ref").count()) > 0);
    const captions = await page.locator(".sv-caption").allInnerTexts();
    check(engine, "captions describe the projection", captions.length > 0 && captions.every((c) => /target|projection/.test(c)), captions.join(" | "));
    const projected = await page.locator(".sv-proj").count();
    const atTarget = captions.filter((c) => /at target in ~\d+ attempt/.test(c)).length;
    check(engine, "projection lines only where a fit exists", projected <= cards && (atTarget === 0 || projected >= atTarget), `${projected} lines, ${atTarget} 'at target in' captions`);
    check(engine, "values are printed on the charts", (await page.locator(".sv-card .sv-value").count()) >= charts);
    await shot("progress");

    // Sessions
    await page.keyboard.press("Tab");
    await page.waitForSelector('.sv[data-tab="sessions"]', { timeout: 3000 });
    const rows = await page.locator(".sv-sessions tbody tr").count();
    check(engine, "sessions table lists the 4 simulated sessions", rows === 4, `${rows} rows`);
    await shot("sessions");

    await page.keyboard.press("1");
    check(engine, "1 returns to skills", (await page.locator('.sv[data-tab="skills"]').count()) === 1);
    await page.locator('.sv-tab[data-tab="sessions"]').click();
    check(engine, "clicking a tab switches to it", (await page.locator('.sv[data-tab="sessions"]').count()) === 1);
  } catch (err) {
    check(engine, "flow completed", false, String(err));
    await page.screenshot({ path: join(shots ?? tmpdir(), `stats-demo-failure-${engine}.png`) }).catch(() => {});
  }
  check(engine, "no console errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

await server.close();
console.log(failures ? `\n${failures} check(s) failed` : "\nall stats-demo checks passed");
process.exit(failures ? 1 : 0);
