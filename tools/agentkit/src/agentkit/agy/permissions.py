"""Reading and extending `agy`'s command allow-list.

Headless `agy` cannot prompt, so anything outside `permissions.allow` is
auto-denied and the run silently does nothing. Granting named rules is preferred
over `--dangerously-skip-permissions`, which auto-approves every tool call
including arbitrary shell commands.

Rules are command *prefixes*, checked per `&&` segment: `command(git log)`
matches `git log -n 5 --oneline`, and one denied segment kills the whole chain.
An environment-variable prefix (`GIT_AUTHOR_DATE="…" git commit …`) does not
match `command(git commit)` at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set

from ..errors import PreflightError

# Not ~/.gemini/settings.json, and project-local .gemini/settings.json is
# ignored. `agy -p "/permissions"` prints the merged view without spending quota.
SETTINGS_PATH = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
CONFIG_PATH = Path.home() / ".gemini" / "config" / "config.json"


def settings_files() -> Sequence[Path]:
    # Resolved on every call rather than bound as a default argument, so the
    # locations stay overridable — which tests rely on.
    return (SETTINGS_PATH, CONFIG_PATH)


def granted_rules(paths: Optional[Sequence[Path]] = None) -> Set[str]:
    """Every allow rule found across agy's settings files.

    The two files do not share a schema, and the schema has changed between
    releases, so this collects any list of strings under an "allow" key at any
    depth rather than pinning one path into the document.
    """
    found: Set[str] = set()
    for path in paths if paths is not None else settings_files():
        if not path.is_file():
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        _collect_allow(document, found)
    return found


def missing_rules(
    required: Iterable[str],
    paths: Optional[Sequence[Path]] = None,
) -> List[str]:
    granted = granted_rules(paths)
    return [rule for rule in required if rule not in granted]


def grant(rules: Iterable[str], *, settings_path: Optional[Path] = None) -> List[str]:
    """Add rules to permissions.allow, backing the file up first.

    Returns the rules that were actually added; already-present ones are left
    alone rather than duplicated.
    """
    settings_path = settings_path if settings_path is not None else SETTINGS_PATH
    if not settings_path.is_file():
        raise PreflightError(
            f"Antigravity CLI settings not found at: {settings_path}",
            "Run `agy` interactively once to create it.",
        )

    document = json.loads(settings_path.read_text(encoding="utf-8"))
    allow = document.setdefault("permissions", {}).setdefault("allow", [])

    added = [rule for rule in rules if rule not in allow]
    if not added:
        return []

    backup = settings_path.with_suffix(settings_path.suffix + ".bak")
    backup.write_text(settings_path.read_text(encoding="utf-8"), encoding="utf-8")

    allow.extend(added)
    settings_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return added


def _collect_allow(node, found: Set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "allow" and isinstance(value, list):
                found.update(item for item in value if isinstance(item, str))
            else:
                _collect_allow(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect_allow(item, found)
