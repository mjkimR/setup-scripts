"""Invoking `agy` headlessly and reading what came back.

The one thing to know about headless `agy`: its exit code and its JSON status
carry no signal. With nobody to prompt for tool permission it soft-denies,
returns `{"status":"SUCCESS","response":""}` and exits 0. So this module never
reports success — it reports what `agy` said, and the caller decides by looking
at the world.

Verified against agy 1.1.12.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_EFFORT = "low"
DEFAULT_TIMEOUT = "600s"

_DENIED_COMMAND = re.compile(r'permission check failed for command "([^"]*)"')
_DENIAL_MARKER = re.compile(r"headless mode cannot prompt", re.IGNORECASE)
_AUTH_MARKER = re.compile(r"auth|login|credential|unauthenticated|token", re.IGNORECASE)


@dataclass
class AgyRun:
    """One `agy -p` invocation: what it printed, and what its log revealed."""

    output: str
    log: str

    def denied_commands(self) -> List[str]:
        """The commands `agy` refused, which only the log file names.

        stdout says merely that "a tool required the command permission". The
        log names it, which is what separates "nothing was ever granted" from
        "one rule is missing".
        """
        return sorted(set(_DENIED_COMMAND.findall(self.log)))

    @property
    def hit_permission_wall(self) -> bool:
        return bool(_DENIAL_MARKER.search(self.output))

    @property
    def looks_unauthenticated(self) -> bool:
        return bool(_AUTH_MARKER.search(self.output))


@dataclass
class AgyClient:
    effort: str = DEFAULT_EFFORT
    timeout: str = DEFAULT_TIMEOUT
    executable: str = "agy"

    @property
    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def run(
        self,
        prompt: str,
        *,
        add_dir: Path,
        env: Optional[Dict[str, str]] = None,
    ) -> AgyRun:
        # --add-dir is not optional. Without it agy resolves its own workspace
        # from its stored project list and runs commands in whatever repository
        # it used last, which with git add/commit granted means commits landing
        # in the wrong repo.
        with tempfile.TemporaryDirectory(prefix="agentkit-agy-") as scratch:
            log_path = Path(scratch) / "agy.log"
            process = subprocess.run(
                [
                    self.executable,
                    "-p",
                    prompt,
                    "--add-dir",
                    str(add_dir),
                    "--effort",
                    self.effort,
                    "--print-timeout",
                    self.timeout,
                    "--log-file",
                    str(log_path),
                ],
                cwd=str(add_dir),
                capture_output=True,
                text=True,
                env={**os.environ, **(env or {})},
            )
            log = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""

        return AgyRun(output=process.stdout + process.stderr, log=log)
