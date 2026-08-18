"""Console output.

Every line is prefixed with the tag of whatever produced it, because the reader
is usually a coding agent relaying the output to a user and needs to tell our
lines apart from the ones the delegated CLI printed.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .errors import Advisory


@dataclass
class Reporter:
    tag: str

    def note(self, message: str) -> None:
        print(f"[{self.tag}] {message}")

    def warn(self, message: str) -> None:
        print(f"[{self.tag}] {message}", file=sys.stderr)

    def advise(self, advisory: Advisory, message: str | None = None) -> None:
        """Print an advisory block for operations that report instead of raising."""
        for line in advisory.lines(message):
            self.warn(line)

    def error(self, message: str) -> None:
        print(f"[{self.tag}] ERROR: {message}", file=sys.stderr)

    def detail(self, lines: Iterable[str], *, stream=None) -> None:
        target = stream if stream is not None else sys.stdout
        for line in lines:
            print(f"  {line}", file=target)

    def block(self, title: str, body: str) -> None:
        """Reproduce another tool's output verbatim, fenced so it is skimmable."""
        print(f"\n----- {title} -----")
        print(body.rstrip("\n"))
        print("-" * (len(title) + 12) + "\n")
