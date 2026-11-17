"""Icon keys from vendor names, by config rules every converter shares."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NameRule:
    r"""One `names` entry: a regex on a file's path and the key it gives.

    Attributes:
        match: Searched against the path inside the download, `/`-separated.
        key: A `re` template such as `res-\1-dark`, or None to skip the file.
        title: A `re` template for the publisher's own name, such as `\1`, or
            None for no title. `-` and `_` in it read as spaces.
    """

    match: re.Pattern[str]
    key: str | None
    title: str | None = None


def rules(raw: Sequence[Mapping[str, str | None]]) -> list[NameRule]:
    """Return a source's compiled `names` rules, in order.

    Raises:
        ValueError: A rule has no `match`.
        re.error: A rule's regex doesn't compile.
    """
    compiled = []
    for entry in raw:
        if not entry.get("match"):
            raise ValueError(f"names rule without a match: {dict(entry)}")
        compiled.append(
            NameRule(
                re.compile(str(entry["match"])), entry.get("key"), entry.get("title")
            )
        )
    return compiled


def slug(text: str) -> str:
    """Return `text` lowercased with every run of other characters as one `-`."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _first(
    path: str, rules: Sequence[NameRule]
) -> tuple[NameRule, re.Match[str]] | None:
    for rule in rules:
        found = rule.match.search(path)
        if found:
            return rule, found
    return None


def key_for(path: str, rules: Sequence[NameRule]) -> str | None | bool:
    """Return the key the first matching rule gives.

    Returns None when a rule skips the file, False when no rule matches.
    """
    hit = _first(path, rules)
    if hit is None:
        return False
    rule, found = hit
    return None if rule.key is None else slug(found.expand(rule.key))


def title_for(path: str, rules: Sequence[NameRule]) -> str | None:
    """Return the publisher's name the first matching rule gives, if it gives one."""
    hit = _first(path, rules)
    if hit is None or hit[0].title is None:
        return None
    return " ".join(re.split(r"[-_\s]+", hit[1].expand(hit[0].title))).strip()
