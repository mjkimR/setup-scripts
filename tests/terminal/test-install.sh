#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
python3 - <<'PY'
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path.cwd()


class TerminalInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'setup'
        shutil.copytree(ROOT / 'modules/terminal', self.project / 'modules/terminal')
        shutil.copytree(ROOT / 'modules/terminal-addons', self.project / 'modules/terminal-addons')
        shutil.copytree(ROOT / 'lib', self.project / 'lib')
        shutil.copy(ROOT / 'setup.sh', self.project / 'setup.sh')
        with (self.project / 'lib/utils.sh').open('a') as stream:
            stream.write('\nget_os() { echo "$TEST_OS"; }\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.home = self.root / 'home'
        self.home.mkdir()
        self.log = self.root / 'calls'
        self.log.touch()
        self.env = {
            'HOME': str(self.home), 'PATH': str(self.bin), 'TEST_OS': 'macos',
            'CALLS': str(self.log), 'SETUP_INSTALL_ONLY': '1',
        }
        for name in ('bash', 'sh', 'dirname', 'mkdir', 'chmod', 'mktemp', 'rm'):
            (self.bin / name).symlink_to(shutil.which(name))
        install_stub = '\n[ "${FAIL:-0}" != 1 ] || exit 9\nfor arg; do case "$arg" in just|apm|gh|ripgrep|gcloud-cli|google-cloud-cli|snapd|docker-desktop) name="$arg" ;; esac; done\ncase "$name" in ripgrep) name=rg ;; gcloud-cli|google-cloud-cli) name=gcloud ;; snapd) name=snap ;; docker-desktop) name=docker ;; esac\nprintf "#!/bin/sh\\nexit 0\\n" > "$(dirname "$0")/$name"\nchmod +x "$(dirname "$0")/$name"'
        self.stub('brew', 'echo "brew $*" >> "$CALLS"' + install_stub)
        self.stub('sudo', 'echo "sudo $*" >> "$CALLS"\nif [ "$1" = sh ]; then name=docker-desktop; fi\nif [ "$2" = update ]; then exit 0; fi' + install_stub)
        self.stub('curl', '''echo "curl $*" >> "$CALLS"
[ "${FAIL:-0}" != 1 ] || exit 9
case "$*" in
  *just.systems*) name=just ;;
  *apm-unix*) name=apm ;;
  *get.docker.com*) printf "#!/bin/sh\\nexit 0\\n" > "$4"; exit 0 ;;
  *) exit 8 ;;
esac
printf 'mkdir -p "$HOME/.local/bin"\nprintf "#!/bin/sh\\\\nexit 0\\\\n" > "$HOME/.local/bin/%s"\nchmod +x "$HOME/.local/bin/%s"\n' "$name" "$name"
''')

    def stub(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)

    def run_module(self, name):
        return subprocess.run(
            ['/bin/bash', str(self.project / f'modules/terminal/{name}/install.sh')],
            env=self.env, capture_output=True, text=True,
        )

    def test_new_tools_install_and_skip_on_both_platforms(self):
        for platform in ('macos', 'ubuntu'):
            self.env['TEST_OS'] = platform
            for name, command in [('just', 'just'), ('ripgrep', 'rg'), ('apm', 'apm'), ('gh', 'gh'), ('gcloud', 'gcloud'), ('docker', 'docker')]:
                with self.subTest(platform=platform, name=name):
                    result = self.run_module(name)
                    self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
                    calls = self.log.read_text()
                    self.assertTrue(calls)
                    result = self.run_module(name)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(self.log.read_text(), calls)
                    for directory in (self.bin, self.home / '.local/bin'):
                        (directory / command).unlink(missing_ok=True)
                    self.log.write_text('')

    def test_failed_install_is_not_reported_as_success(self):
        self.env['FAIL'] = '1'
        for platform in ('macos', 'ubuntu'):
            self.env['TEST_OS'] = platform
            for name in ('just', 'apm', 'gh', 'gcloud', 'docker'):
                with self.subTest(platform=platform, name=name):
                    self.assertNotEqual(self.run_module(name).returncode, 0)

    def test_docker_without_compose_is_preserved_and_reported(self):
        self.stub('docker', 'if [ "$1" = compose ]; then exit 1; fi')
        result = self.run_module('docker')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Compose is missing', result.stderr)
        self.assertEqual(self.log.read_text(), '')

    def test_existing_git_uv_and_nvm_skip_install_and_configuration(self):
        for name in ('git', 'uv', 'node', 'npm'):
            self.stub(name, 'echo "$0 $*" >> "$CALLS"')
        nvm = self.home / '.nvm/nvm.sh'
        nvm.parent.mkdir()
        nvm.write_text('nvm() { case "$1" in version) echo v24.0.0 ;; install|alias) return 99 ;; esac; }\n')
        for name in ('git', 'uv', 'nvm'):
            result = self.run_module(name)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        calls = self.log.read_text()
        for forbidden in ('config', 'brew', 'sudo', 'curl', 'clone'):
            self.assertNotIn(forbidden, calls)

    def test_terminal_mode_runs_every_registered_terminal_and_stops_on_failure(self):
        for path in (self.project / 'modules/terminal').glob('*/install.sh'):
            name = path.parent.name
            path.write_text(f'#!/bin/bash\n[ "$SETUP_INSTALL_ONLY" = 1 ] || exit 7\necho {name} >> "$CALLS"\n')
        def run():
            return subprocess.run(['/bin/bash', str(self.project / 'setup.sh'), '--terminal'],
                                  env=self.env, capture_output=True, text=True)
        (self.project / 'modules/terminal-addons/zsh/install.sh').write_text('exit 88\n')
        result = run()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text().splitlines(), ['git', 'nvm', 'uv', 'just', 'ripgrep', 'apm', 'gh', 'gcloud', 'docker'])
        self.log.write_text('')
        (self.project / 'modules/terminal/nvm/install.sh').write_text('exit 9\n')
        self.assertEqual(run().returncode, 9)
        self.assertEqual(self.log.read_text().splitlines(), ['git'])


unittest.main()
PY
