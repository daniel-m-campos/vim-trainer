# Non-Reddit community recommendations for Vim/Neovim learning and practice resources (HN, Stack Exchange, curated lists, blogs, YouTube)

Method note: HN figures come from the HN Algolia API (`hn.algolia.com/api/v1`), pulled 2026-10-11. Story points and comment counts are exact as of that date. "Mention counts" are the number of HN comments matching an exact phrase (Algolia `advancedSyntax`, typo tolerance off). They are approximate: Algolia phrase matching is imperfect, and one odd result appeared ("vim-be-good" returned 0 all-time but 2 since 2022). Stack Exchange scores come from the SE API (api.stackexchange.com). GitHub stars come from the GitHub REST API. YouTube views were scraped from YouTube search-result pages ("N views", "Ny ago") on 2026-10-11. Lobste.rs could not be queried: an Anubis bot wall blocked access. Slant.co returned 403.

## 1. Hacker News: highest-scoring threads about Vim learning resources, and their sentiment

### Takeaway
HN's biggest Vim-learning threads are launches of **interactive browser courses and games**. These are vim.so (667 pts, 2021), OpenVim (566 pts, 2017), vimified (344 pts, 2022) and Vim Adventures (285 pts, 2017). The top comments in those threads keep redirecting people to **free and built-in options**: vimtutor first, then `:help user-manual`, plus Practical Vim and vim-be-good. Paid or subscription products draw distrust. In 2022–2026 the energy moved to habit-correction tools (hardtime.nvim, 214 pts, 2025), to deeper free texts (Learn Vim (the Smart Way), 303 pts, 2023; Vimtutor Sequel, 229 pts, 2024), and to a motions essay (425 pts, 2023).

