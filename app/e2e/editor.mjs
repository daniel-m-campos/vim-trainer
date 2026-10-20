// Editor-level regressions: key sequences typed into the practice editor (the
// emulator-check.html harness) and compared with Neovim. The cases are inputs only
// (e2e/cases/*.json): a buffer, a start cursor [line 1-based, col 0-based] and keys in Vim
// notation. Neovim is the oracle at test time: one `vimtrainer-content expect` run (from
// content/, ~3 s) gives its lines, cursor and mode for every case before the browser starts.
//
// Case fields besides name/lang/lines/cursor/keys:
//   oracle: "typed"   replay as typed keys (a failing motion aborts a macro or a :normal
//                     line; the default batch oracle runs under silent!, which does not)
//   skip: ["cursor"]  a field not compared, with `why` saying which divergence is open
//   xfailIn: [engine] an engine-specific, timing-dependent failure: reported, never counted
//   known: true       an open emulator bug: XFAIL; XPASS fails the run so the flag is removed
//   why               the reason for the case (or for its skip)
//
//   npm run e2e:editor            # Chromium
//   npm run e2e:editor -- --all   # Chromium, Firefox, WebKit
process.env.PLAYWRIGHT_BROWSERS_PATH ??= "0";

const { createServer } = await import("vite");
const { chromium, firefox, webkit } = await import("playwright");
const { fileURLToPath } = await import("node:url");
const { readFileSync } = await import("node:fs");
const { spawnSync } = await import("node:child_process");
const { typeKeys, tokenize } = await import("./keys.mjs");

const caseFile = (name) => JSON.parse(readFileSync(new URL(`./cases/${name}`, import.meta.url), "utf8"));
// macros, :normal, auto-indent, Insert <C-w>, :j (vimfixes-macros-indent.ts) come last.
const CASES = [...caseFile("editor.json"), ...caseFile("macros-indent.json")];
// Smoke: Playwright must accept the key name each of these tokens maps to (keys.mjs);
// a bad name would otherwise throw only when a real exercise first uses the token.
const SMOKE_KEYS = "<Nul><C-@><NL><F12><C-Space><C-Bslash><C-->";
const FIELDS = ["lines", "cursor", "mode"];

// Run `vimtrainer-content expect` once over all cases; returns Neovim's {lines, cursor, mode, errmsg} per case, in order. Called at startup.
function nvimResults(cases) {
  const input = cases.map((c, id) =>
    JSON.stringify({ id, lang: c.lang, lines: c.lines, cursor: c.cursor, keys: c.keys, oracle: c.oracle })).join("\n");
  const content = fileURLToPath(new URL("../../content", import.meta.url));
  const run = spawnSync("uv", ["run", "--quiet", "vimtrainer-content", "expect"],
    { cwd: content, input, encoding: "utf8", maxBuffer: 64 << 20 });
  if (run.error || run.status !== 0) {
    const why = run.error ? String(run.error) : run.stderr.trim().split("\n").at(-1);
    console.error(`FAIL  the Neovim oracle did not run (\`uv run vimtrainer-content expect\` in content/):\n        ${why}`);
    if (/nvim not found|ENOENT/.test(why)) console.error("        e2e:editor needs nvim and uv on PATH, as `make content` does: Neovim gives every case's expected result.");
    process.exit(1);
  }
  const byId = new Map(run.stdout.trim().split("\n").map((line) => JSON.parse(line)).map((r) => [r.id, r]));
  return cases.map((_, id) => byId.get(id));
}

// Mount case `c` in the emulator page, type its keys and read lines/cursor/mode; called per case by the loop below.
async function runCase(page, c) {
  // expect: {} never matches, so emu's "passed" never latches and nothing else reacts.
  const ex = {
    id: "e2e/editor", skill: "e2e", lang: c.lang ?? "python", kind: "edit", task: c.name,
    start: { lines: c.lines, cursor: c.cursor }, expect: {}, par: { keys: c.keys, count: 0 },
  };
  await page.evaluate((ex) => window.emu.mount(ex), ex);
  await page.waitForFunction(() => !!document.activeElement?.closest(".cm-editor"), null, { timeout: 3000 });
  await typeKeys(page, c.keys);
  await page.waitForTimeout(50);
  return page.evaluate(readState);
}

// Runs in the page: lines, cursor and mode as Vim sees them (same as difftest-worker.mjs readState); called by runCase.
function readState() {
  const { snap } = window.emu.status();
  const a = document.activeElement;
  const cmdline = a instanceof HTMLInputElement && !!document.getElementById("code")?.contains(a);
  const vim = document.querySelector("#code .cm-content")?.cmTile?.root?.view?.cm?.state?.vim;
  const s = vim?.inputState;
  const pending = !!s && (s.keyBuffer.length > 0 || !!s.operator || s.prefixRepeat.length > 0 ||
    s.motionRepeat.length > 0 || !!s.registerName);
  const h = vim?.visualMode && vim.sel?.head;
  const cursor = h ? [h.line + 1, Math.max(0, Math.min(h.ch, (snap.lines[h.line] ?? "").length))] : snap.cursor;
  return { lines: snap.lines, cursor, mode: cmdline ? "cmdline" : pending ? "pending" : snap.mode };
}

// Fields of `got` that differ from Neovim's `want`, minus the case's skip list; called per case by the loop below.
function differing(c, want, got) {
  return FIELDS.filter((f) => !c.skip?.includes(f) && JSON.stringify(got[f]) !== JSON.stringify(want[f]));
}

const t0 = Date.now();
const NVIM = nvimResults(CASES);
console.log(`Neovim oracle: ${CASES.length} cases in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
let failures = 0;
CASES.forEach((c, i) => {
  // An oracle that timed out or errored has no answer to compare with: fix the case.
  if (["timeout", "error"].includes(NVIM[i]?.mode ?? "error")) {
    failures++;
    console.log(`FAIL  [nvim] ${c.name}\n        oracle: ${NVIM[i]?.errmsg || "no result"}`);
  }
});

const root = fileURLToPath(new URL("..", import.meta.url));
const server = await createServer({ root, logLevel: "error", server: { port: 0 } });
await server.listen();
const url = server.resolvedUrls.local[0];
const engines = process.argv.includes("--all") ? { chromium, firefox, webkit } : { chromium };

for (const [engine, type] of Object.entries(engines)) {
  const browser = await type.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(`${url}emulator-check.html`);
  await page.waitForFunction(() => !!window.emu);
  for (const [i, c] of CASES.entries()) {
    const got = await runCase(page, c);
    const bad = differing(c, NVIM[i], got);
    const ok = bad.length === 0;
    if (c.xfailIn?.includes(engine)) {
      // A known engine-specific, timing-dependent failure: reported, never counted.
      console.log(`${ok ? "XPASS" : "XFAIL"}  [${engine}] ${c.name} (xfailIn ${engine}: does not count)`);
      continue;
    }
    if (c.known) {
      if (ok) failures++;
      console.log(`${ok ? "XPASS (now passes: drop `known`)" : "XFAIL"}  [${engine}] ${c.name}`);
      continue;
    }
    if (!ok) failures++;
    const show = (s) => `${JSON.stringify(s.lines)} cursor ${JSON.stringify(s.cursor)} ${s.mode}`;
    console.log(`${ok ? "PASS" : "FAIL"}  [${engine}] ${c.name}${ok ? "" :
      `\n        differs in ${bad.join(", ")}\n        nvim ${show(NVIM[i])}\n        web  ${show(got)}`}`);
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
