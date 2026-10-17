// Browser side of the differential fuzzer (docs/design/differential-testing.md):
// a long-lived worker that replays key sequences in the practice editor
// (emulator-check.html, as e2e/emulator.mjs does) and reports the editor state.
// content/src/vimtrainer_content/difftest/web.py spawns it and talks JSON lines:
//
//   stdin   {"id": 7, "lang": "python", "lines": [...], "cursor": [1, 0], "keys": "dw"}
//   stdout  {"id": 7, "lines": [...], "cursor": [1, 0], "mode": "normal", "ms": 12}
//        or {"id": 7, "error": "timeout after 10000 ms" | "pageerror: ..."}
//
// Replies can come out of order (N pages work in parallel). "ready" is printed once
// the pages are loaded. Mode is the recorder's (normal, insert, replace, visual,
// visual-line, visual-block), "pending" after an unfinished operator/count/register, or
// "cmdline" when the ":" / "/" input has focus.
//
//   node e2e/difftest-worker.mjs [--pages N] [--job-timeout-ms MS]   # serve until stdin closes
//   node e2e/difftest-worker.mjs --self-test     # 3 built-in cases, exit 0 or 1
process.env.PLAYWRIGHT_BROWSERS_PATH ??= "0";

const { createServer } = await import("vite");
const { chromium } = await import("playwright");
const { fileURLToPath } = await import("node:url");
const { createInterface } = await import("node:readline");
const { typeKeys } = await import("./keys.mjs");

const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : null;
};
const PAGES = Number(arg("--pages") ?? 4);
const SELF_TEST = process.argv.includes("--self-test");
const JOB_TIMEOUT_MS = Number(arg("--job-timeout-ms") ?? 10_000); // per-job watchdog

const root = fileURLToPath(new URL("..", import.meta.url));
const server = await createServer({ root, logLevel: "error", server: { port: 0 } });
await server.listen();
// Vite closes itself and exits when stdin ends (outside CI); here stdin ending means
// "no more requests", and the jobs in flight must still finish and reply.
process.stdin.removeAllListeners("end");
const url = server.resolvedUrls.local[0];
const browser = await chromium.launch();

// Open one harness page and record its page errors in page.errors; called at start and after a timeout.
async function openPage() {
  const page = await browser.newPage();
  page.errors = [];
  page.on("pageerror", (e) => page.errors.push(String(e)));
  await page.goto(`${url}emulator-check.html`);
  await page.waitForFunction(() => !!window.emu);
  return page;
}

// Mount the request's buffer, type its keys, and read back lines/cursor/mode; called by runJob.
async function replay(page, req) {
  const lines = req.lines.length ? req.lines : [""]; // mountEditor needs at least one line
  // expect: {} never matches, so emu's "passed" never latches and nothing else reacts.
  const ex = {
    id: "difftest", skill: "difftest", lang: req.lang, kind: "edit", task: "",
    start: { lines, cursor: req.cursor }, expect: {}, par: { keys: "", count: 0 },
  };
  await page.evaluate((ex) => window.emu.mount(ex), ex);
  await page.waitForFunction(() => !!document.activeElement?.closest(".cm-editor"), null, { timeout: 3000 });
  await typeKeys(page, req.keys);
  return page.evaluate(readState);
}

// Runs in the page after one animation frame: lines, cursor and mode as Vim sees them; called by replay.
// In Visual mode the CodeMirror selection head is one past the Vim cursor, so the cursor
// comes from codemirror-vim's own state (vim.sel.head), reached through CM6's DOM tile
// (the same path as EditorView.findFromDOM). "pending" = an operator, count or register
// typed but not finished; "cmdline" = the ":" or "/" input has focus.
function readState() {
  return new Promise((done) => requestAnimationFrame(() => {
    const { snap } = window.emu.status();
    const a = document.activeElement;
    const cmdline = a instanceof HTMLInputElement && !!document.getElementById("code")?.contains(a);
    const vim = document.querySelector("#code .cm-content")?.cmTile?.root?.view?.cm?.state?.vim;
    const s = vim?.inputState;
    const pending = !!s && (s.keyBuffer.length > 0 || !!s.operator || s.prefixRepeat.length > 0 ||
      s.motionRepeat.length > 0 || !!s.registerName);
    const h = vim?.visualMode && vim.sel?.head;
    // ch can be Infinity after `$`: clamp to the line length, where Vim puts a Visual-mode
    // cursor after `$` (on the end-of-line position).
    const cursor = h ? [h.line + 1, Math.max(0, Math.min(h.ch, (snap.lines[h.line] ?? "").length))] : snap.cursor;
    done({ lines: snap.lines, cursor, mode: cmdline ? "cmdline" : pending ? "pending" : snap.mode });
  }));
}

