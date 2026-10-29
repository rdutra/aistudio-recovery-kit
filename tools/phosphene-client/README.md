# Phosphene video client

Standalone Python 3 client for the loopback Phosphene API. It supports LTX text-to-video and image-to-video, submits one asynchronous job, polls `/status`, requests `/stop?id=…` on timeout or interruption, waits until the server confirms a terminal state, downloads the MP4 via `/file`, validates the video stream with `ffprobe`, and writes a JSON sidecar under `~/AIStudio/outputs/video`.

Every real generation must run under the shared scheduler:

```sh
python3 ~/AIStudio/tools/gpu-job-scheduler/gpu_job_scheduler.py --wait-timeout 3600 -- \
  python3 ~/AIStudio/tools/phosphene-client/phosphene_client.py \
  --mode t2v --prompt "A slow aerial establishing shot over a fogbound fjord" \
  --duration 5 --width 512 --height 320 --quality balanced --output-name fjord-establishing
```

The default API is `http://127.0.0.1:8198`; override with `PHOSPHENE_URL`. Frame count is rounded to the nearest valid LTX count (`8n+1`, 24 fps). Supported options: `--mode t2v|i2v`, `--prompt`, `--duration` or `--frames`, `--width`, `--height`, `--quality`, `--seed`, `--image`, `--output-name`, `--job-timeout`, `--poll-interval`, `--dry-run`. Existing MP4/JSON files are never overwritten. Output names gain a timestamp. `--dry-run` does not invoke the server or scheduler.

On cancellation uncertainty, the client stays alive and retains the scheduler lock until Phosphene reports the job terminal (or no longer running/queued). Do not kill the client or scheduler to recover a stuck job; inspect Phosphene status and use its stop controls. The API's hard `/stop?id=…` endpoint is documented by Phosphene and is issued on timeout/interruption. The scheduler's guardian covers the child process group if its parent exits, but cannot guarantee protection from host power loss or out-of-process jobs that Phosphene itself starts. A lost client before obtaining a job ID is inherently ambiguous; check `/status` and the panel before launching another render.

## Validation and tests

```sh
python3 -m unittest discover -s ~/AIStudio/tools/phosphene-client/tests -v
```

Tests use mocked API and ffprobe responses; no model is loaded and no GPU generation occurs.
