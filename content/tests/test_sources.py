"""Tests for vimtrainer_content.sources (allowlist and licence gate)."""

import subprocess

import pytest

from conftest import FIXTURES
from vimtrainer_content import sources

GPL = "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n"


def _toml(tmp_path, license_name="MIT", **extra):
    body = (f'[[source]]\nname = "t"\nlang = "python"\nrepo = "r"\nlicense = "{license_name}"\n'
            f'local = "."\ninclude = ["*.py"]\n')
    body += "".join(f'{k} = "{v}"\n' for k, v in extra.items())
    path = tmp_path / "sources.toml"
    path.write_text(body)
    return path


def test_repo_sources_toml_pins_exercism_mit():
    (src,) = [s for s in sources.load_sources() if s.lang == "python"]
    assert src.repo == "github.com/exercism/python"
    assert src.license == "MIT"
    assert len(src.commit) == 40


def test_non_allowlisted_license_is_rejected(tmp_path):
    with pytest.raises(sources.LicenseError):
        sources.load_sources(_toml(tmp_path, "GPL-3.0"))


def test_local_mit_license_verifies():
    (src,) = sources.load_sources(FIXTURES / "sources.toml")
    assert sources.verify_license(src) == "Copyright (c) 2026 Fixture"
    assert [p for p, _ in sources.snippet_files(src)] == ["src/inventory.py"]


def test_gpl_text_under_mit_label_fails(tmp_path):
    (tmp_path / "LICENSE").write_text(GPL)
    (src,) = sources.load_sources(_toml(tmp_path))
    with pytest.raises(sources.LicenseError, match="copyleft"):
        sources.verify_license(src)


def test_missing_license_file_fails(tmp_path):
    (src,) = sources.load_sources(_toml(tmp_path))
    with pytest.raises(sources.LicenseError, match="no LICENSE"):
        sources.verify_license(src)


def test_license_is_read_at_pinned_commit(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.invalid")
    git("config", "user.name", "t")
    (tmp_path / "LICENSE").write_text((FIXTURES / "LICENSE").read_text())
    git("add", "LICENSE")
    git("commit", "-qm", "mit")
    mit_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    (tmp_path / "LICENSE").write_text(GPL)  # relicensed later: the pinned commit is what counts
    git("commit", "-qam", "gpl")
    (src,) = sources.load_sources(_toml(tmp_path, commit=mit_commit))
    assert sources.verify_license(src).startswith("Copyright")
