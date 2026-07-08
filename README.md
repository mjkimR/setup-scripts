# Development Environment Setup Scripts

An interactive, terminal-based (TUI) setup tool for automating the configuration of fresh development environments on macOS and Ubuntu.

## Features

- **No Dependency TUI Menu**: Uses pure Bash (ANSI escape codes) to draw an interactive checkbox list. Navigate with arrow keys, select/deselect with Space, and confirm with Enter.
- **Cohesive Modular Design**: Every tool is packaged in its own directory under `modules/` (e.g. `git/`, `nvm/`), grouping Linux/macOS installers (`install.sh`) and future Windows installers (`install.ps1`) together.
- **Git Installer & Configurer**: Installs Git and configures global credentials dynamically.
- **NVM & Node 24**: Sets up Node Version Manager and configures Node.js v24 LTS as the default.
- **Astral UV**: Installs the high-performance Python package manager.
- **Zsh & Oh My Zsh**: Performs unattended setup of Zsh, Oh My Zsh, and installs helper plugins (`zsh-autosuggestions`, `zsh-syntax-highlighting`).
- **IDE Sync (VS Code, Cursor, VSCodium)**: Auto-detects installed editors, backs up existing configurations, copies preset settings/keybindings, and auto-installs plugins listed in `extensions.txt`.

---

## Directory Structure

```text
setup-scripts/
├── setup.sh          # Main entry point script (for macOS/Ubuntu)
├── setup.ps1         # [Future] Entry point script (for Windows)
├── README.md         # Documentation
├── lib/              # Shared helper libraries (UI & Utilities)
├── config/           # VS Code settings and extension lists
└── modules/          # Installation scripts grouped by tool categories
```

---

## Usage

Simply make the entry point script executable and run it:

```bash
# Make sure files are executable
chmod +x setup.sh lib/*.sh modules/terminal/*/install.sh modules/ide/*/install.sh

# Run the setup wizard
./setup.sh
```

### Customizing Configuration Files

Before running the script, you can adjust the configs inside the `config/` directory to suit your preferences:

1. **`config/vscode/settings.json`**: Place your customized IDE settings here (e.g., font size, tab sizing, format-on-save preference).
2. **`config/vscode/keybindings.json`**: Add your custom editor shortcut mappings.
3. **`config/extensions.txt`**: List the extensions you want to install, one per line. Blank lines and lines starting with `#` are ignored.
