# AIStudio recovery kit

Recovery kit for this Apple Silicon Mac's local AI tools. It keeps our custom clients, Codex skills, dmux hook documentation, and repeatable setup scripts in Git. It does not store virtual environments, model weights, generated media, Codex sessions, or credentials.

## Restore the machine

1. Install macOS command line tools and Homebrew.
2. Clone this repository to `~/AIStudio`.
3. Run `./scripts/setup-macos.sh` to install Homebrew packages, dmux, Codex CLI, Pinokio, the Python clients, ACE-Step, and the four game skills.
4. Open Pinokio once and complete its first-run setup.
5. Run `./scripts/download-models.sh` to pre-download the core Hugging Face model repos, or let each tool fetch its weights the first time it runs.
6. Run `./scripts/install-phosphene.sh` to download Phosphene and run its Pinokio-managed installer. In Pinokio, start the app after installation completes.
7. Run `codex` and sign in. Install ChatGPT desktop separately from [chatgpt.com/download](https://chatgpt.com/download) if you use its Codex app.

The install scripts are safe to rerun. Core setup does not automatically download model weights. `download-models.sh` downloads several gigabytes into Hugging Face's normal cache. Phosphene downloads its weights through its own Pinokio installer, which resumes interrupted downloads. The Pinokio helper installs the latest Apple Silicon release into `~/Applications/Pinokio.app`; macOS first launch and permissions remain a user step.

## Included tools

- **dmux** 5.11.1 and tmux; `.dmux-hooks/` contains dmux hook documentation and examples. There are no active custom lifecycle hooks in this kit.
- **Codex CLI**, installed through npm; sign-in and app/plugin connections are completed in Codex after setup.
- **MFLUX** image client, pinned to 0.24.0.
- **ACE-Step 1.5** and our API client. The upstream source is cloned at the commit recorded in `versions.lock`.
- **MLX AudioGen** SFX client, plus its Python requirements.
- **Phosphene** video client; Pinokio manages the Phosphene engine, Python environment, and LTX model files.
- **Shared GPU scheduler** and four skills: game art, music, SFX, and cinematics.

## Models

`scripts/download-models.sh` downloads these Hugging Face repos: FLUX.2 Klein 4B, AudioGen Medium, T5 Large, ACE-Step 1.5, and the ACE-Step 5Hz LM. It may need a Hugging Face login if a repo's access policy requires it. The AudioGen Medium model is non-commercial under its model license; the script does not grant new rights.

Phosphene's Pinokio install fetches its base LTX-2.5 Q4 engine and support assets (about 27.5 GB before first start, with about 10.7 GB of extras downloaded afterward). Q8, High, Hailuo H3, YuE2 music, and character-training assets are optional and are not automatically installed by this kit. Download them from Phosphene only if you need them. Check each model's included license terms before commercial use.

## Launching services

- ACE-Step API: `cd ~/AIStudio/tools/ACE-Step-1.5 && ./start_api_server_macos.sh`. The client expects port `8001`.
- Phosphene: use Pinokio's Start button; its client expects `http://127.0.0.1:8198`.
- MFLUX, AudioGen, and the custom clients launch on demand.

## Kept out of Git

`outputs/` holds generated media and is ignored. Model caches, Phosphene's Pinokio data, `.venv` directories, API keys, Codex login/session data, and personal Codex databases are also outside this repo. Back up outputs separately if you want to preserve them across a factory reset. Reconnect GitHub, Hugging Face, and any other accounts after reinstalling; do not put tokens in this repo.

## Optional local checks

```sh
tools/ace-step-client/.venv/bin/python -m unittest discover -s tools/ace-step-client/tests
tools/phosphene-client/.venv/bin/python -m unittest discover -s tools/phosphene-client/tests
tools/mlx-audiocraft/.venv/bin/python -m unittest discover -s tools/mlx-audiocraft/tests
```

The scripts do not run these checks automatically.

