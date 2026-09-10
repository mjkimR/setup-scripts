"""Invoking `agy` headlessly and reading what came back.

The one thing to know about headless `agy`: its exit code and its JSON status
carry no signal. With nobody to prompt for tool permission it soft-denies,
returns `{"status":"SUCCESS","response":""}` and exits 0. So this module never
reports success — it reports what `agy` said, and the caller decides by looking
at the world.

Verified against agy 1.2.0. Since 1.2.0 the `--log-file` log no longer names a
denied command: it only records `soft-denying tool confirmation "RunCommand"`
plus the conversation id. The command text lives in the conversation record
(`~/.gemini/antigravity-cli/conversations/<id>.db`), so denials are read from
both. The log itself is kept under LOG_DIR so a failed run can be examined
after the fact.
"""

from __future__ import annotations

import datetime as dt
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

# agy escapes quotes inside the command (`grep -E \"...\"`), so the class allows `\"`.
_DENIED_COMMAND = re.compile(r'permission check failed for command "((?:[^"\\]|\\.)*)"')
_CONVERSATION = re.compile(r"Print mode: conversation=([0-9a-fA-F-]{8,})")
# Where agy keeps conversation records, and where this module keeps agy's logs.
CONVERSATIONS_DIR = Path.home() / ".gemini" / "antigravity-cli" / "conversations"
LOG_DIR = Path.home() / ".local" / "state" / "agentkit" / "agy-logs"
KEEP_LOGS = 20
_DENIAL_MARKER = re.compile(r"headless mode cannot prompt", re.IGNORECASE)
_AUTH_MARKER = re.compile(r"auth|login|credential|unauthenticated|token", re.IGNORECASE)
_QUOTA_MARKER = re.compile(r"quota|rate.?limit|resource.?exhausted|too many requests|usage limit", re.IGNORECASE)
_TIMEOUT_MARKER = re.compile(r"\btimed? ?out\b|deadline exceeded", re.IGNORECASE)


@dataclass
class AgyRun:
    """One `agy -p` invocation: what it printed, and what its log revealed."""

    output: str
    log: str
    log_path: Path | None = None  # the kept copy of agy's log, if it could be kept
    conversation_db: Path | None = None  # agy's record of this run, if the log named it

    @property
    def conversation_id(self) -> str | None:
        match = _CONVERSATION.search(self.log)
        return match.group(1) if match else None

    def denied_commands(self) -> list[str]:
        """Refused commands, from the log (agy <= 1.1) and the conversation record (agy >= 1.2)."""
        found = set(_DENIED_COMMAND.findall(self.log))
        if self.conversation_db is not None and self.conversation_db.is_file():
            try:
                text = self.conversation_db.read_bytes().decode("utf-8", errors="ignore")
            except OSError:
                text = ""
            found.update(_DENIED_COMMAND.findall(text))
        return sorted(cmd.replace('\\"', '"') for cmd in found)

    def evidence(self) -> list[str]:
        """Where a reader can look after the fact."""
        out: list[str] = []
        if self.log_path is not None:
            out.append(f"Log: {self.log_path}")
        if self.conversation_id:
            where = f" ({self.conversation_db})" if self.conversation_db is not None else ""
            out.append(f"Conversation: {self.conversation_id}{where}")
        return out

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
            kept = _keep_log(log_path) if log_path.is_file() else None

        run = AgyRun(output=process.stdout + process.stderr, log=log, log_path=kept)
        if run.conversation_id:
            run.conversation_db = CONVERSATIONS_DIR / f"{run.conversation_id}.db"
        return run


def _keep_log(source: Path) -> Path | None:
    """Copy agy's log where it survives the run; keep the newest KEEP_LOGS. Never fails the run."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        target = LOG_DIR / f"{stamp}-{os.getpid()}.log"
        shutil.copyfile(source, target)
        logs = sorted(LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime)
        for old in logs[:-KEEP_LOGS]:
            old.unlink(missing_ok=True)
        return target
    except OSError:
        return None
