"""Export the public source tree and sweep it for words that must not ship.

Usage::

    python tools/export_public.py --out DIR      # copy the public tree into DIR, then sweep it
    python tools/export_public.py --check        # sweep the current tree in place, copy nothing

The file list is ``git ls-files --cached --others --exclude-standard`` (tracked files plus
new files that .gitignore does not hide) minus the ``[exclude]`` globs in
``tools/public_manifest.toml``. Every text file is then searched for the ``[forbidden]``
regexes, case-insensitive, except where an ``[[allow]]`` entry covers that path and word.
Each hit prints as ``path:line: text``. The exit code is 1 when there is any hit.
Standard library only (Python 3.12).
"""

import argparse
import fnmatch
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parent.parent
MANIFEST: Final = ROOT / "tools" / "public_manifest.toml"


# Public Functions =================================================================================

def main(argv: list[str] | None = None) -> int:
    """Parse arguments, export and sweep; return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, help="fresh directory to copy the public tree into")
    parser.add_argument("--check", action="store_true", help="sweep the current tree only; copy nothing")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args(argv)
    if not args.check and args.out is None:
        parser.error("give --out DIR, or --check")
    manifest = tomllib.loads(args.manifest.read_text())
    files = public_files(manifest["exclude"]["paths"])
    base = ROOT
    if not args.check:
        copy_tree(files, args.out)
        base = args.out
    hits = sweep(base, files, manifest["forbidden"]["words"], manifest.get("allow", []))
    for hit in hits:
        print(hit)
    where = "current tree" if args.check else str(args.out)
    print(f"{len(files)} files, {len(hits)} forbidden-word hits ({where})", file=sys.stderr)
    return 1 if hits else 0


def public_files(exclude: list[str]) -> list[str]:
    """Return the repo-relative paths that belong in the public tree, sorted."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.split("\0")
    return sorted({path for path in listed if path and (ROOT / path).is_file() and not _excluded(path, exclude)})


def copy_tree(files: list[str], out: Path):
    """Copy files into out, which must not exist or must be empty."""
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty; give a fresh directory")
    for path in files:
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, target)


def sweep(base: Path, files: list[str], words: list[str], allow: list[dict]) -> list[str]:
    """Return ``path:line: text`` for every forbidden word outside the allow list."""
    patterns = [(word, re.compile(word, re.IGNORECASE)) for word in words]
    hits = []
    for path in files:
        text = _read_text(base / path)
        if text is None:
            continue
        active = [(word, rx) for word, rx in patterns if not _allowed(path, word, allow)]
        for number, line in enumerate(text.splitlines(), start=1):
            if any(rx.search(line) for _, rx in active):
                hits.append(f"{path}:{number}: {line.strip()[:160]}")
    return hits


# Private Functions ================================================================================

def _excluded(path: str, globs: list[str]) -> bool:
    """True when path matches a glob, or sits under a glob that ends in '/'."""
    return any(path.startswith(glob) if glob.endswith("/") else fnmatch.fnmatch(path, glob) for glob in globs)


def _allowed(path: str, word: str, allow: list[dict]) -> bool:
    """True when an allow entry covers this path and this forbidden word."""
    return any(fnmatch.fnmatch(path, entry["path"]) and word in entry["words"] for entry in allow)


def _read_text(path: Path) -> str | None:
    """Return the file as text, or None for a binary file."""
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


if __name__ == "__main__":
    sys.exit(main())
