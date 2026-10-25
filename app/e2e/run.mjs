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
// Round 4: no skill ids or header context before the language is chosen, a reload
// mid-placement resumes at the same exercise with its records, the "not quite ... u to
// undo" nudge, the "placement complete" line, hash routing (Esc / Back from stats,
// direct load of #stats), the version and "Sources & attribution" in settings, the
// error ring buffer (export and the "!" issue carry it), and the placement key cap
// (11 presses of l on a par-3 cursor exercise is not a placement pass).
//
// /build/ is forced to 404 so the app uses the bundled sample (deterministic, and
// it exercises the fallback path). Browsers live in node_modules
// (PLAYWRIGHT_BROWSERS_PATH=0); install with
//   PLAYWRIGHT_BROWSERS_PATH=0 npx playwright install chromium firefox webkit
process.env.PLAYWRIGHT_BROWSERS_PATH ??= "0";

const { createServer } = await import("vite");
const { chromium, firefox, webkit } = await import("playwright");
const { fileURLToPath } = await import("node:url");
const { readFileSync } = await import("node:fs");

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
// One wait budget for every UI transition: 5 s flaked once locally on the placement-gate
// page and once on WebKit in CI; a real hang still fails, just later.
const WAIT = 15000;
const editorFocused = (page) => page.waitForFunction(() => !!document.activeElement?.closest(".cm-editor"), null, { timeout: WAIT });
const waitTask = (page, s) => page.waitForFunction((s) => document.querySelector("#task")?.textContent?.includes(s), s, { timeout: WAIT });
const waitResult = (page) => page.waitForSelector("#result", { timeout: WAIT });

