#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v uv >/dev/null 2>&1; then
  echo "Install core tools first with ./scripts/setup-macos.sh" >&2
  exit 1
fi

echo "This downloads MFLUX, AudioGen, T5, and ACE-Step weights into the Hugging Face cache."
echo "The files require several gigabytes of free disk space."
uv run --no-project --with huggingface_hub python "$ROOT/scripts/download-hf-models.py"

