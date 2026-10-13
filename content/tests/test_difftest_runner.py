"""Tests for the difftest runners: web.WebWorker (fake worker process), run.nvim_sides, run.run.

The real browser worker runs only with DIFFTEST_E2E=1 (needs app/node_modules and Chromium).
"""

import argparse
import json
import os
import shutil
import sys
import textwrap

import pytest

from vimtrainer_content import cli, oracle
from vimtrainer_content.difftest import compare, generate, run, web

needs_nvim = pytest.mark.skipif(shutil.which("nvim") is None, reason="nvim not installed")
e2e = pytest.mark.skipif(os.environ.get("DIFFTEST_E2E") != "1", reason="set DIFFTEST_E2E=1 to drive the browser")

# Echoes each request's buffer back in Normal mode; keys "hang" never get a reply,
# keys "freeze" stop all replies until a restart, keys "boom" get a page error.
# Prints noise before "ready" like Vite might.
FAKE_WORKER = textwrap.dedent("""
    import json, sys, time
    print("vite noise", flush=True)
    print("ready", flush=True)
    for line in sys.stdin:
        req = json.loads(line)
        if req["keys"] == "hang":
            continue
        if req["keys"] == "freeze":
            time.sleep(3600)
        if req["keys"] == "boom":
            out = {"id": req["id"], "error": "pageerror: boom"}
        else:
            out = {"id": req["id"], "lines": req["lines"], "cursor": req["cursor"], "mode": "normal", "ms": 0}
        print(json.dumps(out), flush=True)
""")


def _case(keys, lines=("abc def",), cursor=(1, 0), index=0):
    return generate.Case(index, 1, generate.Buffer("t/1", "python", list(lines), cursor, {}), keys)


@pytest.fixture
def fake_worker(tmp_path):
    script = tmp_path / "worker.py"
    script.write_text(FAKE_WORKER)
    return [sys.executable, str(script)]


def _args(tmp_path, **over):
    ns = argparse.ArgumentParser()
    run._add_arguments(ns)
    args = ns.parse_args(["--seed", "7", "--out", str(tmp_path / "out"), "--known", str(tmp_path / "known.jsonl")])
    for k, v in over.items():
        setattr(args, k, v)
    return args


# web.WebWorker ====================================================================================


def test_worker_replies_in_order(fake_worker, tmp_path):
    cases = [_case("x", index=i, lines=(f"line {i}",)) for i in range(5)]
    with web.WebWorker(tmp_path, command=fake_worker) as w:
        sides = w.run(cases)
        again = w.run(cases[:2])
    assert [s.lines for s in sides] == [(f"line {i}",) for i in range(5)]
    assert all(s.mode == "normal" for s in sides)
    assert [s.lines for s in again] == [("line 0",), ("line 1",)]


def test_worker_stall_restarts_then_errors(fake_worker, tmp_path):
    cases = [_case("x"), _case("hang"), _case("boom")]
    with web.WebWorker(tmp_path, command=fake_worker, stall_s=0.5) as w:
        sides = w.run(cases)
        assert w.restarts == 2
    assert sides[0].mode == "normal"
    assert sides[1].mode == "error" and "stalled" in sides[1].error
    assert sides[2].mode == "error" and sides[2].error.startswith("pageerror")


def test_worker_stall_loses_only_the_stalling_case(fake_worker, tmp_path):
    cases = [_case("x", index=0), _case("freeze", index=1)] + [_case("x", index=i) for i in range(2, 6)]
    with web.WebWorker(tmp_path, command=fake_worker, stall_s=0.5) as w:
        sides = w.run(cases)
    assert [s.mode for s in sides] == ["normal", "error", "normal", "normal", "normal", "normal"]
    assert sides[1].error == run.STALLED


def test_worker_that_never_starts(tmp_path):
    with pytest.raises(RuntimeError, match="did not start"):
        with web.WebWorker(tmp_path, command=[sys.executable, "-c", "pass"]):
            pass


@pytest.mark.parametrize(("line", "byte_col", "utf16_col"), [
    ("abc", 2, 2),
    ("é = 1", 3, 2),
    ("名前 = 1", 7, 3),
    ("x = '😀' + y", 10, 8),
])
def test_web_cursor_converts_byte_columns(line, byte_col, utf16_col):
    buf = generate.Buffer("t", "python", [line], (1, byte_col), {})
    assert web.web_cursor(buf) == (1, utf16_col)


# run.nvim_sides ===================================================================================


@needs_nvim
def test_nvim_sides_batches_and_converts(monkeypatch):
    monkeypatch.setattr(run, "NVIM_BATCH", 2)
    cases = [_case("dw"), _case("A!<Esc>"), _case("ix", lines=("é",)), _case("vl")]
    sides = run.nvim_sides(cases)
    assert [s.lines for s in sides] == [("def",), ("abc def!",), ("xé",), ("abc def",)]
    assert sides[1].cursor == (1, 7) and sides[1].mode == "normal"
    # oracle.lua records the state before its <C-\\><C-n>, so the Insert-mode cursor is the true one.
    assert sides[2].mode == "insert" and sides[2].cursor == (1, 1)
    assert sides[3].mode == "visual"


