# Test boundaries and layout

- Unit tests exercise parsing, configuration, error contracts and command building
  with controlled inputs/doubles. No real Git or agent subprocess is started.
- Integration tests exercise actual Git, filesystem state, installed command
  boundaries and installers, with temporary homes and stubbed external providers.
- E2e is reserved for actual machine provisioning/user journeys. This repository
  intentionally has no routine live installer e2e suite.

Shell suites mirror `modules/` under `tests/integration/modules/`. Each Python tool
keeps its own environment and `tests/unit/` / `tests/integration/`, mirroring
`src/<tool>/` below those tiers. Shared Git builders live in `tests/support/` and
CLI stubs in `tests/stubs/`; never invoke a real agent, clipboard, or installer on
the developer's configuration as part of these tests.

```sh
bash tests/run-all.sh                # all shell and Python tests
bash tests/run-all.sh '' unit        # all tool unit tests
bash tests/run-all.sh '' integration # shell + tool integration
bash tests/run-all.sh agentkit unit  # one tool's unit tests
bash tests/run-all.sh terminal       # focused installer integration
./check.sh --check                   # formatting, lint, and all tests
```

The first argument remains a suite-name substring; the optional second argument
selects a tier. Full checks keep all suites. Use unit plus relevant integration
while iterating, and `check.sh --check` before completion. Missing uv is reported
as skipped, not successful Python verification.