// Run one request on a page with the 10 s watchdog; returns [reply, page] (a fresh page after a timeout). Called by serve.
async function runJob(page, req) {
  const t0 = Date.now();
  page.errors.length = 0;
  let timer;
  const timeout = new Promise((_, fail) => { timer = setTimeout(() => fail(new Error("timeout")), JOB_TIMEOUT_MS); });
  try {
    const state = await Promise.race([replay(page, req), timeout]);
    if (page.errors.length) return [{ id: req.id, error: `pageerror: ${page.errors.join(" | ")}` }, page];
    return [{ id: req.id, ...state, ms: Date.now() - t0 }, page];
  } catch (e) {
    if (String(e.message) === "timeout") {
      page.close().catch(() => {});
      return [{ id: req.id, error: `timeout after ${JOB_TIMEOUT_MS} ms` }, await openPage()];
    }
    const pe = page.errors.length ? `pageerror: ${page.errors.join(" | ")}` : `error: ${e.message.split("\n")[0]}`;
    return [{ id: req.id, error: pe }, page];
  } finally {
    clearTimeout(timer);
  }
}

// Feed requests from `next()` to `pages` in parallel and pass each reply to `reply`; called by main and selfTest.
async function serve(pages, next, reply) {
  await Promise.all(pages.map(async (page) => {
    for (let req = await next(); req; req = await next()) {
      const [out, fresh] = await runJob(page, req);
      page = fresh;
      reply(out);
    }
  }));
}

// Three fixed cases with known nvim results; called with --self-test.
async function selfTest(pages) {
  const cases = [
    { id: 1, lang: "python", lines: ["foo bar"], cursor: [1, 0], keys: "dw",
      want: { lines: ["bar"], cursor: [1, 0], mode: "normal" } },
    { id: 2, lang: "python", lines: ["ab"], cursor: [1, 0], keys: "Axy", want: { lines: ["abxy"], cursor: [1, 4], mode: "insert" } },
    { id: 3, lang: "cpp", lines: ["int x;", "int y;"], cursor: [1, 0], keys: "Vj", want: { lines: ["int x;", "int y;"], cursor: [2, 0], mode: "visual-line" } },
  ];
  const queue = [...cases];
  let bad = 0;
  await serve(pages, async () => queue.shift(), (out) => {
    const { want } = cases.find((c) => c.id === out.id);
    const got = { lines: out.lines, cursor: out.cursor, mode: out.mode };
    const ok = JSON.stringify(got) === JSON.stringify(want);
    if (!ok) bad++;
    console.log(`${ok ? "PASS" : "FAIL"}  case ${out.id}${ok ? "" : `: got ${JSON.stringify(out)} want ${JSON.stringify(want)}`}`);
  });
  return bad;
}

// Read JSON-line requests from stdin and write replies to stdout until stdin closes; the normal mode.
// Lines are queued from readline's "line" events (its async iterator can drop lines that
// arrive before it is first awaited); next() hands them out one at a time.
async function main(pages) {
  const queue = [];
  const waiting = [];
  let closed = false;
  const rl = createInterface({ input: process.stdin });
  rl.on("line", (line) => (waiting.length ? waiting.shift()(line) : queue.push(line)));
  rl.on("close", () => { closed = true; while (waiting.length) waiting.shift()(null); });
  const nextLine = () => (queue.length ? Promise.resolve(queue.shift()) : closed ? Promise.resolve(null)
    : new Promise((resolve) => waiting.push(resolve)));
  const next = async () => {
    for (let line = await nextLine(); line !== null; line = await nextLine()) {
      if (!line.trim()) continue;
      try {
        return JSON.parse(line);
      } catch (e) {
        process.stdout.write(JSON.stringify({ id: null, error: `bad request: ${e.message}` }) + "\n");
      }
    }
    return null;
  };
  console.log("ready");
  await serve(pages, next, (out) => process.stdout.write(JSON.stringify(out) + "\n"));
}

const pages = await Promise.all(Array.from({ length: SELF_TEST ? 2 : PAGES }, openPage));
const failed = SELF_TEST ? await selfTest(pages) : (await main(pages), 0);
await browser.close();
await server.close();
if (SELF_TEST) console.log(failed ? `${failed} self-test case(s) failed` : "self-test passed");
await new Promise((flushed) => process.stdout.write("", flushed)); // pipes are async on macOS
process.exit(failed ? 1 : 0);
