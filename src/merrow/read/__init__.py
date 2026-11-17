"""Diagram readers: each turns a format into the neutral Graph."""

import re


def skipper(patterns: object) -> re.Pattern[str] | None:
    """Return one regex matching any of a reader's `skip_labels`, or None."""
    listed = [str(p) for p in patterns] if isinstance(patterns, list) else []
    return re.compile("|".join(f"(?:{p})" for p in listed)) if listed else None
