#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS="$ROOT/tools"
SKILL_DEST="${AGENTS_SKILLS_DIR:-$HOME/.agents/skills}"
ACE_STEP_COMMIT="ca1e85fe9430179831e6bc6be790c332190a3866"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "AIStudio setup targets Apple Silicon macOS." >&2
  exit 1
fi
if ! command -v brew >/dev/null 2>&1; then
  echo "Install Homebrew first: https://brew.sh" >&2
  exit 1
fi

brew install ffmpeg git gh node python@3.12 tmux uv
npm install --global dmux@5.11.1 @openai/codex@latest
"$ROOT/scripts/install-pinokio.sh"
PYTHON="$(brew --prefix python@3.12)/bin/python3.12"

make_venv() {
  local directory="$1"
  "$PYTHON" -m venv "$directory/.venv"
  "$directory/.venv/bin/python" -m pip install --upgrade pip
}

make_venv "$TOOLS/mlx-audiocraft"
"$TOOLS/mlx-audiocraft/.venv/bin/python" -m pip install -r "$TOOLS/mlx-audiocraft/requirements.txt"

make_venv "$TOOLS/mflux-client"
"$TOOLS/mflux-client/.venv/bin/python" -m pip install 'mflux==0.24.0'

make_venv "$TOOLS/ace-step-client"
"$TOOLS/ace-step-client/.venv/bin/python" -m pip install -e "$TOOLS/ace-step-client"

make_venv "$TOOLS/phosphene-client"

if [[ ! -d "$TOOLS/ACE-Step-1.5/.git" ]]; then
  git clone https://github.com/ace-step/ACE-Step-1.5.git "$TOOLS/ACE-Step-1.5"
  git -C "$TOOLS/ACE-Step-1.5" checkout "$ACE_STEP_COMMIT"
fi
(cd "$TOOLS/ACE-Step-1.5" && uv sync)

mkdir -p "$SKILL_DEST"
for skill in generate-game-art generate-game-music generate-game-sfx generate-game-cinematic; do
  source="$ROOT/skills/$skill"
  target="$SKILL_DEST/$skill"
  if [[ -d "$source" ]]; then
    mkdir -p "$target"
    rsync -a --ignore-existing "$source/" "$target/"
  fi
done

mkdir -p "$ROOT/outputs/images" "$ROOT/outputs/music" "$ROOT/outputs/sfx" "$ROOT/outputs/video"
echo
echo "Core tools installed. Sign in to Codex by running: codex"
echo "Then run ./scripts/download-models.sh for Hugging Face models."
echo "Install Phosphene with ./scripts/install-phosphene.sh after Pinokio is installed."
