"""The build is a pure function of its inputs: byte-identical across hash seeds and input order.

``make content-check`` rebuilds on Linux CI and diffs against the build/ committed from
macOS, so anything that depends on ``PYTHONHASHSEED``, file-system listing order, draft
order or the wall clock shows up there as a spurious failure. These tests catch it locally.
"""

import datetime
import os
import pathlib
import shutil
import subprocess
import sys

from conftest import FIXTURES

from vimtrainer_content import build

EPOCH = 981158400  # 2001-02-03T00:00:00Z

# Runs one build in a fresh interpreter (PYTHONHASHSEED only applies at start-up) with the
# source files and each window's drafts shuffled by argv[3].
_DRIVER = """
import pathlib, random, sys
from vimtrainer_content import build, sources, templates

rng = random.Random(int(sys.argv[3]))
snippet_files, generate = sources.snippet_files, templates.generate

def shuffled_files(src):
    items = list(snippet_files(src))
    rng.shuffle(items)
    return iter(items)

def shuffled_drafts(*args, **kwargs):
    drafts = list(generate(*args, **kwargs))
    rng.shuffle(drafts)
    return drafts

sources.snippet_files, templates.generate = shuffled_files, shuffled_drafts
build.build(out=pathlib.Path(sys.argv[1]), cap=3, workers=2, sources_toml=pathlib.Path(sys.argv[2]),
            log=lambda *_: None)
"""


def test_build_is_byte_identical_across_hash_seed_and_input_order(tmp_path):
    toml = _multi_file_source(tmp_path / "src-root")
    first, second = tmp_path / "one" / "build", tmp_path / "two" / "build"
    _run_build(first, toml, hash_seed="1", shuffle_seed=1)
    _run_build(second, toml, hash_seed="4242", shuffle_seed=7)
    a, b = _tree(first), _tree(second)
    assert sorted(a) == sorted(b)
    differing = [rel for rel in a if a[rel] != b[rel]]
    assert not differing, f"differs between runs: {differing[:5]}"
    assert len([rel for rel in a if rel.startswith("exercises/")]) > 3


def test_build_date_comes_from_source_date_epoch(tmp_path):
    toml = _multi_file_source(tmp_path / "src-root")
    out = tmp_path / "b" / "build"
    _run_build(out, toml, hash_seed="0", shuffle_seed=0)
    index = (out / "index.json").read_text()
    assert '"generated": "2001-02-03"' in index
    assert '"verified": "nvim ' in index and ' 2001-02-03"' in index
    commands = (out / "supported_commands.md").read_text()
    assert "verified in nvim " in commands and "2001-02-03" not in commands


def test_build_date_is_utc(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(EPOCH + 86399))  # 23:59:59Z, any local timezone
    assert build.build_date().isoformat() == "2001-02-03"
    monkeypatch.delenv("SOURCE_DATE_EPOCH")
    assert build.build_date() == datetime.date.today()


# Private Functions ================================================================================


def _multi_file_source(root: pathlib.Path) -> pathlib.Path:
    """A local source with several files, so that file order has something to shuffle."""
    (root / "src").mkdir(parents=True)
    shutil.copy(FIXTURES / "LICENSE", root / "LICENSE")
    text = (FIXTURES / "src" / "inventory.py").read_text()
    for name in ("zeta.py", "alpha.py", "Mid.py"):
        (root / "src" / name).write_text(text)
    toml = root / "sources.toml"
    toml.write_text((FIXTURES / "sources.toml").read_text())
    return toml


def _run_build(out: pathlib.Path, toml: pathlib.Path, hash_seed: str, shuffle_seed: int):
    env = {**os.environ, "PYTHONHASHSEED": hash_seed, "SOURCE_DATE_EPOCH": str(EPOCH)}
    subprocess.run([sys.executable, "-c", _DRIVER, str(out), str(toml), str(shuffle_seed)],
                   env=env, check=True, timeout=600)


def _tree(root: pathlib.Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
