# tools

Repo maintenance scripts. Standard-library Python 3.12; run them from the repo root.

## export_public.py

`python tools/export_public.py --out DIR` copies the public source tree into `DIR`, a
fresh directory with no `.git`, and then sweeps it. The tree is every file that
`git ls-files --cached --others --exclude-standard` lists (tracked files plus new files
that `.gitignore` does not hide), minus the `[exclude]` globs in `public_manifest.toml`.
The sweep searches every text file for the `[forbidden]` regexes, case-insensitively,
and prints each hit as `path:line: text`; an `[[allow]]` entry lets named words through in
named paths, with a reason. Any hit makes the script exit 1. `--check` sweeps the
current tree in place and copies nothing. A run takes well under a second.

The manifest is the record of what is left out of the public tree and why. This
README, the script and the manifest are themselves excluded: the word list and the
exclude list describe what the planning repo holds. To change
what is excluded or forbidden, edit `public_manifest.toml`, run
`python tools/export_public.py --check`, and fix each hit in the file or, when the word
is legitimate there (for example a Playwright API name), add a short `[[allow]]` entry
with its reason.

## GitHub Pages

`.github/workflows/deploy.yml` builds the site and publishes it to
https://daniel-m-campos.github.io/vim-trainer/ on every push to `main`. It needs one manual
setting in the repository: Settings > Pages > Build and deployment > Source: "GitHub
Actions". It can also be started by hand from the Actions tab (`workflow_dispatch`).

First deploy, once, after the public repo exists and `main` is pushed:

1. Set Pages to deploy from GitHub Actions:
   `gh api -X POST repos/daniel-m-campos/vim-trainer/pages -f build_type=workflow`
   (if Pages already exists, use `-X PUT` instead).
2. Check that the `github-pages` environment lets `main` deploy (Settings > Environments >
   github-pages > Deployment branches). It does by default.
3. Start the deploy with `gh workflow run deploy.yml --repo daniel-m-campos/vim-trainer`
   and follow it with `gh run watch --repo daniel-m-campos/vim-trainer`.
4. Open https://daniel-m-campos.github.io/vim-trainer/#practice and answer the first-visit
   questions. An exercise editor should appear, with no `build-sample` warning in the
   browser console.
5. Open `#settings` and click "Sources & attribution". It should show
   `build/ATTRIBUTION.md` as plain text.

The first run has no content-build cache, so the Neovim stage runs in full. Later deploys
reuse the cache that `ci.yml` saves under the same key.
