"""HTTP client for submitting and retrieving ACE-Step music generations."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from .errors import ApiError, GenerationFailed, PollTimeout


@dataclass(frozen=True)
class GenerationResult:
    """Paths and server metadata for a completed generation."""

    task_id: str
    audio_path: Path
    metadata_path: Path
    metadata: dict[str, Any]


class AceStepClient:
    """Submit text-to-music jobs to a local ACE-Step 1.5 API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8001",
        output_dir: Path | str = Path.home() / "AIStudio/outputs/music",
        api_key: str | None = None,
        poll_interval: float = 2.0,
        timeout: float = 30.0,
        max_wait: float = 3600.0,
        session: requests.Session | None = None,
    ) -> None:
        """Configure API location, output directory, and polling behavior."""
        self.base_url = base_url.rstrip("/") + "/"
        self.output_dir = Path(output_dir).expanduser()
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.max_wait = max_wait
        self.session = session or requests.Session()

    def generate(
        self, prompt: str, duration: float, output_name: str, *, thinking: bool = False
    ) -> GenerationResult:
        """Generate a track, download audio, and write a JSON metadata sidecar."""
        if not prompt.strip():
            raise ValueError("prompt must not be empty")
        if duration <= 0:
            raise ValueError("duration must be greater than zero")
        stem = _safe_stem(output_name)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        audio_path = self.output_dir / f"{stem}.mp3"
        metadata_path = self.output_dir / f"{stem}.json"
        if audio_path.exists() or metadata_path.exists():
            raise ApiError(f"Output already exists; refusing to overwrite: {stem}")
        task_id = self.submit(prompt, duration, thinking=thinking)
        item = self.wait_for_task(task_id)
        audio_url = item.get("file")
        if not audio_url:
            raise ApiError(f"Task {task_id} succeeded without an audio file path")
        response = self._request("get", _audio_url(self.base_url, audio_url), stream=True)
        with audio_path.open("xb") as target:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    target.write(chunk)
        metadata = {
            "task_id": task_id,
            "prompt": prompt,
            "duration_seconds": duration,
            "thinking": thinking,
            "output_name": stem,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "audio_file": audio_path.name,
            "server_result": item,
        }
        try:
            with metadata_path.open("x", encoding="utf-8") as target:
                json.dump(metadata, target, indent=2, ensure_ascii=False)
                target.write("\n")
        except Exception:
            audio_path.unlink(missing_ok=True)
            raise
        return GenerationResult(task_id, audio_path, metadata_path, metadata)

    def submit(self, prompt: str, duration: float, *, thinking: bool = False) -> str:
        """Create a text-to-music task and return its task ID."""
        payload: dict[str, Any] = {
            "prompt": prompt,
            "audio_duration": duration,
            "task_type": "text2music",
            "audio_format": "mp3",
            "thinking": thinking,
        }
        response = self._request("post", urljoin(self.base_url, "release_task"), json=payload)
        data = _unwrap(response)
        task_id = data.get("task_id")
        if not task_id:
            raise ApiError(f"Submission response has no task_id: {data}")
        return str(task_id)

    def wait_for_task(self, task_id: str) -> dict[str, Any]:
        """Poll until completion, raising on server failure or timeout."""
        deadline = time.monotonic() + self.max_wait
        while time.monotonic() < deadline:
            response = self._request(
                "post",
                urljoin(self.base_url, "query_result"),
                json={"task_id_list": [task_id]},
            )
            results = _unwrap(response)
            if not isinstance(results, list) or not results:
                raise ApiError(f"Malformed poll response for task {task_id}: {results}")
            item = results[0]
            status = item.get("status")
            if status == 1:
                return _parse_result_item(item)
            if status == 2:
                raise GenerationFailed(
                    item.get("error") or item.get("progress_text") or f"Task {task_id} failed"
                )
            time.sleep(self.poll_interval)
        raise PollTimeout(f"Task {task_id} did not complete within {self.max_wait:g} seconds")

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Perform an authenticated request with consistent API errors."""
        headers = kwargs.pop("headers", {})
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = getattr(self.session, method)(url, headers=headers, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise ApiError(f"API request failed: {exc}") from exc


def _unwrap(response: requests.Response) -> Any:
    """Decode the API envelope and report server-declared errors."""
    try:
        payload = response.json()
    except ValueError as exc:
        raise ApiError("API returned invalid JSON") from exc
    if isinstance(payload, dict) and "data" in payload:
        if payload.get("code", 200) != 200:
            raise ApiError(payload.get("error") or f"API error code {payload.get('code')}")
        return payload["data"]
    return payload


def _parse_result_item(item: dict[str, Any]) -> dict[str, Any]:
    """Decode the task's JSON-encoded result list and merge its first item."""
    raw = item.get("result", "[]")
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError) as exc:
        raise ApiError(f"Task result is invalid JSON: {raw!r}") from exc
    if not isinstance(parsed, list) or not parsed or not isinstance(parsed[0], dict):
        raise ApiError(f"Task result contains no audio item: {parsed!r}")
    return {**parsed[0], **{key: item[key] for key in ("progress_text",) if key in item}}


def _audio_url(base_url: str, file_path: str) -> str:
    """Translate an API result path or URL to its audio download endpoint."""
    from urllib.parse import quote, urlsplit

    if file_path.startswith(("http://", "https://")):
        return file_path
    if file_path.startswith("/v1/audio"):
        return urljoin(base_url, file_path.lstrip("/"))
    return urljoin(base_url, f"v1/audio?path={quote(file_path, safe='')}")


def _safe_stem(name: str) -> str:
    """Normalize an output name to a safe filename stem."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip(".-_")
    if not stem:
        raise ValueError("output name must contain at least one filename-safe character")
    return stem
