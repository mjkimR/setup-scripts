# Repository commit onboarding

Check if the current repository has an active commit configuration:
```bash
agentkit commit config
```

- **If configuration is missing (`[INFO] No repository commit config found`)**:
  1. Analyze git history:
     ```bash
     agentkit commit analyze
     ```
  2. In an **interactive session**, present the detected defaults and ask the user to confirm:
     - **Whitelist**: Enable author email verification? (Default: ON, email: `user.email`)
     - **Timeline**: Enable time window spoofing? (Default: OFF, 09:00~18:00 Asia/Seoul)
     - **Guards**: Any branches to protect from direct commits? (Default: none — ask, do not assume `main`). Secret scanning is on by default and needs no question.
     - **Language**: Preferred commit language (`ko` / `en`)
     - **Style & Template**: Detected style (Conventional / Bracketed / Ticket) and template
     - **Verify commands**: how to run this repo's tests and linter. If the repo has a ready-made entry point (Makefile target, package script), store that. If not, ask the user to choose: generate a small script and store its path, or store the raw shell command inline. Leaving a field empty deliberately skips that verification everywhere. Also confirm `verify.enabled`: a repo with known-broken tests can record the commands now but start switched off (`--no-verify`), flipping it back on with `agentkit commit config --set verify.enabled=true` once fixed.
     - **Auto-Push**: Enable automatic git push after commit? (Default: OFF)
     - **Hooks policy**: default `bypass-intermediate`; offer `run-all` only as a visibly closed option (it errors as not implemented).
  3. Save the configuration:
     ```bash
     agentkit commit onboard --language <ko|en> --style <style> [--whitelist/--no-whitelist] [--timeline/--no-timeline] \
       [--test-cmd "<command>"] [--lint-cmd "<command>"] [--verify/--no-verify] [--hooks <policy>] [--push/--no-push]
     ```
  In a headless handoff, use caller-supplied configuration. Only run
  `agentkit commit onboard` if the runner grants it; it initializes detected
  defaults without prompting. Otherwise report missing configuration to the caller.

- **If already onboarded**: Load and proceed with the stored configuration. For
  an explicit `/git-commit onboard` request, review the requested changes and use
  `config --set` for individual settings, or `onboard --force` for an explicitly
  authorized full replacement.

Any stored setting can be changed later with `agentkit commit config --set KEY=VALUE`.
`--set` is repeatable and applies as a unit — every pair lands, or none does:

```bash
agentkit commit config --set timeline.enabled=true --set guards.protected_branches=main,release/*
```

