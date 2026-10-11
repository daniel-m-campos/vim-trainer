# Technical building blocks and licensing for a browser-based Vim-motions trainer

Research date: 2026-10-11. Licence names are quoted as they appear in the linked licence files. "Could not determine" marks anything I could not confirm from a primary source.

## Key Question 1: Which emulator gives the best fidelity-to-effort ratio for a trainer, and what Vim features would it fail on?

### Takeaway
For a solo developer, CodeMirror 6 + `@replit/codemirror-vim` (MIT, ~39 KB gzip, actively maintained, public `Vim.handleKey` API) is the pragmatic default; its gaps are edge-case Vim features (`%` on some brackets, `U`, `g@`/operatorfunc, Select mode, macro-replay hangs) rather than core motions/operators/text objects. Real Vim in WASM (rhysd/vim.wasm) is effectively frozen at Vim 8.2.0055 since Dec 2019, and Neovim-in-WASM (MuNeNICK/nvim-wasm) is real but ~8 MB, requires COOP/COEP or Asyncify, and is not an official Neovim build target as of May 2026.

### Cited Findings

**CodeMirror 6 + @replit/codemirror-vim**
- Licence: "MIT License". Repository stats as fetched: 476 stars, 55 forks, 641 commits, 33 open issues; core engine credited to "@mightyguava" (Yunchi Luo) — [replit/codemirror-vim](https://github.com/replit/codemirror-vim); licence file: https://github.com/replit/codemirror-vim/blob/master/LICENSE
- Bundle size (bundlephobia): version 6.4.0, minified 121,759 bytes, gzip 38,525 bytes; the package has one dependency, `@replit/codemirror-vim-core`, which bundlephobia reports as adding approximately 188,374 bytes (CodeMirror 6 core itself not included in these figures) — [bundlephobia API](https://bundlephobia.com/api/size?package=@replit/codemirror-vim)
- Public API documented in the package README: `getCM(view)` returns the CM5-compatible adapter; `Vim.handleKey(cm, "<Esc>")` processes a key programmatically; `Vim.exitInsertMode(cm)`; `Vim.defineEx(name, prefix, fn)` defines Ex commands; `Vim.map(keys, target, mode)` / `Vim.unmap`; `Vim.defineOperator()` registers custom operators. Setup notes: "make sure vim is included before other keymaps" and include `drawSelection` for visual-mode rendering — [packages/codemirror-vim/README.md](https://raw.githubusercontent.com/replit/codemirror-vim/master/packages/codemirror-vim/README.md)
- Open issues as of Oct 2026 that indicate fidelity gaps: #239 "Implement Select mode" (Jul 2025); #234 "Not support `%` to jump to a matching opening or closing parenthesis" (Jun 2025); #225 "add 'U' to undo all changes on the current line" (Mar 2025); #199 "Support mapping an operator (`g@` and `operatorfunc`)" (Dec 2024); #172 "Increment zero-padded decimal" (Apr 2024); #177 "Macro replay hang" (May 2024); #229 "`v2a` behaves incorrectly" (Apr 2025); #251 "Mode change event not firing" (Jan 2026); #276 undo/redo marker placement (Sep 2026); #277 visual-mode cursor positioning (Sep 2026); #178/#153 IME and Japanese-keyboard problems — [issue tracker](https://github.com/replit/codemirror-vim/issues)
- The existence of issue #251 ("Mode change event not firing") confirms the engine exposes a mode-change event that consumers rely on — [issue list](https://github.com/replit/codemirror-vim/issues)
- A third-party open-source course, dofy/learning-vim, is built on "CodeMirror 6 with @replit/codemirror-vim", confirming the stack is used for trainers — [dofy/learning-vim](https://github.com/dofy/learning-vim)

**Monaco + monaco-vim**
- Licence: "MIT license". README: "Vim keybindings for Monaco Editor"; API `initVimMode(editor, statusNode)` returning an object with `dispose()`; Ex commands via `VimMode.Vim.defineEx()`; `VimMode.Vim` exposes "CodeMirror Vim layer" (i.e. it is a port of the CodeMirror vim keymap). README caveat: "there may be issues in some of the keybindings, especially those that expect extra input like the Ex commands or search/replace." 146 commits, 30 open issues — [brijeshb42/monaco-vim](https://github.com/brijeshb42/monaco-vim); licence file: https://github.com/brijeshb42/monaco-vim/blob/master/LICENSE
- Bundle size: version 0.4.4, minified 100,776 bytes, gzip 30,699 bytes, no dependencies, `monaco-editor` as peer dependency (Monaco itself is multi-MB and not included) — [bundlephobia API](https://bundlephobia.com/api/size?package=monaco-vim)
- npm registry: latest 0.4.4; licence MIT; the registry fetch showed versions 0.1.18/0.1.19 in Aug/Sep 2021; exact publish date of 0.4.4 could not be read from the truncated response — [npm registry](https://registry.npmjs.org/monaco-vim)

**vim.wasm (real Vim compiled to WebAssembly)**
- Compiles "Vim 8.2.0055" in 'normal' and 'small' feature sets using Emscripten and Binaryen, TypeScript runtime. Requires `SharedArrayBuffer` and `Atomics`; works in desktop Chrome, Chromium-based browsers, Safari, Firefox (with `javascript.options.shared_memory`). "Lacks mouse and IME support currently." Keystrokes: main thread captures `keydown` and writes into a shared memory buffer read by the worker. Buffer out: `:export` downloads the current buffer, `:export {file}` exports a file; files persist in IndexedDB under `~/.vim`; `:!/path/to/file.js` evaluates JavaScript from Vim. Licence: "All additional files in this repository are licensed under the same license as Vim (VIM LICENSE)" — [rhysd/vim.wasm](https://github.com/rhysd/vim.wasm)
- npm `vim-wasm`: latest 0.0.13 published December 30, 2019; first publish July 3, 2018; licence field "Vim" — [npm registry](https://registry.npmjs.org/vim-wasm)
- Last five commits on the `wasm` branch are all "renew origin trial token" (Feb 25 2026, Oct 21 2025, May 12 2025, Jun 27 2024, Jun 4 2023); no functional change since 2023 at the latest — [commits/wasm](https://github.com/rhysd/vim.wasm/commits/wasm)
- Startup time: could not determine from sources (README did not state it; no benchmark found).

**Neovim in the browser (2025–2026)**
- Official tracking issue neovim/neovim#35567 "tracking: WASM (webassembly) as Nvim build target" remains open and blocked as of May 2026; blockers: libuv/luv (#37885), LuaJIT under Emscripten (#38224), cross-compilation toolchain (#38076). Only minor supporting PRs merged (#38089). Labelled for GSoC but with no active assignment; maintainer comment on March 13, 2026 asked MuNeNICK about a PR timeline — [neovim#35567](https://github.com/neovim/neovim/issues/35567)
- Three GSoC 2026 proposal discussions exist: #37903, #38033, #38643 — [GSoC discussion](https://github.com/neovim/neovim/discussions/38643)
- MuNeNICK/nvim-wasm: "generates a wasm32-wasi build of Neovim without modifying the upstream source"; optional Binaryen Asyncify post-processing for SharedArrayBuffer-free execution; standard builds "require COOP/COEP headers"; Neovim submodule pinned at commit `c40cb2a`; 36 stars, 28 commits; licence not stated in README excerpt — [MuNeNICK/nvim-wasm](https://github.com/MuNeNICK/nvim-wasm)
- Author blog post (July 30, 2026): wasm binary "approximately 7.8 MB for the standard build and 8.4 MB for the Asyncify build"; stdin via a SharedArrayBuffer ring buffer (or postMessage in the Asyncify build); state read via "Msgpack-RPC transport" with the browser subscribing through `nvim_buf_attach` and receiving redraws via `ext_linegrid`; limitations: no PTY/child processes, no signals/pthreads, no access outside the browser sandbox, no plugins needing native libraries. Demos: https://nvim-wasm.pages.dev/, https://nvim-wasm-monaco.pages.dev/, https://nvim-wasm-xterm.pages.dev/ — [munenick.me](https://www.munenick.me/en/blog/nvim-wasm/)
- Startup time for nvim-wasm: not documented in the post — [munenick.me](https://www.munenick.me/en/blog/nvim-wasm/)

**xterm.js + server-side Neovim**
- No source consulted gave cost/latency figures; see Gaps.

**Purpose-built engines used by trainers**
- OpenVim (egaga/openvim): "MIT License"; "a custom engine that interprets vim commands" operating directly on the DOM, "could be easily refactored to a model that is not view-dependent"; 73 commits; initial version 2011 — [egaga/openvim](https://github.com/egaga/openvim); licence file: https://github.com/egaga/openvim/blob/master/LICENSE
- VimMaster (renzorlive/vimmaster): "MIT License"; lessons are JSON files in `content/lessons/*.json` compiled to `content/index.json`; a golden test suite replays the lesson's `solution` keypress array through the engine and compares the final editor state to the target; the underlying engine type (custom vs CodeMirror) could not be determined from the README — [renzorlive/vimmaster](https://github.com/renzorlive/vimmaster); licence file: https://github.com/renzorlive/vimmaster/blob/main/LICENSE
- Vim Mastery (Ichihiroy/vim-mastery): "MIT" (© 2026); custom TypeScript engine `handleKey(state, key) → { state }`, no React, no Monaco/CodeMirror, DOM grid renderer with hidden input; supports modes, motions, operators, text objects, counts, find/search; 49 lessons; describes VimHero as "a paid competitor" — [Ichihiroy/vim-mastery](https://github.com/Ichihiroy/vim-mastery)
- vimee (vimeejs/vimee): "MIT"; "A headless vim engine for the web"; pure function `processKeystroke(key, ctx, buffer) → { newCtx, actions[] }`; packages for Monaco, CodeMirror 6, textarea, React hook; claims Normal/Insert/Visual/Visual-Line/Visual-Block/Command-Line modes, text objects, macros, marks, registers, undo/redo, counts; 44 stars, 127 commits — [vimeejs/vimee](https://github.com/vimeejs/vimee)
- Vim Hero (vim-hero.com): "50+ interactive lessons", "Challenges are generated dynamically", "Your proficiency in each skill is tracked", "Free to start", copyright "HAUGE LLC" (© 2026); editor technology not disclosed on the site — [vim-hero.com](https://www.vim-hero.com/)
- vimified.com: $20 "Lifetime Access"; tracks per-lesson time and keystrokes; editor technology not disclosed — [vimified.com](https://www.vimified.com/)
- vim.so: author Kenneth Cassel, launched Feb 2021, "10 interactive lessons"; editor technology not stated in the launch post — [dev.to](https://dev.to/kennethcassel/i-built-an-interactive-course-that-teaches-you-vim-in-the-browser-411c)

### Inferences
- monaco-vim is a port of the same CodeMirror vim keymap, so its fidelity gaps will largely mirror codemirror-vim's but with a less active upstream (146 commits, README itself warns about Ex/search edge cases). For a trainer, `@replit/codemirror-vim` is the better-maintained branch of the same lineage.
- Capturing the keystroke stream with codemirror-vim: because the trainer owns the DOM, a `keydown` listener on the editor plus `Vim.handleKey` for replay/testing is sufficient; command completion can be detected by diffing `cm.state.vim` (mode, pending operator/count) or by listening for the engine's mode-change event, whose existence issue #251 confirms. The exact event-name strings (`vim-mode-change`, `vim-keypress`, `vim-command-done`) are known from the CodeMirror 5 keymap lineage but I could not fetch the source file to quote them; verify in `packages/codemirror-vim-core/src/vim.js` before relying on them.
- vim.wasm is suitable only as a reference oracle or demo: a 2019 Vim 8.2 snapshot, no mouse/IME, SharedArrayBuffer required, and buffer extraction only via `:export`/IndexedDB rather than a direct JS API.
- nvim-wasm is the only path that gives real Neovim semantics plus a clean programmatic interface (`nvim_input` for keys, `nvim_buf_attach` for buffer state via msgpack-RPC), but ~8 MB download plus COOP/COEP hosting requirements make it heavy for a lesson page; it would be a strong choice for an offline "verify par against real Neovim" build step (as vimhjkl does with real Vim) rather than the interactive editor.
- Headless engines (vimee, vim-mastery) are attractive for deterministic grading and Dijkstra-style optimal-path computation, but are young (44 stars / 3 commits respectively) and their feature claims are self-reported.

### Gaps
- Exact event names and `cm.state.vim` fields in `@replit/codemirror-vim`: the raw `src/vim.js` paths I tried returned 404 (repo was restructured into a pnpm workspace); the npm page returned 403. Needs a direct repo browse.
- Startup time for vim.wasm and nvim-wasm: no measured figures found.
- xterm.js + server-side Neovim cost/latency: no sources consulted; would require pricing research for per-session containers/PTYs.
- Vim Hero, vimified and vim.so editor technology: not disclosed in any fetched page; "could not determine".
- vim.wasm "status": README describes GitHub Projects tracking, but commit history shows only token-renewal commits since 2023; treat as maintained-but-frozen.

## Key Question 2: Can VimGolf or vimhjkl exercises be legally reused or must they be written fresh?

### Takeaway
The VimGolf *software* is MIT, but the challenge texts live on vimgolf.com, which publishes no terms or licence for user-submitted challenges, so reuse rights for that content could not be determined. vimhjkl's 230 challenges are MIT-licensed (including contributor content), partially LLM-generated but machine-verified against real Vim, and tagged by skill, making it the most clearly reusable open set.

### Cited Findings

**VimGolf**
- Client/server code licence: "The MIT License (MIT)", "Copyright (c) 2010 Ilya Grigorik" — [LICENSE](https://raw.githubusercontent.com/igrigorik/vimgolf/master/LICENSE)
- Challenge content is hosted on vimgolf.com ("pick a challenge on vimgolf.com", challenges are "downloaded from the site"); the repo contains only seeds/migrations, not the challenge corpus — [igrigorik/vimgolf](https://github.com/igrigorik/vimgolf)
- vimgolf.com's about page states "anyone can create a new challenge" and "Entries are ranked by score (lowest wins), ties broken by time"; rules: "No plugins, predefined macros, etc, are allowed", "refrain from copy/paste, reading in the solution (:read), or using external tools". It contains no terms of use, licence, or ownership statement for challenges or solutions — [vimgolf.com/about](https://www.vimgolf.com/about)
- Per-challenge JSON is available at `http://vimgolf.com/challenges/<id>.json` (documented by the Yi editor's vimgolf client) — [yi-editor](https://yi-editor.github.io/pages/vimgolf/)
- A mirror site exposes `GET /api/challenge?id=<id>` and `GET /api/challenge?list=true&page=1&limit=9` — [vimgolf.netlify.app](https://vimgolf.netlify.app/)
- A scraped dataset `James4Ever0/vimgolf_challenges_and_solutions` on Hugging Face is labelled "unlicense" and consists of `metadata.json`, `challenge.json` (input/output/type), and `worst_solution.json` per challenge; the data "originates from vimgolf.com"; anonymous viewers can see only the worst solution — [Hugging Face](https://huggingface.co/datasets/James4Ever0/vimgolf_challenges_and_solutions)
- `vimgolf-gym` (same author) is "The Unlicense", verifies by buffer equality, uses vimgolf angle-bracket keystroke notation, and gives "no explicit licensing statement for challenge data sourcing or attribution to vimgolf.com" — [James4Ever0/vimgolf-gym](https://github.com/James4Ever0/vimgolf-gym)

**vimhjkl**
- Licence: "MIT"; "66 skills, 230 challenges"; "Every challenge is machine-verified against real vim"; `content/llm_pool.json` "holds extra verified instances" (LLM-generated pool); grading uses `vim -W` keystroke capture scored "against a verified par" with a pass requiring correctness and "≤ 2× par"; "Command drills mandate actual ex commands rather than hand-editing"; scheduling is Leitner boxes 1–5 plus a rep count toward 25 then maintenance; curriculum generated into `src/vimhjkl/data/skills.json` ("not hand-edited") from `build/passes/*.py` — [README](https://raw.githubusercontent.com/S-Sigdel/vimhjkl/main/README.md); repo: https://github.com/S-Sigdel/vimhjkl; licence file: https://github.com/S-Sigdel/vimhjkl/blob/main/LICENSE
- CONTRIBUTING: the generator "validates every solution against real Vim" and rejects a challenge "if anything fails to verify — so a wrong solution or goal cannot ship"; challenges carry `why_not` explanations of rejected alternatives; categories in `challenge.py` determine "how it's graded"; motion challenges use cursor positions and targets rather than goal buffers; contributors "agree their work falls under the MIT License" — [CONTRIBUTING.md](https://raw.githubusercontent.com/S-Sigdel/vimhjkl/main/CONTRIBUTING.md)
- Skills covered include "dot command, operator+motion grammar, text objects, registers, marks, macros, :g / :normal / ranges, regex and substitution, indentation, joins, and paragraph motions" — [search summary of README](https://github.com/S-Sigdel/vimhjkl)

**Vimtutor Sequel**
- "MIT License" (LICENSE file); content in `vimtutor-sequel.txt` loaded via `vimtutor-sequel.vimrc`; author Micah Kepe — [micahkepe/vimtutor-sequel](https://github.com/micahkepe/vimtutor-sequel); licence file: https://github.com/micahkepe/vimtutor-sequel/blob/main/LICENSE

**vimtutor (Vim's own tutor)**
- Vim's LICENSE ("VIM LICENSE"): modified distribution requires including the licence unmodified, documenting changes with maintainer contact, and either providing source changes, sharing them with the maintainer, distributing under GPL v2+, or retaining changes for three years; a visible notice of modification is required — [vim/vim LICENSE](https://github.com/vim/vim/blob/master/LICENSE)
- The tutor text (`runtime/tutor/tutor1`, "Version 1.7") ends: "This tutorial was written by Michael C. Pierce and Robert K. Ware, Colorado School of Mines using ideas supplied by Charles Smith, Colorado State University... Modified for Vim by Bram Moolenaar." The file itself carries no separate licence statement — [tutor1](https://raw.githubusercontent.com/vim/vim/master/runtime/tutor/tutor1)
- Directory also contains `tutor2`, `tutor.tutor`, `tutor.tutor.json`, `tutor.vim`, README.txt and translations — [runtime/tutor](https://github.com/vim/vim/tree/master/runtime/tutor)

**OpenVim / VimMaster / Vim Mastery content**
- OpenVim: "MIT License" covering the repo, tutorial content embedded in HTML/JS — [egaga/openvim](https://github.com/egaga/openvim)
- VimMaster: "MIT License"; lessons are JSON files in `content/lessons/` — [renzorlive/vimmaster](https://github.com/renzorlive/vimmaster)
- Vim Mastery: "MIT"; 49 lessons "deterministically generated, non-hand-authored" — [Ichihiroy/vim-mastery](https://github.com/Ichihiroy/vim-mastery)

### Inferences
- VimGolf challenge texts: the MIT licence covers only Ilya Grigorik's code. User-submitted challenge input/output text has no stated licence; the Unlicense label on the Hugging Face scrape is applied by the scraper, not by vimgolf.com or the challenge authors, so it cannot be relied on. Treat VimGolf challenge content as "could not determine; assume not freely reusable" and write fresh exercises or seek permission per challenge.
- vimhjkl is reusable under MIT with attribution; the LLM-generated subset is explicitly machine-verified, but the LLM provenance may matter for copyright certainty in some jurisdictions (no human authorship) — a legal question, not resolved by sources.
- vimtutor text: covered by the Vim licence as a runtime file in the distribution; copying it verbatim into a web trainer would require honouring the modification/source-sharing clauses (or choosing the GPL v2+ option). Rewriting lessons in your own words avoids this.
- Skill tagging: vimhjkl is the only open set found that tags exercises by skill (66 named skills with categories that drive grading). VimMaster's JSON lessons and Vim Mastery's generated lessons are organised by lesson rather than by an explicit skill taxonomy, based on fetched READMEs.

### Gaps
- vimgolf.com has no terms-of-service page I could find; whether challenge authors retain copyright or grant any licence is unknown.
- Whether vimhjkl's `llm_pool.json` instances are copyrightable (LLM output) — not addressed by any source.
- Whether Vim's runtime/tutor text falls under the VIM LICENSE or has a separate status: the LICENSE file does not enumerate runtime files and the tutor file carries no licence header; "could not determine" with certainty.
- Exact lesson count and skill schema of VimMaster: README did not state a count.

## Key Question 3: Is anyone already combining real Vim/Neovim in WASM with a trainer?

### Takeaway
No. The only real-Vim-verified trainer found (vimhjkl) runs in the terminal against a locally installed Vim/Neovim; all browser trainers found use either CodeMirror-vim or custom JS engines. nvim-wasm exists as a playground (including Monaco and xterm front-ends) but is not wired to any exercise or grading system.

### Cited Findings
- vimhjkl: "learn vim from your terminal... in real vim/nvim, graded on your keystrokes" via `vim -W` — [S-Sigdel/vimhjkl](https://github.com/S-Sigdel/vimhjkl)
- nvim-wasm demos are playgrounds (nvim-wasm.pages.dev, -monaco, -xterm) with no trainer features described — [munenick.me](https://www.munenick.me/en/blog/nvim-wasm/)
- Neovim Web Playground at nvim.nry.app exists as a demo of "Neovim running in a web browser using WASM" — [nvim.nry.app](https://nvim.nry.app/)
- Browser trainers found use: CodeMirror 6 + @replit/codemirror-vim (dofy/learning-vim), custom engines (OpenVim, Vim Mastery), undisclosed (Vim Hero, vimified, vim.so, VimMaster) — see Key Question 1 citations.
- AI-benchmark projects (vimgolf-gym, ai-vim-golf-arena) run real Vim headless/Docker for verification, not in the browser — [vimgolf-gym](https://github.com/james4ever0/vimgolf-gym); [ai-vim-golf-arena](https://github.com/preyam2002/ai-vim-golf-arena)

### Inferences
- A hybrid is open territory: use codemirror-vim for the interactive lesson UI, and use real Neovim (nvim-wasm in a worker, or headless `nvim --headless`/`vim -W` at build time as vimhjkl does) only to verify pars and expected outputs offline. This gives real-Vim correctness for the answer key without shipping 8 MB to each learner.

### Gaps
- I could not find any blog post or repo describing a WASM-Neovim-backed trainer; absence of evidence, not proof of absence.

## Key Question 4 (supporting): Skill-model references — keybr, FSRS, SM-2, and academic work on command proficiency

### Takeaway
keybr's model (per-key EMA of reaction time -> confidence = target/EMA, unlock when all active keys hit confidence 1, drill the weakest "focus key") maps directly onto Vim commands as "keys"; FSRS's DSR model gives a principled schedule for revisiting a skill, with 21 trainable parameters in FSRS-6. No academic paper on modelling Vim/editor-command proficiency was found; the closest literature is the Keystroke-Level Model (1980) and Autodesk's CommunityCommands command-recommender work.

### Cited Findings
- keybr.com source licence: "GNU Affero General Public License v3.0 (AGPL-3.0)"; README: "automatically generates lessons that focus on your weakest keys", "starts with a small set of the most frequent letters", new letters "once you reach the target speed with the current ones", and it "can even predict how many more lessons you will need" — [aradzie/keybr.com](https://github.com/aradzie/keybr.com); licence file: https://github.com/aradzie/keybr.com/blob/master/LICENSE
- Relevant packages in the monorepo: `keybr-lesson`, `keybr-result`, `keybr-math`, `keybr-phonetic-model`, `keybr-generators` — [packages/](https://github.com/aradzie/keybr.com/tree/master/packages)
- Secondary summary of the algorithm (GitHub issue in another project, not keybr's own docs): confidence = targetTime / EMA(timeToType) with α = 0.1; default target 175 CPM (35 WPM); first 6 letters always included; next letter unlocks once every included key has ever hit confidence 1 (stricter "recover keys" option requires current confidence 1); focus key = included key with lowest confidence, every generated word must contain it — [pauldavidkelly/velvet issue #5](https://github.com/pauldavidkelly/velvet/issues/5)
- keybr user forum (user-reported, not author): new letters are added "once you achieve a confidence level of 1 with all your unlocked letters... you need a 35 WPM speed and a low error rate" — [Google Groups](https://groups.google.com/g/keybr/c/nWWdhRpFn1c)
- FSRS: DSR model — Stability S is "the interval when retrievability equals 90%", Difficulty D ranges 1–10; FSRS-6 forgetting curve R(t,S) = (1 + factor·t/S)^(−w20) with factor chosen so R(S,S)=90%; stability after recall S'_r = S·e^{w17(G−3+w18)}·S^{−w19}; after forgetting S'_f = w11·D^{−w12}·((S+1)^{w13}−1)·e^{w14(1−R)}; difficulty uses mean reversion; parameter counts: FSRS-6 21, FSRS-5 19, FSRS-4.5/v4 17; unlike SM-2's linear interval scaling, stability "converges to an upper limit" on overdue reviews; parameters are fit by ML on review logs (MaiMemo KDD/TKDE papers) — [awesome-fsrs wiki: The Algorithm](https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm)
- vimhjkl uses a simpler Leitner-box (1–5) scheduler with a 25-rep mastery threshold then maintenance — [vimhjkl README](https://raw.githubusercontent.com/S-Sigdel/vimhjkl/main/README.md)
- Keystroke-Level Model (Card, Moran, Newell 1980): predicts expert error-free task time by summing operator times K (keystroke), M (mental preparation), P, H, R; validated on text editors — [Wikipedia](https://en.wikipedia.org/wiki/Keystroke-level_model); [original paper PDF](https://iihm.imag.fr/blanch/ens/2010-2011/M1/EIHM/cours/1980-Card-KLM.pdf)
- CommunityCommands (Matejka, Li, Grossman, Fitzmaurice; Autodesk): item-based collaborative filtering over command usage logs to recommend unknown commands; deployed to >1100 AutoCAD users over a year; "2.1 times as many good suggestions as existing techniques" — [ACM DL](https://dl.acm.org/doi/10.1145/1970378.1970380); [deployment case study PDF](https://damassets.autodesk.net/content/dam/autodesk/www/autodesk-reasearch/Publications/pdf/deploying-communitycommands-a-software1.pdf)

### Inferences
- A Vim adaptation of keybr: treat each skill (e.g. `ciw`, `dap`, `f{char}`) as a "key"; measure per-skill latency from challenge presentation to command completion (detected via the emulator's command-done/mode-change signal), keep an EMA, define confidence = par_time/EMA (or par_keys/actual_keys), unlock new skills when all active ones reach confidence 1, and bias challenge generation toward the weakest skill. FSRS can then schedule *re-tests* of mastered skills, with grade G derived from (correct, keystrokes ≤ par, time) rather than self-report.
- The M operator from KLM is a useful framing: Vim proficiency is largely the removal of mental-preparation pauses between operator and motion; latency-based scoring captures this better than keystroke count alone.

### Gaps
- No peer-reviewed study on learning curves for modal-editor commands was found; "could not determine" whether one exists.
- keybr's exact confidence formula was only available via secondary sources; the primary `keybr-lesson` source was not fetched.
- SM-2 formula details were not re-fetched (well known; not cited here).

## Key Question 5 (supporting): Grading approaches used by existing trainers and pitfalls

### Takeaway
Every system found grades by buffer equality first and keystroke count against par second; time is a tiebreaker (VimGolf) or a tracked metric (vimified). The robust patterns are: compute par by replaying a canonical solution through the real engine (vimhjkl, VimMaster, Vim Mastery), accept any solution within a multiple of par (vimhjkl: ≤2×), and grade motion-only drills by cursor target rather than buffer.

### Cited Findings
- VimGolf: "Entries are ranked by score (lowest wins), ties broken by time"; bans plugins, predefined macros, copy/paste, `:read`, external tools — [vimgolf.com/about](https://www.vimgolf.com/about)
- vimgolf-gym: verifies by buffer equality; keystrokes in angle-bracket notation (`<Esc>`, `<NL>`), with a warning to "manually sanitize the string" — [vimgolf-gym](https://github.com/James4Ever0/vimgolf-gym)
- vimhjkl: pass = correct output AND ≤2× par keystrokes; par computed by replaying the solution through real Vim; command drills "mandate actual ex commands rather than hand-editing"; motion challenges graded by cursor position/target rather than goal buffer; challenges include `why_not` notes explaining why naive alternatives fail; buffers sized so that "simpler alternatives would fail" — [README](https://raw.githubusercontent.com/S-Sigdel/vimhjkl/main/README.md); [CONTRIBUTING](https://raw.githubusercontent.com/S-Sigdel/vimhjkl/main/CONTRIBUTING.md)
- VimMaster: golden tests replay `solution` keypresses through the engine and compare final editor state to target content — [renzorlive/vimmaster](https://github.com/renzorlive/vimmaster)
- Vim Mastery: cursor-target challenges score efficiency against an optimal path computed "via Dijkstra search through the real engine"; edit-goal challenges pass when the buffer matches the target derived from a canonical solution — [Ichihiroy/vim-mastery](https://github.com/Ichihiroy/vim-mastery)
- vimified: tracks time and keystrokes per lesson with averages across attempts — [vimified.com](https://www.vimified.com/)
- Vim Hero: "Challenges are generated dynamically, allowing you to repeat them until you achieve mastery"; proficiency per skill tracked; grading criteria not published — [vim-hero.com](https://www.vim-hero.com/)

### Inferences
- Pitfalls and mitigations suggested by the sources:
  - Multiple valid solutions: grade on buffer equality plus a par-multiple band (vimhjkl's ≤2×), not on matching a specific keystroke string.
  - Insert-mode "cheating" (retyping the target): size the buffer so retyping exceeds the par band (vimhjkl's guidance), and for Ex-command drills require that the Ex command actually ran (vimhjkl's "mandate actual ex commands").
  - Undo: a learner who undoes and retries inflates keystroke count but still reaches the buffer; treating keystrokes as a soft score within a band rather than pass/fail accommodates this, as vimhjkl does.
  - Keystroke normalisation: use VimGolf angle-bracket notation so `<Esc>`, `<CR>`, `<C-r>` count as one key each, and sanitise before counting (vimgolf-gym warning).
  - Dynamically generated challenges (Vim Hero, Vim Mastery) avoid memorisation of fixed VimGolf-style puzzles and sidestep content-licence questions.
- Detecting "command completion" in codemirror-vim for latency measurement: a transition back to normal mode with no pending operator/count is the practical signal; verify the event name against the source (see Key Question 1 gaps).

### Gaps
- How Vim Hero, vimified and vim.so grade internally is not published.
- No source discussed register/clipboard side effects or macro recording in grading.
