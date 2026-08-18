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
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EFFORT = "medium"
DEFAULT_TIMEOUT = "600s"

_DENIED_COMMAND = re.compile(r'permission check failed for command "([^"]*)"')
_DENIAL_MARKER = re.compile(r"headless mode cannot prompt", re.IGNORECASE)
_AUTH_MARKER = re.compile(r"auth|login|credential|unauthenticated|token", re.IGNORECASE)
_QUOTA_MARKER = re.compile(r"quota|rate.?limit|resource.?exhausted|too many requests|usage limit", re.IGNORECASE)
_TIMEOUT_MARKER = re.compile(r"\btimed? ?out\b|deadline exceeded", re.IGNORECASE)


@dataclass
class AgyRun:
    """One `agy -p` invocation: what it printed, and what its log revealed."""

    output: str
    log: str

    def denied_commands(self) -> list[str]:
        """Extract refused commands from the agy log output."""
        return sorted(set(_DENIED_COMMAND.findall(self.log)))

    @property
    def hit_permission_wall(self) -> bool:
        return bool(_DENIAL_MARKER.search(self.output))

    @property
    def looks_unauthenticated(self) -> bool:
        return bool(_AUTH_MARKER.search(self.output))

    @property
    def looks_quota_limited(self) -> bool:
        return bool(_QUOTA_MARKER.search(self.output))

    @property
    def looks_timed_out(self) -> bool:
        return bool(_TIMEOUT_MARKER.search(self.output))


@dataclass
class AgyClient:
    effort: str | None = DEFAULT_EFFORT  # None: leave it to agy's own default
    timeout: str = DEFAULT_TIMEOUT
    model: str | None = None  # None: whatever the Antigravity CLI is configured with
    # Execution mode, e.g. "accept-edits" to auto-approve file edits. None keeps
    # agy's default, where a headless run soft-denies every edit. Verified
    # against agy 1.1.12: accept-edits applies edits without prompting.
    mode: str | None = None
    executable: str = "agy"

    @property
    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def run(
        self,
        prompt: str,
        *,
        add_dir: Path,
        extra_dirs: Sequence[Path] = (),
        env: dict[str, str] | None = None,
    ) -> AgyRun:
        args = [self.executable, "-p", prompt, "--add-dir", str(add_dir)]
        for extra in extra_dirs:
            args += ["--add-dir", str(extra)]
        if self.mode is not None:
            args += ["--mode", self.mode]
        if self.effort is not None:
            args += ["--effort", self.effort]
        if self.model is not None:
            args += ["--model", self.model]
        # Ensure agy runs strictly within the target directory.
        with tempfile.TemporaryDirectory(prefix="agentkit-agy-") as scratch:
            log_path = Path(scratch) / "agy.log"
            process = subprocess.run(
                [
                    *args,
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
