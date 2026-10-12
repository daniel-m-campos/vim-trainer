# Tech stack

Chosen for a solo developer who writes Python and C++, with the browser app as the one
unavoidable TypeScript surface. Prefer boring, well-maintained pieces; the product's
novelty is in the model and content, not the stack.

## Decisions

| layer | choice | why |
|---|---|---|
| Vim in the browser | CodeMirror 6 + `@replit/codemirror-vim` (MIT) | best fidelity-to-effort (research/02); active; exposes `Vim.handleKey`, mode events, custom operators. vim.wasm frozen, Neovim WASM blocked |
| Front-end | TypeScript, Vite, no framework for the practice screen; Preact or Svelte if the stats screen needs components | the practice screen is three regions and a key handler; a framework adds more than it saves. Decide when the stats screen is built |
| Charts | a small library loaded from CDN (uPlot or Chart.js), following the dataviz skill's palette rules | stats screen only; keep the practice screen library-free |
| Storage | `localStorage` in v1 with JSON export/import; IndexedDB if the log exceeds ~2 MB | no accounts in v1 (10-ux). Sync is a pro feature later |
| Content build | Python 3.12, `py-tree-sitter` + grammar wheels, `pynvim` or `subprocess` to `nvim --headless --clean` | author's language; see 03 |
| Emulator oracle | Playwright (Python) driving a headless Chromium page that loads codemirror-vim | same language as the build; jsdom lacks the layout codemirror needs (verify) |
| Model | pure TypeScript module in the app, mirrored by a pure Python module for simulation and tests; shared JSON test vectors keep them identical | the model must be testable offline (04) |
| Hosting | static files on Cloudflare Pages or GitHub Pages; no server in v1 | nothing is server-side until accounts/sync |
| Accounts & sync (later) | Cloudflare Workers + D1 or Supabase; passkeys or magic link; no passwords | smallest ops burden for a solo dev |
| Payments (later) | Polar or Paddle (merchant of record) | VAT handled; see 07 |
| Analytics | none in v1 beyond an opt-in "send anonymous exercise log" button | audience hostility to tracking; the log is the only data we need |
| CI | GitHub Actions: content build + oracle on every content change, TS and Python tests, deploy on main | pars are verified in CI, never by hand |

## Repository layout (when code starts)

```
app/          TypeScript: practice screen, stats, settings, model (ts)
content/      Python: sources allowlist, lang mappings, templates, oracle, review CLI
model/        Python mirror of the model + simulators + shared test vectors
build/        generated exercises, stats, ATTRIBUTION.md (committed? decide: likely yes, for reproducible deploys)
docs/         this plan
```

## Constraints and known gaps

- codemirror-vim gaps that affect exercises (research/02): no Select mode, some `%`
  matching failures, no `U`, no `g@`, macro-replay hang (#177). The emulator oracle
  marks affected exercises unsupported in the browser; the supported-command list is
  generated, not hand-written.
- `<Esc>` handling and key capture differ across browsers; test Firefox and Safari early.
- Bundle size target: < 300 KB gzip for the practice screen including codemirror-vim
  (~40 KB) and fonts.
- Offline after first load: a service worker is not available in the artifact sandbox
  but is on a normal host; add one once hosted.

## To research

- Confirm codemirror-vim's hook names and reliability for command-done / mode-change
  (issues #251, #276, #277). Build a 1-day spike before committing to the key logger
  design in 05.
- Playwright vs jsdom for the emulator oracle.
- Whether to commit `build/` or generate on deploy (size vs reproducibility).
