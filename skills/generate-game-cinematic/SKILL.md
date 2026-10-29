---
name: generate-game-cinematic
description: Generate local LTX-2.5 cinematic video clips through the Phosphene panel for game development.
metadata:
  short-description: Generate game cinematics with Phosphene
---

# Generate game cinematics

Use `~/AIStudio/tools/phosphene-client/phosphene_client.py` with the local Phosphene panel (`http://127.0.0.1:8198`). This skill works in Codex and OpenCode Devstral: both can invoke the same Python client from a shell. Generated files stay in `~/AIStudio/outputs/video/`; do not move them into a game repository until reviewed. Never overwrite existing assets.

## Required workflow

1. Check `http://127.0.0.1:8198/status` before generation. Confirm `current` is null, `queue` is empty, and `gpu.busy` is false. Respect the installed tier and its T2V/I2V limits. On this Mac the tier is Compact, LTX-2.5 base Q4, T2V/I2V only, with a 768 px maximum side. High, extend, keyframe, Q8 and Hailuo H3 are not supported here. Do not install H3 or optional music engines.
2. Choose T2V for a scene made from text or I2V to animate reviewed source artwork. For I2V, use a valid existing PNG/JPG and explicitly describe restrained motion, camera movement, and elements that should remain stable.
3. Use concise prompts that describe shot size, camera path, subject/environment action, atmosphere, lighting, palette, and continuity. Avoid requesting complex simultaneous motion in short clips.
4. Run the client through the shared scheduler, which serializes video with art and music jobs:

   ```sh
   python3 ~/AIStudio/tools/gpu-job-scheduler/gpu_job_scheduler.py --wait-timeout 3600 -- \
     python3 ~/AIStudio/tools/phosphene-client/phosphene_client.py \
     --mode t2v --prompt "..." --duration 5 --width 512 --height 320 \
     --quality balanced --seed 41 --output-name scene-establishing
   ```

   For I2V, add `--mode i2v --image /absolute/path/to/reviewed-art.png`. Dimensions must be divisible by 32 and within live tier limits. Frame counts must be `8n+1`; `--duration` rounds to the nearest valid frame count at 24 fps. Use short 5-second clips for local prototyping. The client polls the asynchronous job through completion, downloads the MP4, validates it with `ffprobe`, and writes JSON metadata beside it.
5. Report the MP4 and sidecar paths, render time, settings and any validation or quality limits. Do not claim success unless ffprobe confirms a video stream.

On timeout or interruption, the client calls Phosphene's documented `/stop?id=…` endpoint and keeps running until server status confirms the job is terminal. The scheduler lock therefore remains held during server-side work, including stop confirmation. If the API is unreachable or cancellation cannot be confirmed, do not start another GPU generation; inspect Phosphene and the scheduler state. Never remove the scheduler lock file as recovery.

## Prompt patterns

- **Cinematic establishing shot:** `Wide 24 mm establishing shot, slow crane forward over [landscape], [weather] drifts through the scene, [distant landmark], restrained motion, layered atmospheric depth, [lighting and palette], stable horizon, cinematic game environment.`
- **Environmental animation:** `Locked wide composition of [environment], only [wind/water/foliage/fire] moves gently, subtle natural secondary motion, architecture and framing remain stable, [time of day], [palette], seamless-feeling pacing (not a loop guarantee).`
- **Image-to-video:** `Preserve the composition, subject design, and palette of the supplied artwork. [Camera move] while [one or two environmental elements] move subtly. Keep the main silhouette and landmarks stable; no new subjects or scene cuts. [Mood/light].`
- **Short cutscene:** `Medium [lens] shot of [character/action] in [place]. The character [single clear action] as the camera [simple move]; [one reaction/beat], then hold on [ending composition]. Consistent costume, face, props and lighting; no dialogue unless specified.`

## Limits, formats and licensing

Phosphene submits asynchronous jobs and returns MP4 video. LTX is trained for 24 fps; valid frame counts are `8n+1`. The 24 GB Apple Silicon compact tier clamps or rejects dimensions beyond its advertised limits and can consume substantial unified memory and swap. Rendering competes with Devstral, MFLUX and ACE-Step, so use the shared scheduler and avoid concurrent generation. Generation time varies by frames, dimensions, model warmup, quality and system memory; measure each run from sidecar and live memory status rather than promising an ETA.

Phosphene's package/license and LTX-2.5 model license are separate from rights in prompts, source images and generated clips. Review Phosphene's included license notices and the installed LTX model's license/terms before commercial distribution. Only use source artwork you have rights to use. The video output is MP4; the sidecar is JSON. No automatic import into the game project occurs.

The installed Phosphene software is MIT licensed, but the LTX-2.5 Q4 weights are distributed under the LTX-2.x Community License. That license distinguishes non-commercial development from commercial use and may require a separate paid Lightricks license before commercial production or revenue-linked use. Read the license and adjacent `NOTICE.md` in Phosphene's `mlx_models/ltx-2.5-mlx-q4/` directory; do not infer output licensing from Phosphene's MIT license.
