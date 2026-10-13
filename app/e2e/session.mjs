// End-to-end session against the real content in ../build (run `make content` first).
//
//   npm run e2e:session            # Chromium
//   npm run e2e:session -- --all   # Chromium, Firefox, WebKit
//
// First visit -> placement solved at par -> a 15-exercise session (warm-ups and
// practice; one give-up, one retry) -> summary. Checks: focus changes, no exercise
// repeats in the session, result-strip values match the exercise, localStorage
// survives a reload, and export -> reset -> import restores the same state. Every
// result strip names the snippet's source ("from exercism/python \u00b7 MIT") from the
// exercise's `source`, and a cursor give-up marks the target in the editor.
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
    return c && { id: c.ex.id, skill: c.skill, role: c.role, phase: c.phase, retry: c.retry, par: c.ex.par, kind: c.ex.kind, source: c.ex.source ?? null };
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

/** The strip's source line, as main.ts derives it from exercise.source. */
const sourceText = (src) => (src?.repo === "author" ? "written for vim-trainer" : src?.repo ? `from ${src.repo.replace(/^(?:https?:\/\/)?(?:www\.)?github\.com\//, "").replace(/\.git$/, "")}${src.license ? ` \u00b7 ${src.license}` : ""}` : "");
let sourceMismatches = [];
async function checkSource(page, ex) {
  const got = (await text(page, "#result #src").catch(() => "<missing>")).trim();
  if (got !== sourceText(ex.source)) sourceMismatches.push(`${ex.id}: ${JSON.stringify(got)} vs ${JSON.stringify(sourceText(ex.source))}`);
}

const { typeKeys } = await import("./keys.mjs");

// How long to wait for the result strip after typing a par. CI runners are slow: 3 s
// flaked on an 11-key edit (run 38317885419), so this is generous on purpose.
const RESULT_TIMEOUT = 15000;

