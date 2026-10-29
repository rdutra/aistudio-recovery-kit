"""Command-line interface for local ACE-Step music generation."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .client import AceStepClient
from .errors import AceStepError


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Generate music with local ACE-Step 1.5")
    parser.add_argument("--prompt", required=True, help="Text description of the music")
    parser.add_argument("--duration", required=True, type=float, help="Duration in seconds")
    parser.add_argument("--output-name", required=True, help="Output filename stem")
    parser.add_argument(
        "--thinking",
        action="store_true",
        help="Enable the server-side 5Hz language model for music code generation",
    )
    parser.add_argument("--api-url", default=os.getenv("ACE_STEP_API_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--output-dir", type=Path, default=Path.home() / "AIStudio/outputs/music")
    parser.add_argument("--api-key", default=os.getenv("ACE_STEP_API_KEY"))
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--max-wait", type=float, default=3600.0)
    return parser


def main() -> int:
    """Run one generation request and report the downloaded asset paths."""
    args = build_parser().parse_args()
    try:
        result = AceStepClient(
            base_url=args.api_url,
            output_dir=args.output_dir,
            api_key=args.api_key,
            poll_interval=args.poll_interval,
            max_wait=args.max_wait,
        ).generate(args.prompt, args.duration, args.output_name, thinking=args.thinking)
    except (AceStepError, ValueError) as exc:
        print(f"ace-step: {exc}", file=sys.stderr)
        return 1
    print(f"Audio: {result.audio_path}")
    print(f"Metadata: {result.metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
