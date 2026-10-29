---
name: generate-game-music
description: Create original game music from a gameplay or scene brief using the local ACE-Step 1.5 music generation client. Use when a user wants a game soundtrack cue, ambient bed, menu theme, or musical prototype generated as an audio file.
metadata:
  short-description: Generate game music with local ACE-Step
---

# Generate game music

Use the local ACE-Step client to turn the user's game-audio brief into an MP3 and JSON metadata sidecar. Preserve the requested mood, gameplay function, and any explicit musical constraints. Do not invent a game title or narrative details the user did not provide.

## Client setup

- Client directory: `~/AIStudio/tools/ace-step-client`
- Executable: `~/AIStudio/tools/ace-step-client/.venv/bin/ace-step`
- API: `http://127.0.0.1:8001`
- Default output directory: `~/AIStudio/outputs/music`

Read `~/AIStudio/tools/ace-step-client/README.md` if the client options or behavior need confirmation. The client submits a job, polls it, downloads the MP3, and writes a JSON sidecar. Existing output files are never overwritten. Keep the API URL on port `8001`; this is the local API server used by the client.

For sound generation, pass `--thinking` so the server-side 5Hz language model generates music codes, matching the UI when its thinking option is enabled. Without this flag, the API defaults to `thinking=false` and skips that LM code-generation path.

## Workflow

1. Translate the brief into a compact, descriptive music prompt. Include the gameplay use (such as exploration, combat, pause/menu, victory, or tension), emotional tone, style, instrumentation, energy, and pacing where known. Mention loop-friendly qualities when useful, but do not claim the generated file is seamless or loop-tested.
2. If an essential choice is missing and would substantially change the cue, ask a focused question. Otherwise use reasonable musical judgment and proceed.
3. Choose a duration that fits the requested use. If none is given, use 30 seconds for a prototype cue. Choose a clear, filesystem-safe output name based on the user's label or the cue's role; never overwrite or rename existing files without being asked.
4. Run the client from its directory through the shared GPU job scheduler. Art and music use the same advisory lock; it waits up to 3600 seconds by default, adjustable with `--wait-timeout`. The scheduler keeps the lock through the local command and drains its process group when it exits normally. A separate guardian keeps the lock and drains that process group if the scheduler crashes after guardian startup. There is a short startup interval after the command launches and before the guardian starts; if the scheduler is killed during that interval, only the direct command is guaranteed to hold the lock. Detached processes that leave the process group are outside this protection. Do not remove the lock file to recover from a stale job. This is local process coordination: if the ACE-Step server continues a submitted task after the client is interrupted or exits, the scheduler cannot detect or cancel that server-side task, so avoid interruption during generation unless server cancellation behavior is confirmed.

   ```bash
   python3 ~/AIStudio/tools/gpu-job-scheduler/gpu_job_scheduler.py --wait-timeout 3600 -- \
     .venv/bin/ace-step --prompt "<music prompt>" --duration <seconds> --output-name <safe-name> --thinking
   ```

   For example:

   ```bash
   python3 ~/AIStudio/tools/gpu-job-scheduler/gpu_job_scheduler.py --wait-timeout 3600 -- \
     .venv/bin/ace-step --prompt "Exploration music for a misty forest in a cozy fantasy game; gentle fingerpicked acoustic guitar, airy woodwinds, warm strings, curious and calm, light steady pulse, instrumental game soundtrack" --duration 30 --output-name misty-forest-exploration --thinking
   ```

5. Report the result only after the command succeeds. Give the MP3 path, duration, and the JSON sidecar path. Briefly summarize the prompt used. If generation fails, report the error and useful next step; do not claim an audio file was created.

Run generation only when the user requested an audio artifact. Do not modify the ACE-Step installation, client, API configuration, or generated files beyond what is needed for the requested cue.
