#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
export PERMISSIONS_INSTALLER="$PROJECT_ROOT/modules/agents/permissions/install.sh"

python3 - <<'PY'
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest


class PermissionInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="codex-permissions-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.target = self.home / ".codex/config.toml"
        self.cache = self.home / 'cache with "quotes" and 한글'
        self.bin = self.root / "bin"
        self.bin.mkdir()
        uv = self.bin / "uv"
        uv.write_text('#!/bin/sh\n[ "$PWD" = "$HOME" ] || exit 1\n[ "$*" = "cache dir" ] || exit 1\nprintf "%s\\n" "$TEST_CACHE"\n')
        uv.chmod(0o755)
        self.env = {"HOME": str(self.home), "PATH": f"{self.bin}:/usr/bin:/bin",
                    "TEST_CACHE": str(self.cache)}

    def write(self, text):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text(text)

    def run_installer(self, success=True):
        result = subprocess.run(["bash", os.environ["PERMISSIONS_INSTALLER"]],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result.stdout

    def parsed(self):
        return tomllib.loads(self.target.read_text())

    def test_missing_config_skips_without_creating_directories(self):
        self.assertIn("[INFO]", self.run_installer())
        self.assertFalse(self.target.parent.exists())

    def test_install_without_codex_cli_and_repeat(self):
        original = '# Personal settings\nmodel = "existing-model"\n[features]\nnetwork_proxy = true\n'
        self.write(original)
        self.target.chmod(0o640)
        self.run_installer()
        data = self.parsed()
        profile = data["permissions"]["setup-scripts-dev"]
        self.assertEqual(data["default_permissions"], "setup-scripts-dev")
        self.assertEqual(profile, {"extends": ":workspace", "filesystem": {
            ":workspace_roots": {".git": "write"}, str(self.cache): "write"}})
        self.assertTrue(self.target.read_text().endswith(original))
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o640)
        backup = Path(str(self.target) + ".bak")
        latest = Path(str(self.target) + ".bak.latest")
        self.assertEqual(backup.read_text(), original)
        installed = self.target.read_bytes()
        stamp = self.target.stat().st_mtime_ns
        self.assertIn("already up to date", self.run_installer())
        self.assertEqual(self.target.read_bytes(), installed)
        self.assertEqual(self.target.stat().st_mtime_ns, stamp)
        self.assertEqual(latest.read_text(), original)
        self.env["TEST_CACHE"] = str(self.home / "new cache")
        self.run_installer()
        self.assertEqual(backup.read_text(), original)
        self.assertEqual(latest.read_bytes(), installed)
        self.assertNotIn(str(self.cache), self.parsed()["permissions"]["setup-scripts-dev"]["filesystem"])

    def test_inherits_existing_profile_and_keeps_network_and_approvals(self):
        self.write('''"default_permissions" = "personal" # previous selection
approval_policy = "on-request"
[permissions.personal]
extends = ":workspace"
[permissions.personal.filesystem]
"~/private" = "deny"
[permissions.personal.network]
enabled = false
''')
        before = self.parsed()
        self.run_installer()
        after = self.parsed()
        self.assertEqual(after["permissions"]["personal"], before["permissions"]["personal"])
        self.assertEqual(after["approval_policy"], before["approval_policy"])
        self.assertEqual(after["permissions"]["setup-scripts-dev"]["extends"], "personal")

    def test_skip_legacy_and_full_access(self):
        for config in ('sandbox_mode = "workspace-write"\n',
                       '[sandbox_workspace_write]\nwritable_roots = ["/tmp/custom"]\n',
                       '[profiles.old]\nsandbox_mode = "read-only"\n',
                       'default_permissions = ":danger-full-access"\n'):
            with self.subTest(config=config):
                self.write(config)
                self.assertIn("Skipping", self.run_installer())
                self.assertEqual(self.target.read_text(), config)
                self.assertFalse(Path(str(self.target) + ".bak").exists())

    def test_reject_invalid_configs_without_backups(self):
        for config in ('invalid = [',
                       '# BEGIN setup-scripts:codex-permissions\n',
                       '[permissions.setup-scripts-dev]\nextends = ":workspace"\n',
                       'default_permissions = "unknown"\n'):
            with self.subTest(config=config):
                self.write(config)
                self.run_installer(success=False)
                self.assertEqual(self.target.read_text(), config)
                self.assertFalse(Path(str(self.target) + ".bak").exists())

    def test_reject_unsafe_cache_path(self):
        for cache in ("/", "relative/cache", ""):
            with self.subTest(cache=cache):
                self.write('model = "keep"\n')
                self.env["TEST_CACHE"] = cache
                self.run_installer(success=False)
                self.assertEqual(self.target.read_text(), 'model = "keep"\n')

    def test_custom_codex_home(self):
        self.target = self.home / "custom codex/config.toml"
        self.env["CODEX_HOME"] = str(self.target.parent)
        self.write("")
        self.run_installer()
        self.assertEqual(self.parsed()["default_permissions"], "setup-scripts-dev")
        self.assertFalse((self.home / ".codex").exists())

    def test_symlink_not_followed(self):
        self.target.parent.mkdir()
        other = self.home / "original.toml"
        other.write_text('model = "keep"\n')
        self.target.symlink_to(other)
        self.run_installer(success=False)
        self.assertTrue(self.target.is_symlink())
        self.assertEqual(other.read_text(), 'model = "keep"\n')


unittest.main()
PY
