#!/usr/bin/env bash
set -euo pipefail

PHOSPHENE_URL="https://github.com/mrbizarro/phosphene"
APP_NAME="phosphene.git"
PTERM="$(command -v pterm || true)"

if [[ -z "$PTERM" && -f "$HOME/.pinokio/config.json" ]]; then
  PINOKIO_HOME="$(python3 -c 'import json,os; print(os.path.expanduser(json.load(open(os.path.expanduser("~/.pinokio/config.json"))).get("home", "")))')"
  for candidate in "$PINOKIO_HOME/bin/npm/bin/pterm" "$PINOKIO_HOME/bin/pterm"; do
    if [[ -x "$candidate" ]]; then PTERM="$candidate"; break; fi
  done
fi

if [[ -z "$PTERM" ]]; then
  echo "Install and open Pinokio first: https://pinokio.computer" >&2
  echo "Then rerun this script. Pinokio provides pterm and manages the Phosphene runtime." >&2
  exit 1
fi

if ! "$PTERM" status "$APP_NAME" >/dev/null 2>&1; then
  "$PTERM" download "$PHOSPHENE_URL" "$APP_NAME"
fi

echo "Starting Phosphene's Pinokio-managed installer. The base model download is about 27.5 GB."
echo "Pinokio will continue downloading optional core extras after first start."
"$PTERM" run "$APP_NAME" --default install.js

echo
echo "Phosphene source and base install are ready. In Pinokio, click Start and wait for the panel at http://127.0.0.1:8198."
echo "Install optional models from Phosphene's Models window only if you need them."
