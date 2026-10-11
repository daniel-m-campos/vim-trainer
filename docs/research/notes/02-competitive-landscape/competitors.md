# Vim trainer competitive landscape — competitor teardown

Research date: 2026-10-11. All GitHub numbers (stars, open issues, `pushed_at`) come from the GitHub REST API on 2026-10-11 unless stated otherwise. Where a fetch failed or a number could not be confirmed it is marked **unverified**. Earlier project research already collected basic stars/pricing; these notes go deeper on features, UX, complaints and gaps, but repeat the star/pricing figures where they anchor a maintenance or positioning claim.

## Key Question 1: Factual profile of every existing Vim practice/training product

### Takeaway
The field splits into (a) paid browser courses with a fixed lesson list (Vim Hero, vim.so/LearnVim, Vimified, Vim Valley, Vimgolf.ai), (b) a single paid narrative game (Vim Adventures), (c) free browser games/drills (OpenVim, VimMaster, Vim Racer, vimtyper, VimGym, vimchi, vim.is, BobaVim), (d) in-editor Neovim/Vim plugins (vim-be-good, vim-be-better, golf.vim, hardtime.nvim, precognition.nvim, vimhjkl, Vimtutor Sequel) and (e) legacy terminal games (PacVim, vimtronner). Only two products (Vim Hero in-browser, vimhjkl in-terminal) do per-skill mastery tracking, and only vimhjkl schedules drills by weakness.

### Cited Findings

