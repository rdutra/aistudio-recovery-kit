# AIStudio recovery kit

Recovery files for rebuilding this Apple Silicon macOS AIStudio setup after a clean install. The repo contains our small clients, scheduler, and Codex skills. Model weights, generated media, virtual environments, credentials, and the upstream ACE-Step checkout are deliberately not tracked.

## Restore

1. Install Xcode Command Line Tools and Homebrew.
2. Clone this repository to `~/AIStudio`.
3. Run `./scripts/setup-macos.sh` from the repository.
4. Follow the post-install checklist below for large models and Phosphene.

The script checks the architecture and installs the custom Python clients into local virtual environments. It also clones and syncs the upstream ACE-Step project. Model downloads can take many gigabytes and happen when each backend is first used.

## What is set up

- MFLUX client for image generation (`tools/mflux-client`)
- ACE-Step API client and upstream ACE-Step (`tools/ace-step-client`, `tools/ACE-Step-1.5`)
- MLX AudioGen client for sound effects (`tools/mlx-audiocraft`)
- Phosphene API client for video (`tools/phosphene-client`)
- Shared local GPU job scheduler (`tools/gpu-job-scheduler`)
- `generate-game-art` and `generate-game-music` Codex skills

## Manual steps after setup

- Install/configure Phosphene through Pinokio and download the LTX model. The local client expects its loopback API at `http://127.0.0.1:8198`.
- Start ACE-Step using `tools/ACE-Step-1.5/start_api_server_macos.sh`; first launch downloads model files. The API client expects port `8001`.
- First MFLUX and AudioGen runs download model weights. AudioGen's default model is about 3.6 GB. Check model licenses before commercial use.
- Restore any wanted files from a separate backup. `outputs/` is intentionally excluded from Git.
- Add any API credentials again through the relevant app or environment. Never put secrets in this repository.

## Verify installations

```sh
tools/ace-step-client/.venv/bin/python -m unittest discover -s tools/ace-step-client/tests
tools/phosphene-client/.venv/bin/python -m unittest discover -s tools/phosphene-client/tests
tools/mlx-audiocraft/.venv/bin/python -m unittest discover -s tools/mlx-audiocraft/tests
```

These are optional local checks and do not generate media or load model weights.

