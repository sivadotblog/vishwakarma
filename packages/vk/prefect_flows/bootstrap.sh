#!/usr/bin/env bash
# Install the toolchain VK needs (make, Node 22, uv) in the Prefect image, then sync deps.
set -euo pipefail

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

if ! command -v make >/dev/null 2>&1 || ! command -v node >/dev/null 2>&1; then
  $SUDO apt-get update
  $SUDO apt-get install -y make curl ca-certificates
  curl -fsSL https://deb.nodesource.com/setup_22.x | $SUDO bash -
  $SUDO apt-get install -y nodejs
fi

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/0.12.1/install.sh | sh
fi

uv sync --locked
