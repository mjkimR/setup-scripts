"""Invoking `codex exec` headlessly.

Unlike agy, codex's exit code is meaningful, so callers may trust it. Model and
reasoning effort default to whatever `~/.codex/config.toml` says; both can be
overridden per run. The sandbox defaults to workspace-write — continuing work
from a handoff document is pointless read-only.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SANDBOX = "workspace-write"
DEFAULT_TIMEOUT = "600s"

_DURATION = re.compile(r"^(\d+)([smh]?)$")
_UNIT_SECONDS = {"": 1, "s": 1, "m": 60, "h": 3600}


def duration_seconds(value: str) -> int:
    """Parse the Go-style duration agentkit uses everywhere ("600s", "10m")."""
    match = _DURATION.match(value.strip())
    if not match:
        raise ValueError(f"not a duration: {value!r} (expected e.g. 600s, 10m, 1h)")
    return int(match.group(1)) * _UNIT_SECONDS[match.group(2)]


@dataclass
class CodexRun:
    output: str
    exit_code: int
    timed_out: bool = False


@dataclass
class CodexClient:
    effort: str | None = None  # None: codex config default (model_reasoning_effort)
    model: str | None = None  # None: codex config default
    timeout: str = DEFAULT_TIMEOUT
    sandbox: str = DEFAULT_SANDBOX
    executable: str = "codex"

    @property
    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def run(self, prompt: str, *, workdir: Path) -> CodexRun:
        args = [self.executable, "exec", "--cd", str(workdir), "--sandbox", self.sandbox]
        if self.model is not None:
            args += ["--model", self.model]
        if self.effort is not None:
            args += ["-c", f"model_reasoning_effort={self.effort}"]
        args.append(prompt)

        try:
            process = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=duration_seconds(self.timeout),
            )
        except subprocess.TimeoutExpired as expired:
            # TimeoutExpired captures bytes on some Python versions even with text=True.
            def text(value: str | bytes | None) -> str:
                return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else (value or "")

            return CodexRun(output=text(expired.stdout) + text(expired.stderr), exit_code=124, timed_out=True)

        return CodexRun(output=process.stdout + process.stderr, exit_code=process.returncode)
