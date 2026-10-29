# AudioGen SFX client

This isolated Python 3.12 environment wraps the upstream `mlx-audiocraft` AudioGen CLI and saves sound effects with JSON sidecars under `~/AIStudio/outputs/sfx`. The upstream AudioGen command currently documents prompt, duration, output, and optional model selection; it does not document a seed option, so this wrapper does not claim reproducibility by seed.

## Setup

From this directory:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

`sentencepiece` is installed explicitly because the package's T5 tokenizer needs it but the published dependency list omits it. `mlx-audiocraft` downloads model files from Hugging Face on first generation. The default `facebook/audiogen-medium` weights are about 3.6 GB. AudioGen's output sample rate is 16 kHz. Its T5 text encoder runs on CPU; the transformer and EnCodec decoder use MLX on Apple GPU/Metal. The installation was checked on Python 3.12 and macOS 26.6; MLX 0.32.4 reported `Device(gpu, 0)` without loading weights or generating audio.

## Check the backend without generation

```bash
.venv/bin/python sfx_client.py --check-backend
```

This imports MLX and reports its default device. It does not load AudioGen weights or generate audio.

## Generate

Every generation command is launched through the shared GPU scheduler, which serializes it with other local GPU jobs. Before scheduling, the client checks for standalone MFLUX generator processes and refuses to run while one is active. Persistent ACE-Step API/UI processes are not treated as active jobs because they remain running while idle; check their generation status and wait for any active generation to finish before starting AudioGen. The API job status covers API-submitted work; check the UI separately for UI-started work. This preflight cannot identify every unrelated GPU workload; other local clients must use the shared scheduler for serialization:

```bash
.venv/bin/python sfx_client.py \
  --prompt "A heavy iron gate creaks open, with a short metallic groan" \
  --duration 5 --output-name iron-gate
```

Default output is `~/AIStudio/outputs/sfx/iron-gate.wav` with `iron-gate.json`. WAV is the upstream native output. `--format flac` encodes through `soundfile`; `--format mp3` requires `ffmpeg` with `libmp3lame`. Existing names are preserved: a numeric suffix is chosen when an audio file, metadata file, or active reservation already uses the requested name. Options include `--output-dir`, `--model`, `--wait-timeout`, and `--command-timeout`. The client has a `--dry-run` mode to inspect the command without invoking generation.

The JSON sidecar records the prompt, requested duration, model, output format, command, and licenses. Upstream documents no seed flag or model seed API, so generation seed control is not supported here.

## Licensing

The wrapper and upstream `mlx-audiocraft` code are MIT licensed. Meta's `facebook/audiogen-medium` model weights use CC-BY-NC 4.0, which restricts commercial use. Do not use these weights for commercial outputs unless you obtain separate authorization. Review the model card and license terms before distribution.

## Tests

Run `.venv/bin/python -m unittest discover -s tests`. The tests mock the subprocess and never invoke a GPU workload.
