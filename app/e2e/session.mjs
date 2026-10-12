// End-to-end session against the real content in ../build (run `make content` first).
//
//   npm run e2e:session            # Chromium
//   npm run e2e:session -- --all   # Chromium, Firefox, WebKit
//
// First visit -> placement solved at par -> a 15-exercise session (warm-ups and
// practice; one give-up, one retry) -> summary. Checks: focus changes, no exercise
// repeats in the session, result-strip values match the exercise, localStorage
// survives a reload, and export -> reset -> import restores the same state.
process.env.PLAYWRIGHT_BROWSERS_PATH ??= "0";

const { createServer } = await import("vite");
const { chromium, firefox, webkit } = await import("playwright");
const { fileURLToPath } = await import("node:url");
const { existsSync, readFileSync } = await import("node:fs");

const root = fileURLToPath(new URL("..", import.meta.url));
if (!existsSync(new URL("../../build/index.json", import.meta.url))) {
  console.error("build/index.json is missing: run `make content` first.");
  process.exit(2);
}
const server = await createServer({ root, logLevel: "error", server: { port: 0 } });
await server.listen();
const url = server.resolvedUrls.local[0];

const SESSION = 15;
const engines = process.argv.includes("--all") ? { chromium, firefox, webkit } : { chromium };
let failures = 0;
function check(engine, name, ok, detail) {
  if (!ok) failures++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${engine}] ${name}${detail && !ok ? `\n        ${detail}` : ""}`);
}

const text = (page, sel) => page.locator(sel).innerText();
const current = (page) =>
  page.evaluate(() => {
    const c = window.vimTrainer.current();
    return c && { id: c.ex.id, skill: c.skill, role: c.role, phase: c.phase, retry: c.retry, par: c.ex.par, kind: c.ex.kind };
  });

/** Wait until a fresh exercise is mounted and the editor has focus. */
async function nextMounted(page, prevKey) {
  await page.waitForFunction(
    (prev) => {
      const c = window.vimTrainer.current();
      return c && c.phase === "solving" && `${c.ex.id}|${c.retry}|${c.editor.view.dom.isConnected}` !== prev && !!document.activeElement?.closest(".cm-editor");
    },
    prevKey,
    { timeout: 8000 },
  );
  return current(page);
}

/** Type a key string in Vim notation (<Esc>, <CR>, or literal characters). */
async function typeKeys(page, keys) {
  for (const tok of keys.match(/<Esc>|<CR>|./gs) ?? []) {
    if (tok === "<Esc>") await page.keyboard.press("Escape");
    else if (tok === "<CR>") await page.keyboard.press("Enter");
    else await page.keyboard.type(tok);
  }
}

async function solveAtPar(page, engine, ex, label) {
  await typeKeys(page, ex.par.keys);
  const done = await page.waitForSelector("#result", { timeout: 3000 }).then(() => true, () => false);
  if (!done) {
    check(engine, `${label}: par ${ex.par.keys} solves ${ex.id} in the browser`, false, "no result after typing the par");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await page.waitForSelector("#result", { timeout: 3000 });
    return false;
  }
  const strip = await text(page, "#result");
  const you = await text(page, "#result .you");
  const par = await text(page, "#result .par");
  const ok = strip.includes("correct") && you.includes(`${ex.par.count} keys`) && you.includes("at par") &&
    par.includes(ex.par.keys) && new RegExp(`\\b${ex.par.count}\\b`).test(par) && /\d+(\.\d)?\s?s/.test(you);
  check(engine, `${label}: ${ex.id} (${ex.kind}) correct at par, strip shows ${ex.par.count} keys`, ok, `${you} || ${par}`);
  return ok;
}

for (const [engine, type] of Object.entries(engines)) {
  const browser = await type.launch();
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  const errors = [];
  page.on("console", (m) => m.type() === "error" && !m.text().startsWith("Failed to load resource") && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(String(e)));
  const warnings = [];
  page.on("console", (m) => m.type() === "warning" && warnings.push(m.text()));

  try {
    await page.goto(url);
    await page.waitForSelector(".choice", { timeout: 8000 });
    check(engine, "real build/ is loaded (no build-sample fallback)", !warnings.some((w) => w.includes("build-sample")), warnings.join(" | "));
    for (let i = 0; i < 3; i++) await page.keyboard.press("Enter"); // Python, Neovim, relative numbers
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("where you are"));
    await page.keyboard.press("Enter");

    // Placement: solve every item at par.
    let key = "";
    let placed = 0;
    for (let i = 0; i < 20; i++) {
      const ex = await nextMounted(page, key).catch(() => null);
      if (!ex) break;
      if (ex.role !== "placement") break;
      key = `${ex.id}|${ex.retry}|true`;
      await solveAtPar(page, engine, ex, `placement ${i + 1}`);
      placed++;
      await page.keyboard.press(" ");
      const atStats = await page
        .waitForFunction(() => document.querySelector("#page")?.textContent?.includes("We'll start with"), null, { timeout: 1500 })
        .then(() => true, () => false);
      if (atStats) break;
    }
    check(engine, `placement ran ${placed} exercises and ended on stats`, placed >= 5 && (await text(page, "#page")).includes("We'll start with"), String(placed));
    const statRows = await page.locator("table.skills tr[data-i]").count();
    check(engine, "stats lists the 15 skills that have exercises", statRows === 15, String(statRows));

    // The session.
    await page.keyboard.press("Enter");
    const seen = [];
    key = "";
    for (let i = 0; i < SESSION; i++) {
      const ex = await nextMounted(page, key);
      key = `${ex.id}|${ex.retry}|true`;
      seen.push(ex);
      const label = `session ${i + 1} ${ex.role}`;
      if (i === 3) {
        // Give up: Esc Esc in normal mode.
        await page.keyboard.press("Escape");
        await page.keyboard.press("Escape");
        await page.waitForSelector("#result", { timeout: 3000 });
        const strip = await text(page, "#result");
        const shows = ex.kind === "cursor" ? strip.includes("target: line") : (await page.locator("#result pre.diff").count()) === 1;
        check(engine, `${label}: Esc Esc gives up and shows the ${ex.kind === "cursor" ? "target" : "expected diff"}`, strip.includes("gave up") && shows, strip);
      } else if (i === 6) {
        // Over par first (a no-op detour), then r and solve at par.
        await page.keyboard.type("jk");
        await typeKeys(page, ex.par.keys);
        const passed = await page.waitForSelector("#result", { timeout: 3000 }).then(() => true, () => false);
        if (!passed) {
          await page.keyboard.press("Escape");
          await page.keyboard.press("Escape");
          await page.waitForSelector("#result", { timeout: 3000 });
        } else {
          const you = await text(page, "#result .you");
          check(engine, `${label}: a detour costs keys (${ex.par.count + 2} keys)`, you.includes(`${ex.par.count + 2} keys`), you);
        }
        await page.keyboard.press("r");
        const again = await nextMounted(page, key);
        key = `${again.id}|${again.retry}|true`;
        check(engine, `${label}: r retries the same exercise`, again.id === ex.id && again.retry === true);
        await solveAtPar(page, engine, again, `${label} retry`);
      } else {
        await solveAtPar(page, engine, ex, label);
      }
      if (i < SESSION - 1) await page.keyboard.press(" ");
    }

    const practice = seen.filter((e) => e.role === "practice");
    const focusSkills = [...new Set(practice.map((e) => e.skill))];
    check(engine, "focus changes during the session", focusSkills.length >= 2, focusSkills.join(","));
    const ids = seen.map((e) => e.id);
    check(engine, "no exercise repeats in the session", new Set(ids).size === ids.length, ids.join(" "));
    const log = await page.evaluate(() => window.vimTrainer.saved().model.log);
    const counted = log.filter((r) => !r.placement);
    check(engine, `model log has the practice attempts (${practice.length} + 1 retry)`, counted.length === practice.length + 1,
      `${counted.length} vs ${practice.length}`);
    check(engine, "every logged practice attempt carries ms, keys and par", counted.every((r) => r.ms > 0 && r.keys >= 0 && r.par > 0));
    console.log(`        [${engine}] focus sequence: ${seen.map((e) => `${e.role === "warmup" ? "w:" : ""}${e.skill}`).join(" ")}`);

    // localStorage round trip.
    const live = await page.evaluate(() => JSON.stringify(window.vimTrainer.saved()));
    const stored = await page.evaluate(() => localStorage.getItem("vim-trainer.v1"));
    check(engine, "localStorage holds exactly the live state", stored === live);

    await page.keyboard.press("q");
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("Session done"), null, { timeout: 5000 });
    const summary = await text(page, "#page");
    check(engine, `summary counts ${SESSION} exercises`, summary.includes(`${SESSION} exercises`), summary);

    await page.reload();
    await page.waitForSelector("#practice:not([hidden])", { timeout: 8000 });
    const afterReload = await page.evaluate(() => window.vimTrainer.saved());
    check(engine, "reload restores the model log and sessions", afterReload.model.log.length === log.length && afterReload.sessions.length === 1 && afterReload.placementDone,
      `${afterReload.model.log.length} vs ${log.length}`);

    // Export -> reset -> import.
    await page.locator("#nav-settings").click();
    const [download] = await Promise.all([page.waitForEvent("download"), page.locator("#btn-export").click()]);
    const file = await download.path();
    const exported = JSON.parse(readFileSync(file, "utf8"));
    check(engine, "export writes the full state", exported.model.log.length === log.length && exported.placementDone === true);
    await page.locator("#btn-reset").click();
    await page.locator("#btn-reset").click(); // armed: erases and reloads
    await page.waitForSelector(".choice", { timeout: 8000 });
    check(engine, "reset returns to the first visit", (await text(page, "#page")).includes("Which language"));
    await page.locator("#nav-settings").click();
    await page.locator("#file-import").setInputFiles(file);
    await page.waitForFunction(() => document.querySelector("#settings-msg")?.textContent?.includes("imported"), null, { timeout: 5000 });
    const imported = await page.evaluate(() => window.vimTrainer.saved());
    check(engine, "import restores the exported state", JSON.stringify(imported.model) === JSON.stringify(exported.model) && imported.sessions.length === 1);
    await page.reload();
    await page.waitForSelector("#practice:not([hidden])", { timeout: 8000 });
    check(engine, "after import, a reload resumes practice", true);
  } catch (err) {
    failures++;
    console.log(`FAIL  [${engine}] ${err.message}`);
    await page.screenshot({ path: `e2e-failure-session-${engine}.png` }).catch(() => {});
  }
  check(engine, "no page errors", errors.length === 0, errors.join(" | "));
  await browser.close();
}

await server.close();
console.log(failures ? `\n${failures} check(s) failed` : "\nall checks passed");
process.exit(failures ? 1 : 0);
