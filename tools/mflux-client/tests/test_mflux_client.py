import struct
import tempfile
import unittest
import zlib
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from mflux_client import inspect_png, unique_paths


def png(path: Path, color_type=2):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", 3, 2, 8, color_type, 0, 0, 0)
    channels = {2: 3, 6: 4}[color_type]
    rows = b"".join(b"\0" + bytes([40, 80, 120] * 3) + (bytes([255] * 12) if channels == 4 else b"") for _ in range(2))
    if color_type == 6:
        rows = b"".join(b"\0" + bytes([40, 80, 120, 100] * 3) for _ in range(2))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


class MfluxClientTests(unittest.TestCase):
    def test_inspects_dimensions_and_channel_without_claiming_transparency(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sample.png"
            png(p, color_type=2)
            result = inspect_png(p)
            self.assertEqual((result["width"], result["height"]), (3, 2))
            self.assertFalse(result["has_alpha_channel"])
            self.assertFalse(result["has_alpha_transparency"])

    def test_alpha_channel_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "alpha.png"
            png(p, color_type=6)
            result = inspect_png(p)
            self.assertTrue(result["has_alpha_channel"])
            self.assertTrue(result["has_alpha_transparency"])

    def test_rejects_corrupt_crc(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.png"
            png(p)
            data = bytearray(p.read_bytes())
            data[-5] ^= 1
            p.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "CRC"):
                inspect_png(p)

    def test_never_reserves_an_existing_image_name(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "warrior.png").touch()
            image, sidecar, lock = unique_paths(root, "warrior")
            self.assertEqual(image.name, "warrior-001.png")
            self.assertFalse(sidecar.exists())
            lock.unlink()


if __name__ == "__main__":
    unittest.main()
