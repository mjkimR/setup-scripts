# Terminal tools

`setup.sh --terminal` installs every tool registered in `setup.sh` and stops on
failure. Each module can also run independently. Existing commands are preserved;
installers do not log in, change cloud projects, or rewrite Git identities.

| Tool | Used by | macOS | Ubuntu |
| --- | --- | --- | --- |
| Git, NVM/Node 24, UV, just, ripgrep, APM | Repository setup and development | Existing modules | Existing modules |
| gh | GitHub webhook registration and repository automation | Homebrew `gh` | APT `gh` |
| gcloud | Secret Manager, Cloud Run, production initialization | Homebrew `gcloud-cli` cask | Snap `google-cloud-cli --classic` (installs snapd if absent) |
| Docker + Compose | workbench services and container-backed tests | Homebrew `docker-desktop` cask | Docker's development convenience installer |

After installation, authenticate gh/gcloud only when needed. Open Docker Desktop
once on macOS to finish setup and start the engine. On Ubuntu, configure rootless
Docker or group access separately; this installer does not alter user groups.
An existing Docker without Compose is reported as incomplete rather than replaced
with another distribution. Install its matching Compose plugin and rerun setup.

Python tools such as pyright/ruff and frontend tools such as Prettier/Svelte/Vite
belong to each repository's UV/npm dependency files, not global terminal installs.

Installation references: [GitHub CLI](https://github.com/cli/cli/blob/trunk/docs/install_linux.md),
[gcloud Homebrew](https://docs.cloud.google.com/sdk/docs/downloads-homebrew),
[gcloud Snap](https://cloud.google.com/sdk/docs/downloads-snap),
[Docker Desktop cask](https://formulae.brew.sh/cask/docker-desktop),
[Docker development installer](https://docs.docker.com/engine/install/ubuntu/#install-using-the-convenience-script).