async function solveAtPar(page, engine, ex, label) {
  await typeKeys(page, ex.par.keys);
  const done = await page.waitForSelector("#result", { timeout: RESULT_TIMEOUT }).then(() => true, () => false);
  if (!done) {
    check(engine, `${label}: par ${ex.par.keys} solves ${ex.id} in the browser`, false, "no result after typing the par");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await page.waitForSelector("#result", { timeout: RESULT_TIMEOUT });
    return false;
  }
  const strip = await text(page, "#result");
  const you = await text(page, "#result .you");
  const par = await text(page, "#result .par");
  await checkSource(page, ex);
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
  sourceMismatches = [];

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
    const statRows = await page.locator(".sv-cell").count();
    const withContent = Object.values(JSON.parse(readFileSync(new URL("../../build/index.json", import.meta.url), "utf8")).langs.python.skills)
      .filter((s) => s.ids.length > 0).length;
    check(engine, `stats grid shows the ${withContent} skills that have python exercises`, statRows === withContent, String(statRows));

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
        await page.waitForSelector("#result", { timeout: RESULT_TIMEOUT });
        const strip = await text(page, "#result");
        const shows = ex.kind === "cursor" ? strip.includes("target: line") : (await page.locator("#result pre.diff").count()) === 1;
        check(engine, `${label}: Esc Esc gives up and shows the ${ex.kind === "cursor" ? "target" : "expected diff"}`, strip.includes("gave up") && shows, strip);
        if (ex.kind === "cursor") check(engine, `${label}: cursor give-up marks the target in the editor`, (await page.locator(".cm-target-reveal").count()) === 1);
        await checkSource(page, ex);
      } else if (i === 6) {
        // Over par first (a no-op detour), then r and solve at par.
        await page.keyboard.type("jk");
        await typeKeys(page, ex.par.keys);
        const passed = await page.waitForSelector("#result", { timeout: RESULT_TIMEOUT }).then(() => true, () => false);
        if (!passed) {
          await page.keyboard.press("Escape");
          await page.keyboard.press("Escape");
          await page.waitForSelector("#result", { timeout: RESULT_TIMEOUT });
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

    check(engine, "every result strip shows the exercise's source line", sourceMismatches.length === 0, sourceMismatches.slice(0, 3).join(" | "));
    check(engine, "real content carries a source (strip is not blank)", seen.some((e) => sourceText(e.source).startsWith("from exercism/python")), JSON.stringify(seen[0]?.source));
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
    check(engine, "reload restores the model log and sessions", afterReload.model.log.length === log.length && afterReload.sessions.length === 1 && afterReload.placementDone.python === true,
      `${afterReload.model.log.length} vs ${log.length}`);

    // Export -> reset -> import.
    await page.locator("#nav-settings").click();
    const [download] = await Promise.all([page.waitForEvent("download"), page.locator("#btn-export").click()]);
    const file = await download.path();
    const exported = JSON.parse(readFileSync(file, "utf8"));
    check(engine, "export writes the full state", exported.model.log.length === log.length && exported.placementDone.python === true);
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

    // Migration: a save from before per-language placement has placementDone: true; a
    // reload turns it into {python: true} (the saved language) and practice resumes.
    await page.evaluate(() => {
      const d = JSON.parse(localStorage.getItem("vim-trainer.v1"));
      d.placementDone = true;
      localStorage.setItem("vim-trainer.v1", JSON.stringify(d));
    });
    await page.reload();
    await page.waitForSelector("#practice:not([hidden])", { timeout: 8000 });
    const migrated = await page.evaluate(() => window.vimTrainer.saved().placementDone);
    check(engine, "old placementDone: true migrates to {python: true}", JSON.stringify(migrated) === JSON.stringify({ python: true }), JSON.stringify(migrated));

    // Switch to C++ mid-exercise: the open Python exercise is dropped unrecorded, the next
    // one is C++, and its attempt lands in the per-language model state next to Python's.
    const pyBefore = await page.evaluate(() => JSON.stringify(window.vimTrainer.saved().model.skills));
    const logBefore = await page.evaluate(() => window.vimTrainer.saved().model.log.length);
    await page.locator("#nav-settings").click();
    await page.selectOption('select[name="lang"]', "cpp");
    check(engine, "switching to C++ says it has no placement yet", (await text(page, "#settings-msg")).includes("placement"), await text(page, "#settings-msg"));
    await page.keyboard.press("Escape");
    // C++ has no placement yet: Esc opens its intro; x skips it and lands on stats.
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("where you are"), null, { timeout: 5000 });
    const intro = await text(page, "#page");
    check(engine, "the C++ placement intro appears on the first switch", intro.includes("C++") && intro.includes("new language") && intro.includes("mastered in another language"), intro);
    await page.keyboard.press("x");
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("We'll start with"), null, { timeout: 5000 });
    const done = await page.evaluate(() => window.vimTrainer.saved().placementDone);
    check(engine, "x skips the C++ placement: placementDone is {python: true, cpp: true}",
      JSON.stringify(done, Object.keys(done).sort()) === JSON.stringify({ cpp: true, python: true }), JSON.stringify(done));
    await page.keyboard.press("Enter");
    const cppEx = await nextMounted(page, "");
    check(engine, "after switching to C++ the next exercise is C++", cppEx.id.startsWith("cpp/"), cppEx.id);
    check(engine, "the C++ editor has syntax highlighting", (await page.locator(".cm-content span[class]").count()) > 0);
    await solveAtPar(page, engine, cppEx, "cpp 1");
    const afterCpp = await page.evaluate(() => window.vimTrainer.saved().model);
    const lastRec = afterCpp.log[afterCpp.log.length - 1];
    check(engine, "the C++ attempt is logged with lang cpp (the dropped Python one is not)",
      afterCpp.log.length === logBefore + 1 && lastRec.lang === "cpp" && lastRec.ex === cppEx.id, JSON.stringify(lastRec));
    const pyKept = Object.entries(JSON.parse(pyBefore)).every(([id, langs]) => !langs.python || JSON.stringify(afterCpp.skills[id]?.python) === JSON.stringify(langs.python) || id === cppEx.skill);
    check(engine, "Python model state is untouched by the C++ attempt", pyKept && !!afterCpp.skills[cppEx.skill]?.cpp);
    await page.keyboard.press("s");
    await page.waitForSelector(".sv-cell", { timeout: 5000 });
    const cppSkills = Object.values(JSON.parse(readFileSync(new URL("../../build/index.json", import.meta.url), "utf8")).langs.cpp.skills)
      .filter((s) => s.ids.length > 0).length;
    check(engine, `C++ stats grid shows the ${cppSkills} C++ skills`, (await page.locator(".sv-cell").count()) === cppSkills && (await text(page, "#page h1")).includes("C++"));
    await page.keyboard.press("f");
    const forcedEx = await nextMounted(page, `${cppEx.id}|false|true`);
    check(engine, "f on the stats grid drills the selected skill next", forcedEx.id.startsWith("cpp/"), forcedEx.id);
    await page.locator("#nav-settings").click();
    await page.selectOption('select[name="lang"]', "python");
    await page.keyboard.press("Escape");
    const backPy = await nextMounted(page, "");
    check(engine, "switching back to Python serves Python again", backPy.id.startsWith("py/"), backPy.id);

    // Second-language placement with enter: forget the C++ skip, switch to C++ again and
    // run its placement. The queue skips skills mastered (or in review) in Python; one
    // exercise at par, then q ends it and marks C++ placed.
    await page.evaluate(() => delete window.vimTrainer.saved().placementDone.cpp);
    await page.locator("#nav-settings").click();
    await page.selectOption('select[name="lang"]', "cpp");
    await page.keyboard.press("Escape");
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("where you are"), null, { timeout: 5000 });
    await page.keyboard.press("Enter");
    const cppPlace = await nextMounted(page, "");
    const { queued, masteredPy } = await page.evaluate(() => ({
      queued: window.vimTrainer.placementSkills(),
      masteredPy: Object.entries(window.vimTrainer.saved().model.skills)
        .filter(([, l]) => l.python && ["mastered", "review"].includes(l.python.status)).map(([id]) => id),
    }));
    check(engine, "the C++ placement queue skips skills mastered in Python",
      cppPlace.role === "placement" && cppPlace.id.startsWith("cpp/") && queued.length > 0 && masteredPy.length > 0 && !queued.some((s) => masteredPy.includes(s)),
      `queued ${queued.join(",")} | mastered ${masteredPy.join(",")}`);
    await solveAtPar(page, engine, cppPlace, "cpp placement 1");
    await page.keyboard.press("q");
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("We'll start with"), null, { timeout: 5000 });
    const afterPlace = await page.evaluate(() => window.vimTrainer.saved());
    const placeRec = afterPlace.model.log[afterPlace.model.log.length - 1];
    check(engine, "q ends the C++ placement: placementDone is {python: true, cpp: true} and the record is logged as cpp placement",
      JSON.stringify(afterPlace.placementDone, ["cpp", "python"]) === JSON.stringify({ cpp: true, python: true }) && Object.keys(afterPlace.placementDone).length === 2 &&
        placeRec.placement === true && placeRec.lang === "cpp" && placeRec.ex === cppPlace.id,
      `${JSON.stringify(afterPlace.placementDone)} ${JSON.stringify(placeRec)}`);
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
