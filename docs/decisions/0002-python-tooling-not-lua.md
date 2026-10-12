# 0002: Tooling in Python, not Lua

Date: 2026-10-11. Status: accepted.

The content pipeline, the review CLI, the oracle driver, the model mirror and the
simulators are Python 3.12 projects managed by uv (`content/` and `model/`, each with its
own `pyproject.toml`). The only Lua is `content/src/vimtrainer_content/oracle.lua`, 58
lines, which runs inside Neovim. The browser app is the one TypeScript surface.

Why: the author writes Python and C++, and reviews exercises faster in the language
they read best. Neovim is a subprocess, so nothing needs Lua beyond the replay script.

Consequences:
- The oracle runs as `nvim --headless --clean -u NONE -l oracle.lua JOBS.json`. This
  replaced the `-u content/oracle.lua -c 'lua Oracle.run(...)'` form in the first
  draft of 03. The same file is loaded by pynvim with `dofile`.
- There is no root `pyproject.toml`. The top-level `Makefile` is the single entry point.
- pynvim relies on a deprecated asyncio call and is not used by the build. The build
  uses the subprocess batch backend.
