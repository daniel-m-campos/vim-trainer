# Reddit community sentiment toward Vim/Neovim learning and practice resources

**How the evidence was collected (read this first).**
- reddit.com and old.reddit.com could not be reached directly. WebSearch with `allowed_domains: reddit.com` returned "domain not accessible". WebFetch of old.reddit.com was refused. curl to the reddit JSON API returned "blocked".
- All Reddit evidence below came from the PullPush archive API (api.pullpush.io). It gave 1 batch of submission searches and full comment dumps for 17 threads. After that it returned HTTP 429 with a message saying it does not provide free scraping for agents, so I stopped using it.
- As a result, the planned systematic mention-frequency count across r/vim and r/neovim (2022–2026) **was not completed**. Every "frequency" statement below is an impression from about 17 threads (mostly 2024–2026, plus one 2019 thread). None of it is a corpus-wide count.
- **Score caveat:** PullPush stores upvote scores as they were when the archive captured the post. Live scores are probably equal or higher, especially for comments. Treat each "[N pts]" as "at least about N".
- Thread dates are the submission dates in UTC. Links point to reddit.com permalinks, which I could not open live.

---

## Which resources come up most often in "how do I get good at vim" threads, and in what order?

### Takeaway
In the threads I sampled, the most common answers to "how do I get better" were vimtutor and the advice to just use Vim daily. Next came Practical Vim, which had the single most-upvoted recommendation. After that came `:help` (especially `:help motion.txt`), vim-be-good, and ThePrimeagen's "Vim As Your Editor" videos. Vim Adventures, VimHero, and VimGolf get named but are framed as optional extras. I found almost no 2024–2026 mentions of OpenVim, Vim Genius, Vimcasts, Mastering Vim Quickly, Modern Vim, or Learn Vim the Smart Way in this sample.

### Cited Findings

**"How to become faster in Vim?" (r/vim, 2025-11-29, ~57 pts, 57 comments).** The OP had used Vim daily for a year and had done vimtutor "a couple of times but never found an occasion to use the stuff I learned".
- Top comment [69 pts], from KitchenFalcon4667: "For me the game changer was a book: Practical Vim: Edit Text at the Speed of Thought by Drew Neil and learning vim grammar". A reply [6 pts] says "this book is really really good". — [thread](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/)
- 2nd comment [34 pts], RickHunter84: "Use it more ….. 30 years and still finding new key bindings". — [thread](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/)
- [13 pts], EmeraldPolder: "Vim-motion is the secret sauce but you must learn it properly. You should do the entire 'vimtutor' tutorial." — [thread](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/)
- [5 pts], gumnos: "`:help motion.txt` has 100+ different motions that are far more efficient/useful than h/j/k/l". The comment also links the "Vim is a language" grammar gist, which describes commands as `«count»«command»«object/motion»`. — [thread](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/)
- [4 pts], sharp-calculation: "The Primagen, on youtube gave me several big boosts in my VIM journey. I recommend you watch at least the first 3 videos in his 'VIM as you editor' series." — [thread](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/)
- [6 pts], TankorSmash: "any time you're repeatedly pressing a button over and over again in a row, there's probably a different single key to press". [6 pts], cassepipe: remap CapsLock to Escape and "learn a bit of vim regex". — [thread](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/)
- [6 pts], captainnoyaux: "go through vimtutor multiple times then … when you have a specific problem you ask yourself if there is a vim solution." — [thread](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/)