for (const [engine, type] of Object.entries(engines)) {
  const browser = await type.launch();
  const page = await browser.newPage();
  const warnings = [];
  const errors = [];
  // Expected 404s (the forced /build/ miss, favicon) are not errors.
  page.on("console", (m) => (m.type() === "warning" ? warnings.push(m.text()) : m.type() === "error" && !m.text().startsWith("Failed to load resource") && !m.text().includes("e2e-injected") ? errors.push(m.text()) : null));
  // The error-buffer check below throws on purpose; those two are not page errors.
  page.on("pageerror", (e) => !String(e).includes("e2e-injected") && errors.push(String(e)));
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
    await page.waitForSelector(".choice", { timeout: WAIT });
    check(engine, "first visit shows the language question", (await text(page, "#page")).includes("Which language"));
    check(engine, "falls back to build-sample with a console warning", warnings.some((w) => w.includes("build-sample")), warnings.join(" | "));
    check(engine, "header names no language or editor before the first choice", (await text(page, "#hdr-ctx")).trim() === "", await text(page, "#hdr-ctx"));

    await page.keyboard.press("Enter"); // Python
    check(engine, "header names the language once it is chosen", (await text(page, "#hdr-ctx")).includes("python"), await text(page, "#hdr-ctx"));
    await page.keyboard.press("Enter"); // Neovim
    check(engine, "first-visit screens show no skill ids (m.rel)", !(await text(page, "#page")).includes("m.rel"), await text(page, "#page"));
    await page.keyboard.press("Enter"); // relative numbers: yes
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("where you are"));
    check(engine, "placement intro lists 3 sample exercises", (await text(page, "#page")).includes("3 short exercises"));
    check(engine, "placement intro after setup says 'first visit 4 of 4' and the hash is #placement-intro",
      (await text(page, "#page")).includes("4 of 4") && new URL(page.url()).hash === "#placement-intro", page.url());
    const introNav = await page.evaluate(() => [...document.querySelectorAll("#hdr .nav a")].map((a) => `${a.hidden ? "hidden:" : ""}${a.textContent}`).join("|"));
    check(engine, "QA #24: the placement intro header shows no s / , keys (they do nothing there)", introNav === "stats|settings", introNav);
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

    // Placement 2: t.quote. A reload here resumes placement 2 of 3 with placement 1's record kept.
    await waitTask(page, "logger.warn");
    await page.reload();
    await waitTask(page, "logger.warn");
    await editorFocused(page);
    const resumed = await page.evaluate(() => ({ p: window.vimTrainer.placement(), prog: document.querySelector("#progress")?.textContent, hash: location.hash }));
    check(engine, "reload mid-placement resumes at placement 2 of 3 with the first record kept",
      resumed.p?.i === 1 && resumed.p.records.length === 1 && resumed.p.records[0].ex === "py/m.rel/0001" && resumed.prog.includes("placement 2 of 3") && resumed.hash === "#placement",
      JSON.stringify({ ...resumed, p: resumed.p && { i: resumed.p.i, n: resumed.p.records.length } }));
    // Solve with ci"retrying<Esc>.
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
    check(engine, "strip lists space / r / ? / q and no replay key",
      ["next", "retry", "hint", "end session"].every((s) => strip.includes(s)) && !strip.includes("replay"), strip);
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
    await page.keyboard.press("2");
    await page.keyboard.press("1");
    const picked = await page.evaluate(() => ({ focus: document.activeElement?.id, sel: document.querySelector("#flagpick .flag-opt.sel")?.dataset.r, note: document.querySelector("#flag-note")?.value }));
    check(engine, "QA #48: a second digit changes the reason; focus stays on the strip and the note stays empty",
      picked.focus === "foot" && picked.sel === "wrong-par" && picked.note === "", JSON.stringify(picked));
    await page.keyboard.press("Tab");
    check(engine, "tab moves focus to the note field", await page.evaluate(() => document.activeElement?.id === "flag-note"));
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
    // Digits before and between them must not become a count in the next exercise (QA #38).
    await page.keyboard.press("3");
    await page.keyboard.press(" ");
    await page.keyboard.press("2");
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
    const row0 = await page.evaluate(() => window.vimTrainer.current().editor.recorder.snapshot().cursor[0]);
    await page.keyboard.press("j");
    const row1 = await page.evaluate(() => window.vimTrainer.current().editor.recorder.snapshot().cursor[0]);
    check(engine, "QA #38: digits typed on the strip are not a count: j moves one line", row1 === row0 + 1, `${row0} -> ${row1}`);
    await page.keyboard.press("k");

    // 5dd deletes lines the target keeps: the footer nudges once; u undoes (nvim: back to the start, cursor 1:0).
    await page.keyboard.type("5dd");
    const nudge = await page.waitForFunction(() => document.querySelector("#nudge:not([hidden])")?.textContent, null, { timeout: 3000 })
      .then((h) => h.jsonValue(), () => "");
    check(engine, "an unrecoverable edit shows 'not quite: <reason> — u to undo'", /^not quite: .+ — u to undo$/.test(nudge), nudge);
    await page.keyboard.type("u");
    await page.waitForFunction(() => window.vimTrainer.current().editor.recorder.snapshot().lines.length === 8, null, { timeout: 3000 });

    // Reach the expected buffer with dd, then give up: the strip explains instead of an empty diff.
    await page.keyboard.type("jddjjddjdd");
    const exNote = await page.waitForFunction(() => document.querySelector("#midhint:not([hidden])")?.textContent?.includes(": command"), null, { timeout: 3000 })
      .then(() => true, () => false);
    check(engine, "ex kind: right buffer without : shows the mid-exercise note", exNote, await text(page, "#midhint").catch(() => ""));
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await waitResult(page);
    const exStrip = await text(page, "#result");
    check(engine, "ex give-up with a matching buffer says a : command was required (no empty diff)",
      exStrip.includes("gave up") && exStrip.includes("a : command was required") && (await page.locator("#result pre.diff").count()) === 0, exStrip);
    const exStatus = await text(page, "#result .row1 .fail");
    check(engine, "QA #40: the status line says why: 'needs an Ex (:) command'", exStatus.includes("gave up: needs an Ex (:) command"), exStatus);
    await page.keyboard.press("r");
    await waitTask(page, "print");
    await editorFocused(page);
    // A :s that matches reports "Found N matches"; it is not an error, so not red (QA #21).
    await page.keyboard.type(":%s/print/print/g");
    await page.keyboard.press("Enter");
    const found = await page.waitForFunction(() => {
      const m = document.querySelector(".cm-vim-message");
      return m?.textContent?.startsWith("Found ") && { text: m.textContent, color: getComputedStyle(m).color };
    }, null, { timeout: 3000 }).then((h) => h.jsonValue(), () => null);
    check(engine, "QA #21: ':%s' that matches shows 'Found N matches' in a neutral colour, not red", !!found && found.color !== "rgb(255, 0, 0)", JSON.stringify(found));
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
    const named = await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("We'll start with"), null, { timeout: WAIT })
      .then(() => true, () => false);
    check(engine, "stats after placement names the starting skill", named, await text(page, "#page"));
    const moment = await text(page, "#placement-moment").catch(() => "");
    check(engine, "a 'placement complete: N skills placed, M mastered' line opens stats", /^placement complete: 3 skills placed, \d+ mastered\.$/.test(moment.trim()), moment);
    // Only skills with exercises are listed: the sample has 3 skills in 3 tiers.
    check(engine, "stats grid grouped by tier", (await page.locator(".sv-tier").count()) === 3, String(await page.locator(".sv-tier").count()));
    check(engine, "stats grid outlines the focus skill", (await page.locator(".sv-cell.sv-focus").count()) === 1);
    const statsNav = await page.evaluate(() => [...document.querySelectorAll("#hdr .nav a")].map((a) => `${a.hidden ? "hidden:" : ""}${a.textContent}`).join("|"));
    check(engine, "QA #24: on stats the header hides the stats link and keeps ', settings'", statsNav === "hidden:stats|, settings", statsNav);
    const pills = await page.locator(".sv-pill").allInnerTexts();
    check(engine, "no tile reads 'locked' with zero attempts (shown as 'untested')", !pills.includes("locked"), pills.join(","));
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
    check(engine, "state saved to localStorage with placement done", JSON.stringify(savedState?.placementDone) === JSON.stringify({ python: true }) && savedState.model.log.length >= 3,
      JSON.stringify(savedState?.model?.log?.length));
    // The flag set on placement 2 reached the log when placement ended, with seq and beatPar.
    const quoteRec = savedState?.model?.log?.find((r) => r.ex === "py/t.quote/0001" && !r.retry);
    check(engine, "flagged placement record is logged with flag {reason, note}, seq and beatPar",
      quoteRec?.flag?.reason === "wrong-par" && quoteRec.flag.note === "par looks long" && quoteRec.seq === 'ci"retrying<Esc>' && quoteRec.beatPar === false,
      JSON.stringify(quoteRec));

    const announcedKeys = await text(page, "#page .lead code");
    await page.keyboard.press("Enter");
    await page.waitForSelector("#practice:not([hidden])", { timeout: WAIT });
    await editorFocused(page);
    const started = await page.evaluate(() => ({ hash: location.hash, phase: window.vimTrainer.current()?.phase, role: window.vimTrainer.current()?.role }));
    check(engine, "enter starts practice", started.hash === "#practice" && started.phase === "solving" && started.role !== "placement", JSON.stringify(started));
    const hdr = await text(page, "#hdr-focus");
    check(engine, "the first exercise is the announced skill and the header names it as the focus",
      hdr.startsWith("focus:") && hdr.includes(announcedKeys), `${announcedKeys} | ${hdr}`);
    const practiceNav = await page.evaluate(() => [...document.querySelectorAll("#hdr .nav a")].map((a) => `${a.hidden ? "hidden:" : ""}${a.textContent}`).join("|"));
    check(engine, "QA #24: practice shows 's stats' and ', settings'", practiceNav === "s stats|, settings", practiceNav);
    const lig = await page.evaluate(() => getComputedStyle(document.querySelector(".code .cm-content")).fontVariantLigatures);
    check(engine, "editor has code ligatures off", lig === "none", lig);
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
    // Browser Back from stats returns to the exercise; the app is not left.
    await page.locator("#nav-stats").click();
    await page.waitForFunction(() => location.hash === "#stats" && document.querySelector("#page")?.textContent?.includes("Stats"));
    await page.goBack();
    await editorFocused(page);
    check(engine, "Back from stats returns to the open exercise (#practice, same page)",
      page.url().startsWith(url) && new URL(page.url()).hash === "#practice" && (await page.evaluate(() => window.vimTrainer.current()?.phase)) === "solving", page.url());
    // F1 shows a hint without touching Vim.
    await page.keyboard.press("F1");
    check(engine, "F1 reveals a mid-exercise hint", await page.locator("#midhint:not([hidden])").count() === 1);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await waitResult(page);
    await page.keyboard.press("q");
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("Session done"), null, { timeout: WAIT });
    check(engine, "q ends the session with a summary", (await text(page, "#page")).includes("1 exercises"), await text(page, "#page"));
    const counts = await text(page, "#summary-counts").catch(() => "");
    check(engine, "QA #35: the summary splits solved and skipped ('0 solved, 1 skipped', no beat-par count)", counts.trim() === "0 solved, 1 skipped", counts);

    await page.keyboard.press(",");
    check(engine, ", opens settings", (await text(page, "#page")).includes("Settings"));
    const settingsNav = await page.evaluate(() => [...document.querySelectorAll("#hdr .nav a")].map((a) => `${a.hidden ? "hidden:" : ""}${a.textContent}`).join("|"));
    check(engine, "QA #24: on settings the header hides the settings link and shows stats without its key", settingsNav === "stats|hidden:settings", settingsNav);
    const attr = page.locator("#attribution-link");
    const href = await attr.getAttribute("href").catch(() => null);
    check(engine, "settings has a 'Sources & attribution' link to ATTRIBUTION.md",
      !!href && href.endsWith("ATTRIBUTION.md") && (await attr.innerText()).includes("Sources & attribution"), String(href));
    const pkgVersion = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf8")).version;
    const shown = await text(page, "#app-version").catch(() => "");
    check(engine, "settings footer shows the package.json version (+ git sha)", new RegExp(`^vim-trainer ${pkgVersion.replace(/\./g, "\\.")}(\\+[0-9a-f]{4,})?$`).test(shown.trim()), shown);
    const data = await text(page, "#your-data").catch(() => "");
    check(engine, "settings 'Your data' says storage is local and names the version",
      data.includes("only in this browser") && data.includes("sent anywhere") && data.includes(pkgVersion), data);
    const issues = await page.locator("#issues-link").getAttribute("href").catch(() => null);
    check(engine, "settings 'share your log' links the issues page", issues === "https://github.com/daniel-m-campos/vim-trainer/issues", String(issues));
    const onPage = (s) => page.waitForFunction((s) => document.querySelector("#page")?.textContent?.includes(s), s, { timeout: 3000 }).then(() => true, () => false);
    await page.keyboard.press("Escape");
    check(engine, "Esc returns to the summary", await onPage("Session done"), await text(page, "#page"));
    // Stats opened from settings: Esc goes back to settings, then to the summary.
    // A short window scrolled to the bottom of settings: stats opens at its top (QA #43).
    await page.keyboard.press(",");
    const viewport = page.viewportSize();
    await page.setViewportSize({ width: 900, height: 650 }); // settings scrolls; the stats selection fits without scrolling
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    const scrolledDown = await page.evaluate(() => window.scrollY);
    await page.evaluate(() => document.querySelector("#nav-stats").click()); // a DOM click: Playwright's would scroll to the link
    await page.waitForFunction(() => document.querySelector("#page")?.textContent?.includes("Stats"));
    const statsScroll = await page.evaluate(() => window.scrollY);
    check(engine, "QA #43: stats opens at the top, not at settings' scroll position", scrolledDown > 0 && statsScroll === 0, `${scrolledDown} -> ${statsScroll}`);
    await page.setViewportSize(viewport);
    await page.keyboard.press("Escape");
    check(engine, "Esc from stats opened in settings returns to settings", await onPage("Settings"), await text(page, "#page"));
    await page.keyboard.press("Escape");
    check(engine, "then Esc returns to the summary", await onPage("Session done"), await text(page, "#page"));

    // Reload keeps state and goes straight to practice.
    await page.reload();
    const practiceShown = await page.waitForSelector("#practice:not([hidden])", { timeout: WAIT }).then(() => true, () => false);
    const afterReload = await page.evaluate(() => ({ hash: location.hash, choices: document.querySelectorAll(".choice").length, editor: !!document.querySelector("#code .cm-editor") }));
    check(engine, "reload resumes practice (no first-visit flow)", practiceShown && afterReload.hash === "#practice" && afterReload.choices === 0 && afterReload.editor,
      JSON.stringify(afterReload));

    // A save bricked by an old unchecked import (no model.skills, unknown language) still loads.
    await page.evaluate(() => {
      const s = JSON.parse(localStorage.getItem("vim-trainer.v1"));
      delete s.model.skills;
      s.settings.lang = "klingon";
      localStorage.setItem("vim-trainer.v1", JSON.stringify(s));
    });
    await page.reload();
    await page.waitForSelector("#practice:not([hidden])", { timeout: WAIT });
    check(engine, "a save without model.skills or with an unknown language recovers on reload",
      !(await text(page, "header")).includes("klingon") && (await page.locator(".code .cm-content").count()) === 1, await text(page, "header"));

    // Error ring buffer: an uncaught error and a rejected promise land in saved.errors, the
    // footer says so, and the "!" issue body and the export carry them.
    await editorFocused(page);
    await page.evaluate(() => {
      setTimeout(() => { throw new Error("e2e-injected boom"); }, 0);
      setTimeout(() => void Promise.reject(new Error("e2e-injected rejection")), 0);
    });
    await page.waitForFunction(() => window.vimTrainer.saved().errors.length === 2, null, { timeout: 3000 });
    const errs = await page.evaluate(() => window.vimTrainer.saved().errors);
    check(engine, "uncaught error and rejection are kept with t, version, route, message, stack",
      errs[0].message.includes("e2e-injected boom") && errs[1].message.includes("e2e-injected rejection") && errs[0].route === "practice" &&
        errs.every((e) => e.t > 0 && e.version && typeof e.stack === "string" && e.stack.split("\n").length <= 5), JSON.stringify(errs));
    check(engine, "the footer says 'something broke — export your data and flag it with !'",
      (await text(page, "#foot")).includes("something broke — export your data and flag it with !"), await text(page, "#foot"));
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await waitResult(page);
    await page.evaluate(() => { window.__opened = []; window.open = (u) => (window.__opened.push(String(u)), {}); });
    await page.keyboard.type("!");
    await page.waitForSelector("#flagpick", { timeout: 2000 });
    await page.keyboard.press("4");
    await page.keyboard.press("Enter");
    const flagged = await page.evaluate(() => window.__opened[0] ?? "");
    const errBody = flagged ? new URL(flagged).searchParams.get("body") ?? "" : "";
    check(engine, "the '!' issue body lists the recent errors", errBody.includes("recent errors") && errBody.includes("e2e-injected boom"), errBody.slice(-400));
    await page.locator("#nav-settings").click();
    const [dl] = await Promise.all([page.waitForEvent("download"), page.locator("#btn-export").click()]);
    const exportMsg = await text(page, "#settings-msg");
    check(engine, "QA #42: export says 'saved vim-trainer-<date>.json'", /^saved vim-trainer-\d{4}-\d\d-\d\d\.json$/.test(exportMsg.trim()), exportMsg);
    const exportedErrs = JSON.parse(readFileSync(await dl.path(), "utf8")).errors ?? [];
    check(engine, "export carries the error buffer", exportedErrs.some((e) => e.message.includes("e2e-injected boom")), JSON.stringify(exportedErrs));

    // Direct load of #stats shows stats; Esc (no earlier app entry) goes to practice.
    await page.goto("about:blank");
    await page.goto(`${url}#stats`);
    const direct = await page.waitForFunction(() => document.querySelector("#page:not([hidden]) h1")?.textContent?.startsWith("Stats"), null, { timeout: WAIT }).then(() => true, () => false);
    check(engine, "direct load of #stats shows the stats page", direct, await text(page, "#page").catch(() => ""));
    await page.keyboard.press("Escape");
    await editorFocused(page);
    check(engine, "Esc from a directly loaded #stats goes to practice", new URL(page.url()).hash === "#practice", page.url());
  } catch (err) {
    failures++;
    console.log(`FAIL  [${engine}] ${err.message}`);
    await page.screenshot({ path: `e2e-failure-${engine}.png` }).catch(() => {});
  }
  check(engine, "no page errors", errors.length === 0, errors.join(" | "));

  // Placement key cap (grading.placementPass): the sample m.rel exercise re-targeted to
  // [3, 15], which nvim reaches with 3fa (par 3) and with eleven l. Eleven keys pass the
  // check but exceed max(2 * 3, 3 + 6) = 9, so the placement record is not ok.
  const gate = await browser.newPage();
  const gateErrors = [];
  gate.on("pageerror", (e) => gateErrors.push(String(e)));
  try {
    await gate.route("**/build/**", (r) => r.fulfill({ status: 404, body: "not found" }));
    await gate.route("**/build-sample/exercises/python/m.rel/*.json", async (r) => {
      const res = await r.fetch();
      const json = await res.json();
      Object.assign(json, { expect: { cursor: [3, 15] }, target: { from: [3, 15], to: [3, 16] }, par: { keys: "3fa", count: 3 }, alternates: [], hints: [] });
      await r.fulfill({ response: res, json });
    });
    await gate.goto(url);
    await gate.waitForSelector(".choice", { timeout: WAIT });
    for (let i = 0; i < 4; i++) await gate.keyboard.press("Enter"); // setup, then start placement
    await waitTask(gate, "assigns");
    await editorFocused(gate);
    for (let i = 0; i < 11; i++) await gate.keyboard.press("l");
    await waitResult(gate);
    const rec = await gate.evaluate(() => window.vimTrainer.placement()?.records[0]);
    const strip = await text(gate, "#result");
    check(engine, "11 presses of l on a par-3 placement exercise: strip says correct, the record is not a pass",
      strip.includes("correct") && strip.includes("not yet known") && rec?.ok === false && rec.keys === 11, `${strip} | ${JSON.stringify(rec)}`);
  } catch (err) {
    failures++;
    console.log(`FAIL  [${engine}] placement gate: ${err.message}`);
  }
  check(engine, "no page errors (placement gate page)", gateErrors.length === 0, gateErrors.join(" | "));
  await browser.close();
}

await server.close();
console.log(failures ? `\n${failures} check(s) failed` : "\nall checks passed");
process.exit(failures ? 1 : 0);