### Cited Findings
**Top HN stories (points / comments / date):**
- "Show HN: I built an online interactive course that helps you learn Vim faster" (vim.so). **667 pts / 280 comments, 2021-01-20**. This is the highest-scoring Vim-learning story found. — [HN 25846347](https://news.ycombinator.com/item?id=25846347)
- "Learn Vim Progressively" (Yann Esposito blog). **605 pts / 113 comments, 2011-08-29**. Still cited in 2022 as the article that took one commenter "from scared of VIM to feeling crippled without it." — [HN 2936670](https://news.ycombinator.com/item?id=2936670); [HN 31337588](https://news.ycombinator.com/item?id=31337588)
- "Interactive Vim tutorial" (OpenVim). **566 pts / 224 comments, 2017-10-04**. Other OpenVim reposts scored 237 (2011), 179 (2020) and 177 (2022-10-23). — [HN 15400037](https://news.ycombinator.com/item?id=15400037); [HN 33306778](https://news.ycombinator.com/item?id=33306778)
- "Moving fast with the core Vim motions" (barbarianmeetscoding, written for VSCodeVim users). **425 pts / 265 comments, 2023-06-13**. — [HN 36312027](https://news.ycombinator.com/item?id=36312027)
- "Your problem with Vim is that you don't grok vi" (Stack Overflow answer). **417 pts / 182 comments, 2011-08-22**. It was reposted at least 7 more times, in 2010, 2015, 2016, 2017 (52), 2018, 2020 and 2021 (51). — [HN 2911930](https://news.ycombinator.com/item?id=2911930)
- "Show HN: … interactive course that helps you learn Vim faster" (vimified). **344 pts / 253 comments, 2022-07-09**. — [HN 32034625](https://news.ycombinator.com/item?id=32034625)
- "Learn Vim (2021)" (iggredible/Learn-Vim, i.e. *Learn Vim the Smart Way*). **303 pts / 204 comments, 2023-02-24**. An earlier post scored 240 pts / 130 comments on 2020-08-26. — [HN 34930113](https://news.ycombinator.com/item?id=34930113); [HN 24287566](https://news.ycombinator.com/item?id=24287566)
- "A CLI game to learn Vim" (PacVim). **296 pts / 52 comments, 2018-05-15**. — [HN 17077668](https://news.ycombinator.com/item?id=17077668)
- "Vim Tutorial as an Adventure Game" (Vim Adventures). **285 pts, 2017-06-28**. Other posts scored 140 pts (2013) and 78 pts ("Show HN: Vim Tutorial as RPG", 2022-09-23). — [HN 14656591](https://news.ycombinator.com/item?id=14656591); [HN 32950623](https://news.ycombinator.com/item?id=32950623)
- "Vimcasts" archive. **277 pts, 2010-03-30**. A 2023-05-13 repost scored 134 pts / 22 comments. — [HN 1228779](https://news.ycombinator.com/item?id=1228779); [HN 35928141](https://news.ycombinator.com/item?id=35928141)
- "I Made an Extended Version of Vimtutor – Introducing Vimtutor Sequel". **229 pts / 35 comments, 2024-08-03**. — [HN 41144843](https://news.ycombinator.com/item?id=41144843)
- "Show HN: Hardtime.nvim – break bad habits and master Vim motions". **214 pts / 86 comments, 2025-05-18**. — [HN 44020734](https://news.ycombinator.com/item?id=44020734)
- "Intermediate Vim tips" (kinbiko). **200 pts / 77 comments, 2017-12-21**. "Best of Vim Tips" (zzapper) scored 290 pts in 2014 and 273 pts in 2012. — [HN 15983758](https://news.ycombinator.com/item?id=15983758); [HN 7943575](https://news.ycombinator.com/item?id=7943575)
- "Learn Vimscript the Hard Way": 195 pts (2013). — [HN 5493029](https://news.ycombinator.com/item?id=5493029)
- "VimGolf.com – real Vim ninjas count every keystroke". **178 pts / 79 comments, 2010-12-28**. — [HN 2046387](https://news.ycombinator.com/item?id=2046387)
- "How I made a profitable Vim course" (vim.so author, "$10k teaching vim"). 174 pts / 52 comments, 2021-04-15. — [HN 26825566](https://news.ycombinator.com/item?id=26825566)
- "How to Learn Vim: A Four Week Plan" (Peter Jang). 171 pts / 103 comments, 2017-10-06. A 2021 commenter said: "I followed this plan, and have recommended it many times." — [HN 15414544](https://news.ycombinator.com/item?id=15414544); [HN 28909432](https://news.ycombinator.com/item?id=28909432)
- "Learn Vim motions with an ice-cream van" (vimscoops). 123 pts / 50 comments, 2026-07-01. — [HN 48750803](https://news.ycombinator.com/item?id=48750803)
- "Practical Vim command workflow (2023)" (m4xshen blog). 106 pts / 97 comments, 2024-04-27. — [HN 40179194](https://news.ycombinator.com/item?id=40179194)
- "Mastering Vim Grammar" (irian.to, by the Learn-Vim author). 60 pts, 2025-05-27. — [HN 44105651](https://news.ycombinator.com/item?id=44105651)
- "Show HN: Vimgolf.ai – Learn Vim by playing through a map of levels". 36 pts / 26 comments, 2026-07-29. — [HN 49095143](https://news.ycombinator.com/item?id=49095143)
- **These resources have little or no HN story presence:** vim-be-good (no story found), Vim Hero (4 pts, 2024-08-08), Vim Genius (9 pts, Show HN 2013), and Mastering Vim Quickly (3 pts or less). — [HN 41195708](https://news.ycombinator.com/item?id=41195708); [HN 6127400](https://news.ycombinator.com/item?id=6127400); [HN 25289995](https://news.ycombinator.com/item?id=25289995)

**HN comment mention counts (exact phrase, all-time / since 2022-01-01; approximate):**
- vimtutor 479 / 128; "Vim Adventures" 192 / 49; vimgolf 143 / 59; vimcasts 142 / 17; "Practical Vim" 131 / 37; primeagen 129 / 127; "Modern Vim" 86 / 24 (this phrase is ambiguous); "Drew Neil" 70 / 18; "grok vi" 61 / 24; "kickstart.nvim" 50 / 48; "user manual" + vim 42 / 22; hardtime 38 / 15; usr_toc 18 / 9; openvim 17 / 2; "TJ DeVries" 12 / 9; "Learn Vimscript the Hard Way" 11 / 3; "Mastering Vim Quickly" 4 / 0; "vim hero" 4 / 1; "vim be good" 3 / 2; "Learn Vim the Smart Way" 1 / 1; "Vim Genius" 0. — [HN Algolia API](https://hn.algolia.com/api)

**Sentiment, by resource (quotes from the threads above):**
- **vimtutor is the default answer.** In the vim.so thread: "Before trying these courses, Please try vimtutor that comes bundled with vim." — [HN 25846347](https://news.ycombinator.com/item?id=25846347). The first two top-level answers in "Ask HN: What is a good guide for learning Vim" (2022) both said "vimtutor." — [HN 31337588](https://news.ycombinator.com/item?id=31337588). A Vimgolf.ai commenter (2026) wrote: "I'm still going to recommend people to use vimtutor." — [HN 49095143](https://news.ycombinator.com/item?id=49095143). The Vimtutor Sequel author built it because the original stops before advanced topics. — [HN 41144843](https://news.ycombinator.com/item?id=41144843)
- **`:help user-manual` is pitched as the free step after vimtutor.** Reply to "how to go from comfortable to expert" (2021): "Read the user manual… the user manual is called out as the next step after `vimtutor`. Start with `:h user-manual`." Another reply in the same subthread: "RTFM. Seriously." — [HN 25846347](https://news.ycombinator.com/item?id=25846347). A vimified critic (2022): "learning Vim has nothing to do with muscle memory and doing it outside of Vim is pointless… `:help user-manual` is easy, built-in, and it goes way beyond this. And it's free." — [HN 32034625](https://news.ycombinator.com/item?id=32034625)
- **Practical Vim and Drew Neil are the consistent book pick.** "Practical Vim by Drew Neil is definitely a way to go. It teached me stuff I wouldn't have discovered otherwise." (2021) — [HN 25846347](https://news.ycombinator.com/item?id=25846347). "Practical Vim is great." (2022) — [HN 31337588](https://news.ycombinator.com/item?id=31337588). In the 2023 Vimcasts thread, a commenter recommended Drew Neil's books (Practical Vim 2e, Modern Vim) as "stellar." Another said Drew's paid course was "worth every penny" even for a long-time user. — [HN 35928141](https://news.ycombinator.com/item?id=35928141)
- **vim-be-good gets a nod as the free, in-editor alternative to paid web courses.** It is plugged as "free, doesn't require a login, and… a native vim plugin." HN discusses it rarely (3–4 phrase mentions). — [HN 25846347](https://news.ycombinator.com/item?id=25846347)
- **Paid web courses and games are polarizing.** About vim.so's $15 lifetime price, one commenter said it "feels a tad unethical to be charging for a slightly more fancy, maybe kinda gamified, vimtutor." — [HN 25846347](https://news.ycombinator.com/item?id=25846347). About Vim Adventures (2022), one user said "This is how I learned vim. Money well spent." Others objected to an undisclosed paywall and to its subscription model ("not worth it imho"). — [HN 32950623](https://news.ycombinator.com/item?id=32950623). Vimgolf.ai (2026) drew complaints about "free trial subscription slop SaaS," confusing $25/6-month pricing, and high CPU use. — [HN 49095143](https://news.ycombinator.com/item?id=49095143)
- **OpenVim is liked as a beginner sandbox.** Its top 2022 comment asked for something more advanced: "I am looking for advanced tutorial… Where can I find such advanced stuff?" — [HN 33306778](https://news.ycombinator.com/item?id=33306778)
- **VimGolf is suggested for the intermediate stage.** "Maybe try vim golf for fun." Another commenter: "Playing some vimgolf and seeing what neat tricks people used. This is where I learned about '.'" — [HN 25846347](https://news.ycombinator.com/item?id=25846347)
- **hardtime.nvim got a warm reception, but many dispute the "never repeat hjkl" premise.** Top comments argue that counting characters for `31l` or `15j` is worse than key repeat. Another commenter says simply mapping the arrow keys to no-op "made the biggest difference." — [HN 44020734](https://news.ycombinator.com/item?id=44020734)
- **Pushback on hjkl-first pedagogy recurs.** "My pet peeve is Vim tutorials that start with 'use hjkl'…" (2022). — [HN 32034625](https://news.ycombinator.com/item?id=32034625). "Are novices well served, in the 2020s, by [hjkl] being the primary thing that they learn?" (2026). — [HN 48750803](https://news.ycombinator.com/item?id=48750803)
- **Vimscript is seen as dated.** In the Learn Vim thread (2023): "No one should be learning Vimscript at this point… best served by using Neovim with Lua." — [HN 34930113](https://news.ycombinator.com/item?id=34930113)
- **Starting in an IDE's Vim mode is a common, accepted path.** "Install vim mode in VSCode…" (2022) — [HN 31337588](https://news.ycombinator.com/item?id=31337588). "I used the VSCode vim extension too, which I believe eased me into it." (2021) — [HN 28909432](https://news.ycombinator.com/item?id=28909432)

### Inferences
- HN upvotes **launches**, so points favour novel web products (vim.so, OpenVim, vimified, Vim Adventures). The comment sections then consistently steer readers to free and built-in material. Points measure novelty; comments measure what people actually recommend.
- By comment mentions, the most recommended named resources on HN are vimtutor, then Vim Adventures, VimGolf, Vimcasts and Practical Vim. Primeagen mentions are almost entirely post-2022 (127 of 129), which shows how recent his influence is.
- vim-be-good is far more prominent on YouTube, GitHub and Reddit than on HN.

### Gaps
- Lobste.rs could not be accessed because of the Anubis bot wall, so no Lobsters scores were collected.
- Comment-level sentiment was sampled from the roughly 10 most-replied top-level comments per thread, not exhaustively.
- Algolia phrase counts include false positives. For example, "Modern Vim" also matches generic phrases.

## 2. Vi & Vim Stack Exchange and Stack Overflow: top-voted "how to learn/master Vim" answers

### Takeaway
Stack Overflow's canonical answers date from 2009–2011 and are now closed as "not constructive." The best known is Jim Dennis's **"Your problem with Vim is that you don't grok vi"** (2,844 votes). It teaches Vim as a composable verb-plus-motion language, and curated lists still cite it as essential. Vi.SE's top "after vimtutor" answer (33 votes, 2015) recommends **"sharpen the saw"** incremental learning (Bram Moolenaar's *Seven habits*, Vimcasts), a near-blank vimrc, and `:help`. The beginner answers are vimtutor and reading `:help`.

### Cited Findings
- SO Q1218390, "What is your most productive shortcut with Vim?" (2009-08-02). Question score **1,121**, 50 answers, about **1.07M views**. The top answer is Jim Dennis's "Your problem with Vim is that you don't grok vi," at **2,844 votes**. It explains `y` as a verb, `yy` as a synonym for `y_`, and the "Zen of vi" as speaking a language. The next answers are visual mode and text objects (502 votes) and smart movements and count prefixes (207 votes). — [SO 1218390](https://stackoverflow.com/questions/1218390/what-is-your-most-productive-shortcut-with-vim/1220118#1220118)
- SO Q597077, "What are the benefits of learning Vim?" (2009, score 465, about 283k views, closed "not constructive"). Top answer (248 votes): "still learning new things" after 20 years, pointing to David Rayner's *Best of Vim Tips* and ViEmu's "Why, oh WHY, do those nutheads use vi?". Third answer (138 votes): "Running through vimtutor only took me 30 minutes… worth every second." — [SO 597077](https://stackoverflow.com/questions/597077/what-are-the-benefits-of-learning-vim)
- SO Q1276403, "Simple Vim commands you wish you'd known earlier" (2009, score 400, about 127k views, closed). Top answers: Ctrl-C as Esc (334 votes), search-then-`:%s//…/` with incsearch (206 votes), and a personal command reference (168 votes). — [SO 1276403](https://stackoverflow.com/questions/1276403/simple-vim-commands-you-wish-youd-known-earlier)
- SO Q5400806, "What are the most-used vim commands/keypresses?" (2011, score 149). Top answer (387 votes) is Greg Hewgill's tip sheet. The ViEmu graphical cheat sheet got 25 votes ("greatest thing ever for learning VIM"). — [SO 5400806](https://stackoverflow.com/questions/5400806/what-are-the-most-used-vim-commands-keypresses)
- Vi.SE Q4111, "Learning Vim after vimtutor" (2015-07-31, score 31, about 6.7k views). Accepted top answer by Peter Rincker (**33 votes**): "Sharpen the saw" from Bram's *Seven habits* essay plus the Vimcasts post of the same name. "Don't learn everything all at once… When you find an inefficiency look for ways to improve it. Repeat." He also advises a "nearly blank vimrc" you understand line by line, `:help`, and adding plugins slowly after checking for native solutions. — [vi.SE 4111](https://vi.stackexchange.com/questions/4111/learning-vim-after-vimtutor)
- Vi.SE Q63, "How can a complete beginner learn Vim using just Vim itself?" (2015, score 27). Top answers: vimtutor (28 votes) and "read `:help` from top to bottom" (20 votes). — [vi.SE 63](https://vi.stackexchange.com/questions/63)
- Vi.SE Q15673, "Why is using arrow keys in normal mode considered bad practice?" (2018, score 46, about 19k views). — [vi.SE 15673](https://vi.stackexchange.com/questions/15673)
- None of the Vi.SE or SO high-vote learning answers mention vim-be-good, Vim Adventures, VimGolf or YouTube creators. Their resource set is vimtutor, `:help` and the user manual, Vimcasts, *Seven habits*, Best of Vim Tips, and the ViEmu cheat sheet. — [vi.SE 4111](https://vi.stackexchange.com/questions/4111/learning-vim-after-vimtutor); [SO 597077](https://stackoverflow.com/questions/597077/what-are-the-benefits-of-learning-vim)

### Inferences
- Vi.SE's moderators close "recommend a resource" questions, so its canonical learning advice is frozen at 2015 and leans on built-in documentation. Fit for the reader: the "sharpen the saw" loop (spot an inefficiency, look up the native way, drill it) is the method Vi.SE endorses for moving from intermediate to advanced.

### Gaps
- No high-scoring Vi.SE or SO question from 2022–2026 about learning resources was found. The search API's "learn"/"practice" queries surfaced only 2015–2020 questions.

## 3. What curated lists and widely shared blog posts treat as essential

### Takeaway
The curated lists agree on a core set:
- vimtutor
- *Practical Vim* ("hands down the best book about Vim," per vim-galore)
- Vimcasts
- the "grok vi" SO answer
- Bram Moolenaar's *Seven habits of effective text editing*
- `:h usr_toc`
- Learn Vimscript the Hard Way (for scripting)

Game-style tools (Vim Adventures, Vim Genius, PacVim) appear in awesome-vim. vim-be-good and Neovim-era tools are absent from the older lists. In GitHub stars, the biggest free texts and tools are vim-galore (18.0k), Learn-Vim (15.2k), vim-be-good (4.6k), hardtime.nvim (3.9k) and PacVim (3.3k).

### Cited Findings
- **vim-galore** (mhinz, 18,015 stars; last push 2023-12-22). Getting started: "`$ vimtutor`… Don't be put off by how boring it looks like and work through the exercises," then "Learn on demand! You never finish learning Vim." It points to `:h usr_toc.txt` as "the user manual… help topics for beginners in a rather friendly way." Its "Additional resources" section lists *Seven habits* (Bram), Learn Vimscript the Hard Way, **Practical Vim 2e ("Hands down the best book about Vim")**, the ViEmu "nutheads" essay, and the "grok vi" SO answer ("Concise, informative and correct. A real gem."). Its screencasts are vimcasts.org, wincent and Derek Wyatt. — [vim-galore README](https://github.com/mhinz/vim-galore)
- **awesome-vim** (akrawchyk, 2,131 stars; pushed 2025-06-06). Its "Learning Vim" section lists *Seven habits*, The Way of the Vim Warrior, Learn Vimscript the Hard Way, **Vim Adventures**, Vim Doctor, **Vim Genius**, Vim Tips (zzapper), vim-galore and **PacVim**. It does not list vim-be-good, VimGolf or Practical Vim. — [awesome-vim README](https://raw.githubusercontent.com/akrawchyk/awesome-vim/master/README.md)
- **awesome-neovim** (rockerBOO, 21,477 stars; actively pushed 2026-10). It is the main Neovim plugin index. Learning-content coverage was not extracted. — [GitHub API: rockerBOO/awesome-neovim](https://github.com/rockerBOO/awesome-neovim)
- **learnbyexample curated Vim resources** (asicsp), cited as a starting list in the 2022 Ask HN thread. — [learnbyexample](https://learnbyexample.github.io/curated_resources/vim.html); [HN 31337588](https://news.ycombinator.com/item?id=31337588)
- **GitHub stars (2026-10-11):**
  - iggredible/Learn-Vim: **15,246** (pushed 2026-09-07)
  - ThePrimeagen/vim-be-good: **4,572** (last push 2024-12-05)
  - m4xshen/hardtime.nvim: **3,857** (pushed 2026-10-02)
  - jmoon018/PacVim: **3,326**
  - tris203/precognition.nvim (motion-hint overlay): **1,387**
  - igrigorik/vimgolf: **780**
  - micahkepe/vimtutor-sequel: **564**
  - nvim-lua/kickstart.nvim: **31,573**
  - LazyVim: **27,632**

  — GitHub REST API for each repo, e.g. [Learn-Vim](https://github.com/iggredible/Learn-Vim), [vim-be-good](https://github.com/ThePrimeagen/vim-be-good), [hardtime.nvim](https://github.com/m4xshen/hardtime.nvim), [kickstart.nvim](https://github.com/nvim-lua/kickstart.nvim)
- **Built-in tutor updates.** A second vimtutor chapter was added on 2024-11-03 (English and French only) and is started with `vimtutor -c 2`. In Neovim, `:Tutor` offers chapter selection, e.g. `:Tutor vim-02-beginner`. — [vim_dev commit notice](https://groups.google.com/g/vim_dev/c/LLX44tFj0OE); [Arch vimtutor(1)](https://man.archlinux.org/man/vimtutor.1.en)
- **Widely shared blog posts with HN traction:**
  - Learn Vim Progressively (605 pts)
  - How to Learn Vim: A Four Week Plan (171 pts). It recommends vimtutor, then gradual adoption, then surround, commentary and repeat in week 4.
  - Moving fast with the core Vim motions (425 pts)
  - Intermediate Vim tips (200 pts)
  - Mastering Vim Grammar (60 pts, 2025)

  — [HN 2936670](https://news.ycombinator.com/item?id=2936670); [HN 15414544](https://news.ycombinator.com/item?id=15414544); [HN 36312027](https://news.ycombinator.com/item?id=36312027); [HN 15983758](https://news.ycombinator.com/item?id=15983758); [HN 44105651](https://news.ycombinator.com/item?id=44105651)
- **dev.to.** The 2026 "Ways to Learn Vim" guide ranks: (1) vimtutor, (2) "cold turkey" via editor extensions, (3) mobile apps (VimKata), (4) YouTube ("motivating but passive"), (5) Vim Adventures ("covering basic motions only. Development largely stagnant"), (6) Practical Vim ("too dense for Day 1"), (7) cheat sheets. **Caveat:** the author founded VimKata, which he ranks #3. — [dev.to, 2026-03-30](https://dev.to/azborovskyi/ways-to-learn-vim-in-2026-a-complete-beginners-guide-ma)
- **Paid courses.**
  - ThePrimeagen's Frontend Masters "VIM Fundamentals": published 2021-04-20, 4h14m. It covers motions, macros, registers, search/replace, quickfix, vimrc and plugins (vim-plug, fzf). Companion repo: ThePrimeagen/vim-fundamentals. — [Frontend Masters](https://frontendmasters.com/courses/vim-fundamentals/introduction/); [GitHub](https://github.com/ThePrimeagen/vim-fundamentals)
  - Frontend Masters' "Developer Productivity, v2 with ThePrimeagen" preview has about 230k YouTube views. — [YouTube 03KsS09YS4E](https://www.youtube.com/watch?v=03KsS09YS4E)
  - Drew Neil's paid Vimcasts course was praised on HN. — [HN 35928141](https://news.ycombinator.com/item?id=35928141)
  - vim.so's author reported about $10k revenue. — [HN 26825566](https://news.ycombinator.com/item?id=26825566)

### Inferences
- The "canon" in curated lists is older, text-first material: Practical Vim, vimtutor, the user manual, Seven habits and grok-vi. The 2020s additions with real traction are free GitHub texts and plugins: Learn-Vim, vim-be-good, hardtime.nvim and Vimtutor Sequel. Paid web products rarely enter curated lists.

### Gaps
- Mastering Vim Quickly (Jovica Ilic), Mastering Vim (Ruslan Osipov, Packt), Modern Vim, egghead and Udemy courses barely appear in the lists or on HN (Mastering Vim Quickly: 4 HN mentions). No vote-based ranking was found for them, because Slant returned 403.
- Vim Hero and Vim Genius have essentially no HN or curated-list footprint beyond an awesome-vim entry for Vim Genius.

## 4. YouTube creators' influence and approximate view counts

### Takeaway
YouTube's Vim-learning audience is dominated by **ThePrimeagen**:
- "0 to LSP": about 2.0M views
- "Vim As Your Editor – Introduction": about 1.45M views
- "Why I use Vim in 2022": about 559k views
- "How to Vim in 2023": about 511k views

Next come **TJ DeVries**: "The Only Video You Need to Get Started with Neovim" (about 1.05M views) and "Effective Neovim: Instant IDE" (about 936k views), both tied to kickstart.nvim. Then **typecraft**'s free Neovim course (EP1 about 965k views). Generic primers also have large audiences: Fireship's Vim in 100 Seconds (about 1.43M views) and freeCodeCamp (about 963k views). These creators steer viewers toward configuring Neovim (kickstart.nvim at 31.6k stars, LazyVim) and toward vim-be-good. Older thoughtbot talks remain the classic "Vim as a language" teaching: about 988k and 647k views.

### Cited Findings (views as shown on YouTube search, 2026-10-11)
- **ThePrimeagen:**
  - "0 to LSP: Neovim RC From Scratch": **2,010,954 views** (about 3 years old) — [YouTube w7i4amO_zaE](https://www.youtube.com/watch?v=w7i4amO_zaE)
  - "Vim As Your Editor – Introduction": **1,451,336** (about 3 years) — [X6AR2RMB5tE](https://www.youtube.com/watch?v=X6AR2RMB5tE)
  - "Advanced Motions P1": 387,949; "Horizontal": 365,831; "Advanced Motions P2": 234,202; "Vertical Movements": 203,175 — [qZO9A5F6BZs](https://www.youtube.com/watch?v=qZO9A5F6BZs); [5JGVtttuDQA](https://www.youtube.com/watch?v=5JGVtttuDQA); [uL9oOZStezw](https://www.youtube.com/watch?v=uL9oOZStezw); [KfENDDEpCsI](https://www.youtube.com/watch?v=KfENDDEpCsI)
  - "Why I use Vim in 2022": 559,001; "How to Vim in 2023: Tips and Tricks": 510,579 — [D4YTJ2W5q4Y](https://www.youtube.com/watch?v=D4YTJ2W5q4Y); [FrMRyXtiJkc](https://www.youtube.com/watch?v=FrMRyXtiJkc)
  - "VimTutor World Record Speed Run": 228,699 — [y6VJBeZEDZU](https://www.youtube.com/watch?v=y6VJBeZEDZU)
  - "Neovim Config – Part 1 – Lazy Vim" (TheVimeagen channel): 298,443 — [ZWWxwwUsPNw](https://www.youtube.com/watch?v=ZWWxwwUsPNw)
  - The vim-be-good highlight clip has only about 21,876 views. Interview "ThePrimeagen On How To Learn Vim" (Tech Over Tea): 49,288. — [Wq8TRKCHbWo](https://www.youtube.com/watch?v=Wq8TRKCHbWo); [WCWJHGEkglQ](https://www.youtube.com/watch?v=WCWJHGEkglQ)
- **TJ DeVries:**
  - "The Only Video You Need to Get Started with Neovim": **1,053,539** (about 2 years) — [m8C0Cq9Uv9o](https://www.youtube.com/watch?v=m8C0Cq9Uv9o)
  - "Effective Neovim: Instant IDE": **935,730** (about 3 years) — [stqUbv-5u2s](https://www.youtube.com/watch?v=stqUbv-5u2s)
  - "PDE: A different take on editing code": 87,892 — [QMVIJhC9Veg](https://www.youtube.com/watch?v=QMVIJhC9Veg)
  - TJ's videos are widely recommended for newcomers, but parts are now outdated (they predate the move from Packer to lazy.nvim). — [mischavandenburg.com](https://mischavandenburg.com/zet/articles/kickstart-nvim/); [HN 38150486](https://news.ycombinator.com/item?id=38150486)
  - TJ also published "advent-of-nvim." — [GitHub tjdevries/advent-of-nvim](https://github.com/tjdevries/advent-of-nvim)
- **typecraft:**
  - "From 0 to IDE in NEOVIM from scratch | FREE COURSE // EP 1": **964,614** — [zHTeCSVAFNY](https://www.youtube.com/watch?v=zHTeCSVAFNY)
  - EP 2: 295,892; EP 5: 163,533
  - "30 Vim commands you NEED TO KNOW": 312,861 — [RSlrxE21l_k](https://www.youtube.com/watch?v=RSlrxE21l_k)
- **General primers:**
  - Fireship "Vim in 100 Seconds": **1,426,121** (about 5 years) — [-txKSRn0qeA](https://www.youtube.com/watch?v=-txKSRn0qeA)
  - freeCodeCamp "Vim Tutorial for Beginners": **963,056** (about 4 years, 1h14m, by NeuralNine's Florian Dedov) — [RZ4p-saaQkc](https://www.youtube.com/watch?v=RZ4p-saaQkc); [Class Central](https://www.classcentral.com/course/freecodecamp-vim-tutorial-for-beginners-270279)
  - tutoriaLinux "Vim Basics in 8 Minutes": 601,248 (about 8 years) — [ggSyF1SVFr4](https://www.youtube.com/watch?v=ggSyF1SVFr4)
  - Dreams of Code "Turn VIM into a full featured IDE with only one command": 837,935 — [Mtgo-nP_r8Y](https://www.youtube.com/watch?v=Mtgo-nP_r8Y)
- **Motions-focused (recent):**
  - Dispatch "Vim Motions for absolute beginners!!!": 375,489 — [lWTzqPfy1gE](https://www.youtube.com/watch?v=lWTzqPfy1gE)
  - DevOps Toolbox "Give Me 20 Minutes and I'll Make You a Vim Motions Expert": 337,085 (about 1 year) — [z4eA2eC28qg](https://www.youtube.com/watch?v=z4eA2eC28qg)
  - Henry Misc "Vim Motions & Tricks I Wish I Learned Sooner": 151,344 — [RdyfT2dbt78](https://www.youtube.com/watch?v=RdyfT2dbt78)
  - Sebastian Daschner "Vim Tips I Wish I Knew Earlier": 145,794 — [5BU2gBOe9RU](https://www.youtube.com/watch?v=5BU2gBOe9RU)
- **VS Code + Vim specific:**
  - Melkey "Mastering VIM Motions in VSCode": 212,956 — [GST8we5uABo](https://www.youtube.com/watch?v=GST8we5uABo)
  - "Getting Started with Vim in Visual Studio Code": 253,412 — [h-epcklOC_g](https://www.youtube.com/watch?v=h-epcklOC_g)
  - Official VS Code channel "Min/Maxxing VS Code by Stripping the UI and Adding Vim": 118,589 — [F7ZEKjDia1c](https://www.youtube.com/watch?v=F7ZEKjDia1c)
- **Older classics still drawing views:**
  - thoughtbot "How to Do 90% of What Plugins Do (With Just Vim)" (Max Cantor): **988,299** (about 10 years) — [XA2WjJbmmoM](https://www.youtube.com/watch?v=XA2WjJbmmoM)
  - thoughtbot "Mastering the Vim Language" (Chris Toomey): **646,527** (about 11 years) — [wlR5gYd6um0](https://www.youtube.com/watch?v=wlR5gYd6um0)
  - Luke Smith "Vimtutor Let's Play": 250,600; "After Vimtutor": 76,414 — [d8XtNXutVto](https://www.youtube.com/watch?v=d8XtNXutVto); [jUfw7aHD_xY](https://www.youtube.com/watch?v=jUfw7aHD_xY)
- **HN cross-references.** In the 2023 Vimcasts thread, a commenter pointed people to Primeagen's "Vim As Your Editor" playlist as the modern counterpart. — [HN 35928141](https://news.ycombinator.com/item?id=35928141). Comment mentions of "primeagen" on HN are almost entirely post-2022 (127 of 129). — [HN Algolia API](https://hn.algolia.com/api)

### Inferences
- The most-viewed creator videos are about **configuring Neovim** ("0 to LSP," TJ's kickstart videos, typecraft EP1), not about editing technique. The motion and editing series (Vim As Your Editor parts, thoughtbot "Mastering the Vim Language") draw roughly 200k–650k per part. That pattern matches the HN complaints about people spending time on config instead of editing skill.
- vim-be-good's reach likely comes through Primeagen's main videos and streams, not a dedicated video. That inference rests on the small clip view count plus 4.6k GitHub stars.
- For a VSCodeVim user, motion-only content (Primeagen's Vim As Your Editor series, thoughtbot "Mastering the Vim Language," the barbarianmeetscoding motions article) transfers directly. Neovim config videos do not.

### Gaps
- Like and comment sentiment on YouTube was not collected. The view counts are snapshots from the search pages and are rounded by age ("3y ago").
- No reliable view figures were found for paid course platforms (Udemy enrollments, Frontend Masters completions).

## 5. Consensus on what takes someone from intermediate to very proficient

### Takeaway
Across HN, Vi.SE and the curated lists, the advice for the jump is consistent and is not "another tutorial":
1. Internalize the **operator + motion/text-object grammar** (grok vi, "Mastering the Vim Language," "Mastering Vim Grammar").
2. Practice **"sharpen the saw"**: notice an inefficiency, look up the native solution, adopt it (Bram's *Seven habits*, Vi.SE 4111).
3. Read **Practical Vim** and the **user manual** (`:h usr_toc`).
4. Use **feedback tools** that catch bad habits (hardtime.nvim, VimGolf replays, vim-be-good drills).
5. Use it **daily without escape hatches**.

Dissent: several veteran HN users argue that optimizing keystrokes gives diminishing returns, and that holding down `j` or using the mouse is fine.

### Cited Findings
- **Grammar over memorization.** The grok-vi answer (2,844 SO votes): "you're speaking a language… `y` is a verb." — [SO 1218390](https://stackoverflow.com/questions/1218390/what-is-your-most-productive-shortcut-with-vim/1220118#1220118). Supporting sources: vim-galore calls that answer "A real gem" ([vim-galore](https://github.com/mhinz/vim-galore)); "Mastering the Vim Language" has about 647k views ([YouTube](https://www.youtube.com/watch?v=wlR5gYd6um0)); "Mastering Vim Grammar" (2025, 60 pts) ([HN 44105651](https://news.ycombinator.com/item?id=44105651)).
- **Incremental "sharpen the saw."** The top Vi.SE answer for "Learning Vim after vimtutor" (33 votes): learn a few things at a time, fix inefficiencies as you find them, keep a near-blank vimrc, look for native solutions before plugins. — [vi.SE 4111](https://vi.stackexchange.com/questions/4111/learning-vim-after-vimtutor)
- **The "comfortable to expert" HN subthread (vim.so, 2021) recommended:**
  - Learn Vimscript the Hard Way
  - the vimtricks.com newsletter
  - questioning your common edits (ci", ct<x>, $)
  - VimGolf ("where I learned about '.'")
  - working "without the mouse because your editor will always give you a way out of learning… Learn to use and love :help"
  - f/F with ; and ,
  - Practical Vim
  - `:h user-manual`
  - "learning q" (macros)

  — [HN 25846347](https://news.ycombinator.com/item?id=25846347)
- **Bad-habit correction.** A 10-year user lists persistent habits: `jjjj` instead of `4j`, `bcw` instead of `ciw`, `Vjjj` + `y` instead of `3yy`. — [HN 34930113](https://news.ycombinator.com/item?id=34930113). A 2017 commenter wished for "a plugin that reminded me how to do things more efficiently". hardtime.nvim later filled that niche (214 pts, 2025). — [HN 15414544](https://news.ycombinator.com/item?id=15414544); [HN 44020734](https://news.ycombinator.com/item?id=44020734)
- **Immersion.** "If you code full time just force yourself to use it. Disable arrow keys…" and "Learn a new key sequence that solves an immediate problem… add it to their set of tools." — [HN 28909432](https://news.ycombinator.com/item?id=28909432). "How to learn ViM: Stop reading articles about how to learn ViM, and start using ViM." — [HN 15414544](https://news.ycombinator.com/item?id=15414544)
- **Advanced users ask for advanced material** (`N%`, `:argdo normal @q`). The answers were Practical Vim, the user manual and Vimtutor Sequel. — [HN 33306778](https://news.ycombinator.com/item?id=33306778); [HN 41144843](https://news.ycombinator.com/item?id=41144843)
- **Dissent.** "To move fast, use the mouse… It's not a game worth playing" (on hyper-optimizing motions, 2023). — [HN 36312027](https://news.ycombinator.com/item?id=36312027). "I honestly don't see the downside of repeating h or j" (10+ year user, 2025). — [HN 44020734](https://news.ycombinator.com/item?id=44020734). "Vim is about gaining mastery rather than actual efficiency. And it's great." — [HN 36312027](https://news.ycombinator.com/item?id=36312027)
- **Concrete higher-level features highlighted in top threads:**
  - `])`/`]}` unmatched-bracket motions, Ctrl-e/y/f/b, H/M/L, `N%` — [HN 36312027](https://news.ycombinator.com/item?id=36312027)
  - Ctrl-R register insertion (98 votes) — [SO 1218390](https://stackoverflow.com/questions/1218390/what-is-your-most-productive-shortcut-with-vim/1220118#1220118)
  - `:%s//…/` reusing the last search (206 votes) — [SO 1276403](https://stackoverflow.com/questions/1276403/simple-vim-commands-you-wish-youd-known-earlier)

### Inferences
- The consensus path for a Neovim 0.12 + VSCodeVim user aiming high runs in this order:
  1. vimtutor chapters 1–2 / `:Tutor`, then Vimtutor Sequel
  2. the user manual (`:h usr_toc`, especially the editing-efficiency chapters)
  3. Practical Vim (its tips are core-Vim and mostly portable to VSCodeVim, except Ex-heavy tips)
  4. continuous habit correction with hardtime.nvim in Neovim, plus VimGolf for exposure to idioms

  vim-be-good and the web games are for warm-up drills, not the ceiling.
- Neovim-config video content (Primeagen, TJ, typecraft) is the most-watched material, but practitioners do not credit it with editing proficiency.

### Gaps
- No quantitative study (e.g. a survey) links any resource to measured proficiency gains. All of the evidence above is testimonial.
- Ex-command and macro mastery for VSCodeVim specifically (which Ex features VSCodeVim supports) was not researched here.
