// Emulator oracle: replay every exercise's par (and alternates) in the browser editor
// (CodeMirror 6 + codemirror-vim, the practice screen's own setup) and record which
// ones pass. Neovim already verified them; this finds where the web emulator differs.
//
//   node e2e/emulator.mjs [--write] [--alternates] [--engine chromium|firefox|webkit] [--only <skill>] [--build <dir>]
//
// Without --write it only reports. With --write it updates ../build in place:
//   - each exercise's emulator.web becomes "pass" or "fail";
//   - par.keys that fail in the browser but have a passing alternate keep the par
//     (the par is what Neovim does) and the exercise is still served;
//   - exercises whose par fails in the browser are moved from index ids to
//     `webFail` in build/index.json (counts updated) so the app never serves them;
//   - build/stats/emulator_web.json lists every failure with the browser's buffer.
// `make content` runs this after the Python build. Without --write the exit status is 1
// if any par fails.
process.env.PLAYWRIGHT_BROWSERS_PATH ??= "0";

const { createServer } = await import("vite");
const playwright = await import("playwright");
const { fileURLToPath } = await import("node:url");
const { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } = await import("node:fs");
const { join } = await import("node:path");

const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : null;
};
const WRITE = process.argv.includes("--write");
const engineName = arg("--engine") ?? "chromium";
const only = arg("--only");
const ALTS = process.argv.includes("--alternates"); // also replay every alternate

const root = fileURLToPath(new URL("..", import.meta.url));
const { resolve } = await import("node:path");
const build = arg("--build") ? resolve(arg("--build")) : fileURLToPath(new URL("../../build", import.meta.url));
const indexPath = join(build, "index.json");
if (!existsSync(indexPath)) {
  console.error(`${indexPath} is missing: run the content build first.`);
  process.exit(2);
}
const index = JSON.parse(readFileSync(indexPath, "utf8"));

const server = await createServer({ root, logLevel: "error", server: { port: 0 } });
await server.listen();
const url = server.resolvedUrls.local[0];
const browser = await playwright[engineName].launch();
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto(`${url}emulator-check.html`);
await page.waitForFunction(() => !!window.emu);

const { typeKeys: typeInto } = await import("./keys.mjs");
const typeKeys = (keys) => typeInto(page, keys);

async function tryKeys(ex, keys, attempt = 1) {
  await page.evaluate((ex) => window.emu.mount(ex), ex);
  await page.waitForFunction(() => !!document.activeElement?.closest(".cm-editor"), null, { timeout: 3000 });
  await typeKeys(keys);
  // Commands finish synchronously, so a pass resolves within a frame; the long timeout
  // only matters on a failure. CI run 38337241533 marked one of 1589 pars as a web fail
  // with a 400 ms wait on a slow runner, which flipped the committed build/.
  await page.waitForFunction(() => window.emu.status().passed, null, { timeout: 3000 }).catch(() => {});
  const status = await page.evaluate(() => window.emu.status());
  // One retry: keys typed before the remounted editor settled can be dropped on a slow runner.
  if (!status.passed && attempt < 2) return tryKeys(ex, keys, attempt + 1);
  return status;
}

const failures = [];
let total = 0, passedPar = 0, rescued = 0;
const altFailures = [];
for (const [lang, { skills }] of Object.entries(index.langs)) {
  for (const [skill, entry] of Object.entries(skills)) {
    if (only && skill !== only) continue;
    // Sorted, so a re-run that rescues a webFail id writes the same index as a fresh build.
    const ids = [...entry.ids, ...(entry.webFail ?? [])].sort();
    const keep = [], drop = [];
    for (const id of ids) {
      const file = join(build, "exercises", lang, skill, `${id.split("/").pop()}.json`);
      const ex = JSON.parse(readFileSync(file, "utf8"));
      total++;
      const par = await tryKeys(ex, ex.par.keys);
      let web = par.passed ? "pass" : "fail";
      const altPass = [];
      if (!par.passed) {
        for (const alt of ex.alternates ?? []) if ((await tryKeys(ex, alt)).passed) altPass.push(alt);
        failures.push({ id, skill, kind: ex.kind, par: ex.par.keys, alternatesPassing: altPass, browser: par.snap, expect: ex.expect });
        if (altPass.length) rescued++;
      } else {
        passedPar++;
        if (ALTS)
          for (const alt of ex.alternates ?? []) {
            const r = await tryKeys(ex, alt);
            if (!r.passed) altFailures.push({ id, alt, browser: r.snap });
          }
      }
      (par.passed ? keep : drop).push(id);
      if (WRITE) {
        ex.emulator = { ...(ex.emulator ?? {}), web };
        writeFileSync(file, JSON.stringify(ex, null, 2) + "\n");
      }
    }
    if (WRITE) {
      entry.ids = keep;
      entry.count = keep.length;
      if (drop.length) entry.webFail = drop;
      else delete entry.webFail;
    }
    const failed = ids.length - keep.length;
    console.log(`${lang} ${skill.padEnd(12)} ${String(keep.length).padStart(3)} pass  ${failed ? `${failed} fail` : ""}`);
  }
}
await browser.close();
await server.close();

console.log(`\n${engineName}: ${passedPar}/${total} pars pass in the browser; ${failures.length} fail (${rescued} of those have a passing alternate).`);
for (const f of failures.slice(0, 15)) console.log(`  ${f.id}  par ${JSON.stringify(f.par)}`);
if (ALTS) {
  console.log(`alternates failing in the browser: ${altFailures.length}`);
  for (const f of altFailures.slice(0, 30)) console.log(`  ${f.id}  alternate ${JSON.stringify(f.alt)}`);
}
if (errors.length) console.log(`page errors: ${errors.join(" | ")}`);
if (WRITE) {
  writeFileSync(indexPath, JSON.stringify(index, null, 2) + "\n");
  mkdirSync(join(build, "stats"), { recursive: true });
  writeFileSync(join(build, "stats", "emulator_web.json"), JSON.stringify({ engine: engineName, total, pass: passedPar, failures }, null, 2) + "\n");
  console.log("wrote build/index.json, build/stats/emulator_web.json and emulator.web on every exercise");
}
// A report run fails on any mismatch; a --write run has already dropped those exercises.
process.exit(errors.length || (!WRITE && failures.length) ? 1 : 0);
