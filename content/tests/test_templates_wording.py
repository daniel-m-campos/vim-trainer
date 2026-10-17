"""Round 4 template rules (QA #7, #13, #20, #23, #27-#30, #33, #49, #50, #52, #54), Python side.

One test per rule, each on its own snippet. Drafts whose buffer the rule changes are replayed
in Neovim (the oracle), so the expected lines are Neovim's, not the template's guess.
C++ counterparts live in test_cpp.py.
"""

import re

from vimtrainer_content import build, oracle, snippets, templates
from vimtrainer_content.lang.python import LANG

SOURCE = {"repo": "fixture/wording", "path": "wording.py", "commit": None, "license": "MIT"}


def _window(text: str, indent: int = 0) -> snippets.Window:
    lines = text.strip("\n").splitlines()
    return snippets.Window(lines=lines, source=SOURCE, first_line=1, last_line=len(lines),
                           tree=snippets.parse("\n".join(lines)), indent=indent)


def _drafts(text: str, *names: str, indent: int = 0) -> list[templates.Draft]:
    return [d for d in templates.generate(_window(text, indent), LANG) if not names or d.template in names]


def _solvable(draft, runner):
    verdicts = [oracle.verify(draft.exercise("python"), k, runner) for k in draft.variants]
    assert any(v.passed for v in verdicts), (draft.task, [(v.keys, v.reason) for v in verdicts])


def _accepted(draft) -> dict:
    report = build.Report()
    verdicts = build._replay([draft], LANG, workers=1, report=report)
    ex, gate, detail = build.evaluate(draft, LANG, verdicts[id(draft)], "nvim test")
    assert ex is not None, (draft.task, gate, detail)
    return ex


# Snippets =========================================================================================

IN_STRINGS = '''
def greet(name, greeting):
    """Say hello to name."""
    message = greeting + ", " + name
    print("name:", name)  # print the name
    message = message.strip()
    log(message, name)
    return message
'''

WHOLE_WORD = '''
def shift(index, items):
    index1 = index + 1
    first = items[index]
    second = items[index1]
    return first, second, index
'''

NO_PARTIAL = '''
def total_price(prices, discount):
    subtotal = sum(prices)
    if subtotal > 100:
        subtotal = subtotal - discount
    return round(subtotal, 2)
'''

CONSTANTS = '''
BLOCK_SIZE = 64
default_name = 'guest'


def area(width, height):
    total_area = width * height
    return total_area


class Box:
    MAX_ITEMS = 10
'''

ROLES = '''
def pay(coins, has_priority, path):
    if has_priority:
        return sum(coins)
    return len(path)
'''

LONG_LINES = '''
def report(rows):
    header = format_header(rows, columns=default_columns, separator=' | ', width=120)
    for row in rows:
        print(row)
    total = sum(r.amount for r in rows)
    footer = format_footer(total, columns=default_columns, separator=' | ', width=120)
    lines = [header, *rows, footer]
    return lines
'''

INNER = '''
def label(item, prefix):
    text = format_label(item.name, prefix)
    return 'item: ' + text.strip() + ('x', 'y')[0]
'''

NUMBERS = '''
def make_window(title):
    window = resize(width=40, height=300)
    window.title = title
    return window
'''


# Rule 1: rename and case targets are code identifiers (QA #7) ===================================


def test_renames_only_touch_code_identifiers(runner):
    win = _window(IN_STRINGS)
    strings = templates._string_cells(win)
    comments = {r for r, ln in enumerate(win.lines) if "#" in ln}
    drafts = [d for d in templates.generate(win, LANG)
              if d.template in ("rename_here", "rename_all_subst", "rename_all_dot", "upper_word")]
    assert drafts
    for d in drafts:
        for t in d.target:
            row, col = t["start"][0] - 1, t["start"][1]
            assert (row, col) not in strings, d.task
            assert not (row in comments and col > win.lines[row].index("#")), d.task
    # `name` is also in the docstring, a string and a comment: :%s and * would change those
    assert not [d for d in drafts if d.template != "rename_here" and d.params.get("old") == "name"]
    (subst,) = [d for d in drafts if d.template == "rename_all_subst"]
    assert subst.params["old"] == "message"
    changed = [(r, a, b) for r, (a, b) in enumerate(zip(subst.lines, subst.expect["lines"])) if a != b]
    assert {r for r, _, _ in changed} == {2, 4, 5, 6}
    assert all(a.replace("message", subst.params["new"]) == b for _, a, b in changed)
    _solvable(subst, runner)  # Neovim's :%s gives the identifier-only buffer


