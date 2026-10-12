# 0004: Exercise JSON details decided during the build

Date: 2026-10-11, amended 2026-10-12. Status: accepted.

03 describes the exercise schema. The build settled these details, which the app and
the model depend on:

- **Ids are content hashes.** `py/<skill>/<10 hex>`, a stable hash of window, template,
  start, cursor and expect. A rebuild keeps ids stable, so `reviewed.txt` and
  `rejected.txt` stay valid. The file is `build/exercises/<lang>/<skill>/<hex>.json`.
- **`target` is a list of inclusive spans.** `[{start, end}, ...]`, each end a
  `[line 1-based, col 0-based]` pair. It drives the highlight. The app also accepts the
  spike's single `{from, to}` form (end exclusive).
- **Hints are objects.** `{trigger, text}`. `trigger` is a regex run against the
  displayed key string, compiled with the JavaScript `u` flag, or null for the fallback.
  Each exercise has 2 to 4 triggered hints plus one fallback. A trigger that matches the
  canonical keys is dropped, so a user at par never sees a hint.
- **`emulator.web`** is `pass` or `fail` after the browser replay. It was `unverified`
  before that step existed.
- **Extra fields:** `template`, `params`, `provenance` (no LLM), `naive` (key count of
  someone who knows only hjkl, x, dd and typing), `reviewed`, `source.lines`, and
  `par.best` when an alternative wins by exactly 1 key.
- **Cursor columns are byte offsets**, as in Neovim. Windows are ASCII-only and
  tab-free, so bytes and UTF-16 units agree. Non-ASCII needs a conversion first.
- **`build/` is committed** (593 files, 2.7 MB), so `make dev` works without Neovim. The
  repo `.gitignore` adds `!/build/` because the author's global ignore excludes it. CI
  rebuilds into a scratch directory and diffs against the committed copy, ignoring the
  `generated` and `verified` date lines.
- **`build/all.json`** is written into `dist/build/` by `vite.config.ts` at build time:
  every exercise in one file, keyed `<lang>/<skill>/<leaf>`. Static hosts with a file
  count cap serve it, and the app reads exercises from it when present. Dev and CI keep
  the per-file layout. It is not in the committed `build/`.
- **`index.json`** has a `skills` level: `langs.<lang>.skills.<skill>` with ids, count,
  parMedian and thin. Composite exercises are listed under every skill they tag.
