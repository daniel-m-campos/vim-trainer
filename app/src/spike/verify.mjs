// Headless verification of the key-logger spike.
//
//   npm run spike:test              # chromium only
//   npm run spike:test -- --all     # chromium, firefox, webkit
//
// Browsers live in node_modules (PLAYWRIGHT_BROWSERS_PATH=0); install with
//   PLAYWRIGHT_BROWSERS_PATH=0 npx playwright install chromium firefox webkit
process.env.PLAYWRIGHT_BROWSERS_PATH ??= "0";

const { createServer } = await import("vite");
const { chromium, firefox, webkit } = await import("playwright");
const { fileURLToPath } = await import("node:url");

const root = fileURLToPath(new URL("../..", import.meta.url));
const server = await createServer({ root, logLevel: "error", server: { port: 0 } });
await server.listen();
const url = `${server.resolvedUrls.local[0]}spike-keylogger.html`;

const engines = process.argv.includes("--all") ? { chromium, firefox, webkit } : { chromium };
let failures = 0;

function check(engine, name, ok, detail) {
  if (!ok) failures++;
  console.log(`${ok ? "PASS" : "FAIL"}  [${engine}] ${name}${detail ? `\n        ${detail}` : ""}`);
}

const snapshot = (page) =>
  page.evaluate(() => {
    const { recorder, view } = window.spike;
    return {
      log: recorder.log.map((e) => ({ ...e })),
      doc: view.state.doc.toString(),
      focused: view.hasFocus,
      mode: recorder.mode(),
    };
  });

const keysOf = (log) => log.filter((e) => e.type === "key").map((e) => e.key);
const doneOf = (log) => log.filter((e) => e.type === "command-done");

