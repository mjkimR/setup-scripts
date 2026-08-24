"""Pre-commit guardrails: where a commit lands, and what goes into it.

commit-safe already refuses the wrong identity and controls the timestamp.
These are the other two questions a commit can get wrong — the branch it
lands on, and the credential someone staged by accident. Both were written
down in the git-commit skill as instructions to the agent; an instruction is
something a model can reason past, so they live here instead.

Detection is deliberately narrow. Every pattern below matches a vendor's own
issued-token format at its own length, which is not a shape that occurs by
accident, so a hit can block rather than warn. Warning would be close to
useless here anyway: the skill tells the agent to commit without asking, so a
line of advice on stderr is a line the agent reads and then commits past.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .. import gitutil
from ..errors import DeniedPathError, ProtectedBranchError, SecretDetectedError
from ..repoconfig import GuardsConfig, load_repo_config

# (label, pattern). Prefix alone is not enough — `sk-` matches SKUs and any
# number of ordinary identifiers — so each of these pins the vendor prefix to
# the length that vendor issues.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("GitHub personal access token", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}")),
    ("Anthropic API key", re.compile(r"\bsk-ant-api\d{2}-[A-Za-z0-9_-]{50,}")),
    ("OpenAI API key", re.compile(r"\bsk-proj-[A-Za-z0-9_-]{40,}")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
)


@dataclass(frozen=True)
class Finding:
    path: str
    label: str
    line: str

    def describe(self) -> str:
        return f"{self.path}: {self.label} — {_redact(self.line)}"


def load_guards(cwd: Path | None = None) -> GuardsConfig:
    """The repository's guard settings, or the defaults.

    A repository that never onboarded still gets the content scan: it costs
    one `git diff` and its patterns do not fire on ordinary code. The two path
    lists stay empty, because those only ever mean something a repo configured.
    """
    repo_cfg = load_repo_config(cwd=cwd)
    return repo_cfg.guards if repo_cfg is not None else GuardsConfig()


def check(
    guards: GuardsConfig,
    *,
    cwd: Path | None = None,
    allow_secret: tuple[str, ...] = (),
) -> list[str]:
    """Run every enabled guard, raising on the first that refuses.

    Returns the lines describing what ran, for the caller to echo.
    """
    if not guards.enabled:
        return ["Guards:     [OFF]"]

    notes: list[str] = []
    _check_branch(guards, cwd=cwd, notes=notes)
    _check_paths(guards, cwd=cwd, notes=notes)
    _check_secrets(guards, cwd=cwd, allow_secret=allow_secret, notes=notes)
    return notes


def _check_branch(guards: GuardsConfig, *, cwd: Path | None, notes: list[str]) -> None:
    if not guards.protected_branches:
        return

    # Empty on a detached HEAD, which no pattern can match — and there the
    # branch is not what makes the commit questionable.
    branch = gitutil.run(["branch", "--show-current"], cwd=cwd).strip()
    if branch and guards.protects(branch):
        raise ProtectedBranchError(
            f"'{branch}' is a protected branch in this repository.",
            what_to_report=(
                f"Committing directly to '{branch}' is blocked by the repository's guard settings. "
                "The user decides whether to branch off or to lift the protection."
            ),
            details=[
                f"Protected: {', '.join(guards.protected_branches)}",
                "Create a branch and commit there, or have the user adjust "
                "`agentkit commit config --set guards.protected_branches=…`.",
            ],
        )
    notes.append(f"Branch:     {branch or 'HEAD detached'} (not protected)")


def _check_paths(guards: GuardsConfig, *, cwd: Path | None, notes: list[str]) -> None:
    if not guards.deny_paths:
        return

    denied = [path for path in _staged_paths(cwd=cwd) if guards.denies(path)]
    if denied:
        raise DeniedPathError(
            f"{len(denied)} staged path(s) match this repository's deny list.",
            what_to_report=(
                "Staged files match the repository's deny list, so nothing was committed. "
                "The user decides whether to unstage them or amend the list."
            ),
            details=[*denied, f"Deny list: {', '.join(guards.deny_paths)}"],
        )
    notes.append(f"Paths:      {len(guards.deny_paths)} deny rule(s), no match")


def _check_secrets(
    guards: GuardsConfig,
    *,
    cwd: Path | None,
    allow_secret: tuple[str, ...],
    notes: list[str],
) -> None:
    if not guards.scan_secrets:
        return

    exempt = set(allow_secret)
    findings = [
        finding for finding in scan_staged(cwd=cwd) if finding.path not in exempt and not guards.exempts(finding.path)
    ]
    if findings:
        raise SecretDetectedError(
            f"staged content matches {len(findings)} known credential format(s).",
            what_to_report=(
                "Staged content looks like a real credential, so nothing was committed. "
                "The user must confirm whether it is a secret — never commit past this on your own."
            ),
            details=[
                *(finding.describe() for finding in findings),
                "If it is a placeholder or a test fixture, the user can re-run with "
                "`--allow-secret <path>`, or record it in `guards.allow_paths`.",
            ],
        )
    if exempt:
        notes.append(f"Secrets:    scanned, exempted by --allow-secret: {', '.join(sorted(exempt))}")
    else:
        notes.append("Secrets:    scanned, none found")


def scan_staged(cwd: Path | None = None) -> list[Finding]:
    """Scan the lines the staged diff adds, attributing each to its file."""
    # -U0 keeps context lines out: an untouched neighbouring line is not
    # something this commit introduces, and flagging it would block a commit
    # for a secret that is already in history.
    diff = gitutil.run(["diff", "--cached", "--no-color", "-U0"], cwd=cwd)

    findings: list[Finding] = []
    path = "(unknown)"
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            path = target[2:] if target.startswith("b/") else target
            continue
        # `+++` is handled above, so what remains starting with a single `+`
        # is an added line.
        if not line.startswith("+"):
            continue
        content = line[1:]
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(content):
                findings.append(Finding(path=path, label=label, line=content))
                break
    return findings


def _staged_paths(cwd: Path | None = None) -> list[str]:
    output = gitutil.run(["diff", "--cached", "--name-only"], cwd=cwd)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _redact(line: str) -> str:
    """Show enough of the offending line to locate it, never the secret."""
    stripped = line.strip()
    for _, pattern in SECRET_PATTERNS:
        match = pattern.search(stripped)
        if match:
            found = match.group(0)
            return stripped.replace(found, f"{found[:8]}…[redacted]")
    return stripped[:60]
