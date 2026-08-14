"""Console output.

Every line is prefixed with the tag of whatever produced it, because the reader
is usually a coding agent relaying the output to a user and needs to tell our
lines apart from the ones the delegated CLI printed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Iterable


@dataclass
class Reporter:
    tag: str

    def note(self, message: str) -> None:
        print(f"[{self.tag}] {message}")

    def warn(self, message: str) -> None:
        print(f"[{self.tag}] {message}", file=sys.stderr)

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
