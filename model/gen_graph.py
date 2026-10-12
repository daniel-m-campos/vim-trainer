"""Generate model/skill-graph.json from the tables in docs/plan/02-skill-graph.md.

The plan doc is the source of truth for skill ids, keys, tiers, prerequisites, emulator
flags and per-language weights. This script parses its Markdown tables, attaches the
target constants (``targetBase`` = 1200 ms, ``perKey`` = 180 ms) and the real-editor tips
from ``model/tips.json``, and writes the graph to ``model/skill-graph.json`` and a copy to
``app/src/model/skill-graph.json`` for the browser app.

Example
-------
    uv run --project model python model/gen_graph.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parent.parent
DOC: Final = ROOT / "docs" / "plan" / "02-skill-graph.md"
TIPS: Final = ROOT / "model" / "tips.json"
OUTPUTS: Final = (ROOT / "model" / "skill-graph.json", ROOT / "app" / "src" / "model" / "skill-graph.json")

TARGET_BASE: Final = 1200
PER_KEY: Final = 180
DEFAULT_ENABLED_MAX_TIER: Final = 10

LANGS: Final = (
    "lua", "python", "javascript", "typescript", "tsx", "jsx", "java", "csharp",
    "c", "cpp", "go", "rust", "html", "json", "yaml", "markdown",
)
WEIGHT_COLUMNS: Final = {
    "Lua": ("lua",),
    "Python": ("python",),
    "JS/TS": ("javascript", "typescript", "tsx", "jsx"),
    "Java/C#": ("java", "csharp"),
    "C/C++": ("c", "cpp"),
    "Go": ("go",),
    "Rust": ("rust",),
    "HTML/JSX": ("html",),
    "JSON/YAML": ("json", "yaml"),
    "Markdown": ("markdown",),
}
WEIGHT_ROW_OVERRIDES: Final = {"comment edits": ("nv.comment",)}
FLAG_WORDS: Final = ("full", "partial", "none", "verify")
SKILL_ID_RE: Final = re.compile(r"\b[a-z]{1,2}\.[A-Za-z]+\b")
TIER_RE: Final = re.compile(r"^## Tier (\d+) [^A-Za-z]* ?(.*)$")


# Public Functions =================================================================================

def build_graph(doc_text: str, tips: dict[str, str]) -> dict:
    """Parse the skill-graph Markdown and return the JSON-ready graph.

    Parameters
    ----------
    doc_text : str
        Contents of docs/plan/02-skill-graph.md.
    tips : dict[str, str]
        Real-editor tip per skill id.

    Returns
    -------
    dict
        ``{"version", "targetBase", "perKey", "langs", "skills": {id: node}, "tips"}``.
    """
    skills = _parse_tiers(doc_text)
    _expand_prereqs(skills)
    weights = _parse_weights(doc_text, set(skills))
    for order, (skill_id, node) in enumerate(skills.items()):
        node["order"] = order
        node["targetBase"] = TARGET_BASE
        node["perKey"] = PER_KEY
        node["enabled"] = node["tier"] <= DEFAULT_ENABLED_MAX_TIER
        node["langWeights"] = weights.get(skill_id, {lang: 1.0 for lang in LANGS})
    unknown = sorted(set(tips) - set(skills))
    if unknown:
        raise ValueError(f"tips.json names unknown skills: {unknown}")
    return {
        "version": 1,
        "source": "docs/plan/02-skill-graph.md",
        "targetBase": TARGET_BASE,
        "perKey": PER_KEY,
        "langs": list(LANGS),
        "skills": skills,
        "tips": tips,
    }


def main():
    """Write the generated graph to every output path."""
    tips = json.loads(TIPS.read_text())
    graph = build_graph(DOC.read_text(), tips)
    text = json.dumps(graph, indent=1, ensure_ascii=True) + "\n"
    for path in OUTPUTS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"wrote {path.relative_to(ROOT)} ({len(graph['skills'])} skills)", file=sys.stderr)


# Private Functions ================================================================================

def _parse_tiers(doc_text: str) -> dict[str, dict]:
    """Return skills in document order, keyed by id."""
    skills: dict[str, dict] = {}
    tier: int | None = None
    tier_name = ""
    header: list[str] | None = None
    for line in doc_text.splitlines():
        heading = TIER_RE.match(line)
        if heading:
            tier, tier_name, header = int(heading.group(1)), heading.group(2).strip(), None
            continue
        if line.startswith("## "):
            tier = None
            continue
        if tier is None or not line.startswith("|"):
            continue
        cells = _split_row(line)
        if header is None:
            header = [cell.lower() for cell in cells]
            continue
        if set(line) <= set("|-: "):
            continue
        row = dict(zip(header, cells))
        skills[row["id"]] = _node_from_row(row, tier, tier_name)
    return skills


def _node_from_row(row: dict[str, str], tier: int, tier_name: str) -> dict:
    """Build one skill node from a parsed table row."""
    return {
        "id": row["id"],
        "tier": tier,
        "tierName": tier_name,
        "keys": row.get("keys", ""),
        "what": row.get("what it is", ""),
        "prereqs": _raw_prereqs(row.get("prereqs", "")),
        "emulator": _parse_emulator(row.get("emulator"), tier),
    }


def _split_row(line: str) -> list[str]:
    """Split a Markdown table row into stripped cells."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _raw_prereqs(cell: str) -> list[str]:
    """Return prerequisite tokens; 'all of tier N' is kept as a marker for expansion."""
    tier_ref = re.match(r"all of tier (\d+)", cell)
    if tier_ref:
        return [f"@tier{tier_ref.group(1)}"]
    return [token.strip("`") for token in cell.split() if token.strip("`")]