# Rule 2: x.subst says "whole word" exactly when the par needs \< or \> (QA #13, #30, #33) =======


def test_subst_says_whole_word_when_the_par_needs_it():
    (whole,) = _drafts(WHOLE_WORD, "rename_all_subst")
    assert whole.params["old"] == "index" and whole.kind == "ex"
    assert "as a whole word" in whole.task and "`index1` stays" in whole.task
    assert "(4 occurrences" in whole.task
    assert re.search(r"\\<|\\>", _accepted(whole)["par"]["keys"])
    (plain,) = _drafts(NO_PARTIAL, "rename_all_subst")
    assert "whole word" not in plain.task and "(5 occurrences)" in plain.task
    assert not re.search(r"\\<|\\>", _accepted(plain)["par"]["keys"])
    for d in (whole, plain):
        assert not re.search(r"\bevery `", d.task), d.task  # "Rename every `words`" read badly (QA #33)


# Rule 3: case drills only on real constants (QA #28) ============================================


def test_case_drills_only_target_constants(runner):
    drafts = _drafts(CONSTANTS, "upper_word")
    words = {d.params["word"] for d in drafts}
    assert words and words <= {"BLOCK_SIZE", "default_name", "MAX_ITEMS"}, words
    for d in drafts:
        _solvable(d, runner)
    # the same top-level assignment inside a dedented function body is a local, not a constant
    assert not [d for d in _drafts(CONSTANTS, "upper_word", indent=4) if d.params["word"] == "default_name"]
    used = CONSTANTS + "\n\ndef show():\n    return default_name\n"
    assert not [d for d in _drafts(used, "upper_word") if d.params["word"] == "default_name"]


# Rule 4: new names come from the role's short list and are not in the window (QA #23) ===========


def test_new_names_fit_the_role_and_are_fresh():
    win = _window(ROLES)
    names = {n: [] for n in ("coins", "has_priority", "path")}
    stack = [win.root]
    while stack:
        n = stack.pop()
        stack.extend(n.children)
        if n.type == "identifier" and templates._text(n) in names:
            names[templates._text(n)].append(templates._new_name(win, templates._text(n), n, "k"))
    assert set(names["coins"]) <= set(templates.ROLE_NAMES["many"])
    assert set(names["has_priority"]) <= set(templates.ROLE_NAMES["flag"])
    assert set(names["path"]) == {"filename"}  # `path` itself is taken
    crowded = _window(ROLES + "\n\nitems = values = value = result = None\n")
    assert templates._new_name(crowded, "coins", None, "k") is None
    words = set(re.findall(r"\w+", ROLES))
    for d in _drafts(ROLES):
        assert d.params.get("new") not in words and d.params.get("text") not in words, d.task


# Rule 5: task wording (QA #20, #29, #49, #50, #52) ==============================================


def test_quotes_hold_no_ellipsis():
    for snippet in (LONG_LINES, IN_STRINGS, INNER, NUMBERS):
        lines = snippet.strip("\n").splitlines()
        for d in _drafts(snippet):
            for quoted in d.task.split("`")[1::2]:
                assert "..." not in quoted or any(quoted in ln for ln in lines), d.task
    tasks = [d.task for d in _drafts(LONG_LINES, "goto_line_rel", "move_line", "copy_line", "duplicate_line")]
    assert any(t.endswith("` ...") for t in tasks), tasks


def test_inner_tasks_share_one_wording(runner):
    drafts = _drafts(INNER, "change_inner", "delete_inner", "upper_inner")
    assert {d.template for d in drafts} >= {"change_inner", "delete_inner"}
    phrase = re.compile(r"the text( `[^`]+`)? inside the (quotes|parentheses|square brackets|braces)")
    for d in drafts:
        assert phrase.search(d.task) and not re.search(r"contents of|everything inside", d.task), d.task
        if d.template == "change_inner":
            m = re.fullmatch(r"Change the text (`([^`]+)` )?inside .* to `([^`]+)`", d.task)
            (row, oc), cc = d.target[0]["start"], d.target[0]["end"][1]
            inner = d.lines[row - 1][oc + 1:cc]
            assert m and m.group(3) == d.params["text"], d.task
            # from and to are both quoted without delimiters; edge spaces would not survive Markdown
            assert m.group(2) == inner if inner == inner.strip() else m.group(1) is None, d.task
            _solvable(d, runner)


def test_number_tasks_say_which_number():
    drafts = _drafts(NUMBERS, "increment")
    assert drafts
    for d in drafts:
        old = d.params["old"]
        which = "first" if old == "40" else "second"
        assert d.task.endswith(f"(the {which} number on the line)"), d.task
