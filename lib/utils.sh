#!/usr/bin/env bash

# Color Definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0;20m' # No Color
BOLD='\033[1m'

# Logging Functions
log_info() {
  printf "${BLUE}[INFO]${NC} %b\n" "$*"
}

log_success() {
  printf "${GREEN}[SUCCESS]${NC} %b\n" "$*"
}

log_warn() {
  printf "${YELLOW}[WARN]${NC} %b\n" "$*"
}

log_error() {
  printf "${RED}[ERROR]${NC} %b\n" "$*" >&2
}

log_header() {
  printf "\n${BOLD}${BLUE}========================================= ${NC}\n"
  printf "${BOLD}${BLUE}  %b ${NC}\n" "$*"
  printf "${BOLD}${BLUE}========================================= ${NC}\n\n"
}

# OS & Environment Detection
get_os() {
  local os_name
  os_name=$(uname -s)
  if [ "$os_name" = "Darwin" ]; then
    echo "macos"
  elif [ "$os_name" = "Linux" ]; then
    if [ -f /etc/os-release ]; then
      . /etc/os-release
      if [ "$ID" = "ubuntu" ] || [ "$ID_LIKE" = "ubuntu" ] || [ "$ID" = "debian" ] || [ "$ID_LIKE" = "debian" ]; then
        echo "ubuntu"
      else
        echo "linux-other"
      fi
    else
      echo "linux"
    fi
  else
    echo "unknown"
  fi
}

# Check if command exists
has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

# Cache sudo password if necessary
sudo_keepalive() {
  if ! sudo -n true 2>/dev/null; then
    log_info "Sudo privileges may be required for some installations. Please enter your password:"
    sudo -v
  fi
  # Keep-alive sudo until script exits
  while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &
}
