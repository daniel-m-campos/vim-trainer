"""``vimtrainer-content expect``: Neovim's result for editor regression cases (the test oracle).

Reads JSON lines ``{id, lang?, lines, cursor, keys, oracle?}`` (cursor [line 1-based, column
0-based in UTF-16 units], as the browser counts) on stdin or from ``--file`` and writes one
JSON line ``{id, lines, cursor, mode, errmsg}`` per case, in input order. ``mode`` uses the
browser's names (``compare.MODES``) and ``cursor`` is in UTF-16 columns.
``app/e2e/editor.mjs`` runs this once per test run instead of storing pasted expectations.

Two replays:

- default: difftest's batch oracle (``run.nvim_sides``: ``oracle.lua`` under ``silent!``,
  batches of ``run.NVIM_BATCH``, 5 s per job, ``startofline`` on).
- ``"oracle": "typed"``: the same reset and options (``oracle.lua``'s ``run(ex, "")``), then
  the keys fed without ``silent!``, as a user types them. ``silent!`` suppresses Vim's
  ``beep_flush``, so under it a failing motion does not abort a macro or a ``:normal`` line;
  typed, it does. Typed mode is not the default because an error there also flushes the
  end marker (``dfz`` reads as "pending") and ``:4,2d`` stops at the "Backwards range"
  prompt. Typed mode also reads ``<lt>`` as ``<`` (Vim notation, as ``app/e2e/keys.mjs``);
  ``oracle.lua`` passes it through literally.

Examples
--------
>>> import io
>>> out = io.StringIO()
>>> main_io(io.StringIO('{"id": 1, "lines": ["abc"], "cursor": [1, 0], "keys": "x"}'), out)  # doctest: +SKIP
0
>>> out.getvalue()  # doctest: +SKIP
'{"id": 1, "lines": ["bc"], "cursor": [1, 0], "mode": "normal", "errmsg": ""}\\n'
"""

import argparse
import concurrent.futures
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Sequence
from typing import IO, Any, Final

from vimtrainer_content import oracle
from vimtrainer_content.difftest import compare, generate, run

TYPED: Final = "typed"
TIMEOUT_S: Final = 5.0
# Typed replay: oracle.lua resets the buffer and options (run with no keys), then the keys
# go in as typed (no silent!) followed by a marker that records the state. Same output
# format as oracle.lua (MARKER + JSON per job).
_TYPED_LUA: Final = r"""
local Oracle = dofile(_G.arg[1])
local jobs = vim.json.decode(table.concat(vim.fn.readfile(_G.arg[2]), '\n'))
local function tc(s) return vim.api.nvim_replace_termcodes(s, true, true, true) end
local final
vim.keymap.set({ 'n', 'i', 'v', 'x', 's', 'o', 'c', 't' }, '<Plug>(expect-done)', function()
  final = { mode = vim.api.nvim_get_mode().mode, lines = vim.api.nvim_buf_get_lines(0, 0, -1, false),
    cursor = vim.api.nvim_win_get_cursor(0) }
end)
for _, job in ipairs(jobs) do
  Oracle.run(job.exercise, '')
  final, vim.v.errmsg = nil, ''
  local ok, err = pcall(vim.api.nvim_feedkeys, tc(job.keys) .. tc('<Plug>(expect-done)'), 'mtx', false)
  local res = final or { mode = vim.api.nvim_get_mode().mode, lines = vim.api.nvim_buf_get_lines(0, 0, -1, false),
    cursor = vim.api.nvim_win_get_cursor(0) }
  res.keys, res.done, res.used_ex, res.recording = job.keys, final ~= nil, false, vim.fn.reg_recording() ~= ''
  res.errmsg = ok and vim.v.errmsg or tostring(err)
  if res.recording then vim.cmd('normal! q') end
  vim.api.nvim_feedkeys(tc('<C-\\><C-n>'), 'nx', false)
  io.stdout:write('\n' .. Oracle.MARKER .. vim.json.encode(res) .. '\n')
end
"""


# Public Functions =================================================================================


def expect(records: Sequence[dict[str, Any]], nvim: run.NvimRunner | None = None,
           typed: run.NvimRunner | None = None) -> list[dict[str, Any]]:
    """Neovim's ``{id, lines, cursor, mode, errmsg}`` for each input record, in order.

    ``nvim`` and ``typed`` replace the two replays in tests.
    """
    cases = [_case(i, r) for i, r in enumerate(records)]
    is_typed = [r.get("oracle") == TYPED for r in records]
    batch = [c for c, t in zip(cases, is_typed) if not t]
    by_hand = [c for c, t in zip(cases, is_typed) if t]
    batch_iter = iter((nvim or run.nvim_sides)(batch) if batch else [])
    typed_iter = iter((typed or typed_sides)(by_hand) if by_hand else [])
    sides = [next(typed_iter) if t else next(batch_iter) for t in is_typed]
    return [_result(r["id"], s) for r, s in zip(records, sides, strict=True)]


