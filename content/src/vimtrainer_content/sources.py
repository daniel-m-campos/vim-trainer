"""Source allowlist: fetch pinned repos, verify their licence, list snippet files.

``content/sources.toml`` lists every source. Each one is cloned at its pinned commit into
``content/.cache/<name>`` and its LICENSE file is checked at that commit (quality gate 1
in docs/design/content-pipeline.md). A source whose licence does not match is a hard build error.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

CONTENT_DIR: Final = pathlib.Path(__file__).resolve().parents[2]
SOURCES_TOML: Final = CONTENT_DIR / "sources.toml"
CACHE_DIR: Final = CONTENT_DIR / ".cache"
ALLOWED_LICENSES: Final = frozenset({"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "own"})

# Markers that must all appear in a licence text for it to count as that licence, and
# markers that must not (copyleft text pasted next to an MIT header, for example).
_LICENSE_MARKERS: Final = {
    "MIT": ("permission is hereby granted, free of charge", 'the software is provided "as is"'),
    "Apache-2.0": ("apache license", "version 2.0"),
    "BSD-2-Clause": ("redistribution and use in source and binary forms",),
    "BSD-3-Clause": ("redistribution and use in source and binary forms", "neither the name"),
}
_COPYLEFT: Final = re.compile(r"gnu (affero |lesser )?general public license|creative commons|share ?alike", re.I)


class LicenseError(RuntimeError):
    """A source's licence file does not match its declared allowlisted licence."""


@dataclass(frozen=True)
class Source:
    """One pinned source repository from sources.toml."""

    name: str
    lang: str
    repo: str
    url: str
    commit: str
    license: str
    license_file: str
    include: tuple[str, ...]
    local: pathlib.Path | None = None  # a local directory instead of a git clone

    @property
    def path(self) -> pathlib.Path:
        """Local checkout directory."""
        return self.local if self.local is not None else CACHE_DIR / self.name

    def meta(self, rel_path: str) -> dict[str, str]:
        """The ``source`` object recorded on every exercise cut from ``rel_path``."""
        return {"repo": self.repo, "path": rel_path, "commit": self.commit or None, "license": self.license}


# Public Functions =================================================================================


def load_sources(path: pathlib.Path = SOURCES_TOML) -> list[Source]:
    """Parse sources.toml into Source records, rejecting non-allowlisted licences."""
    data = tomllib.loads(path.read_text())
    sources = [
        Source(
            name=s["name"], lang=s["lang"], repo=s["repo"], url=s.get("url", ""), commit=s.get("commit", ""),
            license=s["license"], license_file=s.get("license_file", "LICENSE"), include=tuple(s["include"]),
            local=(path.parent / s["local"]).resolve() if "local" in s else None,
        )
        for s in data.get("source", [])
    ]
    for s in sources:
        if s.license not in ALLOWED_LICENSES:
            raise LicenseError(f"{s.name}: licence {s.license!r} is not on the allowlist")
    return sources


def fetch(source: Source) -> pathlib.Path:
    """Shallow-fetch ``source`` at its pinned commit into the cache (no-op when present or local)."""
    if source.local is not None or _head(source.path) == source.commit:
        return source.path
    source.path.mkdir(parents=True, exist_ok=True)
    if not (source.path / ".git").exists():
        _git(source.path, "init", "-q")
        _git(source.path, "remote", "add", "origin", source.url)
    _git(source.path, "fetch", "-q", "--depth", "1", "origin", source.commit)
    _git(source.path, "checkout", "-q", "--force", source.commit)
    return source.path


def verify_license(source: Source) -> str:
    """Check the licence file at the pinned commit; return its copyright line.

    Raises
    ------
    LicenseError
        When the file is missing, matches a copyleft licence, or lacks the markers of
        the declared licence.
    """
    text = license_text(source)
    if _COPYLEFT.search(text):
        raise LicenseError(f"{source.name}: {source.license_file} mentions a copyleft licence")
    lowered = " ".join(text.lower().split())
    missing = [m for m in _LICENSE_MARKERS.get(source.license, ()) if m not in lowered]
    if missing:
        raise LicenseError(f"{source.name}: {source.license_file} is not {source.license} (missing {missing})")
    return next((ln.strip() for ln in text.splitlines() if ln.lower().startswith("copyright")), "")


def license_text(source: Source) -> str:
    """The licence file's text at the pinned commit (or on disk for a local source)."""
    try:
        if source.local is not None and not source.commit:
            return (source.path / source.license_file).read_text()
        return _git(source.path, "show", f"{source.commit}:{source.license_file}")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise LicenseError(f"{source.name}: no {source.license_file} at {source.commit or source.path}") from exc


def snippet_files(source: Source) -> Iterator[tuple[str, str]]:
    """Yield ``(repo-relative path, text)`` for every file matching ``include``, sorted."""
    paths = sorted({p for pattern in source.include for p in source.path.glob(pattern) if p.is_file()})
    for p in paths:
        yield p.relative_to(source.path).as_posix(), p.read_text(errors="replace")


# Private Functions ================================================================================


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _head(path: pathlib.Path) -> str | None:
    if not (path / ".git").exists():
        return None
    try:
        return _git(path, "rev-parse", "HEAD").strip()
    except subprocess.CalledProcessError:
        return None
