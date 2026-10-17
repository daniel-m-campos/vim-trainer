"""Per-language node -> skill mappings (docs/design/content-pipeline.md, "Node -> skill mapping")."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Use:
    """One use of a node type: the skill it drills and the templates that cut exercises from it."""

    skill: str
    templates: tuple[str, ...]


@dataclass(frozen=True)
class Language:
    """A language's grammar plus its declarative node -> skill mapping."""

    name: str
    short: str
    grammar: str
    nodes: dict[str, tuple[Use, ...]]
    line_templates: tuple[Use, ...] = ()
    find_targets: tuple[str, ...] = ()
    comment_leader: str = "#"
    keywords: frozenset[str] = field(default_factory=frozenset)
