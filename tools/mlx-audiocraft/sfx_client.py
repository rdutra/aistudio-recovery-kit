"""Scheduled, metadata-preserving AudioGen SFX wrapper."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_ROOT = Path.home() / "AIStudio/outputs/sfx"
SCHEDULER = Path.home() / "AIStudio/tools/gpu-job-scheduler/gpu_job_scheduler.py"
MODEL = "facebook/audiogen-medium"


def safe_stem(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip(".-_")
    if not stem:
        raise ValueError("output name must contain a filename-safe character")
    return stem


def reserve(directory: Path, stem: str, extension: str) -> tuple[Path, Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    for n in range(10000):
        candidate = stem if n == 0 else f"{stem}-{n:03d}"
        audio = directory / f"{candidate}.{extension}"
        metadata = directory / f"{candidate}.json"
        lock = directory / f".{candidate}.lock"
        if audio.exists() or metadata.exists():
            continue
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        os.close(fd)
        if audio.exists() or metadata.exists():
            lock.unlink(missing_ok=True)
            continue
        return audio, metadata, lock
    raise RuntimeError("could not reserve a unique output name")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate sound effects with mlx-audiocraft AudioGen.")
    p.add_argument("--prompt")
    p.add_argument("--duration", type=float, default=5, help="seconds (upstream default is 5)")
    p.add_argument("--output-name")
    p.add_argument("--format", choices=("wav", "flac", "mp3"), default="wav")
    p.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    p.add_argument("--model", default=MODEL)
    p.add_argument("--wait-timeout", type=float, default=3600)
    p.add_argument("--command-timeout", type=float, default=None)
    venv_audiogen = Path(sys.prefix) / "bin" / "audiogen-mlx"
    p.add_argument("--audiogen-executable", default=str(venv_audiogen) if venv_audiogen.is_file()
                   else shutil.which("audiogen-mlx") or "audiogen-mlx")
    p.add_argument("--scheduler-python", default=sys.executable)
    p.add_argument("--scheduler", type=Path, default=SCHEDULER)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--check-backend", action="store_true", help="report MLX device without generating")
    return p


def check_backend() -> int:
    try:
        import mlx.core as mx
    except ImportError as exc:
        print(f"MLX unavailable: {exc}", file=sys.stderr)
        return 1
    device = str(mx.default_device())
    print(f"MLX {mx.__version__}; default device: {device}")
    if "gpu" not in device.lower():
        print("MLX is not reporting GPU/Metal as its default device", file=sys.stderr)
        return 1
    return 0


def active_known_gpu_workloads() -> list[str]:
    """Find standalone known GPU generators, not persistent API/UI services."""
    try:
        listing = subprocess.check_output(["ps", "-axo", "pid=,command="], text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"cannot inspect running processes before generation: {exc}") from exc
    # ACE-Step API and UI processes stay alive while idle, so their presence
    # does not indicate an active generation. ACE-Step activity is checked by
    # the skill through the UI/API status; the scheduler handles managed jobs.
    markers = ("mflux-generate-flux", "mflux_generate_flux")
    found = []
    for line in listing.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        pid, command = parts
        if int(pid) == os.getpid():
            continue
        if any(marker in command.lower() for marker in markers):
            found.append(f"pid {pid}: {command}")
    return found


def validate_audio(path: Path, expected_duration: float) -> dict:
    """Decode audio and reject empty, malformed, non-finite, or wrong-length output."""
    import numpy as np
    import soundfile as sf

    try:
        info = sf.info(path)
        audio, rate = sf.read(path, dtype="float32", always_2d=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeError(f"cannot decode audio output {path.name}: {exc}") from exc
    duration = len(audio) / rate if rate else 0
    if rate <= 0 or info.samplerate != rate or info.channels < 1 or audio.shape[1] != info.channels:
        raise RuntimeError("audio output has invalid sample rate or channel count")
    if len(audio) == 0 or duration <= 0:
        raise RuntimeError("audio output has no samples")
    if not np.isfinite(audio).all():
        raise RuntimeError("audio output contains non-finite samples")
    tolerance = max(0.25, expected_duration * 0.05)
    if abs(duration - expected_duration) > tolerance:
        raise RuntimeError(
            f"audio duration {duration:.3f}s differs from requested {expected_duration:.3f}s"
        )
    return {"sample_rate_hz": rate, "channels": info.channels, "frames": len(audio),
            "duration_seconds": duration, "subtype": info.subtype}


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.check_backend:
        return check_backend()
    if not args.prompt or not args.output_name:
        parser().error("--prompt and --output-name are required")
    if not args.prompt.strip():
        parser().error("prompt must not be empty")
    if args.duration <= 0:
        parser().error("duration must be greater than zero")
    if not math.isfinite(args.duration):
        parser().error("duration must be finite")
    if not math.isfinite(args.wait_timeout) or args.wait_timeout < 0:
        parser().error("wait-timeout must be finite and non-negative")
    if args.command_timeout is not None and (
        not math.isfinite(args.command_timeout) or args.command_timeout < 0
    ):
        parser().error("command-timeout must be finite and non-negative")
    if args.dry_run:
        pass
    else:
        try:
            workloads = active_known_gpu_workloads()
        except RuntimeError as exc:
            print(f"sfx: preflight failed: {exc}", file=sys.stderr)
            return 2
        if workloads:
            print("sfx: standalone known GPU generator is active; wait for it to finish before AudioGen:\n  " +
                  "\n  ".join(workloads), file=sys.stderr)
            return 75
    try:
        stem = safe_stem(args.output_name)
        output, sidecar, lock = reserve(args.output_dir.expanduser(), stem, args.format)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"sfx: {exc}", file=sys.stderr)
        return 2
    published_audio = False
    published_metadata = False
    try:
        with tempfile.TemporaryDirectory(prefix=".sfx-", dir=output.parent) as temp_dir:
            wav = Path(temp_dir) / "generation.wav"
            staged = Path(temp_dir) / f"final.{args.format}"
            generation = [args.audiogen_executable, args.prompt, "-d", str(args.duration), "-o", str(wav), "--no-open"]
            if args.model != MODEL:
                generation += ["-m", args.model]
            command = [args.scheduler_python, str(args.scheduler), "--wait-timeout", str(args.wait_timeout)]
            if args.command_timeout is not None:
                command += ["--command-timeout", str(args.command_timeout)]
            command += ["--", *generation]
            if args.dry_run:
                print(json.dumps({"command": command, "output": str(output), "model": args.model}, ensure_ascii=False))
                return 0
            result = subprocess.run(command, check=False)
            if result.returncode:
                print(f"scheduled AudioGen command failed with exit code {result.returncode}", file=sys.stderr)
                return result.returncode
            if not wav.is_file() or wav.stat().st_size == 0:
                raise RuntimeError("AudioGen exited successfully but produced no WAV")
            validate_audio(wav, args.duration)
            if args.format == "wav":
                staged = wav
            elif args.format == "flac":
                import soundfile as sf
                data, rate = sf.read(wav, always_2d=True)
                sf.write(staged, data, rate, format="FLAC")
            else:
                ffmpeg = shutil.which("ffmpeg")
                if not ffmpeg:
                    raise RuntimeError("MP3 output requires ffmpeg; install it or select wav/flac")
                subprocess.run([ffmpeg, "-v", "error", "-n", "-i", str(wav), "-codec:a", "libmp3lame", "-q:a", "2", str(staged)], check=True)
            if not staged.is_file() or staged.stat().st_size == 0:
                raise RuntimeError(f"audio conversion did not produce a non-empty {args.format.upper()} file")
            audio_details = validate_audio(staged, args.duration)
            # Hard links publish atomically and fail if another process created the destination.
            os.link(staged, output)
            published_audio = True
        metadata = {
            "generated_at": datetime.now(timezone.utc).isoformat(), "prompt": args.prompt,
            "duration_seconds_requested": args.duration, "model": args.model,
            "audio_file": output.name, "format": args.format,
            "generation_backend": "MLX (Apple Metal GPU) with CPU T5 encoder",
            "generation_command": generation,
            "audio_validation": audio_details,
            "code_license": "MIT", "model_weights_license": "CC-BY-NC-4.0",
            "commercial_use": "Not permitted under the model weights license; obtain separate authorization before commercial use.",
        }
        fd, metadata_temp = tempfile.mkstemp(prefix=f".{output.stem}.", suffix=".json.tmp", dir=output.parent)
        metadata_staging = Path(metadata_temp)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.link(metadata_staging, sidecar)
            published_metadata = True
        finally:
            metadata_staging.unlink(missing_ok=True)
        print(f"Audio: {output}\nMetadata: {sidecar}")
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        if published_audio:
            output.unlink(missing_ok=True)
        if published_metadata:
            sidecar.unlink(missing_ok=True)
        print(f"sfx: generation/output failed: {exc}", file=sys.stderr)
        return 2
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