for (const [engine, type] of Object.entries(engines)) {
  const browser = await type.launch();
  const page = await browser.newPage();
  const fresh = async () => {
    await page.goto(url);
    await page.waitForFunction(() => window.spike);
  };

  // 1. ci"retrying<Esc> from column 0 of the logger.warn line.
  await fresh();
  await page.keyboard.type('ci"');
  let s = await snapshot(page);
  check(engine, 'after ci" : no command-done yet, mode insert', doneOf(s.log).length === 0 && s.mode === "insert",
    `done=${doneOf(s.log).length} mode=${s.mode}`);
  await page.keyboard.type("retrying");
  s = await snapshot(page);
  check(engine, "after typing text: still no command-done", doneOf(s.log).length === 0, `done=${doneOf(s.log).length}`);
  await page.keyboard.press("Escape");
  s = await snapshot(page);
  const line6 = s.doc.split("\n")[5];
  check(engine, "buffer line 6 is logger.warn(\"retrying\")", line6 === '            logger.warn("retrying")', JSON.stringify(line6));
  const keys = keysOf(s.log);
  check(engine, "key log is c i \" r e t r y i n g <Esc>", keys.join(" ") === 'c i " r e t r y i n g <Esc>', keys.join(" "));
  const done = doneOf(s.log);
  check(engine, "exactly one command-done, on the <Esc> (key #11)", done.length === 1 && done[0].keyIndex === 11,
    JSON.stringify(done.map((d) => ({ k: d.keyIndex, src: d.source, cur: d.cursor }))));
  check(engine, "cursor after <Esc> matches nvim (5:32)", done[0]?.cursor.line === 5 && done[0]?.cursor.ch === 32,
    JSON.stringify(done[0]?.cursor));
  check(engine, "editor still focused after <Esc>", s.focused && !s.log.some((e) => e.type === "focus-lost"));
  const rawDone = s.log.filter((e) => e.type === "raw-signal" && e.name === "vim-command-done").length;
  const rawKeypress = s.log.filter((e) => e.type === "raw-signal" && e.name === "vim-keypress").map((e) => e.detail);
  console.log(`        info: raw vim-command-done fired ${rawDone}x for 12 keys; vim-keypress saw [${rawKeypress.join(" ")}]`);
  const ts = s.log.filter((e) => e.type === "key").map((e) => e.t);
  check(engine, "key timestamps are monotonic performance.now()", ts.every((t, i) => i === 0 || t >= ts[i - 1]));

  // 2. Mode coverage.
  await fresh();
  for (const k of ["v", "Escape", "Shift+V", "Escape", "Control+v", "Escape", "Shift+R", "x", "Escape", "i", "Escape", "a", "Escape"])
    await page.keyboard.press(k);
  s = await snapshot(page);
  const modes = s.log.filter((e) => e.type === "mode").map((e) => e.to);
  const expectModes = ["visual", "normal", "visual-line", "normal", "visual-block", "normal", "replace", "normal", "insert", "normal", "insert", "normal"];
  check(engine, "mode sequence v V <C-v> R i a", modes.join(",") === expectModes.join(","), modes.join(","));
  const sig = s.log.filter((e) => e.type === "mode-signal").map((e) => e.mode + (e.subMode ? "/" + e.subMode : ""));
  console.log(`        info: raw vim-mode-change: ${sig.join(", ")}`);
  console.log(`        info: keys: ${keysOf(s.log).join(" ")}`);

  // 3. Partial commands do not fire; dw fires once at w; 3j once; u once.
  await fresh();
  await page.keyboard.press("d");
  s = await snapshot(page);
  const afterD = doneOf(s.log).length;
  await page.keyboard.press("w");
  await page.keyboard.type("3j");
  await page.keyboard.press("u");
  await page.keyboard.press(".");
  await page.keyboard.type("qaxq@a");
  s = await snapshot(page);
  // keys: d0 w1 3 2 j3 u4 .5 q6 a7 x8 q9 @10 a11
  check(engine, "d -> none; dw, 3j, u, ., x (in qa), @a -> one each",
    afterD === 0 && doneOf(s.log).map((d) => d.keyIndex).join(",") === "1,3,4,5,8,11",
    `afterD=${afterD} done@${doneOf(s.log).map((d) => d.keyIndex + ":" + d.source).join(",")}`);

  // 4. Ex command line.
  await fresh();
  await page.keyboard.type(":s/logger/log/");
  s = await snapshot(page);
  const midEx = doneOf(s.log).length;
  await page.keyboard.press("Enter");
  s = await snapshot(page);
  const exDone = doneOf(s.log);
  check(engine, ":s/logger/log/<CR> -> keys logged in cmdline, one command-done on <CR>",
    midEx === 0 && exDone.length === 1 && s.doc.includes("log.warn(") &&
      keysOf(s.log).join("") === ":s/logger/log/<CR>" && s.focused,
    `mid=${midEx} done=${JSON.stringify(exDone.map((d) => [d.keyIndex, d.source]))} keys=${keysOf(s.log).join("")} focused=${s.focused}`);

  // 5. <Esc><Esc> in normal mode (the skip gesture): logged, focus kept, nothing done.
  await fresh();
  await page.keyboard.press("Escape");
  await page.keyboard.press("Escape");
  s = await snapshot(page);
  check(engine, "<Esc><Esc> in normal: 2 keys, no command-done, still focused",
    keysOf(s.log).join("") === "<Esc><Esc>" && doneOf(s.log).length === 0 && s.focused,
    `keys=${keysOf(s.log).join("")} done=${doneOf(s.log).length} focused=${s.focused}`);
  const prevented = await page.evaluate(() => {
    const el = window.spike.view.contentDOM;
    const ev = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    el.dispatchEvent(ev);
    return ev.defaultPrevented;
  });
  check(engine, "normal-mode <Esc> keydown is defaultPrevented", prevented);

  // 6. Tab never blurs; <C-[> works as <Esc> and is one token.
  await fresh();
  await page.keyboard.press("Tab");
  await page.keyboard.press("i");
  await page.keyboard.press("Tab");
  await page.keyboard.press("Control+[");
  s = await snapshot(page);
  check(engine, "<Tab> keeps focus (normal + insert), inserts \\t in insert; <C-[> leaves insert",
    s.focused && s.mode === "normal" && s.doc.split("\n")[5].startsWith("\t ") && keysOf(s.log).join(" ") === "<Tab> i <Tab> <C-[>",
    `focused=${s.focused} mode=${s.mode} line6=${JSON.stringify(s.doc.split("\n")[5])} keys=${keysOf(s.log).join(" ")}`);

  // 7. Clock pauses while hidden.
  await fresh();
  const clock = await page.evaluate(async () => {
    const { recorder } = window.spike;
    const setVis = (v) => {
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => v });
      Object.defineProperty(document, "hidden", { configurable: true, get: () => v === "hidden" });
      document.dispatchEvent(new Event("visibilitychange"));
    };
    recorder.reset();
    const t0 = performance.now();
    setVis("hidden");
    await new Promise((r) => setTimeout(r, 400));
    setVis("visible");
    const t1 = performance.now();
    const ev = new KeyboardEvent("keydown", { key: "l", bubbles: true, cancelable: true });
    window.spike.view.contentDOM.dispatchEvent(ev);
    const k = recorder.log.find((e) => e.type === "key");
    return { wall: t1 - t0, active: k.active, clockEvents: recorder.log.filter((e) => e.type === "clock").length };
  });
  check(engine, "clock excludes hidden time", clock.wall >= 400 && clock.active < 100 && clock.clockEvents === 2, JSON.stringify(clock));

  await browser.close();
}

await server.close();
console.log(failures ? `\n${failures} check(s) failed` : "\nall checks passed");
process.exit(failures ? 1 : 0);
