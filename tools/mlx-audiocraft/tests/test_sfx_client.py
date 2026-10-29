import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import soundfile as sf

import sfx_client


class SfxClientTests(unittest.TestCase):
    def test_safe_stem(self):
        self.assertEqual(sfx_client.safe_stem("footsteps / stone"), "footsteps-stone")
        with self.assertRaises(ValueError):
            sfx_client.safe_stem("...---")

    def test_dry_run_shows_scheduler_and_upstream_command(self):
        with tempfile.TemporaryDirectory() as td:
            output_stream = io.StringIO()
            with redirect_stdout(output_stream), patch("sfx_client.subprocess.run") as run:
                code = sfx_client.main([
                    "--prompt", "wind through pine trees", "--output-name", "forest-wind",
                    "--output-dir", td, "--dry-run", "--scheduler-python", "/python",
                    "--scheduler", "/scheduler.py", "--audiogen-executable", "/audiogen",
                ])
            self.assertEqual(code, 0)
            run.assert_not_called()
            plan = json.loads(output_stream.getvalue())
            self.assertEqual(plan["command"][:4], ["/python", "/scheduler.py", "--wait-timeout", "3600"])
            self.assertIn("wind through pine trees", plan["command"])
            self.assertIn("--no-open", plan["command"])
            self.assertFalse((Path(td) / ".forest-wind.lock").exists())

    def test_default_upstream_executable_is_from_active_venv(self):
        args = sfx_client.parser().parse_args(["--prompt", "x", "--output-name", "x"])
        self.assertEqual(Path(args.audiogen_executable), Path(sfx_client.sys.prefix) / "bin" / "audiogen-mlx")

    def test_success_invokes_scheduler_validates_and_records_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "impact.wav"
            out, err = io.StringIO(), io.StringIO()
            calls = []

            def fake_run(command, check=False):
                calls.append(command)
                wav_path = Path(command[command.index("-o") + 1])
                sf.write(wav_path, np.zeros((32000, 1), dtype=np.float32), 16000)
                return SimpleNamespace(returncode=0)

            with patch("sfx_client.active_known_gpu_workloads", return_value=[]), \
                    patch("sfx_client.subprocess.run", side_effect=fake_run), \
                    redirect_stdout(out), redirect_stderr(err):
                code = sfx_client.main([
                    "--prompt", "a low stone impact", "--duration", "2", "--output-name", "impact",
                    "--output-dir", td, "--audiogen-executable", "/audiogen",
                    "--scheduler-python", "/python", "--scheduler", "/scheduler.py",
                ])
            self.assertEqual(code, 0, err.getvalue())
            self.assertEqual(len(calls), 1)
            command = calls[0]
            self.assertEqual(command[:2], ["/python", "/scheduler.py"])
            self.assertIn("--", command)
            self.assertIn("--no-open", command)
            self.assertTrue(output.is_file())
            metadata = json.loads(output.with_suffix(".json").read_text())
            self.assertEqual(metadata["prompt"], "a low stone impact")
            self.assertEqual(metadata["duration_seconds_requested"], 2)
            self.assertEqual(metadata["audio_file"], "impact.wav")
            self.assertEqual(metadata["code_license"], "MIT")
            self.assertEqual(metadata["model_weights_license"], "CC-BY-NC-4.0")
            self.assertEqual(metadata["audio_validation"]["sample_rate_hz"], 16000)
            self.assertEqual(metadata["audio_validation"]["channels"], 1)
            self.assertAlmostEqual(metadata["audio_validation"]["duration_seconds"], 2)

    def test_nonzero_scheduled_exit_reports_failure(self):
        with tempfile.TemporaryDirectory() as td:
            err = io.StringIO()
            with patch("sfx_client.active_known_gpu_workloads", return_value=[]), \
                    patch("sfx_client.subprocess.run", return_value=SimpleNamespace(returncode=23)), \
                    redirect_stderr(err):
                code = sfx_client.main(["--prompt", "impact", "--output-name", "failed", "--output-dir", td])
            self.assertEqual(code, 23)
            self.assertIn("exit code 23", err.getvalue())
            self.assertFalse(list(Path(td).glob("failed.*")))

    def test_missing_empty_and_invalid_wav_outputs_are_rejected(self):
        for outcome in ("missing", "empty", "invalid"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as td:
                err = io.StringIO()

                def fake_run(command, check=False):
                    wav_path = Path(command[command.index("-o") + 1])
                    if outcome == "empty":
                        wav_path.touch()
                    elif outcome == "invalid":
                        wav_path.write_bytes(b"not a wav file")
                    return SimpleNamespace(returncode=0)

                with patch("sfx_client.active_known_gpu_workloads", return_value=[]), \
                        patch("sfx_client.subprocess.run", side_effect=fake_run), redirect_stderr(err):
                    code = sfx_client.main(["--prompt", "impact", "--output-name", "bad", "--output-dir", td])
                self.assertEqual(code, 2)
                self.assertIn("generation/output failed", err.getvalue())
                self.assertFalse(list(Path(td).glob("bad.*")))

    def test_validate_audio_rejects_nonfinite_and_out_of_tolerance_duration(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.wav"
            sf.write(path, np.array([[np.nan], [0]], dtype=np.float32), 16000, subtype="FLOAT")
            with self.assertRaisesRegex(RuntimeError, "non-finite"):
                sfx_client.validate_audio(path, 1)
            sf.write(path, np.zeros((100, 2), dtype=np.float32), 16000)
            with self.assertRaisesRegex(RuntimeError, "differs from requested"):
                sfx_client.validate_audio(path, 5)

    def test_existing_file_is_preserved_and_suffix_used(self):
        with tempfile.TemporaryDirectory() as td:
            original = Path(td) / "impact.wav"
            original.write_bytes(b"keep this file")

            def fake_run(command, check=False):
                sf.write(Path(command[command.index("-o") + 1]), np.zeros((80000, 1)), 16000)
                return SimpleNamespace(returncode=0)

            with patch("sfx_client.active_known_gpu_workloads", return_value=[]), \
                    patch("sfx_client.subprocess.run", side_effect=fake_run), redirect_stdout(io.StringIO()):
                code = sfx_client.main(["--prompt", "impact", "--output-name", "impact", "--output-dir", td])
            self.assertEqual(code, 0)
            self.assertEqual(original.read_bytes(), b"keep this file")
            self.assertTrue((Path(td) / "impact-001.wav").is_file())

    def test_raced_in_target_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "race.wav"

            def fake_run(command, check=False):
                sf.write(Path(command[command.index("-o") + 1]), np.zeros((16000, 1)), 16000)
                target.write_bytes(b"concurrent writer")
                return SimpleNamespace(returncode=0)

            err = io.StringIO()
            with patch("sfx_client.active_known_gpu_workloads", return_value=[]), \
                    patch("sfx_client.subprocess.run", side_effect=fake_run), redirect_stderr(err):
                code = sfx_client.main(["--prompt", "impact", "--duration", "1", "--output-name", "race", "--output-dir", td])
            self.assertEqual(code, 2)
            self.assertEqual(target.read_bytes(), b"concurrent writer")

    def test_raced_in_metadata_is_not_removed_during_failure_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "race.json"

            def fake_run(command, check=False):
                sf.write(Path(command[command.index("-o") + 1]), np.zeros((16000, 1)), 16000)
                target.write_text("concurrent metadata", encoding="utf-8")
                return SimpleNamespace(returncode=0)

            err = io.StringIO()
            with patch("sfx_client.active_known_gpu_workloads", return_value=[]), \
                    patch("sfx_client.subprocess.run", side_effect=fake_run), redirect_stderr(err):
                code = sfx_client.main(["--prompt", "impact", "--duration", "1", "--output-name", "race", "--output-dir", td])
            self.assertEqual(code, 2)
            self.assertEqual(target.read_text(encoding="utf-8"), "concurrent metadata")
            self.assertFalse((Path(td) / "race.wav").exists())

    def test_active_mflux_generator_blocks_generation(self):
        with tempfile.TemporaryDirectory() as td:
            err = io.StringIO()
            with patch("sfx_client.active_known_gpu_workloads", return_value=["pid 123: mflux-generate-flux"]), \
                    patch("sfx_client.subprocess.run") as run, redirect_stderr(err):
                code = sfx_client.main(["--prompt", "impact", "--output-name", "blocked", "--output-dir", td])
            self.assertEqual(code, 75)
            self.assertIn("wait for it to finish before AudioGen", err.getvalue())
            run.assert_not_called()

    def test_flac_is_validated_after_conversion(self):
        with tempfile.TemporaryDirectory() as td:
            err = io.StringIO()

            def fake_scheduler(command, check=False):
                sf.write(Path(command[command.index("-o") + 1]), np.zeros((32000, 2)), 16000)
                return SimpleNamespace(returncode=0)

            with patch("sfx_client.active_known_gpu_workloads", return_value=[]), \
                    patch("sfx_client.subprocess.run", side_effect=fake_scheduler), redirect_stderr(err):
                code = sfx_client.main([
                    "--prompt", "impact", "--duration", "2", "--output-name", "flac",
                    "--format", "flac", "--output-dir", td,
                ])
            self.assertEqual(code, 0, err.getvalue())
            details = sfx_client.validate_audio(Path(td) / "flac.flac", 2)
            self.assertEqual(details["channels"], 2)

    def test_mp3_conversion_uses_no_clobber_and_validates_result(self):
        with tempfile.TemporaryDirectory() as td:
            calls = []
            err = io.StringIO()

            def fake_run(command, check=False):
                calls.append(command)
                if command[0] == "scheduler-python":
                    sf.write(Path(command[command.index("-o") + 1]), np.zeros((32000, 1)), 16000)
                else:
                    self.assertIn("-n", command)
                    sf.write(command[-1], np.zeros((32000, 1)), 16000)
                return SimpleNamespace(returncode=0)

            with patch("sfx_client.active_known_gpu_workloads", return_value=[]), \
                    patch("sfx_client.subprocess.run", side_effect=fake_run), \
                    patch("sfx_client.shutil.which", return_value="ffmpeg"), redirect_stderr(err):
                code = sfx_client.main([
                    "--prompt", "impact", "--duration", "2", "--output-name", "mp3",
                    "--format", "mp3", "--output-dir", td, "--scheduler-python", "scheduler-python",
                ])
            self.assertEqual(code, 0, err.getvalue())
            self.assertEqual(len(calls), 2)
            self.assertTrue((Path(td) / "mp3.mp3").is_file())

    def test_invalid_converted_audio_is_not_published(self):
        with tempfile.TemporaryDirectory() as td:
            err = io.StringIO()

            def fake_run(command, check=False):
                if command[0] == "scheduler-python":
                    sf.write(Path(command[command.index("-o") + 1]), np.zeros((32000, 1)), 16000)
                else:
                    Path(command[-1]).write_bytes(b"not decoded audio")
                return SimpleNamespace(returncode=0)

            with patch("sfx_client.active_known_gpu_workloads", return_value=[]), \
                    patch("sfx_client.subprocess.run", side_effect=fake_run), \
                    patch("sfx_client.shutil.which", return_value="ffmpeg"), redirect_stderr(err):
                code = sfx_client.main([
                    "--prompt", "impact", "--duration", "2", "--output-name", "broken-mp3",
                    "--format", "mp3", "--output-dir", td, "--scheduler-python", "scheduler-python",
                ])
            self.assertEqual(code, 2)
            self.assertIn("cannot decode audio output", err.getvalue())
            self.assertFalse((Path(td) / "broken-mp3.mp3").exists())
            self.assertFalse((Path(td) / "broken-mp3.json").exists())


if __name__ == "__main__":
    unittest.main()
