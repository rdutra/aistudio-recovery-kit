"""Mocked API tests; these tests never contact the generation server."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

from ace_step_client import AceStepClient, ApiError, GenerationFailed


def response(payload=None, content=b"", status=200):
    """Build a requests response fake with JSON or streamed content."""
    result = requests.Response()
    result.status_code = status
    result._content = content
    result.headers["Content-Type"] = "application/json"
    if payload is not None:
        result._content = json.dumps(payload).encode()
    return result


class ClientTests(unittest.TestCase):
    """Exercise submission, polling, download, and failure paths."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = Mock()
        self.client = AceStepClient(
            output_dir=self.temp.name, session=self.session, poll_interval=0, max_wait=1
        )

    def test_generate_submits_polls_downloads_and_records_metadata(self):
        self.session.post.side_effect = [
            response({"data": {"task_id": "task-123"}, "code": 200}),
            response({"data": [{"task_id": "task-123", "status": 0}], "code": 200}),
            response({"data": [{
                "task_id": "task-123", "status": 1,
                "result": json.dumps([{"file": "/tmp/generated.mp3", "prompt": "ambient"}]),
            }], "code": 200}),
        ]
        self.session.get.return_value = response(content=b"audio bytes")
        self.session.get.return_value.iter_content = Mock(return_value=[b"audio bytes"])

        result = self.client.generate("soft ambient piano", 12, "scene-theme")

        self.assertEqual(b"audio bytes", result.audio_path.read_bytes())
        saved = json.loads(result.metadata_path.read_text())
        self.assertEqual("task-123", saved["task_id"])
        self.assertEqual("soft ambient piano", saved["prompt"])
        self.assertEqual("scene-theme.mp3", saved["audio_file"])
        self.assertEqual(3, self.session.post.call_count)
        self.session.post.assert_any_call(
            "http://127.0.0.1:8001/release_task",
            headers={}, timeout=30.0,
            json={"prompt": "soft ambient piano", "audio_duration": 12,
                  "task_type": "text2music", "audio_format": "mp3"},
        )

    def test_generation_failure_is_reported(self):
        self.session.post.side_effect = [
            response({"data": {"task_id": "bad-task"}, "code": 200}),
            response({"data": [{"task_id": "bad-task", "status": 2,
                                 "error": "out of memory", "result": "[]"}], "code": 200}),
        ]
        with self.assertRaisesRegex(GenerationFailed, "out of memory"):
            self.client.generate("music", 10, "failed")

    def test_non_success_http_response_is_reported(self):
        self.session.post.return_value = response({"detail": "unauthorized"}, status=401)
        with self.assertRaises(ApiError):
            self.client.submit("music", 10)

    def test_existing_output_is_never_overwritten(self):
        path = Path(self.temp.name) / "keep.mp3"
        path.write_bytes(b"original")
        self.session.post.return_value = response({"data": {"task_id": "task"}, "code": 200})
        with self.assertRaisesRegex(ApiError, "refusing to overwrite"):
            self.client.generate("music", 10, "keep")
        self.session.post.assert_not_called()
        self.assertEqual(b"original", path.read_bytes())


if __name__ == "__main__":
    unittest.main()
