#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$ROOT/tools"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This setup script targets Apple Silicon macOS." >&2
  exit 1
fi
if ! command -v brew >/dev/null 2>&1; then
  echo "Install Homebrew first: https://brew.sh" >&2
  exit 1
fi

brew install python@3.12 uv ffmpeg git
PYTHON="$(brew --prefix python@3.12)/bin/python3.12"

install_requirements() {
  local directory="$1" requirements="$2"
  "$PYTHON" -m venv "$directory/.venv"
  "$directory/.venv/bin/python" -m pip install --upgrade pip
  "$directory/.venv/bin/python" -m pip install -r "$directory/$requirements"
}

install_requirements "$TOOLS/mlx-audiocraft" requirements.txt

for directory in ace-step-client phosphene-client; do
  "$PYTHON" -m venv "$TOOLS/$directory/.venv"
  "$TOOLS/$directory/.venv/bin/python" -m pip install --upgrade pip
done
"$TOOLS/ace-step-client/.venv/bin/python" -m pip install -e "$TOOLS/ace-step-client"

if [[ ! -d "$TOOLS/ACE-Step-1.5/.git" ]]; then
  git clone https://github.com/ACE-Step/ACE-Step-1.5.git "$TOOLS/ACE-Step-1.5"
fi
(cd "$TOOLS/ACE-Step-1.5" && uv sync)

# MFLUX is installed separately so the wrapper can call its documented CLI.
"$PYTHON" -m venv "$TOOLS/mflux-client/.venv"
"$TOOLS/mflux-client/.venv/bin/python" -m pip install --upgrade pip
"$TOOLS/mflux-client/.venv/bin/python" -m pip install 'mflux==0.24.0'

mkdir -p "$ROOT/outputs/images" "$ROOT/outputs/music" "$ROOT/outputs/sfx" "$ROOT/outputs/video"
echo "\nCore setup finished. See README.md for Phosphene, model downloads, and launch instructions."