@needs_nvim
def test_nvim_sides_counted_insert_and_swallowed_marker():
    sides = run.nvim_sides([_case("3iW"), _case("<C-w>"), _case("dd")])
    assert sides[0].lines == ("Wabc def",) and sides[0].mode == "insert"  # count applies only on <Esc>
    assert sides[1].mode == "pending"  # <C-w> swallowed oracle.lua's end marker
    assert sides[2].cursor == (1, 0)  # startofline on, as in Vim


@needs_nvim
def test_nvim_jobs_do_not_leak_repeat_state():
    """oracle.lua resets `.`, `@:`, `@@`, `&`, the last search and `".` between jobs of one batch."""
    setup = ["x", ":s/abc/Q/<CR>", "/def<CR>", "ihello<Esc>", "qaxq"]
    probes = [".", "@:", "&", "g&", ":&&<CR>", "n", '".p', "@@", "gi<Esc>"]
    cases = [_case(k, index=i) for i, k in enumerate(setup + probes)]
    sides = run.nvim_sides(cases)[len(setup):]
    assert [(s.lines, s.cursor) for s in sides] == [(("abc def",), (1, 0))] * len(probes), probes


class _Crashy:
    """Oracle runner that raises like a crashed nvim on any batch holding keys ``crash``."""

    def __init__(self, err):
        self.err = err

    def __call__(self, jobs):
        if any(keys == "crash" for _, keys in jobs):
            raise self.err
        return [oracle.Outcome(keys, list(ex["start"]["lines"]), [1, 0], "n", False, False, "") for ex, keys in jobs]


