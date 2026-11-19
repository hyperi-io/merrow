"""Lint finding ids: the name each finding prints first, which a profile waives it by."""

from collections.abc import Collection, Iterable

IDS = frozenset(
    {
        "acc-descr",
        "acc-title",
        "arrows",
        "back-arrow",
        "back-arrows",
        "banned-syntax",
        "boundary-missing",
        "boundary-phantom",
        "caption",
        "caption-styling",
        "caption-up",
        "class-line",
        "class-lines-incomplete",
        "class-undefined",
        "colour-classes",
        "crossing",
        "default-class",
        "direction",
        "fence",
        "figure-numbers",
        "frontmatter",
        "graph-keyword",
        "h1-anchor",
        "height",
        "html-entity",
        "icon-pack",
        "intro-announces",
        "label-styling",
        "label-wrap",
        "landscape",
        "node-arrows",
        "nodes",
        "orphan",
        "overlap",
        "parse",
        "participants",
        "sequence-colour",
        "skip-arrow",
        "state-default-class",
        "state-direction",
        "subgraphs",
        "text-diagram",
        "through-box",
        "title-level",
        "two-way",
        "type",
        "uncoloured-type",
        "vertical-chain",
        "width",
    }
)


def finding(key: str, text: str) -> str:
    """Return a finding as lint prints it: `[id] text`.

    Raises:
        KeyError: The id isn't in `IDS`.
    """
    if key not in IDS:
        raise KeyError(key)
    return f"[{key}] {text}"


def unwaived(problems: Iterable[str], waive: Collection[str]) -> list[str]:
    """Return the findings whose id isn't in `waive`."""
    return [
        problem for problem in problems if problem[1 : problem.find("]")] not in waive
    ]
