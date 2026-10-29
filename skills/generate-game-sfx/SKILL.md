---
name: generate-game-sfx
description: Create original game sound effects from a gameplay or scene brief using local mlx-audiocraft AudioGen on Apple Silicon.
metadata:
  short-description: Generate game sound effects with local AudioGen
---

# Generate game SFX

Use local AudioGen to create a sound effect from a concise, literal prompt. Preserve the requested gameplay function, material, action, environment, and timing. Avoid adding story or setting details the user did not provide.

## Client

- Directory: `~/AIStudio/tools/mlx-audiocraft`
- Python: `~/AIStudio/tools/mlx-audiocraft/.venv/bin/python`
- Client: `~/AIStudio/tools/mlx-audiocraft/sfx_client.py`
- Default output: `~/AIStudio/outputs/sfx`
- Default model: `facebook/audiogen-medium`
- Native format: WAV, 16 kHz

Read the client's README if you need option or installation details. The wrapper schedules its upstream AudioGen command through `~/AIStudio/tools/gpu-job-scheduler/gpu_job_scheduler.py`; do not wrap it in the scheduler a second time. The shared scheduler serializes managed local generation processes, but cannot detect unrelated GPU work or server-side work that does not use the scheduler.

Before generation, determine whether another GPU generation is actually active. An idle ACE-Step API or UI process is not itself an active generation. Check API job status for API-submitted work and the UI status for UI-started work; wait for any active generation to finish. The client ignores persistent ACE-Step API/UI processes and blocks standalone MFLUX generator processes. Its process check cannot identify every unrelated GPU workload. The shared scheduler serializes AudioGen with other clients that use the same lock, but does not cover ACE-Step UI/API jobs that do not use it. Do not remove the shared lock file to recover from a stale job.

## Workflow

1. Turn the brief into a compact sound description. Include the source/action, texture, environment, distance, and any requested onset, tail, or repetition. Example: `A short iron sword impact, sharp clang with a low resonant ring fading quickly, close and dry`.
2. Choose a duration that fits the effect. If none is given, use 5 seconds. Upstream's documented CLI has no seed option; do not claim repeatability from a seed.
3. Choose a filesystem-safe output name. Existing files are never overwritten; the client adds a numeric suffix when a name is occupied.
4. Run:

   ```bash
   ~/AIStudio/tools/mlx-audiocraft/.venv/bin/python \
     ~/AIStudio/tools/mlx-audiocraft/sfx_client.py \
     --prompt "<sound description>" --duration <seconds> --output-name <safe-name>
   ```

   WAV is default. Use `--format flac` for FLAC or `--format mp3` when ffmpeg with `libmp3lame` is installed.
5. Report the created audio path, requested duration, format, and JSON sidecar. Summarize the prompt briefly. If generation fails, report the error without claiming an asset was created.

## Model license

The upstream `mlx-audiocraft` code is MIT licensed. Meta's default `facebook/audiogen-medium` weights use CC-BY-NC 4.0 and are not licensed for commercial use. Do not create outputs for commercial use with these weights unless separate authorization is obtained. The client records both licenses in every sidecar. Verify the selected model's own license if a different model is specified.