#### Vim Hero (vim-hero.com) — paid browser course, closest to the keybr model
- Teaches "motions, operators, and text objects through interactive lessons and real code challenges"; "50+ interactive lessons"; "Every lesson puts you inside a real editor. No passive reading, no videos to pause". Claims "Your proficiency in each skill is tracked so you always know where you stand and what to practice next" and that challenges are "generated dynamically, allowing you to repeat them until you achieve mastery". "Free to start". — [vim-hero.com](https://www.vim-hero.com/)
- Stats page (visible without login, 2026-10-11): "Sign in to track your progress and level up every command." Lists 76 commands in 9 categories (Basic Vim 10, Insert Like a Pro 7, Essential Motions 11, Basic Operators 7, Advanced Vertical Movement 6, Search 6, Text Objects 20, Visual Mode 3, Not Yet Covered 6). Each command has a level (lv) and XP; proficiency states shown are Started, Learning, Practiced, Fluent; commands marked "[pro]" are premium-only. — [vim-hero.com/stats](https://www.vim-hero.com/stats)
- Practice page: tabs for "movement," "insertion," "editing," "text objects," "visual"; goal modes "goals," "time," "endless"; tagline "Drill Commands Until They Stick". No text describes how challenges are selected (weak-skill targeting or random). — [vim-hero.com/practice](https://www.vim-hero.com/practice)
- Lesson UI shows "Mode: Normal" and a "0 / 10 goals" counter; sidebar sections Basic Vim, Insert Like a Pro, Essential Motions, Basic Operators, Advanced Vertical Movement, Search, Text Objects, Visual Mode; top nav Lessons / Practice / Stats. No emulator library name appears in page content. — [vim-hero.com/lessons/search-review](https://www.vim-hero.com/lessons/search-review)
- Pricing (from search snippet; the /pricing URL returned 404 on 2026-10-11, so treat the amounts as **unverified**): lifetime access at "early adopter price of $20 (regularly $50)"; "first 12 lessons available free without requiring an account, and full access to all 50+ lessons for $20"; no monthly option. — [Search result summarizing vim-hero.com](https://www.vim-hero.com/)
- Traffic signal: HN submission "VimHero teaches you how to use Vim with interactive challenges and games", 4 points, 0 comments, 2024-08-08. — [HN Algolia](https://hn.algolia.com/api/v1/search?query=vim%20hero&tags=story)
- No Reddit threads mentioning vim-hero.com surfaced in two searches (`site:reddit.com vim-hero.com`, `r/neovim vim-hero.com`). — [WebSearch, 2026-10-11]
- Third-party validation of its format: vimchi's README says it was "inspired by vim-hero's short-lesson format — small lessons of 1–4 keys, each with one practice challenge". — [gig3m/vimchi](https://github.com/gig3m/vimchi)
- Site testimonials (self-published, unverifiable): "I learned more in an hour of VimHero than I did from a week of using reference materials and tutorials." — [vim-hero.com](https://www.vim-hero.com/)

#### Vim Adventures (vim-adventures.com) — paid narrative puzzle game
- "more than 60 commands and motions" across 13 levels; HTML5 canvas; requires a physical keyboard, no mobile. Email accounts; save/load via `:w [filename]` / `:e [filename]`; statistics tracking of progress. — [vim-adventures.com](https://vim-adventures.com/)
- Pricing (2026-10-11): Game-Only License "$35" for "6 months access"; Game & Challenges License "$40" for "6 months access" including timed CTF challenges and a macro training level; group/enterprise pricing on request. — [vim-adventures.com](https://vim-adventures.com/)
- HN "Vim Tutorial as an Adventure Game", 285 points, 59 comments, 2017-06-28. Complaints: filchermcurr "It's great until you realize it costs $50. A year."; dllthomas "I'd happily pay a flat $30, or $10/yr, but $50/yr turned me away."; wjakob "licenses are limited to 6 months...paying another $25 every time just seems excessive." Praise: alex_marchant "more helpful than any other vim resource i found when beginning." — [HN 14656591](https://news.ycombinator.com/item?id=14656591)
- 2024 HN thread: spiderice "I think the creator does himself a disservice by selling 6 month licenses rather than lifetime."; bravetraveler "Presenting a subscription is just a little off-putting. How deep does the hole go, you know?"; emgeee "+1 to vim-adventures, excellent game and well worth the money if you're a committed power user". — [HN 40198745](https://news.ycombinator.com/item?id=40198745)
- Creator's stated reason for 6-month licences (per HN 2015 thread summary): legal/refund exposure if the site shuts down; said the limit "will not actually be enforced" (search-snippet paraphrase; **unverified** direct quote). — [HN 9250490](https://news.ycombinator.com/item?id=9250490)
- Trustpilot: 3.3/5 from 1 review (2 stars, 2025-10-06, D.T., Bulgaria): "I spent $40 on VIM Adventures, and it wasn't worth it. The early levels are great for learning basic VIM commands, but the later ones turn into overcomplicated puzzles." Also cites 6-month limit and frequent re-logins. — [Trustpilot](https://www.trustpilot.com/review/vim-adventures.com)
- Product Hunt: 4.5/5 from 2 reviews, 88 upvotes. Roland Haller: "Awesome concept, I'd love to be able to bring the move optimization advice into my actually coding environment." — [Product Hunt](https://www.producthunt.com/products/vim-adventures/reviews)
- dev.to critique: calls the price "daylight robbery even *Electronic Arts* would be ashamed of", says the game has "the graphics and gameplay quality of a free itch.io game", that it is online-only with server-side game logic, and the author built a free GPL alternative "Vim: BackSpace" in response. — [dev.to](https://dev.to/mousepotatodoesstuff/vim-backspace-because-vim-adventures-isnt-worth-the-license-cost-338)
- Repeated low-score HN resubmissions 2020–2024 (26, 4, 4, 2, 2, 1 points). — [HN Algolia](https://hn.algolia.com/api/v1/search?query=learn%20vim%20game&tags=story&hitsPerPage=50)

#### OpenVim (openvim.com) — free browser tutorial, custom JS engine
- Sections: Tutorial, Practice sandbox, Development; virtual keyboard highlights the key to press; issues link to GitHub; no pricing, no accounts, no progress tracking visible. — [openvim.com](https://www.openvim.com/)
- "based on a custom engine that interprets vim commands. Everything runs inside the browser"; originally published 2011. — [WebSearch summary citing egaga/openvim and i-programmer](https://github.com/egaga/openvim)
- Repo egaga/openvim: 636 stars, 75 forks, 70 open issues, created 2015-04-16, pushed 2026-07-29. — [GitHub API](https://api.github.com/search/repositories?q=repo:egaga/openvim)

#### Vim Genius (vimgenius.com) — free timed flashcards, effectively dead
- "timed flashcard-style game designed to make you faster in Vim. It's free and you don't need to sign up"; lessons include arglist, basic motions, macros, copy & paste, Rails Vim. — [Class Central listing](https://www.classcentral.com/course/independent-vimgenius-203194)
- Repo vicramon/vimgenius: 21 stars, 25 open issues, created 2013-06-21, pushed 2023-05-04. — [GitHub API](https://api.github.com/search/repositories?q=repo:vicramon/vimgenius)
- On 2026-10-11 both `https://www.vimgenius.com/` and `http://vimgenius.com/` failed with a TLS error: "Host: www.vimgenius.com. is not in the cert's altnames: DNS:*.herokuapp.com" (i.e. the Heroku app no longer has a valid cert for the custom domain). — [WebFetch, 2026-10-11]

#### vim-be-good (ThePrimeagen) — free Neovim plugin, unmaintained
- Games: relative (delete the "DELETE ME" line via relative jumps), ci{, whackamole, plus words/hjkl; "difficulty only works on a few games for now"; author: "The code is a heaping pile of awfulness. It was developed live on Twitch". Needs Neovim 0.5+. Docker image offered. — [GitHub README](https://github.com/ThePrimeagen/vim-be-good)
- 4,572 stars, 184 forks, 52 open issues, created 2020-05-10, **last push 2024-12-05**. — [GitHub API](https://api.github.com/search/repositories?q=repo:ThePrimeagen/vim-be-good)
- Open issues include: "vim.schedule callback error" (2026-06-16), "Regex Practice" (2025-04), "Add option to select number of rounds" (2024-07), "Give more hints please" (2023-04), "VSCode emulation using ncurses" (2023-09), "E492: Not an editor command: VimBeGood" (2022-11), Docker-on-M1 failures; "make a website out of this" (2023-10, closed). Themes: crashes, install/compat, more games, hints. No stats/progress feature exists or is requested by name. — [GitHub issues](https://github.com/ThePrimeagen/vim-be-good/issues?q=is%3Aissue)

#### vim-be-better (szymonwilczek) — fork, 25+ games, short burst of activity
- "25+ Different Games across 8 categories" (Navigation, Text Objects, Substitution, Formatting, Numbers, Advanced, Mixed incl. "vim-golf", Classic); difficulty noob → easy → medium → hard → nightmare → tpope; Neovim 0.8+; README does not document any statistics or progress tracking. — [GitHub README](https://github.com/szymonwilczek/vim-be-better)
- 112 stars, 4 forks, 0 open issues, created 2025-06-18, pushed 2025-06-21 (three days of commits, then nothing). — [GitHub API](https://api.github.com/search/repositories?q=repo:szymonwilczek/vim-be-better)

#### vimhjkl (S-Sigdel) — terminal, real Vim, spaced repetition, weakest-skill practice
- Edits happen in real vim/nvim; goal shown in a read-only split. "Keystrokes are captured with `vim -W` and scored on correctness and efficiency against a verified par." Pass requires correctness and ≤2× the benchmark keystroke count; ex-command drills reject hand-editing. — [GitHub README](https://github.com/S-Sigdel/vimhjkl)
- Mastery model: per-skill Leitner box levels 1–5 for scheduling and unlocks, rep counter to 25 then maintenance schedule; harder tiers unlock as lower tiers are mastered. Modes: Learn, Blind, Practice ("Focuses on weakest skills with retries until passing"), Grind, Review. 66 skills, 230 challenges. Install via Homebrew tap, AUR, or uv. MIT, stdlib only. No roadmap. — [GitHub README](https://github.com/S-Sigdel/vimhjkl)
- 544 stars, 13 forks, 2 open issues, created 2026-06-01, pushed 2026-07-03. — [GitHub API](https://api.github.com/search/repositories?q=repo:S-Sigdel/vimhjkl)

#### Vimtutor Sequel (micahkepe) — text lessons in real Vim
- "advanced Vim tutor lessons"; `brew install vimtutor-sequel`; manual clone for Windows/Linux; MIT; CHANGELOG and version check from v1.2.3. — [GitHub README](https://github.com/micahkepe/vimtutor-sequel)
- 564 stars, 9 forks, 0 open issues, created 2024-08-02, pushed 2026-02-01. — [GitHub API](https://api.github.com/search/repositories?q=repo:micahkepe/vimtutor-sequel)

#### VimMaster (renzorlive/vimmaster, vim-master.com) — free browser game, local-only progress
- "in-browser game that teaches core Vim motions and editing commands"; JSON-driven lessons; XP, combos, badges/achievements; "Practice Arena" time-limited speed challenges; "Cheat Mode" reference; local save with import/export of progress; no account system; V3 roadmap is UX polish with "public beta launching soon". — [GitHub README](https://github.com/renzorlive/vimmaster)
- "16 short, progressive levels, where the player edits text inside a simulated Vim editor"; "just open `index.html`". — [WebSearch summary citing freetoolonline/devtalk](https://devtalk.com/t/vim-master-is-a-lightweight-in-browser-game-that-teaches-core-vim-motions-and-editing-commands-through-short-focused-levels/212582)
- 1,713 stars, 71 forks, 7 open issues, created 2025-08-27, pushed 2026-07-16. — [GitHub API](https://api.github.com/search/repositories?q=repo:renzorlive/vimmaster)
- vim-master.com returned HTTP 530 on two fetch attempts on 2026-10-11 (Cloudflare origin error); HN Algolia has no indexed story for it (nbHits 0) despite a @betterhn50 tweet. — [WebFetch; HN Algolia](https://hn.algolia.com/api/v1/search?query=%22vim%20master%22%20game&tags=story)

#### vim.so → LearnVim (learnvim.com) — paid browser course, Ace editor
- vim.so now 301-redirects to learnvim.com. — [WebFetch, 2026-10-11](https://www.vim.so/)
- "10 interactive lessons"; "$35" "Pay once, own it forever"; "2,082 engineers have learned to love vim with our no-BS approach"; sign-in; attempt counter and averages shown per exercise; copyright 2025; refund policy. — [learnvim.com](https://www.learnvim.com/)
- Show HN (2021-01), 667 points, 280 comments, author CoffeePython (Kenneth Cassel); launched at one-time $15 lifetime. Complaints: ahussain "doesn't go much beyond basics"; tyingq "`:5d` doesn't delete line #5" (Ace Editor vim bindings, not real Vim); rav: backspace behaves unlike Vim; several said lesson list not visible before purchase; blangk: demo lesson "meaningless". Praise: one-time pricing; windexh8er bought after testing with an 8-year-old. Creator said revenue sponsors FastAPI at $250/month. — [HN 25846347](https://news.ycombinator.com/item?id=25846347)
- Later HN thread: a paying user "found it helpful for learning basic commands but wished it had more exercises"; another commenter called vim.is "simply ripping off the original site". — [HN 29431946](https://news.ycombinator.com/item?id=29431946)

#### Vimified (vimified.com) — paid browser course with keystroke/time stats
- 8 chapters (Survival Essentials → macros/dot command); "$20" "Lifetime Access"; stats: Total Time, Fastest Time, Fewest Keystrokes, Average Time, Average Keystrokes with targets such as "Get to 300s" / "Get to 8s"; login; badge "FEATURED ON Hacker News" 344 points. — [vimified.com](https://www.vimified.com/)
- Show HN 2022-07-09, 344 points, 253 comments (author Silica6149). Complaints: mastermedo "might be in a way too early stage to justify the pricing" (8 chapters, 34 lessons); johncoltrane "learning Vim has nothing to do with muscle memory... `:help user-manual` is easy, built-in, and goes way beyond this. And it's free." Requests: xavdid wanted "how to browse the directory, switch between files, open multiple panels"; giansegato wanted vim-surround and .vimrc content. — [HN 32034625](https://news.ycombinator.com/item?id=32034625)
- Earlier Show HN 2022-06-22: 12 points, 10 comments. — [HN Algolia](https://hn.algolia.com/api/v1/search?query=vimified&tags=story)

#### VimGolf (vimgolf.com) — free keystroke-golf leaderboard, real Vim via CLI
- Homepage 2026-10-11: "621 challenges", "512,014 total entries", "45,161 active golfers"; submit via `gem install vimgolf` / `vimgolf put`; CLI v0.5.0; accounts required to submit; free. — [vimgolf.com](https://www.vimgolf.com/)
- CLI repo igrigorik/vimgolf: 780 stars, 42 open issues, created 2010-12-28, pushed 2024-07-04. — [GitHub API](https://api.github.com/search/repositories?q=repo:igrigorik/vimgolf)
- Launch HN 2010-12-28: 178 points, 79 comments. — [HN Algolia](https://hn.algolia.com/api/v1/search?query=vimgolf&tags=story&hitsPerPage=50)
- Reliability: users reported "We're sorry, but something went wrong" / 500 errors around Aug–Sep 2025 (search-snippet; **unverified** primary source). Historic issue #124 "Unable to golf" shows recurring client/host connectivity confusion across 2013–2014. — [issue #124](https://github.com/igrigorik/vimgolf/issues/124)

#### Vimgolf.ai — paid browser levels, real Neovim in a web container
- Show HN 2026-07-29, 36 points, 26 comments, author nickandbro. Progressive level map; compares your keystrokes to bot entries; "$25 for 6-month access" (author said a lifetime option might come if demanded); runs in a web container rather than an emulator. Complaints: BoxwoodSeed "Uses unholy amounts of CPU making my laptop's fans spin out of control. Editing is very slow"; einpoklum "overwhelming and visually tiring for me, especially with the animation"; pluc got a 403 white screen on Firefox/Mullvad; NewsaHackO called the model "SaaS slop". Requests: Enter to advance (bhkdotdev), Helix support (nylonstrung), a real step-by-step tutorial mode (Hugsbox). — [HN 49095143](https://news.ycombinator.com/item?id=49095143)
- 72 skills; first 4 skills free without account; free account unlocks "basics zone"; paid $25/6 months; "race against a vimbot on keystroke efficiency"; "real nvim". — [daily.dev listing](https://daily.dev/posts/vimgolf-ai-cnxen6ryw)
- Direct fetches of vimgolf.ai and /pricing returned only the page title (JS-rendered), so on-site pricing text is **unverified** beyond HN/daily.dev. — [vimgolf.ai](https://vimgolf.ai/)

#### golf.vim (vuciv/golf) — in-editor daily VimGolf, 2025
- Daily challenge fetched from an external API (`:Golf today`, by difficulty, date or tag); par value; success screen with leaderboard of "player ranks, keystroke counts, and solution times"; MIT; web interface for submitting challenges. 297 stars, 6 forks, 9 open issues, 38 commits (repo page, 2026-10-11). Last push date **unverified** (not returned by the batched API call). — [GitHub README](https://github.com/vuciv/golf)
- Show HN 2025-04-13: 3 points, 1 comment. Scores labelled Eagle/Birdie/Bogey. — [HN 43674438](https://news.ycombinator.com/item?id=43674438)

#### hardtime.nvim (m4xshen) — habit-breaker with report, active
- Blocks repeated keys within a time window, hints better motions (e.g. "Use `ct(` instead of `dt(i`"), "block" vs "hint" modes, mouse disabling, insert-idle exit, log at `~/.local/state/nvim/hardtime.nvim.log`. — [GitHub README](https://github.com/m4xshen/hardtime.nvim)
- `:Hardtime report` lists most frequently triggered hints; a user quoted: the "Hardtime Report" "really shows just how pervasive bad habits are". — [WebSearch summary](https://www.kishorenewton.com/posts/improve_nvim_with_hardtime/)
- 3,857 stars, 11 open issues, created 2023-04-24, pushed 2026-10-02. — [GitHub API](https://api.github.com/search/repositories?q=repo:m4xshen/hardtime.nvim)
- Show HN 2025-05: 214 points, 86 comments. mnurzia: "after the (short) initial period of frustration with the delays I was able to start really flying with vim motions." yegle: disappointed it is Neovim-only. Long debate whether `jjjj` is actually a bad habit (perrygeo: repeated keys enable flow). Alternatives pushed: vim-sneak, leap.nvim, flash.nvim. — [HN 44020734](https://news.ycombinator.com/item?id=44020734)

#### precognition.nvim (tris203) — motion hints, active
- Virtual-text and gutter hints for available motions, text-object hints, f/F targets, peek/toggle; 1,387 stars, 7 open issues, created 2023-12-26, pushed 2026-10-11. No training/scoring component. — [GitHub README](https://github.com/tris203/precognition.nvim); [GitHub API](https://api.github.com/search/repositories?q=repo:tris203/precognition.nvim)

#### vscodevimacademy (kaisunc) — VS Code game, abandoned 2022
- "10 sets of tasks as quickly with as little key presses as possible... performance is logged per task"; level text and keys randomly generated; categories Motions, Actions-Horizontal, Actions-Vertical, Surrounds, UI; requires VSCodeVim. — [GitHub README](https://github.com/kaisunc/vscodevimacademy)
- Marketplace: 13,682 installs, 3/5 stars (12 ratings), v1.1.9, last updated 2022-06-02. Repo: 78 stars, 8 open issues, pushed 2023-10-02. — [VS Marketplace](https://marketplace.visualstudio.com/items?itemName=kaisun.vscodevimacademy); [GitHub API](https://api.github.com/search/repositories?q=repo:kaisunc/vscodevimacademy)

#### "Learn Vim" VS Code extension (vintharas) — lesson docs inside VS Code, abandoned 2022
- 331,524 installs, 5/5 (65 ratings), v0.0.28, last updated June 2022; lessons on basics, motions/operators, insert, visual, text objects, registers, undo; "still a work in progress"; free. — [VS Marketplace](https://marketplace.visualstudio.com/items?itemName=vintharas.learn-vim)

#### chronicles-of-vimia (RaphaelKMandel) — falling-text arcade, WIP
- Python + Arcade, pynvim; only Arcade mode exists; planned Campaign mode and "training mode where puzzles are generated to practice specific motions or commands"; 45 stars, pushed 2025-05-29. — [GitHub README](https://github.com/RaphaelKMandel/chronicles-of-vimia); [GitHub API](https://api.github.com/search/repositories?q=repo:RaphaelKMandel/chronicles-of-vimia)

#### PacVim (jmoon018) — terminal Pac-Man, legacy
- ~20 commands (hjkl, w/W/e/E/b/B, $ 0 ^ gg G #G); unresolved out-of-bounds bugs in TODO; 3,326 stars, 23 open issues, pushed 2024-03-23 (created 2014). HN 2018 article hit 296 points / 52 comments. — [GitHub README](https://github.com/jmoon018/PacVim); [GitHub API](https://api.github.com/search/repositories?q=repo:jmoon018/PacVim); [HN Algolia](https://hn.algolia.com/api/v1/search?query=learn%20vim%20game&tags=story&hitsPerPage=50)

#### VimKata (iOS/macOS/visionOS app)
- 7 levels, 135 exercises using JS/Python/HTML/CSS/Markdown; watch animation then practice on an on-screen keyboard; grade "S (perfect) to D (keep practicing)" with "the optimal solution alongside yours"; "A COMPANION, NOT A REPLACEMENT"; free with "Unlock All Levels $4.99" (first three levels free); 5.0 from 4 ratings; v1.1.2 released March 31 (year not shown; **unverified**, app ID suggests 2026); developer Andrii Zborovskyi. — [App Store](https://apps.apple.com/app/vimkata-learn-vim-visually/id6759241557)

#### vimtronner (carbonfive) — multiplayer TRON, abandoned
- "a multiplayer, realtime, command-line game that teaches you the core vim keys" (hjkl + INSERT-mode walls); Node.js; GPL-2.0; 313 stars, pushed 2018-11-21. HN 2014: 6 points. — [GitHub README](https://github.com/carbonfive/vimtronner); [GitHub API](https://api.github.com/search/repositories?q=repo:carbonfive/vimtronner)

#### Additional products found
- **Vim Racer (vim-racer.com)** — free; "navigate to every target as quickly as possible"; shows elapsed time, "Navigations: 0/12", NPM (navigations per minute); leaderboards show the key sequence used; no full accounts ("rate limiting keeps the leaderboard from filling up"); donations; "Built by Shaun Brazzoni". Show HN 2024-08-26: 351 points, 86 comments; complaints: impossible 1-second leaderboard times (cheating), relative-numbers default confusion ("I just thought it was broken." — dools), `/term/e` unsupported, deletion crashes; requests: keystroke-minimisation ranking, configurable settings, colourblind-friendly targets, replays. — [vim-racer.com](https://vim-racer.com/); [HN 41347051](https://news.ycombinator.com/item?id=41347051)
- **vimtyper (vimtyper.dev)** — "a free typing game for vim users"; modes Motions ("Land the cursor on it in as few keystrokes as you can"), Edit ("delete or change a word, join or duplicate lines, indent, change case, clear inside quotes, search & replace"), Type (WPM/accuracy), Tutor (full vimtutor); live hint of shortest key sequence; 15/30/60-second rounds; settings choose edit types; no accounts or stats visible; emulator library not disclosed; © 2026. — [vimtyper.dev](https://www.vimtyper.dev/)
- **VimGym (vimgym.dev / oller/vimgym)** — React 19 + `@replit/codemirror-vim` (CodeMirror 6) + Supabase; 33 challenges in 6 categories; "vimsplain" motion log explains keystrokes as chips; anonymous completion submissions with global best, percentile and score distribution; per-category progress bars; 4 stars, created 2025-12-11, pushed 2026-10-06. Site marketing says "premium features that unlock additional advanced exercises and detailed progress tracking" and "visual progress charts", but the repo documents no pricing — **conflict; premium tier unverified**. — [GitHub](https://github.com/oller/vimgym); [vimgym.dev via search](https://www.vimgym.dev/)
- **vimchi (vimchi.dev / gig3m/vimchi)** — "a Vim engine written from scratch in TypeScript" (modes, operators, text objects, registers, macros, dot-repeat, undo, Vim regex, ex commands, splits, quickfix, folds) plus emulations of mini.surround, mini.ai, treesitter-textobjects, flash.nvim, telescope, neo-tree, gitsigns, lazygit, grug-far, snippets/completion; arrow keys disabled; Go backend with GitHub OAuth and SQLite sync of lesson runs, localStorage fallback; MIT; 0 stars, created 2026-09-28, pushed 2026-10-06. — [GitHub](https://github.com/gig3m/vimchi)
- **BobaVim (bobavim.com)** — browser game, solo + 1v1 multiplayer racing, leaderboard, HTML/CSS/JS + Go; tested with 42 Heilbronn students; HN 2025-07-27: 4 points, 1 comment; no pricing stated. — [HN 44705127](https://news.ycombinator.com/item?id=44705127)
- **vim.is** — 32 browser exercises (motions, insert, delete, yank, search/replace, g command); no setup; an HN commenter called it a clone of vim.so. — [WebSearch summary](https://vim.is/); [HN 29431946](https://news.ycombinator.com/item?id=29431946)
- **Vim Valley (vimvalley.com)** — browser exercise engine, 10 sections, first 7 exercises free, "$39" lifetime, by Muse In Motion, LLC; no progress tracking described. — [vimvalley.com](https://vimvalley.com/)
- **KeyCombiner (keycombiner.com/vim)** — flashcard trainer with "spaced repetition algorithms"; public Vim collection of 210 shortcuts; free trial of 20 random Vim shortcuts; saves "detailed statistics"; paid tier price not on page (**unverified**). Trains shortcut recall, not editing in a buffer. — [keycombiner.com/vim](https://keycombiner.com/vim/)
- **vim-mastery (Ichihiroy)** — "free, browser-based interactive Vim trainer. 49 lessons... simulated modal editor... no install, no signup"; 2 stars, created 2026-07-12, pushed 2026-07-22. — [GitHub API](https://api.github.com/search/repositories?q=repo:Ichihiroy/vim-mastery)
- **hjkl (hjkl.pinkpixel.dev)** — 17 lessons, 124 hand-written drills with keystroke par, "VS Code style habit each one replaces", optional local Gemma coach via WebGPU/Transformers.js. — [dev.to](https://dev.to/sizzlebop/i-built-my-husband-a-vim-trainer-with-a-gemma-coach-that-runs-in-the-browser-5fmh)
- **Vimurai** — Rust CLI "dojo" with spaced repetition and gamification, last updated 2026-02-05 (search-snippet only; stars **unverified**). — [WebSearch summary](https://github.com/topics/vim-motions?o=asc&s=updated)
- **vimtype (HotelBudapest)** — "A Vim-first terminal typing game inspired by Monkeytype"; 0 stars, created 2026-09-08. — [GitHub API](https://api.github.com/search/repositories?q=repo:HotelBudapest/vimtype)
- **Vim Snake (vimsnake.com)** — free browser snake with hjkl + INSERT mode; "Sign in to save your score!"; by @patmood. — [vimsnake.com](https://vimsnake.com/)
- **Legacy/other**: vim-man (162 stars, pushed 2025-05-20), A-Vim-Story (9 stars, pushed 2019), Vim-Katas (597 stars, exercise text files from Practical Vim, pushed 2025-03-30), VimInteractive (vim-interactive-tutor.vercel.app), VimDojo (vimdojo.tech) — details **unverified**. — [GitHub API](https://api.github.com/search/repositories?q=repo:ozankasikci/vim-man+repo:coditva/A-Vim-Story+repo:adomokos/Vim-Katas)

### Inferences
- Emulator landscape: at least four distinct approaches are in use — Ace vim bindings (vim.so/LearnVim), CodeMirror 6 `@replit/codemirror-vim` (VimGym), custom from-scratch JS/TS engines (OpenVim, vimchi, probably VimMaster and Vim Hero — the latter two undisclosed), and real Vim/Neovim (VimGolf CLI, vimhjkl, golf.vim, hardtime, Vimgolf.ai's web container). Vimgolf.ai is the only browser product running real Neovim and it drew the only CPU/latency complaints, which suggests the real-Vim-in-browser route costs UX.
- Pricing has converged on one-time lifetime ($15–$39) after years of HN hostility to Vim Adventures' 6-month licence; Vimgolf.ai's choice of a 6-month $25 model in 2026 drew the same "SaaS slop" reaction within hours.
- Progress stats are shallow where they exist: Vimified exposes five aggregate numbers, vscodevimacademy logs speed/keypresses per task but shows no trend, VimGym shows percentile per challenge. Only Vim Hero exposes a per-command level/XP ladder in the browser.

#### Feature matrix (derived from the cited findings above; "?" = not determinable from sources)

| Product | Form | Engine | Price | Accounts/sync | Per-skill tracking | Adapts to weak skills | Charts over time | Maintained (last signal) |
|---|---|---|---|---|---|---|---|---|
| Vim Hero | browser lessons + practice | undisclosed browser emulator | free 12 lessons; $20 lifetime (unverified) | yes (login for stats) | yes: 76 commands, lv/XP, 4 states | claims "what to practice next"; selection algorithm undocumented | ? | active (site live Oct 2026) |
| Vim Adventures | browser RPG | HTML5 canvas, server-side logic | $35 / $40 per 6 months | yes | no (level progress) | no | no | active (site live) |
| OpenVim | browser tutorial | custom JS engine | free | no | no | no | no | repo pushed 2026-07 |
| Vim Genius | browser flashcards | n/a | free | no | no | no | no | dead (TLS broken, repo 2023) |
| vim-be-good | nvim plugin | real Neovim | free | n/a | no | no | no | last push 2024-12 |
| vim-be-better | nvim plugin | real Neovim | free | n/a | no | no (manual difficulty) | no | 3 days in Jun 2025 |
| vimhjkl | terminal CLI | real vim (`-W`) | free | local only | yes: Leitner box per skill, reps | yes: Practice mode = weakest skills | no charts | pushed 2026-07 |
| Vimtutor Sequel | vim text lessons | real Vim | free | no | no | no | no | pushed 2026-02 |
| VimMaster | browser game | simulated editor (JSON-driven) | free | no (local save, import/export) | XP/badges only | no | no | pushed 2026-07; site 530 on 2026-10-11 |
| vim.so / LearnVim | browser course | Ace vim bindings | $35 lifetime | yes | attempt count/avg per exercise | no | no | site live, © 2025 |
| Vimified | browser course | web editor (unspecified) | $20 lifetime | yes | 5 aggregate stats + targets | no | no | site live |
| VimGolf | CLI + leaderboard | real Vim | free | yes | no | no | no | site live; CLI pushed 2024-07 |
| Vimgolf.ai | browser level map | real nvim in web container | 4 skills free; $25 / 6 months | yes | 72 skills with bot comparison | no | ? | launched 2026-07 |
| golf.vim | vim plugin, daily | real Vim | free | leaderboard | no | no | no | 2025 (push date unverified) |
| hardtime.nvim | nvim plugin | real Neovim | free | local log | habit report by hint frequency | hints only | no | pushed 2026-10-02 |
| precognition.nvim | nvim plugin | real Neovim | free | n/a | no | no | no | pushed 2026-10-11 |
| vscodevimacademy | VS Code ext | VSCodeVim | free | local | speed+keypresses per task | no | no | updated 2022-06 |
| Learn Vim (VS Code) | VS Code ext | VSCodeVim | free | no | no | no | no | updated 2022-06 |
| chronicles-of-vimia | desktop arcade | pynvim | free | no | no | planned | no | pushed 2025-05 |
| PacVim | terminal | own | free | no | no | no | no | pushed 2024-03 |
| VimKata | iOS/macOS | on-screen keyboard | free + $4.99 | ? | S–D grade per exercise | no | no | v1.1.2 2026 (unverified yr) |
| vimtronner | terminal multiplayer | own | free | no | no | no | no | pushed 2018 |
| Vim Racer | browser race | own | free/donations | pseudo (username) | time + NPM per race | no | no | active 2024–? |
| vimtyper | browser timed drills | undisclosed full emulation | free | none visible | none visible | no (configurable) | no | © 2026 |
| VimGym | browser challenges | @replit/codemirror-vim | free (premium claimed, unverified) | anon submissions, Supabase | per-category completion, percentile | no | "progress charts" claimed, unverified | pushed 2026-10-06 |
| vimchi | browser lessons | custom TS engine | free, MIT | GitHub OAuth + SQLite sync | lesson runs | no | no | pushed 2026-10-06 |
| KeyCombiner | flashcards | n/a | free trial; paid (unverified) | yes | per-shortcut stats | spaced repetition | "detailed statistics" | active |

### Gaps
- Vim Hero: emulator library, pricing page (404), the actual algorithm behind "what to practice next", and whether Stats shows historical charts — none determinable without an account. No third-party reviews found anywhere (HN 4 points; nothing on Reddit via search).
- Vimgolf.ai: on-site pricing/feature text not retrievable (JS-only render); user counts unknown.
- VimMaster hosted site unreachable (HTTP 530) on research date; level count (16) comes from a secondary source.
- No SimilarWeb-style traffic estimates were obtained for any product; all usage signals are GitHub stars, marketplace installs, self-reported counters (VimGolf, LearnVim) or HN scores.
- Vim Genius site content could not be fetched (TLS failure), so lesson counts are unknown.
- Reddit: `site:reddit.com` searches returned no Reddit pages at all (search engine limitation), so Reddit sentiment is not covered; HN is the main community source here.

## Key Question 2: Does any product adapt drills to weak skills or chart per-skill speed/accuracy over time (keybr-style)? How well?

### Takeaway
Only vimhjkl truly adapts (Leitner scheduling plus a "weakest skills" practice mode), and it is a terminal tool with no charts and no sync. Vim Hero is the only browser product with a per-command proficiency ladder, but it does not document how practice picks challenges or whether it charts speed/accuracy over time. Nothing found matches keybr's combination of per-skill speed+accuracy time series and automatic drill weighting in the browser.

### Cited Findings
- vimhjkl: "Each skill uses a Leitner box (levels 1–5) for scheduling and unlock progression, plus a rep counter toward 25 total reps"; Practice mode "Focuses on weakest skills with retries until passing"; grading is correctness plus keystrokes vs par (≤2×). No time-series charts described; terminal only; progress is local. — [GitHub README](https://github.com/S-Sigdel/vimhjkl)
- Vim Hero: "Your proficiency in each skill is tracked so you always know where you stand and what to practice next"; stats page lists 76 commands with lv/XP and states Started/Learning/Practiced/Fluent; practice page offers category tabs and goals/time/endless but "lacks detailed explanatory text about challenge selection methodology, whether skills are adaptively chosen, or what specific metrics are tracked". — [vim-hero.com](https://www.vim-hero.com/); [stats](https://www.vim-hero.com/stats); [practice](https://www.vim-hero.com/practice)
- hardtime.nvim reports frequency of triggered hints (`:Hardtime report`) — a weakness report, but it does not generate drills. — [GitHub README](https://github.com/m4xshen/hardtime.nvim)
- KeyCombiner applies spaced repetition to shortcut flashcards with "detailed statistics", but it is recall of key names, not editing in a buffer. — [keycombiner.com/vim](https://keycombiner.com/vim/)
- Vimified tracks Total Time, Fastest Time, Fewest Keystrokes, Average Time, Average Keystrokes with static targets. — [vimified.com](https://www.vimified.com/)
- vscodevimacademy: "performance is logged per task based on how fast they performed and how many keypresses they used" with randomly generated level text; no adaptivity. — [GitHub README](https://github.com/kaisunc/vscodevimacademy)
- VimGym: percentile rank and score distribution per challenge; marketing claims "visual progress charts" and "identify which exercises need more practice" (**unverified**, not in repo docs). — [GitHub](https://github.com/oller/vimgym)
- Vimgolf.ai: per-level comparison to "vimbot" keystroke counts across 72 skills; no adaptivity mentioned by author or commenters. — [daily.dev](https://daily.dev/posts/vimgolf-ai-cnxen6ryw); [HN 49095143](https://news.ycombinator.com/item?id=49095143)
- vim-be-good: "difficulty only works on a few games for now"; no stats. — [GitHub README](https://github.com/ThePrimeagen/vim-be-good)
- chronicles-of-vimia plans but has not built "a training mode where puzzles are generated to practice specific motions or commands". — [GitHub README](https://github.com/RaphaelKMandel/chronicles-of-vimia)
- vimtyper gives a live "hint showing the shortest possible key sequence to the current target" and configurable drill types, i.e. user-configured rather than adaptive. — [vimtyper.dev](https://www.vimtyper.dev/)

### Inferences
- The two products with any adaptivity (vimhjkl, KeyCombiner) are spaced-repetition schedulers borrowed from flashcard apps; neither models speed/accuracy per motion as a continuous metric the way keybr does for letters.
- Vim Hero's XP/level ladder is a gamification layer rather than a measured-performance model (XP accrues from completing goals, not from keystroke efficiency or latency) — inferred from the lv/xp presentation; not confirmed.
- Nobody charts per-skill latency (time from prompt to correct keystroke) or keystroke-efficiency ratio over sessions. That is the empty slot.

### Gaps
- Could not log into Vim Hero to see whether Stats has historical charts or whether Practice weights weak commands.
- VimGym's premium "progress charts" could not be confirmed.

## Key Question 3: What do users complain about most?

### Takeaway
Ranked by frequency across HN threads and review sites: (1) time-limited licences / subscription pricing (Vim Adventures, Vimgolf.ai); (2) "too basic / stops too early" and price not justified by lesson count (vim.so, Vimified); (3) "not real Vim" emulator inaccuracies (vim.so/Ace, Vim Racer); (4) performance and browser bugs (Vimgolf.ai CPU, Vim Racer crashes, Vim Adventures re-login); (5) puzzle design that stops teaching Vim (Vim Adventures later levels); (6) plugin install/crash issues (vim-be-good). Lack of progress tracking is rarely complained about explicitly — users ask for it indirectly via "more exercises", "practice mode", and "bring the advice into my real editor".

### Cited Findings
- Licence/pricing: "It's great until you realize it costs $50. A year." (filchermcurr); "paying another $25 every time just seems excessive." (wjakob) — [HN 14656591](https://news.ycombinator.com/item?id=14656591); "does himself a disservice by selling 6 month licenses rather than lifetime" (spiderice, 2024) — [HN 40198745](https://news.ycombinator.com/item?id=40198745); Vimgolf.ai subscription called "SaaS slop" (NewsaHackO) — [HN 49095143](https://news.ycombinator.com/item?id=49095143); Vim Adventures price "daylight robbery even *Electronic Arts* would be ashamed of" — [dev.to](https://dev.to/mousepotatodoesstuff/vim-backspace-because-vim-adventures-isnt-worth-the-license-cost-338)
- Too basic / stops early: vim.so "doesn't go much beyond basics" (ahussain), course sections hidden before purchase — [HN 25846347](https://news.ycombinator.com/item?id=25846347); Vimified "too early stage to justify the pricing" with 34 lessons (mastermedo); "`:help user-manual`... goes way beyond this. And it's free." (johncoltrane) — [HN 32034625](https://news.ycombinator.com/item?id=32034625); a vim.so buyer "wished it had more exercises" — [HN 29431946](https://news.ycombinator.com/item?id=29431946)
- Not real Vim / emulator inaccuracy: "`:5d` doesn't delete line #5" (tyingq), backspace behaviour wrong (rav) — [HN 25846347](https://news.ycombinator.com/item?id=25846347); Vim Racer `/term/e` unsupported, relative numbers "I just thought it was broken." (dools), deletion crashes — [HN 41347051](https://news.ycombinator.com/item?id=41347051); HN commenters argued learning outside Vim is "pointless" — [HN 29431946](https://news.ycombinator.com/item?id=29431946)
- Performance/bugs: Vimgolf.ai "unholy amounts of CPU... Editing is very slow" (BoxwoodSeed), 403 white screen on Firefox (pluc), animation "visually tiring" (einpoklum) — [HN 49095143](https://news.ycombinator.com/item?id=49095143); Vim Adventures "you often have to re-login and reload your saved game" — [Trustpilot](https://www.trustpilot.com/review/vim-adventures.com); vimgolf.com 500 errors Aug–Sep 2025 (unverified) — [issitedownrightnow](https://issitedownrightnow.com/status/vimgolf.com)
- Puzzle design drifting away from Vim: "the later ones turn into overcomplicated puzzles. Instead of building VIM muscle memory, you end up stuck figuring out how to solve the puzzles themselves" — [Trustpilot](https://www.trustpilot.com/review/vim-adventures.com)
- Plugin friction: vim-be-good issues "E492: Not an editor command: VimBeGood", Docker-on-M1, Mason/Packer install failures, "vim.schedule callback error" (2026) — [GitHub issues](https://github.com/ThePrimeagen/vim-be-good/issues?q=is%3Aissue); hardtime.nvim "only supports Neovim while claiming to teach Vim mastery" (yegle) — [HN 44020734](https://news.ycombinator.com/item?id=44020734)
- Leaderboard integrity: Vim Racer 1-second times flagged as scripted — [HN 41347051](https://news.ycombinator.com/item?id=41347051)
- Transfer to real work: "I'd love to be able to bring the move optimization advice into my actually coding environment." — [Product Hunt](https://www.producthunt.com/products/vim-adventures/reviews)
- Over-strictness debate: hardtime's blocking of `jjjj` contested — "repeated keys enable flow state better than numeric jumps" (perrygeo) — [HN 44020734](https://news.ycombinator.com/item?id=44020734)

### Inferences
- Pricing anger is about the model, not the amount: $20–$35 lifetime passes without comment, while $25–$50 per 6 months is attacked every time, even in 2026.
- "Too basic" complaints are really "the course ends where real Vim gets interesting" (dot command, registers, macros, ex ranges, file/window navigation) — the same list vimhjkl and vimchi were built to fill.
- Emulator fidelity complaints land on products using off-the-shelf editor bindings (Ace); custom engines (OpenVim, vimchi) and real-Vim products did not draw fidelity complaints in the sources found, but real Neovim in the browser drew performance complaints instead.

### Gaps
- No Reddit threads could be retrieved; complaint ranking rests on HN plus Trustpilot/Product Hunt/dev.to.
- No direct user complaints about Vim Hero, VimMaster, vimtyper, VimGym or vimchi were found (too small or too new).

## Key Question 4: Which products are actively maintained in 2026 and which are abandoned?

### Takeaway
Active (code or site activity in the last ~6 months, as of 2026-10-11): hardtime.nvim, precognition.nvim, OpenVim repo, VimMaster repo, vimhjkl, VimGym, vimchi, Vim Hero, LearnVim, Vimified, Vim Adventures, VimGolf site, Vimgolf.ai, vimtyper. Stale or abandoned: vim-be-good (Dec 2024), vim-be-better (Jun 2025, 3 days), PacVim (Mar 2024), vimtronner (2018), Vim Genius (2023; TLS broken), vscodevimacademy and Learn Vim extension (both June 2022), chronicles-of-vimia (May 2025), VimGolf CLI (Jul 2024).

### Cited Findings
- `pushed_at` 2026: precognition.nvim 2026-10-11; hardtime.nvim 2026-10-02; vimgym 2026-10-06; vimchi 2026-10-06; egaga/openvim 2026-07-29; vimmaster 2026-07-16; vimhjkl 2026-07-03; vim-mastery 2026-07-22; vimtutor-sequel 2026-02-01. — [GitHub API batch 1](https://api.github.com/search/repositories?q=repo:ThePrimeagen/vim-be-good+repo:renzorlive/vimmaster+repo:micahkepe/vimtutor-sequel+repo:m4xshen/hardtime.nvim+repo:tris203/precognition.nvim+repo:S-Sigdel/vimhjkl+repo:vuciv/golf+repo:szymonwilczek/vim-be-better+repo:RaphaelKMandel/chronicles-of-vimia+repo:jmoon018/PacVim+repo:carbonfive/vimtronner+repo:kaisunc/vscodevimacademy+repo:igrigorik/vimgolf+repo:vintharas/learn-vim); [batch 2](https://api.github.com/search/repositories?q=repo:egaga/openvim+repo:gig3m/vimchi+repo:vicramon/vimgenius+repo:patmood/vim-snake+repo:HotelBudapest/vimtype+repo:spcask/vimex+repo:adomokos/Vim-Katas+repo:ozankasikci/vim-man+repo:coditva/A-Vim-Story)
- Stale `pushed_at`: vim-be-good 2024-12-05 (52 open issues); vim-be-better 2025-06-21; PacVim 2024-03-23; vimtronner 2018-11-21; vimgenius 2023-05-04; vscodevimacademy 2023-10-02 (marketplace last update 2022-06-02); chronicles-of-vimia 2025-05-29; igrigorik/vimgolf CLI 2024-07-04; A-Vim-Story 2019-04-28. — same API sources
- Learn Vim VS Code extension last updated June 2022 (v0.0.28) and described as "still a work in progress". — [VS Marketplace](https://marketplace.visualstudio.com/items?itemName=vintharas.learn-vim)
- Vim Genius domains fail TLS with a `*.herokuapp.com` certificate on 2026-10-11. — [WebFetch]
- Sites live on 2026-10-11 with current content: vim-hero.com, vim-adventures.com, vimgolf.com (counters), learnvim.com (© 2025), vimified.com, vimtyper.dev (© 2026), vim-racer.com, vimsnake.com, openvim.com. vim-master.com returned HTTP 530 twice; vimgolf.ai and vimchi.dev and vim.is returned only JS shells (live but unreadable). — [WebFetch results]
- Launch dates of the 2025–2026 wave: VimMaster created 2025-08-27; VimGym 2025-12-11; vimhjkl 2026-06-01; vim-mastery 2026-07-12; Vimgolf.ai Show HN 2026-07-29; vimtype 2026-09-08; vimchi 2026-09-28. — GitHub API; [HN Algolia](https://hn.algolia.com/api/v1/search?query=vimgolf&tags=story&hitsPerPage=50)

### Inferences
- The in-editor game niche that vim-be-good owned is effectively vacant: the original is unmaintained with a 2026 crash issue open, and the fork went quiet after three days.
- The 2025–2026 wave is dominated by free, solo-developer browser trainers with 0–5 GitHub stars (VimGym, vimchi, vim-mastery, hjkl), showing low barriers to entry and a crowded free tier; differentiation will have to come from measurement/adaptivity rather than "interactive lessons" alone.

### Gaps
- golf.vim push date and Vim Racer's last update are unverified.
- VimMaster's hosted site outage could be transient; cannot distinguish from abandonment on one day's evidence.

## Key Question 5: What do people explicitly ask for that no product offers? (unmet needs)

### Takeaway
Users repeatedly ask for lifetime pricing, deeper content beyond basics (registers, macros, ex commands, file/window navigation, plugins), efficiency-based scoring rather than raw speed, practice that transfers into their real editor, configurable/true-to-their-setup Vim behaviour, and a way to see and fix their own bad habits. No single product combines measured per-skill weakness detection with browser convenience, lifetime pricing and synced history.

### Cited Findings
- Lifetime instead of time-limited access: "I'd happily pay a flat $30" (dllthomas) — [HN 14656591](https://news.ycombinator.com/item?id=14656591); Vimgolf.ai author conceded a lifetime option "if demand warrants" — [HN 49095143](https://news.ycombinator.com/item?id=49095143)
- Content past the basics: dot command, `/` search, `G`, `dw` missing (ahussain) — [HN 25846347](https://news.ycombinator.com/item?id=25846347); "how to browse the directory, switch between files, open multiple panels" (xavdid); vim-surround and .vimrc (giansegato) — [HN 32034625](https://news.ycombinator.com/item?id=32034625); "Regex Practice" issue on vim-be-good — [GitHub issues](https://github.com/ThePrimeagen/vim-be-good/issues?q=is%3Aissue)
- Efficiency scoring and replay: Vim Racer users asked for "ranking by efficiency rather than speed, similar to VimGolf", replays of leaderboard runs, sorting by keystrokes vs time — [HN 41347051](https://news.ycombinator.com/item?id=41347051)
- Transfer into the real editor: "bring the move optimization advice into my actually coding environment" — [Product Hunt](https://www.producthunt.com/products/vim-adventures/reviews); vim-be-good issue "make a website out of this" (the reverse direction) — [GitHub issues](https://github.com/ThePrimeagen/vim-be-good/issues?q=is%3Aissue)
- Guided tutorial inside a game: "tutorial mode with actual step-by-step instruction" (Hugsbox) and Enter-to-advance (bhkdotdev) on Vimgolf.ai — [HN 49095143](https://news.ycombinator.com/item?id=49095143); "Give more hints please" on vim-be-good — [GitHub issues](https://github.com/ThePrimeagen/vim-be-good/issues?q=is%3Aissue)
- Respect the user's own Vim config: Vim Racer requests to disable relative numbers and "support vim configurations" — [HN 41347051](https://news.ycombinator.com/item?id=41347051); hardtime.nvim users want it for Vim, not just Neovim (yegle) — [HN 44020734](https://news.ycombinator.com/item?id=44020734)
- Editor-agnostic/alternative editors: Helix support requested (nylonstrung) — [HN 49095143](https://news.ycombinator.com/item?id=49095143)
- Habit visibility: hardtime report praised for showing "how pervasive bad habits are" — [kishorenewton.com](https://www.kishorenewton.com/posts/improve_nvim_with_hardtime/); but the strictness debate shows users want hints, not blocks — [HN 44020734](https://news.ycombinator.com/item?id=44020734)
- Session customisation: "Add option to select number of rounds" (vim-be-good) — [GitHub issues](https://github.com/ThePrimeagen/vim-be-good/issues?q=is%3Aissue); vimtyper offers 15/30/60s rounds and selectable edit types — [vimtyper.dev](https://www.vimtyper.dev/)
- Accessibility: colourblind-distinct targets (3np) — [HN 41347051](https://news.ycombinator.com/item?id=41347051)
- Low CPU / fast editing in the browser: Vimgolf.ai fan-spinning complaint — [HN 49095143](https://news.ycombinator.com/item?id=49095143)
- Offline/own-your-data: dev.to critic wanted a downloadable, not server-dependent, game — [dev.to](https://dev.to/mousepotatodoesstuff/vim-backspace-because-vim-adventures-isnt-worth-the-license-cost-338); VimMaster ships import/export of local progress — [GitHub README](https://github.com/renzorlive/vimmaster)

### Inferences — unmet-needs list for an adaptive trainer
1. Per-motion speed and accuracy measured over time and charted (keybr-style) — nobody does this; Vim Hero has levels, vimhjkl has Leitner boxes, Vimified has five aggregates.
2. Drill selection weighted by measured weakness in the browser — only vimhjkl does it, in a terminal with no sync.
3. Keystroke-efficiency scoring (vs par) combined with latency, not just one or the other (Vim Racer = time; VimGolf/vimhjkl/Vimgolf.ai = keystrokes).
4. Accounts with cross-device history plus an export (VimMaster has export without accounts; vimchi has sync without stats).
5. Curriculum that continues past basics into dot-repeat, registers, macros, `:g`/`:normal`/ranges, regex substitution, text objects, and optionally plugin motions (flash/leap/surround) — the vimhjkl and vimchi scope lists are a ready checklist.
6. A faithful, low-CPU browser engine (custom or CodeMirror-based) with a published list of supported commands, since fidelity complaints hit Ace-based products and CPU complaints hit real-nvim-in-container.
7. Lifetime or clearly-free pricing; avoid 6-month licences.
8. A bridge to the real editor: export of weak-skill hints to hardtime-style in-editor nudges, or a companion plugin that feeds real-editing telemetry back into the trainer (the Product Hunt "bring the advice into my coding environment" request, inverted).
9. Configurable editor behaviour (relative numbers, leader keys, arrow keys allowed or not) and colourblind-safe target highlighting.
10. Honest leaderboards or none: Vim Racer's scripted 1-second entries show that public speed boards without accounts degrade quickly.

### Gaps
- No source explicitly asks for "a keybr for Vim" by name; the need is inferred from the combination of requests above. Reddit, where such requests are most likely phrased that way, could not be searched.
- Demand sizing for a paid adaptive trainer is unknown; the only revenue datapoints are LearnVim's "2,082 engineers" at $15–$35 and vim.so's $250/month FastAPI sponsorship (2021).
