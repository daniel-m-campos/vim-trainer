# Vim/Neovim Learning & Practice Resources: Popularity Metrics, Pricing, Status

All numbers observed **2026-10-11** unless noted. GitHub numbers come from the GitHub REST API (`api.github.com/repos/...`). The "last push" date is `pushed_at`, i.e. the latest push to any branch. It is a close proxy for the last commit date, but not identical to it.

## What are the current GitHub stars for each open-source resource?

### Takeaway
Learn Vim the Smart Way (15.2k stars) is the most-starred learning-specific repo. Next come vim-be-good (4.6k), hardtime.nvim (3.9k) and precognition.nvim (1.4k). The browser game VIM Master (renzorlive/vimmaster, 1.7k) is a notable newcomer that is still active in 2026. Of the plugins, hardtime.nvim and precognition.nvim are actively developed. vim-be-good has had no push since Dec 2024.

### Cited Findings
Learning-specific repos (stars / forks / last push / format):
- **iggredible/Learn-Vim** (Learn Vim the Smart Way): 15,246 stars / 1,136 forks / last push 2026-09-07. Free online book. Not archived. — [GitHub](https://github.com/iggredible/Learn-Vim)
- **ThePrimeagen/vim-be-good**: 4,572 stars / 184 forks / last push 2024-12-05. Neovim plugin game (motion drills). Not archived. — [GitHub](https://github.com/ThePrimeagen/vim-be-good)
- **m4xshen/hardtime.nvim**: 3,857 stars / 48 forks / last push 2026-10-02. Neovim plugin that blocks repeated keys and suggests better motions (habit trainer). — [GitHub](https://github.com/m4xshen/hardtime.nvim)
- **renzorlive/vimmaster** ("VIM Master: in-browser game that teaches core Vim motions and editing commands"): 1,713 stars / 71 forks / last push 2026-07-16. — [GitHub](https://github.com/renzorlive/vimmaster)
- **tris203/precognition.nvim**: 1,387 stars / 17 forks / last push 2026-10-11. Neovim plugin that shows available motion hints inline. — [GitHub](https://github.com/tris203/precognition.nvim)
- **takac/vim-hardtime** (the older Vim-script predecessor of hardtime.nvim): 903 stars / 30 forks / last push 2022-05-06. — [GitHub](https://github.com/takac/vim-hardtime)
- **igrigorik/vimgolf** (the VimGolf CLI/site code): 780 stars / 64 forks / last push 2024-07-04. — [GitHub](https://github.com/igrigorik/vimgolf)
- **egaga/openvim** (OpenVim interactive tutorial): 636 stars / 75 forks / last push 2026-07-29. — [GitHub](https://github.com/egaga/openvim)
- **ThePrimeagen/vim-with-me**: 348 stars / 30 forks / last push 2025-03-06. — [GitHub](https://github.com/ThePrimeagen/vim-with-me)
- **carbonfive/vimtronner** ("A multi-player Vim trainer"): 313 stars / last push 2018-11-21. Abandoned. — [GitHub](https://github.com/carbonfive/vimtronner)
- **tris203/hawtkeys.nvim** (keymap suggestion plugin): 253 stars / last push 2026-03-09. — [GitHub](https://github.com/tris203/hawtkeys.nvim)
- **canadaduane/VimKata** ("Deliberate Practice lessons for learning the Vim Editor"): 145 stars / last push 2010-08-02. Abandoned. — [GitHub](https://github.com/canadaduane/VimKata)
- **antonk52/bad-practices.nvim**: 145 stars / last push 2025-04-25. — [GitHub](https://github.com/antonk52/bad-practices.nvim)
- **kaisunc/vscodevimacademy** (VS Code extension/game for Vim motions): 78 stars / last push 2023-10-02. — [GitHub](https://github.com/kaisunc/vscodevimacademy)
- **vicramon/vimgenius** (Vim Genius source): 21 stars / 7 forks / last push 2023-05-04. — [GitHub](https://github.com/vicramon/vimgenius)
- **vimcasts/vimcasts.org**: 30 stars / last push 2023-01-18. — [GitHub](https://github.com/vimcasts/vimcasts.org)
- Small 2026 newcomers: error311/vimmonsters-academy (22 stars, browser retro game, last push 2026-04-26) and jjimenezgarcia/vim-caddie (11 stars, last push 2026-08-27). — [GitHub search API "vim motions game"](https://api.github.com/search/repositories?q=vim+motions+game&sort=stars)

Context repos (editors and guides):
- **mhinz/vim-galore** (guide): 18,015 stars / last push 2023-12-22. — [GitHub](https://github.com/mhinz/vim-galore)
- **nvim-lua/kickstart.nvim** (starter config, often used as a learning path): 31,573 stars / 46,429 forks / last push 2026-10-05. — [GitHub](https://github.com/nvim-lua/kickstart.nvim)
- **vim/vim**: 41,197 stars / 6,158 forks / last push 2026-10-10. **neovim/neovim**: 103,013 stars / 7,165 forks / last push 2026-10-11. These matter because vimtutor and `:Tutor` ship inside them. — [vim/vim](https://github.com/vim/vim), [neovim/neovim](https://github.com/neovim/neovim)
- **VSCodeVim/Vim**: 15,223 stars / 1,468 forks / last push 2026-10-10. — [GitHub](https://github.com/VSCodeVim/Vim)

VS Code Marketplace (Marketplace gallery API, observed 2026-10-11):
- **"Learn Vim"** (vintharas.learn-vim): 331,516 installs; average rating 4.95 from 65 ratings; last updated 2022-05-30. — [Marketplace](https://marketplace.visualstudio.com/items?itemName=vintharas.learn-vim)
- **VSCodeVim** (vscodevim.vim): 9,123,552 installs; 4.09 from 395 ratings; last updated 2025-12-14. — [Marketplace](https://marketplace.visualstudio.com/items?itemName=vscodevim.vim)
- **Vim Cheatsheet** (AndenetAlexander.vim-cheatsheet): 129,109 installs; last updated 2022-07-05. — [Marketplace](https://marketplace.visualstudio.com/items?itemName=AndenetAlexander.vim-cheatsheet)

Usage counts for non-GitHub resources:
- **VimGolf**: 621 challenges, 45,161 "active golfers", and 512,007 total entries shown on the homepage. Entries per challenge range from 42 to 1,829. The latest listed challenge is "Filling braces" (328 entries). CLI version 0.5.0. — [vimgolf.com](https://www.vimgolf.com/)
- **Goodreads, Practical Vim** (all editions aggregated): 4.50 average from 1,465 ratings and 145 reviews. — [Goodreads](https://www.goodreads.com/book/show/13607232-practical-vim)
- **Goodreads, Modern Vim**: 3.69 average from 166 ratings and 18 reviews. — [Goodreads](https://www.goodreads.com/book/show/36517607-modern-vim)
- **Goodreads, Mastering Vim (Osipov, 1st ed.)**: 3.86 from 29 ratings. The 2nd ed., subtitled "Efficient and effortless editing with Vim and Vimscript", has 4.0 from 2 ratings. — [Goodreads 1st ed](https://www.goodreads.com/book/show/43497352-mastering-vim), [Goodreads 2nd ed](https://www.goodreads.com/book/show/207052933-mastering-vim)
- **ThePrimeagen "VIM Fundamentals"** (Frontend Masters, now master.dev): rated 4.9/5. The page does not show a rating count. — [master.dev course page](https://master.dev/courses/vim-fundamentals/)
- **Udemy** (search-engine snippet only, not verified on the Udemy pages): "Vim Masterclass" is a Bestseller with 4.8 from 6,155 ratings and 40,459 students. "Vim, aumenta tu velocidad de desarrollo" has 4.8 from 11,125 ratings and 77,940 students. "Vim Essentials in 1 Hour" has 4.4 from 1,328 ratings and 12,694 students. — [Udemy Vim Masterclass](https://www.udemy.com/course/vim-commands-cheat-sheet/), [Udemy Spanish course](https://www.udemy.com/course/vim-aumenta-tu-velocidad-de-desarrollo/), [Udemy Vim Essentials](https://www.udemy.com/course/vim-essentials/)

### Inferences
- Ranked by stars, Learn-Vim far outweighs the trainer plugins. Among in-editor trainers, vim-be-good still leads on stars, but hardtime.nvim is close and still actively developed.
- The VS Code "Learn Vim" extension has a large install base (~330k) but no update since 2022.

### Gaps
- No public repos were found for "Vim Racer", "vimified" as a trainer, or "VimTrainer". The GitHub "vimified" hits are dotfiles/configs, and "vim-racer" is Rust's Racer completion. I could not verify that these trainers exist under those names.
- Amazon ratings were not collected; Amazon pages could not be scraped reliably.
- No Goodreads or Amazon ratings were collected for Mastering Vim Quickly or Learn Vim the Smart Way.
- The Udemy figures come from search snippets and were not confirmed on the course pages.

## What are the current prices and pricing models for paid ones?

### Takeaway
Most resources are free. Paid options:
- Vim Adventures: time-limited licence ($35 or $40 for 6 months).
- Vim Hero: one-time $20 after 12 free lessons.
- Pragmatic Bookshelf ebooks: $26.95 (Practical Vim) and $24.95 (Modern Vim).
- Mastering Vim Quickly: Gumroad packages at $79 and $129.
- ThePrimeagen's course: requires a master.dev (formerly Frontend Masters) subscription at $39/mo or $390/yr.

### Cited Findings
- **Vim Adventures**: "Game-Only" licence $35 for 6 months, or "Game & Challenges" $40 for 6 months (adds timed challenges and a macro level). Group licences are available on request. The game has 13 main levels and is browser-based. Unlocked levels can be replayed free, but progression needs a licence. Copyright reads "© Doron Linder, 2012–2026". — [vim-adventures.com](https://vim-adventures.com/)
- **Vim Hero** (vim-hero.com): free tier is "First 12 lessons free, no account required". "Full Access" is $20 USD to "Unlock all 50+ lessons". These offers come from the page's schema.org Offer data. — [vim-hero.com](https://www.vim-hero.com/)
  - Search snippets describe the $20 as a one-time lifetime "early adopter" price, normally $50. I did not see this on the page itself. — [WebSearch summary of vim-hero.com](https://www.vim-hero.com/)
- **Practical Vim, 2nd ed.** (Pragmatic Bookshelf): ebook $26.95 (PDF/epub/mobi), 354 pages, published Oct 2015, "In Print". Latest printing P2.0 (2017-01-17) was "Updated for Vim 8 and errata cleared". — [pragprog.com](https://pragprog.com/titles/dnvim2/practical-vim-second-edition/)
- **Modern Vim**: ebook $24.95, 166 pages, May 2018, "In Print", 28 tips covering Vim 8 and Neovim. — [pragprog.com](https://pragprog.com/titles/modvim/modern-vim/)
- **Mastering Vim Quickly** (Jovica Ilic): Gumroad "Professional Training Package" $79 and "Premium Training Package" $129. — [Gumroad Professional](https://jovica.gumroad.com/l/YzaRR), [Gumroad Premium](https://jovica.gumroad.com/l/gcsRg)
  - The Professional package includes the book plus screencasts. Premium adds the bonus books. — [WebSearch summary](https://jovica.gumroad.com/l/gcsRg)
  - A $39 "Standard Edition" is mentioned in a search summary, but its source page (jovicailic.org/mastering-vim-quickly-v1/) now returns 404, so it is unverified. — [jovicailic.org](https://jovicailic.org/mastering-vim-quickly-v1/)
  - The paperback was published in 2018 with 143 pages; Walmart lists it at $25.40. — [Walmart](https://www.walmart.com/ip/Mastering-Vim-Quickly-From-WTF-to-OMG-in-no-time-Paperback-by-Jovica-ILIC-9781983325748/917608969)
  - The current official page lists the book as "Status: Completed" with Amazon and digital links, but shows no prices. — [jovica.org](https://jovica.org/projects/mvq/mastering-vim-quickly/)
- **ThePrimeagen "VIM Fundamentals"**: 4h14m course published 2021-04-20. frontendmasters.com/courses/vim-fundamentals now 301-redirects to master.dev. — [master.dev course](https://master.dev/courses/vim-fundamentals/)
  - Subscription: $39/month or $390/year. Team plans are $24.50/seat/month or $245/seat/year. There is also a free tier of 5 courses. — [master.dev/join](https://master.dev/join/)
- **Free resources**:
  - Vim Genius: "It's free and you don't need to sign up". — [vimgenius.com](http://www.vimgenius.com/)
  - OpenVim, Learn-Vim, vim-be-good, hardtime.nvim and precognition.nvim are free and open source (see the repos above).
  - VimGolf is free to play. — [vimgolf.com](https://www.vimgolf.com/)
  - vimtutor and `:Tutor` are bundled with Vim and Neovim. — [vimhelp pi_tutor](https://vimhelp.org/pi_tutor.txt.html)

### Inferences
- Vim Adventures is the only subscription-like product (a recurring 6-month licence). Vim Hero and the books are one-time purchases. The Primeagen course costs a general platform subscription, not a per-course fee.

### Gaps
- Vim Hero's /pricing URL returns 404, and the "$50 regular price" claim could not be confirmed.
- No Mastering Vim (Osipov, Packt) price was collected.
- No paperback prices were collected for the Pragmatic books; pragprog sends readers to Bookshop.org.

## Which are actively maintained vs abandoned?

### Takeaway
Actively maintained (updates in 2026):
- hardtime.nvim, precognition.nvim, Learn-Vim, OpenVim, vimmaster.
- vimtutor/`:Tutor`, which ship with the editors.
- Vim Adventures and VimGolf, which are live sites with 2026 copyright or new challenges.

Dormant or abandoned:
- Vimcasts: last episodes Feb 2018.
- vim-be-good: no push since Dec 2024.
- Vim Genius: code last pushed 2023, but the site is still up.
- VS Code "Learn Vim": last update 2022.
- vim-hardtime (2022), VimKata (2010), vimtronner (2018).

The books are in print but not updated: Practical Vim was last revised in 2017 and Modern Vim was published in 2018.

### Cited Findings
- **Vimcasts**: the archive lists 76 episodes. The newest month heading is "February 2018" (Neovim terminal episodes), after 2017 episodes and a gap back to 2014. — [vimcasts.org archive](http://vimcasts.org/episodes/archive/)
- **vimtutor (Vim)**: now has 2 chapters (`vimtutor -c 2`). Vim's interactive tutor plugin (`:Tutor`, vim-01-beginner and vim-02-beginner) "replaces the venerable vimtutor system". — [vimhelp pi_tutor.txt](https://vimhelp.org/pi_tutor.txt.html), [vim_dev commit: add chapter two](https://groups.google.com/g/vim_dev/c/HLlCKe1B918)
- **Neovim `:Tutor`**: the source file is in neovim/runtime/tutor. — [neo.vimhelp pi_tutor](https://neo.vimhelp.org/pi_tutor.txt.html), [neovim tutor.tutor](https://github.com/neovim/neovim/blob/master/runtime/tutor/tutor.tutor)
- **Vim Genius**: the site was live on 2026-10-11 (HTTP 200) and describes itself as a "timed flashcard-style game". Repo last pushed 2023-05-04. — [vimgenius.com](http://www.vimgenius.com/), [GitHub](https://github.com/vicramon/vimgenius)
- **OpenVim**: site live (HTTP 200), with Tutorial and Practice modes. Repo last pushed 2026-07-29. — [openvim.com](https://openvim.com/), [GitHub](https://github.com/egaga/openvim)
- **VimGolf**: site active with 621 challenges. The igrigorik/vimgolf repo was last pushed 2024-07-04. — [vimgolf.com](https://www.vimgolf.com/), [GitHub](https://github.com/igrigorik/vimgolf)
- **Vim Hero**: site live with 2026 copyright. — [vim-hero.com](https://www.vim-hero.com/)
- **Mastering Vim (Osipov)**: a 2nd edition exists on Goodreads ("Efficient and effortless editing with Vim and Vimscript"). — [Goodreads](https://www.goodreads.com/book/show/207052933-mastering-vim)
- **Vim user manual** (usr_*.txt): ships with Vim and is hosted at vimhelp.org. It is maintained along with the vim/vim repo (last push 2026-10-10). — [vimhelp usr_01](https://vimhelp.org/usr_01.txt.html), [vim/vim](https://github.com/vim/vim)
- **Primeagen course**: 2021 course still listed on master.dev. — [master.dev](https://master.dev/courses/vim-fundamentals/)

### Inferences
- vim-be-good is "stable but unmaintained": it is unarchived but has had no pushes for about 22 months as of Oct 2026.
- Neovim users wanting an in-editor trainer that is maintained in 2026 have hardtime.nvim and precognition.nvim.

### Gaps
- Whether Vim Hero is still adding lessons could not be determined; no changelog was found.
- The publication date of Osipov's 2nd edition and the date of VimGolf's newest challenge were not captured.
- Mastering Vim Quickly's last content update is unknown.

## Which are Neovim-native (run in your own editor) vs browser-based?

### Takeaway
In-editor resources:
- Neovim plugins: vim-be-good (Neovim only), hardtime.nvim, precognition.nvim, hawtkeys.nvim, bad-practices.nvim.
- Built into the editors: vimtutor / `:Tutor`.
- VimGolf: played in your local Vim through its CLI, with the website for the leaderboard.

Browser-based:
- Games: Vim Adventures, Vim Hero, OpenVim, Vim Genius, VIM Master (vimmaster).
- Reading: Vimcasts (video) and Learn-Vim (book).

VS Code:
- "Learn Vim" and vscodevimacademy run inside VS Code.

### Cited Findings
- **vim-be-good**: Neovim plugin, a game in a buffer — [GitHub](https://github.com/ThePrimeagen/vim-be-good)
- **hardtime.nvim**: Neovim plugin — [GitHub](https://github.com/m4xshen/hardtime.nvim)
- **precognition.nvim**: Neovim plugin — [GitHub](https://github.com/tris203/precognition.nvim)
- **`:Tutor`**: built into Vim and Neovim — [neo.vimhelp](https://neo.vimhelp.org/pi_tutor.txt.html)
- **VimGolf**: CLI version 0.5.0 runs challenges in the local editor; scores go to vimgolf.com — [vimgolf.com](https://www.vimgolf.com/)
- **Vim Adventures**: browser canvas game, requires a physical keyboard — [vim-adventures.com](https://vim-adventures.com/)
- **Vim Hero**: "Every lesson puts you inside a real editor" in the browser, with dynamically generated challenges — [vim-hero.com](https://www.vim-hero.com/)
- **VIM Master**: in-browser game — [GitHub](https://github.com/renzorlive/vimmaster)
- **Vim Genius**: browser flashcards — [vimgenius.com](http://www.vimgenius.com/)
- **OpenVim**: browser tutorial — [openvim.com](https://openvim.com/)
- **VS Code "Learn Vim"**: VS Code extension — [Marketplace](https://marketplace.visualstudio.com/items?itemName=vintharas.learn-vim)

Format summary (for the table):

| Resource | Format | Runs where |
|---|---|---|
| vimtutor / :Tutor | interactive tutorial | in editor |
| vim-be-good | game/drills | Neovim |
| hardtime.nvim | habit trainer | Neovim |
| precognition.nvim | hint overlay | Neovim |
| VimGolf | puzzles | local editor + web |
| Vim Adventures | game | browser |
| Vim Hero | lessons/drills | browser |
| OpenVim | tutorial | browser |
| Vim Genius | flashcards | browser |
| Practical/Modern Vim, Mastering Vim, MVQ, Learn-Vim | books | read |
| Vimcasts | screencasts | web |
| Primeagen VIM Fundamentals, Udemy | video courses | web |

### Inferences
- VimGolf is the only competitive puzzle format with large-scale participation data (45k golfers, 512k entries).

### Gaps
- Whether vim-be-good works on current Neovim releases was not tested.
