# 0005: The browser emulator replay is a build step in `make content`

Date: 2026-10-12. Status: accepted.

`make content` runs two stages: the Python build (`vimtrainer-content build`, about
25 s), then `node app/e2e/emulator.mjs --write` (about 90 s). The second stage types
every par into the app's own editor in headless Chromium. With `--write` it sets
`emulator.web` on every exercise and moves failing ids into `webFail` in `index.json`.
Without `--write` it reports and exits 1 on any mismatch (`make emulator`).

Why: 03 had the emulator oracle as a later milestone, and 06 left Playwright against
jsdom open. Running it inside the build means the app never serves an exercise it
cannot grade, and a codemirror-vim change that breaks a par shows up at once.

Choices:
- Playwright (JavaScript, in `app/`), not Python Playwright and not jsdom. The oracle
  and the app then share one editor setup. jsdom was not tried.
- The harness page `emulator-check.html` is dev-only and not in `dist/`.
- `make content-check` runs the same two stages into `content/.cache/build-check` and
  diffs against `build/`. CI runs it. Two local builds with 8 and 2 Neovim jobs were
  byte-identical. Whether Linux reproduces the macOS output is not yet known.
- CI runs Chromium only. `make e2e-all` covers Firefox and WebKit locally.
