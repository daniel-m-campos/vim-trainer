"""Browser side of the differential fuzzer: drive ``app/e2e/difftest-worker.mjs``.

The worker is one Node process (Vite + headless Chromium, N pages) that reads JSON-line
requests ``{id, lang, lines, cursor, keys}`` on stdin and answers ``{id, lines, cursor,
mode, ms}`` or ``{id, error}`` on stdout, possibly out of order. ``WebWorker`` keeps one
worker alive across calls and restarts it when it prints nothing for ``STALL_S`` seconds.

Examples
--------
>>> with WebWorker(APP_DIR) as web:  # doctest: +SKIP
...     sides = web.run(cases)
"""

import json
import pathlib
import queue
import subprocess
import threading
from collections.abc import Sequence
from typing import Any, Final, Self

from vimtrainer_content import sources
from vimtrainer_content.difftest import compare, generate

APP_DIR: Final = sources.CONTENT_DIR.parent / "app"
WORKER: Final = "e2e/difftest-worker.mjs"
STALL_S: Final = 60.0
READY: Final = "ready"


class WebWorker:
    """Long-lived ``difftest-worker.mjs`` process; use as a context manager.

    Parameters
    ----------
    app_dir
        The ``app/`` directory (the worker runs with it as cwd).
    pages
        Browser pages replaying in parallel.
    command
        Override the worker command line (tests use a fake worker).
    stall_s
        Seconds without any output before the worker is killed and restarted.
    """

    def __init__(self, app_dir: pathlib.Path = APP_DIR, pages: int = 4, command: Sequence[str] | None = None,
                 stall_s: float = STALL_S):
        self._app_dir = pathlib.Path(app_dir)
        self._command = list(command or ["node", WORKER, "--pages", str(pages)])
        self._stall_s = stall_s
        self._proc: subprocess.Popen[str] | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self.restarts = 0

    def __repr__(self) -> str:
        pid = self._proc.pid if self._proc else None
        return f"WebWorker(command={self._command!r}, pid={pid}, restarts={self.restarts})"

    def __enter__(self) -> Self:
        self._start()
        return self

    def __exit__(self, *exc: object):
        self.close()

    def run(self, cases: Sequence[generate.Case]) -> list[compare.Side]:
        """Replay every case in the browser; one ``Side`` per case, in order.

        After a stall the worker restarts and the unanswered cases are resent in halves, so
        only a case that stalls the worker on its own gets an ``error`` side ("worker stalled").
        """
        replies: dict[int, dict[str, Any]] = {}
        self._run_ids(cases, list(range(len(cases))), replies)
        return [compare.web_side(replies.get(i, {"error": "worker stalled"})) for i in range(len(cases))]

    def close(self):
        """Close the worker's stdin and wait for it to exit (kill after 10 s)."""
        if self._proc is None:
            return
        proc, self._proc = self._proc, None
        try:
            proc.stdin.close()
            proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait()

    # Private Functions ============================================================================

    def _run_ids(self, cases: Sequence[generate.Case], ids: list[int], replies: dict[int, dict[str, Any]]):
        """Send ``ids``; on a stall restart and bisect the unanswered ones down to single cases."""
        if self._proc is None:
            self._start()
        self._send([_request(i, cases[i]) for i in ids])
        if self._collect(replies, set(ids)):
            return
        self._restart()
        todo = [i for i in ids if i not in replies]
        if len(ids) == 1 or not todo:
            return
        if len(todo) < len(ids):  # progress was made: retry the rest together first
            self._run_ids(cases, todo, replies)
            return
        mid = len(todo) // 2
        self._run_ids(cases, todo[:mid], replies)
        self._run_ids(cases, todo[mid:], replies)

    def _start(self):
        self._lines = queue.Queue()
        self._proc = subprocess.Popen(
            self._command, cwd=self._app_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            encoding="utf-8", bufsize=1,
        )
        threading.Thread(target=_pump, args=(self._proc.stdout, self._lines), daemon=True).start()
        while True:
            line = self._next_line()
            if line is None:
                self._proc.kill()  # __exit__ does not run when __enter__ raises
                self._proc.wait()
                self._proc = None
                raise RuntimeError(f"difftest worker did not start: {self._command}")
            if line.strip() == READY:
                return

    def _restart(self):
        self.restarts += 1
        if self._proc is not None:
            self._proc.kill()
            self._proc.wait()
            self._proc = None
        self._start()

    def _send(self, requests: list[dict[str, Any]]):
        """Write requests from a thread so a full stdout pipe cannot deadlock us."""
        proc = self._proc

        def write():
            try:
                for req in requests:
                    proc.stdin.write(json.dumps(req) + "\n")
                proc.stdin.flush()
            except OSError:
                pass

        threading.Thread(target=write, daemon=True).start()

    def _collect(self, replies: dict[int, dict[str, Any]], wanted: set[int]) -> bool:
        """Read replies until all ``wanted`` ids arrived (True) or the worker stalls or dies (False)."""
        while wanted - replies.keys():
            line = self._next_line()
            if line is None:
                return False
            reply = _parse(line)
            if reply is not None and reply.get("id") in wanted:
                replies[reply["id"]] = reply
        return True

    def _next_line(self) -> str | None:
        try:
            return self._lines.get(timeout=self._stall_s)
        except queue.Empty:
            return None


def web_cursor(buf: generate.Buffer) -> tuple[int, int]:
    """Start cursor in UTF-16 columns (CodeMirror) from ``Buffer.cursor`` in byte columns (nvim)."""
    line_no, byte_col = buf.cursor
    line = buf.lines[line_no - 1] if 0 < line_no <= len(buf.lines) else ""
    prefix = line.encode("utf-8")[:byte_col].decode("utf-8", errors="ignore")
    return line_no, len(prefix.encode("utf-16-le")) // 2


# Private Functions ================================================================================


def _pump(stream, lines: queue.Queue[str | None]):
    for line in stream:
        lines.put(line)
    lines.put(None)


def _parse(line: str) -> dict[str, Any] | None:
    if not line.startswith("{"):
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _request(i: int, case: generate.Case) -> dict[str, Any]:
    buf = case.buffer
    return {"id": i, "lang": buf.lang, "lines": list(buf.lines), "cursor": list(web_cursor(buf)), "keys": case.keys}
