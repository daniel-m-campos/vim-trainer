// End-to-end check of the practice loop in a real browser engine.
//
//   npm run e2e            # Chromium
//   npm run e2e -- --all   # Chromium, Firefox, WebKit
//
// Flow: first visit (language, editor, relative numbers) -> placement -> skip the
// first exercise with Esc Esc -> solve the ci" exercise -> the result strip says
// "correct" with par 12. Then the ex exercise, the end of placement, stats, one
// practice exercise and the session summary.
//
// /build/ is forced to 404 so the app uses the bundled sample (deterministic, and
// it exercises the fallback path). Browsers live in node_modules
// (PLAYWRIGHT_BROWSERS_PATH=0); install with
//   PLAYWRIGHT_BROWSERS_PATH=0 npx playwright install chromium firefox webkit
process.env.PLAYWRIGHT_BROWSERS_PATH ??= "0";

const { createServer } = await import("vite");
const { chromium, firefox, webkit } = await import("playwright");
const { fileURLToPath } = await import("node:url");

const root = fileURLToPath(new URL("..", import.meta.url));
const server = await createServer({ root, logLevel: "error", server: { port: 0 } });
await server.listen();
const url = server.resolvedUrls.local[0];

const engines = process.argv.includes("--all") ? { chromium, firefox, webkit } : { chromium };
let failures = 0;
function check(engine, name, ok, detail) {
  if (!ok) failures++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${engine}] ${name}${detail && !ok ? `\n        ${detail}` : ""}`);
}

const text = (page, sel) => page.locator(sel).innerText();
const editorFocused = (page) => page.waitForFunction(() => !!document.activeElement?.closest(".cm-editor"), null, { timeout: 5000 });
const waitTask = (page, s) => page.waitForFunction((s) => document.querySelector("#task")?.textContent?.includes(s), s, { timeout: 5000 });
const waitResult = (page) => page.waitForSelector("#result", { timeout: 5000 });

for (const [engine, type] of Object.entries(engines)) {
  const browser = await type.launch();
  const page = await browser.newPage();
  const warnings = [];
  const errors = [];
  // Expected 404s (the forced /build/ miss, favicon) are not errors.
  page.on("console", (m) => (m.type() === "warning" ? warnings.push(m.text()) : m.type() === "error" && !m.text().startsWith("Failed to load resource") ? errors.push(m.text()) : null));
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.route("**/build/**", (r) => r.fulfill({ status: 404, body: "not found" }));

  try {
    await page.goto(url);
    await page.waitForSelector(".choice", { timeout: 5000 });
    check(engine, "first visit shows the language question", (await text(page, "#page")).includes("Which language"));
    check(engine, "falls back to build-sample with a console warning", warnings.some((w) => w.includes("build-sample")), warnings.join(" | "));

    await page.keyboard.press("Enter"); // Python
    await page.keyboard.press("Enter"); // Neovim
    await page.keyboard.press("Enter"); // relative numbers: yes
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("where you are"));
    check(engine, "placement intro lists 3 sample exercises", (await text(page, "#page")).includes("3 short exercises"));
    await page.keyboard.press("Enter");

    // Placement 1: m.rel (cursor kind). Give up with Esc Esc.
    await waitTask(page, "assigns");
    await editorFocused(page);
    check(engine, "mode line says NORMAL and placement 1 of 3",
      (await text(page, "#mode")) === "NORMAL" && (await text(page, "#progress")).includes("placement 1 of 3"));
    const nums = await page.locator(".cm-relnums .cm-gutterElement").allInnerTexts();
    check(engine, "relative line numbers (current line absolute)", nums.includes("3") && nums.filter((n) => n === "1").length >= 2, nums.join(","));
    check(engine, "target is highlighted", (await page.locator(".cm-target").count()) > 0);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await waitResult(page);
    check(engine, "Esc Esc gives up and shows the strip", (await text(page, "#result")).includes("gave up"), await text(page, "#result"));
    await page.keyboard.press(" ");

    // Placement 2: t.quote. Solve with ci"retrying<Esc>.
    await waitTask(page, "logger.warn");
    await editorFocused(page);
    await page.keyboard.type('ci"');
    check(engine, 'after ci" the mode line says INSERT', (await text(page, "#mode")) === "INSERT");
    await page.keyboard.type("retrying");
    check(engine, "no result strip before <Esc>", (await page.locator("#result").count()) === 0);
    await page.keyboard.press("Escape");
    await waitResult(page);
    const strip = await text(page, "#result");
    check(engine, "result strip says correct", strip.includes("correct"), strip);
    const par = await text(page, "#result .par");
    check(engine, "result strip shows par ci\"retrying<Esc> 12", par.includes('ci"retrying<Esc>') && /\b12\b/.test(par), par);
    const you = await text(page, "#result .you");
    check(engine, "result strip shows your 12 keys and at par", you.includes('ci"retrying<Esc>') && you.includes("12 keys") && you.includes("at par"), you);
    check(engine, "strip lists space / r / ? / p (pro) / q",
      ["next", "retry", "hint", "replay par", "end session"].every((s) => strip.includes(s)), strip);
    check(engine, "editor is locked and the strip has focus", await page.evaluate(() => document.activeElement?.id === "foot"));

    // r retries the same exercise; a retry with f" first triggers the exercise hint.
    await page.keyboard.press("r");
    await waitTask(page, "logger.warn");
    await editorFocused(page);
    check(engine, "retry restores the start buffer", (await page.locator(".cm-content").innerText()).includes("timeout, trying again"));
    await page.keyboard.type('f"ci"retrying');
    await page.keyboard.press("Escape");
    await waitResult(page);
    const hint = await text(page, "#result .hint").catch(() => "");
    check(engine, "f\" before ci\" triggers the exercise hint", hint.includes("was unnecessary"), hint);
    const you2 = await text(page, "#result .you");
    check(engine, "retry: f\"ci\"retrying<Esc> is 14 keys, close band", you2.includes("14 keys") && you2.includes("close"), you2);

    // jk escape preference: Vim insert mapping, and jk counts as one key.
    await page.evaluate(() => (window.vimTrainer.saved().settings.escape = "jk"));
    await page.keyboard.press("r");
    await waitTask(page, "logger.warn");
    await editorFocused(page);
    await page.keyboard.type('ci"retryingjk');
    await waitResult(page);
    const you3 = await text(page, "#result .you");
    check(engine, "jk escape: ci\"retryingjk passes as 12 keys", (await text(page, "#result")).includes("correct") && you3.includes("12 keys"), you3);
    await page.evaluate(() => (window.vimTrainer.saved().settings.escape = "esc"));

    // F1 mid-command: the hint shows and the pending `ci` survives (F1 never reaches Vim).
    await page.keyboard.press("r");
    await waitTask(page, "logger.warn");
    await editorFocused(page);
    await page.keyboard.type("ci");
    await page.keyboard.press("F1");
    check(engine, "F1 during ci shows the mid-exercise hint", await page.locator("#midhint:not([hidden])").count() === 1);
    await page.keyboard.type('"retrying');
    await page.keyboard.press("Escape");
    await waitResult(page);
    const you4 = await text(page, "#result .you");
    check(engine, "F1 between ci and \" keeps the pending command: 12 keys", (await text(page, "#result")).includes("correct") && you4.includes("12 keys"), you4);
    await page.keyboard.press(" ");

    // Placement 3: x.global (ex kind).
    await waitTask(page, "print");
    check(engine, "ex-kind task says it wants a : command", (await text(page, "#task .req")).includes("Ex"), await text(page, "#task"));
    await editorFocused(page);
    await page.keyboard.type(":g/print/d");
    await page.keyboard.press("Enter");
    await waitResult(page);
    check(engine, ":g/print/d<CR> passes the ex exercise", (await text(page, "#result")).includes("correct"), await text(page, "#result"));
    await page.keyboard.press(" ");

    // End of placement -> stats with the focus line.
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("We'll start with"), null, { timeout: 5000 });
    check(engine, "stats after placement names the starting skill", true);
    // Only skills with exercises are listed: the sample has 3 skills in 3 tiers.
    check(engine, "stats table grouped by tier", (await page.locator("table.skills tr.tier").count()) === 3);
    await page.keyboard.press("Tab");
    check(engine, "tab switches to sessions", (await text(page, "#page")).includes("no sessions yet") || (await page.locator("table.sessions").count()) === 1);
    await page.keyboard.press("Tab");
    const savedState = await page.evaluate(() => JSON.parse(localStorage.getItem("vim-trainer.v1") ?? "null"));
    check(engine, "state saved to localStorage with placement done", savedState?.placementDone === true && savedState.model.log.length >= 3,
      JSON.stringify(savedState?.model?.log?.length));

    await page.keyboard.press("Enter");
    await page.waitForSelector("#practice:not([hidden])", { timeout: 5000 });
    await editorFocused(page);
    check(engine, "enter starts practice", true);
    // F1 shows a hint without touching Vim.
    await page.keyboard.press("F1");
    check(engine, "F1 reveals a mid-exercise hint", await page.locator("#midhint:not([hidden])").count() === 1);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await waitResult(page);
    await page.keyboard.press("q");
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("Session done"), null, { timeout: 5000 });
    check(engine, "q ends the session with a summary", (await text(page, "#page")).includes("1 exercises"), await text(page, "#page"));

    await page.keyboard.press(",");
    check(engine, ", opens settings", (await text(page, "#page")).includes("Settings"));
    await page.keyboard.press("Escape");
    check(engine, "Esc returns to the summary", (await text(page, "#page")).includes("Session done"));

    // Reload keeps state and goes straight to practice.
    await page.reload();
    await page.waitForSelector("#practice:not([hidden])", { timeout: 5000 });
    check(engine, "reload resumes practice (no first-visit flow)", true);
  } catch (err) {
    failures++;
    console.log(`FAIL  [${engine}] ${err.message}`);
    await page.screenshot({ path: `e2e-failure-${engine}.png` }).catch(() => {});
  }
  check(engine, "no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

await server.close();
console.log(failures ? `\n${failures} check(s) failed` : "\nall checks passed");
process.exit(failures ? 1 : 0);