def typed_sides(cases: Sequence[generate.Case], timeout_s: float = TIMEOUT_S) -> list[compare.Side]:
    """Replay cases as typed keys (no ``silent!``); see the module docstring.

    Without ``silent!`` Neovim pauses ~1 s after each displayed error, so the cases are
    spread over one headless Neovim per CPU.
    """
    workers = max(1, min(len(cases), os.cpu_count() or 1))
    chunks = [list(cases[i::workers]) for i in range(workers)]
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(lambda chunk: _typed_batch(chunk, timeout_s), chunks))
    # Chunk i holds cases i, i + workers, ...: interleave the results back into input order.
    return [results[i % workers][i // workers] for i in range(len(cases))]


def main_io(src: IO[str], dst: IO[str]) -> int:
    """Read JSON-line records from ``src`` and write Neovim's results to ``dst``."""
    for result in expect(list(_records(src))):
        dst.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Register the ``expect`` subcommand on the ``vimtrainer-content`` parser."""
    p = sub.add_parser("expect", help="Neovim's result (lines, cursor, mode) for editor test cases (JSON lines)")
    p.add_argument("--file", type=pathlib.Path, help="read cases from FILE instead of stdin")
    p.set_defaults(func=_run)
    return p


# Private Functions ================================================================================


def _run(args: argparse.Namespace) -> int:
    if args.file is None:
        return main_io(sys.stdin, sys.stdout)
    with args.file.open(encoding="utf-8") as fh:
        return main_io(fh, sys.stdout)


def _records(src: Iterable[str]) -> Iterable[dict[str, Any]]:
    return (json.loads(line) for line in src if line.strip())


def _case(index: int, record: dict[str, Any]) -> generate.Case:
    lines = list(record["lines"])
    line_no, col = record["cursor"]
    buf = generate.Buffer(f"expect/{record['id']}", record.get("lang") or "python", lines,
                          (int(line_no), _byte_col(lines, int(line_no), int(col))), {})
    return generate.Case(index, 0, buf, record["keys"])


def _byte_col(lines: Sequence[str], line_no: int, utf16_col: int) -> int:
    """UTF-8 byte column (Neovim) of a UTF-16 column (CodeMirror); inverse of ``compare.utf16_col``.

    Examples
    --------
    >>> _byte_col(["a😀b"], 1, 3)
    5
    """
    line = lines[line_no - 1] if 0 < line_no <= len(lines) else ""
    prefix = line.encode("utf-16-le")[:utf16_col * 2].decode("utf-16-le", errors="ignore")
    return len(prefix.encode())


def _typed_batch(cases: Sequence[generate.Case], timeout_s: float) -> list[compare.Side]:
    """One headless Neovim running ``_TYPED_LUA`` over ``cases``; every case gets an error side on failure."""
    jobs = [{"exercise": run._job(c)[0], "keys": c.keys} for c in cases]
    with tempfile.TemporaryDirectory() as tmp:
        driver, payload = pathlib.Path(tmp, "expect_typed.lua"), pathlib.Path(tmp, "jobs.json")
        driver.write_text(_TYPED_LUA)
        payload.write_text(json.dumps(jobs))
        try:
            proc = subprocess.run(
                [oracle._nvim_path(), *oracle.NVIM_BASE_ARGS, "-l", str(driver), str(oracle.ORACLE_LUA), str(payload)],
                capture_output=True, text=True, timeout=timeout_s + 1.1 * len(jobs), stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return [compare.Side((), (0, 0), "timeout", f"typed replay timed out after {timeout_s}s")] * len(cases)
    raw = [json.loads(line[len(oracle.MARKER):]) for line in proc.stdout.splitlines() if line.startswith(oracle.MARKER)]
    if len(raw) != len(cases):
        err = f"typed replay returned {len(raw)}/{len(cases)} results: {proc.stderr.strip()[-300:]}"
        return [compare.Side((), (0, 0), "error", err)] * len(cases)
    return [compare.nvim_side(_outcome(r)) for r in raw]


def _outcome(raw: dict[str, Any]) -> oracle.Outcome:
    return oracle.Outcome(raw["keys"], list(raw["lines"]), list(raw["cursor"]), raw["mode"], False,
                          bool(raw["recording"]), raw.get("errmsg") or "", bool(raw["done"]))


def _result(case_id: Any, side: compare.Side) -> dict[str, Any]:
    return {"id": case_id, "lines": list(side.lines), "cursor": list(side.cursor), "mode": side.mode,
            "errmsg": side.error or ""}
