"""Small, metadata-preserving wrapper around the installed MFLUX CLI."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path


OUTPUT_ROOT = Path.home() / "AIStudio/outputs/images"
CATEGORIES = ("characters", "concepts", "environments", "equipment", "sprites", "textures", "ui", "backgrounds")


def inspect_png(path: Path) -> dict:
    """Validate PNG structure and report an alpha channel and non-opaque pixels."""
    with path.open("rb") as f:
        if f.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("MFLUX output is not a PNG")
        width = height = color_type = depth = interlace = None
        compressed = bytearray()
        transparency = None
        saw_iend = False
        while True:
            head = f.read(8)
            if len(head) != 8:
                raise ValueError("Truncated PNG chunk header")
            length, kind = struct.unpack(">I4s", head)
            data = f.read(length)
            crc_bytes = f.read(4)
            if len(data) != length or len(crc_bytes) != 4:
                raise ValueError("Truncated PNG chunk")
            expected = struct.unpack(">I", crc_bytes)[0]
            if zlib.crc32(kind + data) & 0xFFFFFFFF != expected:
                raise ValueError(f"PNG {kind.decode('ascii', 'replace')} CRC mismatch")
            if kind == b"IHDR":
                if length != 13:
                    raise ValueError("Invalid PNG IHDR")
                width, height, depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", data)
                if not width or not height or color_type not in (0, 2, 3, 4, 6):
                    raise ValueError("Invalid PNG dimensions or color type")
            elif kind == b"IDAT":
                compressed.extend(data)
            elif kind == b"tRNS":
                transparency = data
            elif kind == b"IEND":
                saw_iend = True
                break
        if not saw_iend or width is None:
            raise ValueError("PNG is missing required chunks")
    if interlace != 0 or depth != 8:
        raise ValueError("MFLUX PNG has unsupported bit depth or interlacing")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    bpp = channels
    row_bytes = width * channels
    raw = zlib.decompress(compressed)
    if len(raw) != height * (row_bytes + 1):
        raise ValueError("PNG pixel data has an invalid length")
    previous = bytearray(row_bytes)
    actual_transparency = False
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        scan = bytearray(raw[offset + 1:offset + 1 + row_bytes])
        offset += row_bytes + 1
        for i in range(row_bytes):
            left = scan[i - bpp] if i >= bpp else 0
            above = previous[i]
            upper_left = previous[i - bpp] if i >= bpp else 0
            if filter_type == 1: scan[i] = (scan[i] + left) & 255
            elif filter_type == 2: scan[i] = (scan[i] + above) & 255
            elif filter_type == 3: scan[i] = (scan[i] + (left + above) // 2) & 255
            elif filter_type == 4:
                p = left + above - upper_left
                pa, pb, pc = abs(p-left), abs(p-above), abs(p-upper_left)
                predictor = left if pa <= pb and pa <= pc else above if pb <= pc else upper_left
                scan[i] = (scan[i] + predictor) & 255
            elif filter_type != 0: raise ValueError("Invalid PNG row filter")
        if color_type == 4:
            actual_transparency |= any(scan[i] != 255 for i in range(1, row_bytes, 2))
        elif color_type == 6:
            actual_transparency |= any(scan[i] != 255 for i in range(3, row_bytes, 4))
        elif color_type == 3 and transparency:
            actual_transparency |= any(transparency[index] < 255 for index in scan if index < len(transparency))
        elif color_type in (0, 2) and transparency:
            transparent_pixel = ((int.from_bytes(transparency, "big") & 255,) if color_type == 0 else
                                 tuple(int.from_bytes(transparency[i:i+2], "big") & 255 for i in (0, 2, 4)))
            actual_transparency |= any(tuple(scan[i:i+channels]) == transparent_pixel for i in range(0, row_bytes, channels))
        previous = scan
    return {"format": "PNG", "width": width, "height": height,
            "has_alpha_channel": color_type in (4, 6) or (color_type == 3 and transparency is not None),
            "has_alpha_transparency": actual_transparency}


def unique_paths(directory: Path, stem: str) -> tuple[Path, Path, Path]:
    for n in range(0, 10000):
        candidate = stem if n == 0 else f"{stem}-{n:03d}"
        image = directory / f"{candidate}.png"
        sidecar = directory / f"{candidate}.json"
        lock = directory / f".{candidate}.lock"
        if image.exists() or sidecar.exists():
            continue
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        os.close(fd)
        if image.exists() or sidecar.exists():
            lock.unlink(missing_ok=True)
            continue
        return image, sidecar, lock
    raise RuntimeError("Could not reserve a unique output name after 10,000 attempts")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate and validate game artwork with local MFLUX FLUX.2 Klein.")
    p.add_argument("--prompt", required=True)
    p.add_argument("--category", choices=CATEGORIES, default="concepts")
    p.add_argument("--output-name", help="Filename stem; a numeric suffix is added if occupied")
    p.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    p.add_argument("--model", default="flux2-klein-4b")
    p.add_argument("--quantize", type=int, choices=(3, 4, 5, 6, 8))
    p.add_argument("--steps", type=int)
    p.add_argument("--seed", type=int)
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--height", type=int, default=1024)
    p.add_argument("--reference-image", type=Path)
    p.add_argument("--image-strength", type=float, default=0.7)
    p.add_argument("--transparent-background", action="store_true", help="Records intent only; MFLUX does not directly promise transparent output.")
    p.add_argument("--mflux-executable", default=shutil.which("mflux-generate-flux2") or "mflux-generate-flux2")
    p.add_argument("--dry-run", action="store_true", help="Print the planned MFLUX command without generating.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.width <= 0 or args.height <= 0:
        parser().error("width and height must be positive")
    if args.steps is not None and args.steps <= 0:
        parser().error("steps must be positive")
    if args.seed is not None and args.seed < 0:
        parser().error("seed must be non-negative")
    if not 0 < args.image_strength <= 1:
        parser().error("image-strength must be greater than 0 and at most 1")
    if args.reference_image and not args.reference_image.is_file():
        parser().error(f"reference image does not exist: {args.reference_image}")

    output_dir = args.output_dir.expanduser() / args.category
    stem = args.output_name or "-".join(args.prompt.lower().split()[:5])
    stem = "".join(c if c.isalnum() or c in "-_." else "-" for c in stem).strip("-.") or "game-art"
    if args.dry_run:
        cmd = [args.mflux_executable, "--prompt", args.prompt, "--model", args.model, "--width", str(args.width), "--height", str(args.height), "--output", str(output_dir / f"{stem}.png")]
        if args.quantize is not None: cmd += ["--quantize", str(args.quantize)]
        if args.steps is not None: cmd += ["--steps", str(args.steps)]
        if args.seed is not None: cmd += ["--seed", str(args.seed)]
        if args.reference_image: cmd += ["--image", str(args.reference_image), str(args.image_strength)]
        print(json.dumps(cmd, ensure_ascii=False))
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    image, sidecar, lock = unique_paths(output_dir, stem)
    command = [args.mflux_executable, "--prompt", args.prompt, "--model", args.model,
               "--width", str(args.width), "--height", str(args.height), "--output", str(image)]
    if args.quantize is not None: command += ["--quantize", str(args.quantize)]
    if args.steps is not None: command += ["--steps", str(args.steps)]
    if args.seed is not None: command += ["--seed", str(args.seed)]
    if args.reference_image: command += ["--image", str(args.reference_image), str(args.image_strength)]
    try:
        result = subprocess.run(command, check=False)
        if result.returncode:
            print(f"MFLUX failed with exit code {result.returncode}; no successful asset is reported.", file=sys.stderr)
            return result.returncode
        if not image.is_file() or image.stat().st_size == 0:
            raise RuntimeError("MFLUX exited successfully but did not create a non-empty image")
        details = inspect_png(image)
        details["alpha_transparency_requested"] = args.transparent_background
        metadata = {
            "created_at": datetime.now(timezone.utc).isoformat(), "image": str(image),
            "category": args.category, "prompt": args.prompt, "model": args.model,
            "mflux_version": "0.24.0", "quantization": args.quantize,
            "steps": args.steps, "seed": args.seed, "requested_dimensions": {"width": args.width, "height": args.height},
            "reference_image": str(args.reference_image) if args.reference_image else None,
            "image_strength": args.image_strength if args.reference_image else None,
            "transparent_background_requested": args.transparent_background,
            "image_validation": details,
            "command": command,
            "licensing_note": "Review the selected model's license and output terms for commercial use before shipping.",
        }
        sidecar.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Image: {image}\nMetadata: {sidecar}\nDimensions: {details['width']}x{details['height']} {details['format']}; alpha channel: {details['has_alpha_channel']}")
        if args.transparent_background and not details["has_alpha_transparency"]:
            print("Requested transparency is absent; use a supported background-removal postprocess and validate its alpha channel.", file=sys.stderr)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Output validation failed: {exc}", file=sys.stderr)
        return 2
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