def _expand_prereqs(skills: dict[str, dict]):
    """Replace '@tierN' markers and validate that every prerequisite exists."""
    for skill_id, node in skills.items():
        expanded: list[str] = []
        for token in node["prereqs"]:
            if token.startswith("@tier"):
                tier = int(token.removeprefix("@tier"))
                expanded += [other for other, o in skills.items() if o["tier"] == tier and other != skill_id]
                continue
            if token not in skills:
                raise ValueError(f"{skill_id}: unknown prerequisite {token!r}")
            expanded.append(token)
        node["prereqs"] = expanded


def _parse_emulator(cell: str | None, tier: int) -> dict[str, str]:
    """Turn the free-text emulator cell into per-editor flags.

    Tier 12 has no emulator column: those skills are Neovim-only.
    """
    if cell is None:
        return {"neovim": "full", "vscodevim": "none", "ideavim": "none", "note": f"tier {tier}: Neovim only"}
    segments = re.split(r"[;,]", cell)
    shared = [re.sub(r"\(.*?\)", "", seg) for seg in segments if "VSC" not in seg and "IJ" not in seg]
    base = next((_first_flag(seg) for seg in shared if _first_flag(seg)), None) or "full"
    vsc = next((_first_flag(seg) for seg in segments if "VSC" in seg and _first_flag(seg)), None)
    ij = next((_first_flag(seg) for seg in segments if "IJ" in seg and _first_flag(seg)), None)
    return {"neovim": "full", "vscodevim": vsc or base, "ideavim": ij or base, "note": cell}


def _first_flag(text: str) -> str | None:
    """Return the first support keyword appearing in text, by position."""
    found = [(m.start(), m.group(0)) for m in re.finditer(r"\b(full|partial|none|verify)\b", text)]
    return min(found)[1] if found else None


def _parse_weights(doc_text: str, skill_ids: set[str]) -> dict[str, dict[str, float]]:
    """Parse the per-language weights table into ``{skill: {lang: weight}}``."""
    section = doc_text.split("## Per-language weights", 1)[1].split("\n## ", 1)[0]
    rows = [_split_row(line) for line in section.splitlines() if line.startswith("|")]
    header, body = rows[0], [row for row in rows[2:]]
    columns = header[1:]
    weights: dict[str, dict[str, float]] = {}
    for row in body:
        targets = _weight_row_skills(row[0], skill_ids)
        values = {lang: 1.0 for lang in LANGS}
        for column, cell in zip(columns, row[1:]):
            for lang in WEIGHT_COLUMNS[column]:
                values[lang] = float(cell.split()[0])
        for skill_id in targets:
            weights[skill_id] = dict(values)
    return weights


def _weight_row_skills(label: str, skill_ids: set[str]) -> tuple[str, ...]:
    """Return the skill ids a weight-table row applies to."""
    for prefix, override in WEIGHT_ROW_OVERRIDES.items():
        if label.startswith(prefix):
            return override
    found = tuple(token for token in SKILL_ID_RE.findall(label) if token in skill_ids)
    if not found:
        raise ValueError(f"weight row names no known skill: {label!r}")
    return found


if __name__ == "__main__":
    main()