**"Learning Vim Motions – offline" (r/vim, 2025-07-21, ~30 pts).** The OP was already using VimHero ("that I love") and LazyVim.
- Top [19 pts], gumnos: refers the OP to `:help motion.txt`: "there were over 100 different motions listed there and I use maybe 80–90% of them". — [thread](https://reddit.com/r/vim/comments/1m5p1f0/learning_vim_motions_offline/)
- [11 pts], AppropriateStudio153: "Drew Neill's *Practical vim* is a must-read for learning vim inside out". The same comment mentions the VimMaster quiz app. — [thread](https://reddit.com/r/vim/comments/1m5p1f0/learning_vim_motions_offline/)
- [8 pts], gumnos: "you could start at :help and read the entire manual (might have to set aside a week or two for this) and **still not** have mastered vim". — [thread](https://reddit.com/r/vim/comments/1m5p1f0/learning_vim_motions_offline/)
- Lower-scored replies [1–2 pts] mention vim-be-good ("vimbgood by primeagen"), vim-be-better (a fork with more games), a vim cheat sheet, and TJ DeVries' video. — [thread](https://reddit.com/r/vim/comments/1m5p1f0/learning_vim_motions_offline/)

**"New to Text Editor Bindings — base Vim or something more modern?" (r/vim, 2025-06-11).**
- Top [17 pts], gumnos: "stick to stock bindings until you have firm grasp on them. Use the `vimtutor` that comes with Vim". The comment adds that "the seasoned vimmer tends to think in terms of being in normal-mode all the time". — [thread](https://reddit.com/r/vim/comments/1l92jzd/new_to_text_editor_bindings_should_i_use_base_vim/)
- [5 pts]: "Neovim with lazyvim.org". [1 pt]: "LazyVim makes the learning curve enjoyable". — [thread](https://reddit.com/r/vim/comments/1l92jzd/new_to_text_editor_bindings_should_i_use_base_vim/)

**"How to practice Vim WITHOUT coding?" (r/vim, 2024-11-02, ~10 pts, 31 comments).** The OP said Vim Adventures "seems like the perfect solution but the $25 license is limited to 6 months which I find to be pretty greedy".
- Replies suggest Vim-Katas, vim-be-good, writing a diary or prose in Vim, speed-running vimtutor, and Vim Adventures. All scored around 1 pt in the archive. — [thread](https://reddit.com/r/vim/comments/1gi8xm4/how_to_practice_vim_without_coding/)

**A self-compiled resource list: "My journey tackling vim and getting better with Neovim" (r/neovim, 2025-08-15, ~27 pts).**
- The list includes ThePrimeagen's "Vim As Your Editor" playlist (Introduction, Horizontal and Vertical Movement, Advanced Motions), kickstart.nvim, and TJ DeVries' "The Only Video You Need to Get Started with Neovim".
- It also names the YouTubers TypeCraft, DevOps Toolbox, Henry Misc, and Josean Martinez, and the LazyVim distro.
- The author says this list came from tips in an earlier r/vim thread. Commenters called it a "Great list of resources!" — [thread](https://reddit.com/r/neovim/comments/1mqvsbc/my_journey_tackling_vim_and_getting_better_with/)

### Inferences
- Impressionistic ranking from the sampled 2024–2026 threads, by how often each resource was named and how it scored:
  1. vimtutor
  2. "just use it / learn the grammar"
  3. Practical Vim
  4. `:help` / `motion.txt`
  5. vim-be-good
  6. ThePrimeagen's YouTube series
  7. Vim Adventures
  8. VimHero
  9. VimGolf
  10. kickstart.nvim / TJ DeVries (this one is for setting up config, not for learning editing)
- Practical Vim had the highest-scoring single recommendation in any "get better" thread I sampled (69 pts). It is the community's main step up from beginner level.
- A small number of veteran posters show up again and again with the `:help` advice, gumnos in particular. Their answers tend to be the top-voted ones in r/vim, which pushes the subreddit's advice toward "read the manual, learn the grammar".

### Gaps
- No real frequency count could be done because PullPush rate-limited me. Reddit itself was not accessible.
- I did not retrieve the well-known older threads from 2015–2021 that are still widely linked, such as the classic "best way to learn vim" megathreads or "Your problem with Vim is that you don't grok vi" discussions. I also did not retrieve the r/vim sidebar or wiki resource list.
- I found no mention in this sample of OpenVim, Vim Genius, Mastering Vim Quickly, Modern Vim, or Vimcasts. This is a gap in the sample, not evidence that nobody recommends them.

---

## What reasons do people give for recommending each resource?

### Takeaway
- **vimtutor:** free, built in, and enough for the basics in about 30 minutes.
- **Practical Vim:** teaches the "Vim grammar" and the "Vim way", and was described as a "game changer".
- **`:help`:** complete and authoritative, with 100+ motions.
- **vim-be-good and VimHero:** fun, gamified drills of common motions that run in a real editor.
- **ThePrimeagen's videos:** motivating, with horizontal and vertical motion explained well.
- **Vim Adventures:** gamified and fun, "how I started vim".

### Cited Findings
- **vimtutor / :Tutor.** "The easiest way to learn vi motions is the built-in interactive Vim tutorial, it taught me everything I needed in half an hour". This came from HiPhish, r/neovim, 2025-05-09. — [thread](https://reddit.com/r/neovim/comments/1kj1bsl/anyone_else_played_vim_adventures/)
- **vimtutor.** A Nordic-keyboard user said "I just started of with vimtutor" (r/neovim, 2025-08-24). — [thread](https://reddit.com/r/neovim/comments/1mysp4z/new_to_vimneovim/)
- **Practical Vim.** Credited with teaching "vim grammar" and called "a must-read for learning vim inside out". — [1p9rrzn](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/), [1m5p1f0](https://reddit.com/r/vim/comments/1m5p1f0/learning_vim_motions_offline/)
- **vim-be-good, in a Vim Adventures thread.** "its good for the basics but for commonly used stuff i recommend theprimeagen's VimBeGood" [5 pts]. Also "yes a lot and Vim be good too, is really fun to learn with games", and "For me it was vim-be-good". — [thread](https://reddit.com/r/neovim/comments/1kj1bsl/anyone_else_played_vim_adventures/)
- **Vim Adventures ("Anyone else played VIM Adventures?", r/neovim, 2025-05-09, ~34 pts).**
  - Top [15 pts]: "Yes. I always use it to promote vim keybindings".
  - [7 pts]: "I like gamified learning, so it's helpful for me".
  - [4 pts]: "That's how I learned vim bindings. Couldn't recommend it more."
  - "best vim game out there and it actually feels like a game … its how i started vim!"
  - [thread](https://reddit.com/r/neovim/comments/1kj1bsl/anyone_else_played_vim_adventures/)
- **VimHero.** The OP of the offline-learning thread said "I have been using VimHero that I love" (r/vim, 2025-07-21). — [thread](https://reddit.com/r/vim/comments/1m5p1f0/learning_vim_motions_offline/)
- **VimHero, off-Reddit.** It describes itself as 50+ interactive lessons on motions, operators, and text objects, free to start. — [vim-hero.com](https://www.vim-hero.com/)
- **VimHero, off-Reddit.** A Show HN launch thread exists. — [HN](https://news.ycombinator.com/item?id=25846347)
- **VimHero, off-Reddit.** Mastodon posts from 2025 call it "actually amazing". — [mementomori.social](https://mementomori.social/@rolle/114914016947922166)
- **ThePrimeagen's "Vim As Your Editor".** Credited with "several big boosts" and recommended for its first 3 videos. — [thread](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/)
- **ThePrimeagen's "Vim As Your Editor".** Listed as the primary "Vim Motion" resource in a 2025 resource list. — [thread](https://reddit.com/r/neovim/comments/1mqvsbc/my_journey_tackling_vim_and_getting_better_with/)
- **VimGolf ("Vimgolf just blew my mind", r/vim, 2019-06-06, ~111 pts, 66 comments).** The OP learned column-wise cut/paste, `{`, `M`, `<C-e>`, `+`, and tricks with the `.` register.
  - Defender [12 pts]: "It encourages you to learn new commands/operators/workflows that may be applicable in actual work."
  - Defender [11 pts]: "vimgolf is about learning vim, and all its wonders, with examples."
  - [thread](https://reddit.com/r/vim/comments/bxcxia/vimgolf_just_blew_my_mind/)
- **VimGolf ("as a beginner, I don't quite understand the goal of vimgolf", r/vim, 2026-06-14).** gumnos, a former #1 VimGolf player, said: "it forced me to consider multiple solutions to problems, often exposing new functionality that I'd never encountered before". — [thread](https://reddit.com/r/vim/comments/1u5jnmh/as_a_beginner_i_dont_quite_understand_the_goal_of/)
- **VimGolf, in-editor daily version.** "I am Building VimGolf: Daily editing challenges…" (r/vim, 2025-04-11, ~221 pts) pitched a "Wordle, but for Vim skills" in-editor plugin. The author said "I've found VimGolf incredibly helpful for discovering new editing techniques". — [thread](https://reddit.com/r/vim/comments/1jx8ipu/i_am_building_vimgolf_daily_editing_challenges/)
- **Touch typing as a prerequisite.** "Touch typing was the missing piece" (r/vim, 2025-06-25, ~93 pts). One commenter [6 pts] had hunt-and-pecked for 45 years and used Vim for about 15: "learning to touch type for the last 6 months … it's all finally coming together". — [thread](https://reddit.com/r/vim/comments/1lkzqjn/touch_typing_was_the_missing_piece/)

### Inferences
- The reasons for recommending each resource line up with skill level:
  - vimtutor and the games are for "getting moving" and muscle memory.
  - Practical Vim and `:help` are for understanding composability (operator + motion/text object, the dot command).
  - VimGolf is for discovering obscure commands.

### Gaps
- No Reddit evidence was retrieved on Vimcasts, Modern Vim, Learn Vim the Smart Way, Mastering Vim Quickly, OpenVim, or Vim Genius.
- The general web-search results did describe Learn Vim the Smart Way as "bridg[ing] the gap between vimtutor and the help manual". — [GitHub sterfield/Learn-Vim](https://github.com/sterfield/Learn-Vim)

---

## What criticisms are common?

### Takeaway
- **Vim Adventures:** criticized for its paid, time-limited license (about $25 for 6 months) and for covering only the basics.
- **VimGolf:** criticized as "unrelated to using vim effectively", for its keystroke-count philosophy, and for locking you out of the better solutions.
- **vimtutor:** criticized for "stopping too early". This complaint drove a highly upvoted 2026 tool.
- **Courses and games in general:** they don't create real-world habits unless you then apply the techniques while editing.
- **New AI-generated trainers:** they draw "AI slop" pushback.

### Cited Findings
- **Vim Adventures, on price.** "the $25 license is limited to 6 months which I find to be pretty greedy" (r/vim OP, 2024-11-02). — [thread](https://reddit.com/r/vim/comments/1gi8xm4/how_to_practice_vim_without_coding/)
- **Vim Adventures, on value.** "I found it rather annoying and bloated, and you have to pay for it", from HiPhish, who preferred vimtutor. Another commenter said "the price point is bit too high and its only temporary". A third asked "is it actually helpful or just a gimmick?" [3 pts]. — [thread](https://reddit.com/r/neovim/comments/1kj1bsl/anyone_else_played_vim_adventures/)
- **Vim Adventures, on scope.** "its good for the basics but for commonly used stuff i recommend … VimBeGood" [5 pts]. — [same thread](https://reddit.com/r/neovim/comments/1kj1bsl/anyone_else_played_vim_adventures/)
- **VimGolf ("as a beginner, I don't quite understand the goal of vimgolf", r/vim, 2026-06-14).**
  - Top [52 pts], internetgarb: "Vim golf is a game people enjoy. It is, more or less, unrelated to using vim effectively. If you like the puzzles, and are having fun, have at it."
  - [15 pts], sharp-calculation: "The shortest path isn't always the best path … arcane solutions … how many people can remember these".
  - [17 pts], m1foley: compared it to rodeos, log rolling, and latte art, i.e., a competition to hone a craft.
  - The OP complained that locked solutions make it "tedious [rather] than rewarding".
  - [thread](https://reddit.com/r/vim/comments/1u5jnmh/as_a_beginner_i_dont_quite_understand_the_goal_of/)
- **VimGolf, 2019.** Top comment [33 pts]: "I find the problems on Vimgolf too far removed from actual work. I wholeheartedly disagree with that keystrokes-counting philosophy … there are smoother and more natural ways to learn those things." Another [25 pts] complained about needing a Twitter account to sign in. — [thread](https://reddit.com/r/vim/comments/bxcxia/vimgolf_just_blew_my_mind/)
- **vimtutor is too shallow.** "vimtutor stops too early, so I made something to drill the dot command, macros, :g in real vim environment" (r/neovim, 2026-06-02, ~479 pts). It was cross-posted to r/vim (~293 pts). Its pitch: "vimtutor gets you moving, then stops right before the techniques that make Vim truly fast: the dot command, operator-motion grammar, text objects, registers, macros, :g, :normal, ranges, and substitution." — [r/neovim](https://reddit.com/r/neovim/comments/1tulbvp/vimtutor_stops_too_early_so_i_made_something_to/), [r/vim](https://reddit.com/r/vim/comments/1tul7jo/vimtutor_stops_too_early_so_i_made_something_to/)
- **Knowing the commands is not the same as using them.** The OP of the "faster" thread had done vimtutor repeatedly "but never found an occasion to use the stuff I learned". — [thread](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/)
- **Weaknesses of the vimhjkl trainer.**
  - "it fell short in drilling obtuse substitutions and never really drilling vertical and horizontal movement motions in larger blocks of text" [1 pt].
  - Users asked for custom keymap support (e.g., a `jk` escape mapping) because the tool launches a minimal nvim.
  - The author admitted "I built most of this in 1 day and had a LLM to generate the 500+ exercises". A commenter replied "you should be up front about … the involvement of LLM".
  - [r/neovim](https://reddit.com/r/neovim/comments/1tulbvp/vimtutor_stops_too_early_so_i_made_something_to/), [r/vim](https://reddit.com/r/vim/comments/1tul7jo/vimtutor_stops_too_early_so_i_made_something_to/)
- **AI-built game, r/commandline.** "I built a 30-level Cyberpunk RPG to teach you VIM" (2026-02-15, ~5 pts) got replies like "AI slop…" and "you instructed an AI to generate this code". — [thread](https://reddit.com/r/commandline/comments/1r5np3p/i_built_a_30level_cyberpunk_rpg_to_teach_you_vim/)
- **Partial Vim emulations.** In a beginner thread, one commenter warned that Obsidian's vim mode "relies on Codemirror's implementation … which is a subset of actual vim". This is relevant by analogy to VSCodeVim. — [thread](https://reddit.com/r/vim/comments/1l92jzd/new_to_text_editor_bindings_should_i_use_base_vim/)

### Inferences
- The community rarely calls the games harmful. It tends to frame them as "fine for basics or fun, not the path to mastery".
- VimGolf splits opinion in a consistent way, in both 2019 and 2026. People who like it value it for discovering commands. Critics say keystroke-minimal answers are not what you use in daily editing.

### Gaps
- I retrieved no Reddit criticism of vim-be-good itself. In the sampled threads it was only praised, briefly.
- I found no criticism of Practical Vim's age (2nd edition, 2015) or of its Vim-versus-Neovim relevance.

---

## Is there a consensus path from intermediate to very proficient?

### Takeaway
The near-consensus path has four parts:
1. Finish vimtutor, then stop drilling basics.
2. Learn the composable grammar: operator + count + motion/text object, plus the dot command. Practical Vim is the usual vehicle.
3. Read `:help` selectively, especially `motion.txt`.
4. Improve inside daily editing: notice repetition, then look up the Vim way to do it.

Macros, registers, regex/`:s`/`:g`, and visual-block are named as the next tier. Since mid-2026, drill trainers aimed at those advanced topics (vimhjkl) have been getting a strong reception.

### Cited Findings
- **Notice repetition, then fix it.** "when you have a specific problem you ask yourself if there is a vim solution" [6 pts]. Also, any repeated keypress means "there's probably a different single key" [6 pts]. — [thread](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/)
- **Learn a subset, add as needed.** "Try to get used to a subset, the typical vi standard vi command (motion, substitution, regexp) then you will add vim features when you need them" [2 pts]. — [thread](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/)
- **Proficiency never "finishes".** A Vim user since 1998: "This feeling never goes away … I still feel slow" [10 pts]. Another: "30 years and still finding new key bindings" [34 pts]. — [thread](https://reddit.com/r/vim/comments/1p9rrzn/how_to_become_faster_in_vim/)
- **Normal mode as the resting state.** The "seasoned vimmer" stays in normal mode by default. gumnos said "someone pointed it out to me (after easily a good 10yr of vimming) and it was a lightbulb". — [thread](https://reddit.com/r/vim/comments/1l92jzd/new_to_text_editor_bindings_should_i_use_base_vim/)
- **Advanced-tier topics.**
  - vimhjkl covers 61 lessons and 563 challenges on the dot command, text objects, registers, macros, `:g`, `:normal`, ranges, and substitution. Each challenge runs in real Vim/Neovim and is scored against an optimal par.
  - Commenters said "after i finished vimtutor … i wished they covered some more advanced stuff, and this is a perfect fit" and "I've been using this daily during standup".
  - [thread](https://reddit.com/r/neovim/comments/1tulbvp/vimtutor_stops_too_early_so_i_made_something_to/); repo: [S-Sigdel/vimhjkl](https://github.com/S-Sigdel/vimhjkl)
- **Visual block as a tool, regex as a skill.** Visual block was called a favorite "cheat". Commenters debated whether everyone should learn regex: "I think everyone using VIM should learn regex. But they have limited uses." — [thread](https://reddit.com/r/vim/comments/1u5jnmh/as_a_beginner_i_dont_quite_understand_the_goal_of/)
- **Practicing ex commands.** "Practicing ex commands / regexes" (r/neovim, 2025-10-07) is a small thread asking for practice material beyond motions. — [thread](https://reddit.com/r/neovim/comments/1o06cvz/practicing_ex_commands_regexes/)

### Inferences
- For a VSCodeVim + Neovim 0.12 user, the Reddit path implies a few things:
  - Practical Vim's grammar, dot-command, and text-object material carries over to both editors.
  - Ex-heavy techniques (`:g`, `:normal`, complex ranges) are best practiced in real Neovim, since VSCodeVim only partly emulates them. This is an inference from the Codemirror-subset comment and from general knowledge of VSCodeVim's limits. I did not find a direct Reddit quote saying it.
- VimGolf is better treated as an occasional discovery tool than as a training regimen.

### Gaps
- I found no single canonical "intermediate to expert" Reddit guide. The path above is assembled from scattered comments.

---

## Recent shifts (2024–2026)

### Takeaway
- **More trainers:** a wave of new drill tools and games appeared in 2025–2026: in-editor daily VimGolf, vimhjkl, vim-be-better, chronicles-of-vimia, VimMaster, and a cyberpunk TUI RPG. Several were openly AI-assisted, which brought some backlash.
- **VimHero:** now named alongside vimtutor as a web-based beginner tool.
- **Neovim on-ramps:** LazyVim and kickstart.nvim, plus the TJ DeVries and Primeagen videos, are the standard Neovim entry points. They are config-oriented rather than editing-skill-oriented.

### Cited Findings
- **vimhjkl (June 2026).** About 479 pts on r/neovim plus about 293 on r/vim. It was the highest-scoring learning-tool post in the sample. — [r/neovim](https://reddit.com/r/neovim/comments/1tulbvp/vimtutor_stops_too_early_so_i_made_something_to/)
- **In-editor daily VimGolf (April 2025).** About 221 pts. The author later posted a 0.1 release. Commenters wanted to "spend 20, 30 minutes playing different challenges" rather than only one daily. — [thread](https://reddit.com/r/vim/comments/1jx8ipu/i_am_building_vimgolf_daily_editing_challenges/)
- **New alternatives named in comments.** vim-be-better ("plugin … to play games that will help you practice various vim skills"), chronicles-of-vimia, and Vim-Katas. — [1m5p1f0](https://reddit.com/r/vim/comments/1m5p1f0/learning_vim_motions_offline/), [1kj1bsl](https://reddit.com/r/neovim/comments/1kj1bsl/anyone_else_played_vim_adventures/), [1gi8xm4](https://reddit.com/r/vim/comments/1gi8xm4/how_to_practice_vim_without_coding/)
- **Mobile companion app.** "Using spare moments to make the switch to Neovim easier – built a small mobile companion" (r/neovim, 2026-02-19, ~8 pts). — [thread](https://reddit.com/r/neovim/comments/1r8zbzk/using_spare_moments_to_make_the_switch_to_neovim/)
- **Neovim mini-guide.** "Neovim/Vim Mini-Guide: A practical 80% reference" (r/neovim, 2026-03-23, ~62 pts). — [thread](https://reddit.com/r/neovim/comments/1s19b2d/neovimvim_miniguide_a_practical_80_reference/)
- **Learning from expert configs.** "I read the entire core maintainers' Neovim config" (r/neovim, 2025-11-28, ~415 pts). This shows interest in learning from experts' setups. — [thread](https://reddit.com/r/neovim/comments/1p90s74/i_read_the_entire_core_maintainers_neovim_config/)
- **Daily editing as the real test.** "Genuinely confused: I've tried Neovim, but still use VSCode" (r/vscode, 2025-11-22, ~20 pts). One commenter said "The vim extension in vscode is excellent if you're just looking for vim motion" [5 pts]. Another said VS Code "makes it easy to be a casual and neovim FORCES you to learn". — [thread](https://reddit.com/r/vscode/comments/1p41bms/genuinely_confused_ive_tried_neovim_but_still_use/)

### Inferences
- A clear 2025–2026 theme is to "go past vimtutor with scored, real-editor drills". The strong vote counts on vimhjkl and daily VimGolf suggest unmet demand at the intermediate level, where only books and `:help` existed before.
- AI-generated learning tools face scrutiny: r/neovim moderators and r/commandline rules require disclosure.

### Gaps
- I could not verify live upvote counts or comment totals.
- I could not check whether vimhjkl or the daily VimGolf plugin have kept traction past launch.
- I had no data on paid courses (e.g., Mastering Vim Quickly, or newer video courses) gaining traction in 2024–2026.
