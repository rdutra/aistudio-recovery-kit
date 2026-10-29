#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This Pinokio installer targets Apple Silicon macOS." >&2
  exit 1
fi
if ! command -v gh >/dev/null 2>&1; then
  echo "Install GitHub CLI first (setup-macos.sh installs it with Homebrew)." >&2
  exit 1
fi

APP_DEST="$HOME/Applications/Pinokio.app"
for candidate in "$APP_DEST" "/Applications/Pinokio.app" "$HOME/pinokio/Pinokio.app"; do
  if [[ -d "$candidate" ]]; then
    echo "Pinokio is already installed at $candidate"
    exit 0
  fi
done

TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT
mkdir -p "$HOME/Applications"
gh release download --repo pinokiocomputer/pinokio --pattern 'Pinokio-*-arm64-mac.zip' --dir "$TEMP_DIR"
ARCHIVE="$(find "$TEMP_DIR" -maxdepth 1 -name 'Pinokio-*-arm64-mac.zip' -print -quit)"
if [[ -z "$ARCHIVE" ]]; then
  echo "The latest Pinokio release did not include an Apple Silicon macOS archive." >&2
  exit 1
fi
mkdir "$TEMP_DIR/unpacked"
unzip -q "$ARCHIVE" -d "$TEMP_DIR/unpacked"
APP_SOURCE="$(find "$TEMP_DIR/unpacked" -maxdepth 4 -name Pinokio.app -type d -print -quit)"
if [[ -z "$APP_SOURCE" ]]; then
  echo "Could not find Pinokio.app in the release archive." >&2
  exit 1
fi
ditto "$APP_SOURCE" "$APP_DEST"
echo "Installed Pinokio at $APP_DEST"
echo "Open it once and complete its first-run setup before installing Phosphene."