@pytest.mark.parametrize("err", [RuntimeError("nvim exited 139"), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad")])
def test_nvim_batch_bisects_down_to_the_crashing_job(err):
    cases = [_case("x", index=i) for i in range(5)] + [_case("crash", index=5), _case("x", index=6)]
    sides = run._nvim_batch(cases, _Crashy(err))
    assert [s.mode for s in sides] == ["normal"] * 5 + ["error", "normal"]
    assert sides[5].error.startswith(type(err).__name__)
    assert all(s.lines == ("abc def",) for i, s in enumerate(sides) if i != 5)


# run.run ==========================================================================================


def _fake_sides(lines_by_keys):
    """A runner returning ``lines_by_keys[keys]`` (default: the start buffer) in Normal mode."""
    def runner(cases):
        return [compare.Side(tuple(lines_by_keys.get(c.keys, c.buffer.lines)), (1, 0), "normal") for c in cases]
    return runner


def test_run_writes_findings_and_strict_exit(tmp_path, monkeypatch):
    cases = [_case("dw", index=0), _case("x", index=1), _case("dw", index=2)]
    monkeypatch.setattr(run, "_cases", lambda args: cases)
    nvim = _fake_sides({"dw": ["def"], "x": ["bc def"]})
    webr = _fake_sides({"dw": ["def"], "x": ["c def"]})
    args = _args(tmp_path, no_minimise=True, strict=True, dump=True)
    assert run.run(args, nvim=nvim, web_runner=webr) == 1
    out = tmp_path / "out" / "7"
    findings = [json.loads(line) for line in (out / "findings.jsonl").read_text().splitlines()]
    assert len(findings) == 1
    assert compare.Finding.from_json(findings[0]).case.keys == "x"
    assert (out / "summary.md").read_text()
    assert len((out / "cases.jsonl").read_text().splitlines()) == 3

    accept = _args(tmp_path, accept=out / "findings.jsonl", cls="b", note="test")
    assert run.run(accept) == 0
    known = [json.loads(line) for line in (tmp_path / "known.jsonl").read_text().splitlines()]
    assert len(known) == 1 and known[0]["class"] == "b" and known[0]["note"] == "test"
    assert run.run(args, nvim=nvim, web_runner=webr) == 0


def test_run_minimises_and_marks_flaky(tmp_path, monkeypatch):
    cases = [_case("x", index=0), _case("ll", index=1)]
    monkeypatch.setattr(run, "_cases", lambda args: cases)
    calls = []
    monkeypatch.setattr(run.shrink, "minimise",
                        lambda case, diverges, max_runs=120: calls.append(case.keys) or (None if case.keys == "ll" else case))
    nvim = _fake_sides({"x": ["bc def"], "ll": ["a"]})
    webr = _fake_sides({"x": ["c def"], "ll": ["b"]})
    assert run.run(_args(tmp_path, strict=True), nvim=nvim, web_runner=webr) == 1
    assert sorted(calls) == ["ll", "x"]
    lines = (tmp_path / "out" / "7" / "findings.jsonl").read_text().splitlines()
    found = {f.case.keys: f for f in (compare.Finding.from_json(json.loads(line)) for line in lines)}
    assert found["x"].minimised == "x"
    assert found["ll"].minimised is None and found["ll"].cls == "c"


def test_run_judges_only_minimised_findings(tmp_path, monkeypatch, capsys):
    cases = [_case("x", index=0), _case("lll", index=1)]
    monkeypatch.setattr(run, "_cases", lambda args: cases)
    monkeypatch.setattr(run.shrink, "minimise", lambda case, diverges, max_runs=120: case)
    nvim = _fake_sides({"x": ["bc def"], "lll": ["a"]})
    webr = _fake_sides({"x": ["c def"], "lll": ["b"]})
    args = _args(tmp_path, strict=True, max_findings=1)
    assert run.run(args, nvim=nvim, web_runner=webr) == 1
    out = tmp_path / "out" / "7"
    lines = (out / "findings.jsonl").read_text().splitlines()
    found = {f.case.keys: f for f in (compare.Finding.from_json(json.loads(line)) for line in lines)}
    assert found["x"].minimised == "x" and found["lll"].minimised is None  # both written
    assert "| unminimised | 1 |" in (out / "summary.md").read_text()
    assert "left unminimised" in capsys.readouterr().out
    # Once the minimised shape is known, the unminimised one does not fail --strict.
    args.known.write_text(json.dumps(compare.known_entry(found["x"], "test")) + "\n")
    assert run.run(args, nvim=nvim, web_runner=webr) == 0


def test_run_strict_fails_when_nothing_could_be_judged(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "_cases", lambda args: [_case("x", index=0)])
    nvim, webr = _fake_sides({"x": ["bc def"]}), _fake_sides({"x": ["c def"]})
    assert run.run(_args(tmp_path, strict=True, max_findings=0), nvim=nvim, web_runner=webr) == 1


def _broken(mode, error):
    """A runner whose every side is ``mode`` with ``error`` (a dead nvim or browser)."""
    return lambda cases: [compare.Side((), (0, 0), mode, error) for _ in cases]


@pytest.mark.parametrize(("nvim_error", "web_error"), [
    ("RuntimeError: no nvim", None), (None, "timeout: 3000 ms"), (None, run.STALLED),
])
def test_run_strict_fails_on_an_unhealthy_harness(tmp_path, monkeypatch, capsys, nvim_error, web_error):
    monkeypatch.setattr(run, "_cases", lambda args: [_case("x", index=i) for i in range(4)])
    ok = _fake_sides({})
    nvim = _broken("error", nvim_error) if nvim_error else ok
    webr = _broken("timeout" if web_error.startswith("timeout") else "error", web_error) if web_error else ok
    args = _args(tmp_path, strict=True, no_minimise=True)
    assert run.run(args, nvim=nvim, web_runner=webr) == 1
    assert "WARNING" in capsys.readouterr().out
    args.strict = False
    assert run.run(args, nvim=nvim, web_runner=webr) == 0


def test_run_page_error_is_a_class_a_finding(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "_cases", lambda args: [_case("x", index=0)])
    nvim = _broken("error", "RuntimeError: nvim crashed")
    webr = _broken("error", "pageerror: TypeError: boom")
    assert run.run(_args(tmp_path, strict=True, no_minimise=True), nvim=nvim, web_runner=webr) == 1
    line = (tmp_path / "out" / "7" / "findings.jsonl").read_text().splitlines()[0]
    f = compare.Finding.from_json(json.loads(line))
    assert f.fields == ["error"] and f.cls == "a"


def test_to_editor_case_prints_literal(tmp_path, capsys):
    f = compare.Finding(_case("x"), compare.Side(("bc def",), (1, 0), "normal"),
                        compare.Side(("c def",), (1, 0), "normal"), ["lines"], "a", "x", None)
    path = tmp_path / "findings.jsonl"
    path.write_text(json.dumps(f.to_json()) + "\n")
    assert run.run(_args(tmp_path, to_editor_case=path), nvim=_fake_sides({"x": ["bc def"]})) == 0
    printed = capsys.readouterr().out
    assert 'keys: "x"' in printed and 'expect: ["bc def"]' in printed and "cursorAfter: [1, 0]" in printed


def test_cli_registers_difftest():
    args = cli._parser().parse_args(["difftest", "--count", "5", "--no-minimise"])
    assert args.func is run.run and args.count == 5 and args.lang == ["python", "cpp"]


# Real browser (DIFFTEST_E2E=1) ====================================================================


@e2e
@needs_nvim
def test_e2e_worker_matches_nvim_on_simple_cases():
    cases = [_case("dw", index=0), _case("A!<Esc>", index=1), _case("Vj", lines=("a", "b"), index=2)]
    with web.WebWorker(web.APP_DIR, pages=2) as w:
        sides = w.run(cases)
    assert [compare.compare(n, s) for n, s in zip(run.nvim_sides(cases), sides)] == [[], [], []]
