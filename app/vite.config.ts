import { resolve, join, normalize, extname } from "node:path";
import { existsSync, statSync, createReadStream, cpSync, readFileSync, writeFileSync, readdirSync } from "node:fs";
import { defineConfig, type Plugin } from "vite";

const repo = resolve(import.meta.dirname, "..");

// The content pipeline's output (repo build/) is served next to the app. Missing files
// answer 404 (never the SPA index.html), so the app can fall back to
// public/build-sample/ when build/ does not exist yet. The skill graph is bundled
// (src/model/skill-graph.json), so it is not served here.
const STATIC_DIRS: Record<string, string> = {
  "/build/": join(repo, "build"),
};

const TYPES: Record<string, string> = {
  ".json": "application/json; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
};

function repoStatic(): Plugin {
  const middleware = (req: { url?: string }, res: any, next: () => void) => {
    const url = decodeURIComponent((req.url ?? "").split("?")[0]);
    const prefix = Object.keys(STATIC_DIRS).find((p) => url.startsWith(p));
    if (!prefix) return next();
    const root = STATIC_DIRS[prefix];
    const file = normalize(join(root, url.slice(prefix.length)));
    if (!file.startsWith(root) || !existsSync(file) || !statSync(file).isFile()) {
      res.statusCode = 404;
      res.setHeader("content-type", "text/plain");
      return res.end("not found");
    }
    res.setHeader("content-type", TYPES[extname(file)] ?? "application/octet-stream");
    res.setHeader("cache-control", "no-cache");
    createReadStream(file).pipe(res);
  };
  return {
    name: "repo-static",
    configureServer: (server) => void server.middlewares.use(middleware),
    configurePreviewServer: (server) => void server.middlewares.use(middleware),
    // Static hosting: ship build/ inside dist/ when present.
    closeBundle() {
      const out = resolve(import.meta.dirname, "dist");
      const build = STATIC_DIRS["/build/"];
      if (!existsSync(build)) return;
      cpSync(build, join(out, "build"), { recursive: true });
      // One-file bundle of every exercise for hosts that cap the file count.
      // Keys are "<lang>/<skill>/<leaf>" to match content.ts.
      const exercises: Record<string, unknown> = {};
      const root = join(build, "exercises");
      for (const lang of readdirSync(root)) {
        for (const skill of readdirSync(join(root, lang))) {
          for (const f of readdirSync(join(root, lang, skill))) {
            if (!f.endsWith(".json")) continue;
            exercises[`${lang}/${skill}/${f.slice(0, -5)}`] = JSON.parse(readFileSync(join(root, lang, skill, f), "utf8"));
          }
        }
      }
      writeFileSync(join(out, "build", "all.json"), JSON.stringify({ exercises }));
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [repoStatic()],
  build: {
    rollupOptions: {
      input: {
        main: resolve(import.meta.dirname, "index.html"),
        "spike-keylogger": resolve(import.meta.dirname, "spike-keylogger.html"),
      },
    },
  },
});
