"""Cleanup for commit messages supplied to the checked wrapper."""

from __future__ import annotations

import re

_CO_AUTHORED_BY = re.compile(r"^[ \t]*Co-Authored-By[ \t]*:", re.IGNORECASE)


def strip_co_authored_by(message: str) -> str:
    """Remove co-author lines, preserving other text and trailers."""
    lines = message.splitlines(keepends=True)
    kept = [line for line in lines if not _CO_AUTHORED_BY.match(line)]
    if len(kept) == len(lines):
        return message
    return "".join(kept).strip("\r\n")
