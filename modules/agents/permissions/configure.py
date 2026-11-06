"""Stage a narrow Codex permission profile, preserving user-owned TOML text."""

import copy
import json
import re
import sys
import tomllib
from pathlib import Path


BEGIN = "# BEGIN setup-scripts:codex-permissions\n"
END = "# END setup-scripts:codex-permissions\n"
PROFILE = "setup-scripts-dev"


def skip(reason):
    print(f"[INFO] Skipping Codex permissions: {reason}")


def configure(source, cache):
    data = tomllib.loads(source)
    if "sandbox_mode" in data or "sandbox_workspace_write" in data or any(
        "sandbox_mode" in profile or "sandbox_workspace_write" in profile
        for profile in data.get("profiles", {}).values()
    ):
        skip("legacy sandbox settings are present; migrate them manually first.")
        return source

    parent = data.get("default_permissions", ":workspace")
    profiles = data.get("permissions", {})
    managed = source.startswith(BEGIN)
    if managed:
        if source.count(BEGIN) != 1 or source.count(END) != 1:
            raise ValueError("Invalid managed permission block markers")
        body = source.split(END, 1)[1]
        parent = profiles[PROFILE]["extends"]
        if data.get("default_permissions") != PROFILE:
            raise ValueError("The managed permission profile is no longer selected")
    else:
        if BEGIN.strip() in source or END.strip() in source:
            raise ValueError("Invalid managed permission block markers")
        if PROFILE in profiles:
            raise ValueError(f"User-owned permission profile {PROFILE!r} already exists")
        body = source
        if "default_permissions" in data:
            # Only remove a single-line root assignment. The semantic comparison
            # below rejects any accidental match inside a string or nested table.
            pattern = r"(?m)^[ \t]*(?:default_permissions|\"default_permissions\"|'default_permissions')[ \t]*=[^\n]*(?:\n|$)"
            body, count = re.subn(pattern, "", body, count=1)
            if count != 1:
                raise ValueError("Cannot safely replace default_permissions")

    if parent == ":danger-full-access":
        skip("the active profile already has full access.")
        return source
    if parent not in (":workspace", ":read-only") and parent not in profiles:
        raise ValueError(f"Unknown parent permission profile: {parent!r}")
    cache_path = Path(cache)
    if not cache_path.is_absolute() or cache_path == Path(cache_path.anchor):
        raise ValueError("uv cache dir must return an absolute, non-root cache path")

    # Dotted keys keep the entire managed block at root scope before user tables.
    prefix = f"permissions.{PROFILE}"
    block = (
        BEGIN
        + f'default_permissions = "{PROFILE}"\n'
        + f"{prefix}.extends = {json.dumps(parent)}\n"
        + f'{prefix}.filesystem.":workspace_roots".".git" = "write"\n'
        + f'{prefix}.filesystem.{json.dumps(str(cache_path), ensure_ascii=False)} = "write"\n'
        + END
    )
    result = block + body
    updated = tomllib.loads(result)
    before = copy.deepcopy(data)
    after = copy.deepcopy(updated)
    for config in (before, after):
        config.pop("default_permissions", None)
        config.get("permissions", {}).pop(PROFILE, None)
        if config.get("permissions") == {}:
            config.pop("permissions")
    if before != after:
        raise ValueError("Refusing to change settings outside the managed profile")
    return result


def main():
    source, staged, cache = sys.argv[1:]
    try:
        original = Path(source).read_text(encoding="utf-8")
        result = configure(original, cache)
    except (ValueError, KeyError, TypeError) as exc:
        print(f"[ERROR] Cannot configure Codex permissions: {exc}", file=sys.stderr)
        return 1
    if result == original:
        if result.startswith(BEGIN):
            print("[INFO] Codex permissions are already up to date.")
    else:
        Path(staged).write_text(result, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
