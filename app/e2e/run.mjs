// End-to-end check of the practice loop in a real browser engine.
//
//   npm run e2e            # Chromium
//   npm run e2e -- --all   # Chromium, Firefox, WebKit
//
// Flow: first visit (language, editor, relative numbers) -> placement -> skip the
// first exercise with Esc Esc -> solve the ci" exercise -> the result strip says
// "correct" with par 12. Then the ex exercise, the end of placement, stats, one
// practice exercise and the session summary. Along the way: an <Esc> that cancels a
// pending operator or count is not half of the give-up (and the first real one shows a
// cue), insert-mode <Tab> follows the oracle's tab stops, a cursor give-up marks the
// target, the snippet source line, a double space advances once, the placement count
// on retries, the ex-kind "a : command was required" give-up, the attempt clock
// pausing while stats / settings are open, the "!" flag (picker, note, prefilled issue
// URL via a stubbed window.open, the flag in the log) and the "beat par" band.
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
  // The sample has no `source`; give t.quote one so the strip's attribution line shows.
  await page.route("**/build-sample/exercises/python/t.quote/*.json", async (r) => {
    const res = await r.fetch();
    const json = await res.json();
    json.source = { repo: "github.com/exercism/python", path: "exercises/practice/x/.meta/example.py", commit: null, license: "MIT", lines: [1, 9] };
    await r.fulfill({ response: res, json });
  });
  // Slow the first load of x.global so a double space lands while it is in flight.
  await page.route("**/build-sample/exercises/python/x.global/*.json", async (r) => {
    await new Promise((res) => setTimeout(res, 600));
    await r.continue();
  });

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

    // An <Esc> that cancels a pending operator or count is not the first half of Esc Esc.
    await page.keyboard.type("d");
    await page.keyboard.press("Escape"); // cancels d
    await page.keyboard.press("Escape"); // first real <Esc>: arms the give-up
    await page.waitForTimeout(100);
    check(engine, "d<Esc><Esc> does not give up", (await page.locator("#result").count()) === 0);
    check(engine, "the first qualifying <Esc> shows 'Esc again to give up'", (await text(page, "#giveup")).includes("again to give up"), await text(page, "#giveup"));
    await page.waitForTimeout(900);
    check(engine, "the give-up cue clears after 800 ms", !(await text(page, "#giveup")).includes("again"), await text(page, "#giveup"));
    await page.keyboard.type("3");
    await page.keyboard.press("Escape"); // cancels the count
    await page.keyboard.press("Escape");
    await page.waitForTimeout(100);
    check(engine, "3<Esc><Esc> does not give up", (await page.locator("#result").count()) === 0);
    await page.waitForTimeout(900);

    // Insert-mode <Tab>: spaces to the next 4-column stop (expandtab, ts=sw=4, sts=0), as in nvim.
    await page.keyboard.type("Ax");
    await page.keyboard.press("Tab");
    await page.keyboard.type("y");
    await page.keyboard.press("Tab");
    await page.keyboard.type("z");
    const line3 = await page.evaluate(() => window.vimTrainer.current().editor.view.state.doc.line(3).text);
    check(engine, "insert-mode <Tab> fills to the next 4-column stop", line3 === '    parser.add_argument("src")x y   z', JSON.stringify(line3));
    check(engine, "<Tab> keeps focus in the editor", await page.evaluate(() => !!document.activeElement?.closest(".cm-editor")));
    await page.keyboard.press("Escape"); // leaves insert mode: not half of the give-up

    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await waitResult(page);
    check(engine, "Esc Esc gives up and shows the strip", (await text(page, "#result")).includes("gave up"), await text(page, "#result"));
    check(engine, "cursor give-up names the target line", (await text(page, "#result")).includes("target: line 10"), await text(page, "#result"));
    check(engine, "cursor give-up shows the target line with a caret", (await text(page, "#result .targetline")).includes("args = parser.parse_args(argv)") && (await text(page, "#result .targetline")).includes("^"));
    check(engine, "cursor give-up marks the target in the editor", (await page.locator(".cm-target-reveal").count()) === 1);
    check(engine, "hand-written sample snippet: source line says so", (await text(page, "#result #src")).trim() === "written for vim-trainer", await text(page, "#result #src"));
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
    const src = await text(page, "#result #src");
    check(engine, "strip shows the snippet source 'from exercism/python \u00b7 MIT'", src.trim() === "from exercism/python \u00b7 MIT", JSON.stringify(src));

    // "!" flags this attempt: pick a reason, type a note, enter opens the prefilled issue.
    // window.open is stubbed so github.com is never loaded; the URL is checked instead.
    await page.evaluate(() => { window.__opened = []; window.open = (u) => (window.__opened.push(String(u)), {}); });
    check(engine, "strip legend lists ! flag", strip.includes("flag"), strip);
    await page.keyboard.type("!");
    await page.waitForSelector("#flagpick", { timeout: 2000 });
    await page.keyboard.press("Escape");
    check(engine, "Esc closes the flag picker without opening anything",
      (await page.locator("#flagpick").count()) === 0 && (await page.evaluate(() => window.__opened.length)) === 0);
    await page.keyboard.type("!");
    await page.waitForSelector("#flagpick", { timeout: 2000 });
    await page.keyboard.press("1");
    check(engine, "picking a reason moves focus to the note field", await page.evaluate(() => document.activeElement?.id === "flag-note"));
    await page.keyboard.type("par looks long");
    await page.keyboard.press("Enter");
    await page.waitForSelector("#flagpick", { state: "detached", timeout: 2000 });
    const opened = await page.evaluate(() => window.__opened);
    check(engine, "enter opens one prefilled issue on daniel-m-campos/vim-trainer",
      opened.length === 1 && opened[0].startsWith("https://github.com/daniel-m-campos/vim-trainer/issues/new?labels=feedback&"), JSON.stringify(opened));
    const body = opened.length ? new URL(opened[0]).searchParams.get("body") ?? "" : "";
    check(engine, "issue body carries the id, the keys, the reason and the note",
      ["py/t.quote/0001", 'ci"retrying<Esc>', "wrong-par", "par looks long"].every((s) => body.includes(s)), body);
    check(engine, "strip says flagged and has focus again", (await text(page, "#result")).includes("flagged: wrong-par") &&
      await page.evaluate(() => document.activeElement?.id === "foot"), await text(page, "#result"));
    check(engine, "strip links the issue form as a fallback",
      await page.evaluate((u) => document.querySelector("#result .flagged a")?.getAttribute("href") === u, opened[0] ?? ""));

    // r retries the same exercise; a retry with f" first triggers the exercise hint.
    await page.keyboard.press("r");
    await waitTask(page, "logger.warn");
    await editorFocused(page);
    const prog = await text(page, "#progress");
    check(engine, "a placement retry keeps its number (placement 2 of 3)", prog.includes("placement 2 of 3") && prog.includes("retry"), prog);
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
    check(engine, "result strip on a retry still says placement 2 of 3", (await text(page, "#progress")).includes("placement 2 of 3"), await text(page, "#progress"));

    // Double space (plus an r) while the next exercise loads: one advance, strip inert.
    await page.keyboard.press(" ");
    await page.keyboard.press(" ");
    await page.keyboard.press("r");
    const midLoad = await page.evaluate(() => ({ phase: window.vimTrainer.current()?.phase, task: document.querySelector("#task")?.textContent }));
    check(engine, "keys on the strip are ignored until the next exercise renders", midLoad.phase === "result" && midLoad.task.includes("logger.warn"), JSON.stringify(midLoad));

    // Placement 3: x.global (ex kind).
    await waitTask(page, "print");
    await editorFocused(page);
    await page.waitForTimeout(700); // past the stray keys: nothing more may arrive
    const after = await page.evaluate(() => ({ n: window.vimTrainer.current().editor.recorder.events.length, retry: window.vimTrainer.current().retry, prog: document.querySelector("#progress")?.textContent }));
    check(engine, "double space advanced once: placement 3 of 3, no stray keys, not a retry", after.n === 0 && !after.retry && after.prog.includes("placement 3 of 3"), JSON.stringify(after));
    check(engine, "ex-kind task says it wants a : command", (await text(page, "#task .req")).includes("Ex"), await text(page, "#task"));

    // Reach the expected buffer with dd, then give up: the strip explains instead of an empty diff.
    await page.keyboard.type("jddjjddjdd");
    await page.waitForFunction(() => document.querySelector("#midhint:not([hidden])")?.textContent?.includes(": command"), null, { timeout: 3000 });
    check(engine, "ex kind: right buffer without : shows the mid-exercise note", true);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await waitResult(page);
    const exStrip = await text(page, "#result");
    check(engine, "ex give-up with a matching buffer says a : command was required (no empty diff)",
      exStrip.includes("gave up") && exStrip.includes("a : command was required") && (await page.locator("#result pre.diff").count()) === 0, exStrip);
    await page.keyboard.press("r");
    await waitTask(page, "print");
    await editorFocused(page);
    await page.keyboard.type(":g/print/d");
    await page.keyboard.press("Enter");
    await waitResult(page);
    check(engine, ":g/print/d<CR> passes the ex exercise", (await text(page, "#result")).includes("correct"), await text(page, "#result"));
    // Fewer keys than par: "nt(" matches only the print( lines. 9 keys against par 11.
    await page.keyboard.press("r");
    await waitTask(page, "print");
    await editorFocused(page);
    await page.keyboard.type(":g/nt(/d");
    await page.keyboard.press("Enter");
    await waitResult(page);
    const beatRow = await text(page, "#result .row1");
    const beatRec = await page.evaluate(() => window.vimTrainer.current().record);
    check(engine, ":g/nt(/d<CR> beats par: 'you beat par: 9 vs 11', band 'beat par', record beatPar",
      beatRow.includes("you beat par: 9 vs 11") && beatRow.includes("beat par") && beatRec?.beatPar === true && beatRec?.seq === ":g/nt(/d<CR>",
      `${beatRow} | ${JSON.stringify(beatRec)}`);
    await page.keyboard.press(" ");

    // End of placement -> stats with the focus line.
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("We'll start with"), null, { timeout: 5000 });
    check(engine, "stats after placement names the starting skill", true);
    // Only skills with exercises are listed: the sample has 3 skills in 3 tiers.
    check(engine, "stats grid grouped by tier", (await page.locator(".sv-tier").count()) === 3, String(await page.locator(".sv-tier").count()));
    check(engine, "stats grid outlines the focus skill", (await page.locator(".sv-cell.sv-focus").count()) === 1);
    await page.keyboard.press("Tab");
    check(engine, "tab switches to progress", (await page.locator('.sv[data-tab="progress"]').count()) === 1);
    await page.keyboard.press("Tab");
    check(engine, "tab switches to sessions", (await text(page, "#page")).includes("no sessions yet") || (await page.locator("table.sv-sessions").count()) === 1);
    await page.keyboard.press("Tab");
    check(engine, "tab cycles back to skills", (await page.locator('.sv[data-tab="skills"]').count()) === 1);
    // A click on the tab already showing must not leave focus on a button (keys aimed at a button are dropped).
    await page.locator('.sv-tab[data-tab="skills"]').click();
    await page.keyboard.press("2");
    check(engine, "keys still switch tabs after clicking the active tab", (await page.locator('.sv[data-tab="progress"]').count()) === 1,
      await page.evaluate(() => document.activeElement?.tagName));
    await page.keyboard.press("1");
    const savedState = await page.evaluate(() => JSON.parse(localStorage.getItem("vim-trainer.v1") ?? "null"));
    check(engine, "state saved to localStorage with placement done", savedState?.placementDone === true && savedState.model.log.length >= 3,
      JSON.stringify(savedState?.model?.log?.length));
    // The flag set on placement 2 reached the log when placement ended, with seq and beatPar.
    const quoteRec = savedState?.model?.log?.find((r) => r.ex === "py/t.quote/0001" && !r.retry);
    check(engine, "flagged placement record is logged with flag {reason, note}, seq and beatPar",
      quoteRec?.flag?.reason === "wrong-par" && quoteRec.flag.note === "par looks long" && quoteRec.seq === 'ci"retrying<Esc>' && quoteRec.beatPar === false,
      JSON.stringify(quoteRec));

    await page.keyboard.press("Enter");
    await page.waitForSelector("#practice:not([hidden])", { timeout: 5000 });
    await editorFocused(page);
    check(engine, "enter starts practice", true);
    // The attempt clock stops while stats and settings cover the exercise.
    await page.locator("#nav-stats").click();
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("Stats"));
    await page.waitForTimeout(1500);
    await page.keyboard.press("Escape");
    await editorFocused(page);
    await page.locator("#nav-settings").click();
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("Settings"));
    await page.waitForTimeout(1000);
    await page.keyboard.press("Escape");
    await editorFocused(page);
    const clockMs = await page.evaluate(() => window.vimTrainer.current().editor.recorder.activeMs());
    check(engine, "clock paused while stats / settings were open (2.5 s away, < 1.2 s counted)", clockMs < 1200, String(Math.round(clockMs)));
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
    const href = await page.locator("#attribution-link").getAttribute("href").catch(() => null);
    check(engine, "settings links ATTRIBUTION.md", !!href && href.endsWith("ATTRIBUTION.md"), String(href));
    const issues = await page.locator("#issues-link").getAttribute("href").catch(() => null);
    check(engine, "settings 'share your log' links the issues page", issues === "https://github.com/daniel-m-campos/vim-trainer/issues", String(issues));
    await page.keyboard.press("Escape");
    check(engine, "Esc returns to the summary", (await text(page, "#page")).includes("Session done"));
    // Stats opened from settings: Esc goes back to settings, then to the summary.
    await page.keyboard.press(",");
    await page.locator("#nav-stats").click();
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("Stats"));
    await page.keyboard.press("Escape");
    check(engine, "Esc from stats opened in settings returns to settings", (await text(page, "#page")).includes("Settings"), await text(page, "#page"));
    await page.keyboard.press("Escape");
    check(engine, "then Esc returns to the summary", (await text(page, "#page")).includes("Session done"), await text(page, "#page"));

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
