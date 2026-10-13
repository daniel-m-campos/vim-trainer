# vim-trainer: one entry point for the three parts.
#   content/  Python (uv): exercises from real code, pars verified in Neovim -> build/
#   model/    Python (uv): the adaptive model; its TypeScript mirror is app/src/model/
#   app/      TypeScript (npm + Vite): the trainer in the browser
#
#   make setup    install everything (uv projects, npm packages, Playwright Chromium)
#   make content  rebuild build/ (needs nvim) and replay every par in the browser
#   make dev      run the app at http://localhost:5173/
#   make test     unit tests: content, model (Python and TS mirror), app grading, typecheck
#   make e2e      Playwright: the sample flow, a 15-exercise session on build/, the stats demo,
#                 editor regressions checked against nvim
#
# Browsers live in app/node_modules (PLAYWRIGHT_BROWSERS_PATH=0), nothing global.

export PLAYWRIGHT_BROWSERS_PATH := 0
BROWSERS ?= chromium
CHECK_DIR := content/.cache/build-check

.PHONY: setup content content-check dev test test-content test-model test-app e2e e2e-all emulator build clean help

help:
	@sed -n '1,15p' Makefile

setup:
	@command -v uv >/dev/null || { echo "uv is missing: brew install uv"; exit 1; }
	@command -v node >/dev/null || { echo "node is missing: brew install node (>= 23)"; exit 1; }
	@command -v nvim >/dev/null || echo "note: nvim is missing (brew install neovim); only 'make content' needs it, build/ is committed"
	cd content && uv sync
	cd model && uv sync
	cd app && npm ci
	cd app && npx playwright install $(BROWSERS)

# Python + C++ build (fetches the pinned exercism/python and exercism/cpp into content/.cache on first run),
# then the browser oracle: emulator.web on every exercise, mismatches dropped from the index.
content:
	cd content && uv run vimtrainer-content build
	cd app && node e2e/emulator.mjs --write

# CI: rebuild into a scratch directory and require it to be byte-identical to the committed
# build/. Fails when someone changes the pipeline without `make content`, or builds with an
# nvim other than the pinned one (par.verified names the version). The build date is the
# only input that changes from day to day, so it is pinned to the committed one:
# SOURCE_DATE_EPOCH = UTC midnight of build/index.json "generated" (see build.py).
content-check:
	rm -rf $(CHECK_DIR)
	cd content && SOURCE_DATE_EPOCH=$$(node -e 'process.stdout.write(String(Date.parse(require("../build/index.json").generated) / 1000))') \
		uv run vimtrainer-content build --out .cache/build-check
	cd app && node e2e/emulator.mjs --write --build ../$(CHECK_DIR)
	diff -r build $(CHECK_DIR)

dev:
	cd app && npm run dev

test: test-content test-model test-app

test-content:
	cd content && uv run pytest -q

test-model:
	cd model && uv run pytest -q

# Grading unit tests, the build/ contract test and the TS model mirror (node --test),
# plus the e2e key-notation helper (keys.mjs).
test-app:
	cd app && npm test
	cd app && npm run test:e2e-helpers
	cd app && npm run typecheck

e2e:
	cd app && npm run e2e
	cd app && npm run e2e:session
	cd app && npm run e2e:stats
	cd app && npm run e2e:editor

# All three engines (run `make setup BROWSERS="chromium firefox webkit"` first).
e2e-all:
	cd app && npm run e2e -- --all
	cd app && npm run e2e:session -- --all
	cd app && npm run e2e:editor -- --all

# Report-only replay of every par and alternate in the browser.
emulator:
	cd app && node e2e/emulator.mjs --alternates

# Static site in app/dist/ (build/ copied in).
build:
	cd app && npm run build

clean:
	rm -rf app/dist $(CHECK_DIR)
