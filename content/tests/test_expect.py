"""Tests for ``vimtrainer-content expect`` (the Neovim oracle behind app/e2e/editor.mjs)."""

import io
import json
import shutil

import pytest

from vimtrainer_content import cli, expect

needs_nvim = pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")

CASES = [
    {"id": "py", "lines": ["abc def"], "cursor": [1, 0], "keys": "dw"},
    {"id": "cpp", "lang": "cpp", "lines": ["int f() {", "    int x = 1;", "}"], "cursor": [2, 4],
     "keys": "A<CR>y();<Esc>"},
    {"id": "incomplete", "lines": ["abc"], "cursor": [1, 0], "keys": "d"},
]


@needs_nvim
def test_cli_round_trip(tmp_path, capsys):
    path = tmp_path / "cases.jsonl"
    path.write_text("".join(json.dumps(c) + "\n" for c in CASES))
    assert cli.main(["expect", "--file", str(path)]) == 0
    out = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert out == [
        {"id": "py", "lines": ["def"], "cursor": [1, 0], "mode": "normal", "errmsg": ""},
        {"id": "cpp", "lines": ["int f() {", "    int x = 1;", "    y();", "}"], "cursor": [3, 7], "mode": "normal",
         "errmsg": ""},
        {"id": "incomplete", "lines": ["abc"], "cursor": [1, 0], "mode": "pending", "errmsg": ""},
    ]


@needs_nvim
def test_typed_oracle_aborts_a_macro_on_a_failing_motion():
    # Under the batch oracle's silent! the failing fx does not abort @a, so A! runs on line 2 too.
    case = {"id": 1, "lines": ["axb", "abb"], "cursor": [1, 0], "keys": "qafxA!<Esc>qj0@a"}
    batch, typed = expect.expect([case, {**case, "id": 2, "oracle": expect.TYPED}])
    assert batch["lines"] == ["axb!", "abb!"]
    assert typed["lines"] == ["axb!", "abb"]
    assert typed["cursor"] == [2, 0]


def test_input_cursor_goes_to_neovim_in_bytes():
    seen = []

    def fake_nvim(cases):
        seen.extend(c.buffer.cursor for c in cases)
        return [expect.compare.Side(("a😀b",), (1, 3), "normal")]

    # UTF-16 column 3 (after the surrogate pair) is UTF-8 byte 5.
    out = io.StringIO()
    src = io.StringIO('{"id": 0, "lines": ["a😀b"], "cursor": [1, 3], "keys": ""}\n')
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(expect.run, "nvim_sides", fake_nvim)
        assert expect.main_io(src, out) == 0
    assert seen == [(1, 5)]
    assert json.loads(out.getvalue())["cursor"] == [1, 3]
