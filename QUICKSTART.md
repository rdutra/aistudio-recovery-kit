# AIStudio Quickstart

Step-by-step restore for the Apple Silicon Mac. Start at step 1 after a factory reset; skip steps for software that is already installed.

## 1. Install the prerequisites and get this repo

Install Xcode Command Line Tools and Homebrew. Homebrew's current install instructions are at [brew.sh](https://brew.sh). Then install GitHub CLI, authenticate to the account that can read this private repo, and clone it into the expected path:

```sh
xcode-select --install
brew install gh
gh auth login
gh repo clone rdutra/aistudio-recovery-kit ~/AIStudio
cd ~/AIStudio
```

If `xcode-select --install` says the tools are already installed, continue.

## 2. Install the tools and skills

```sh
./scripts/setup-macos.sh
```

This installs the Homebrew dependencies, dmux with tmux, Codex CLI, Pinokio, the local Python clients, and ACE-Step 1.5. It also copies the four AIStudio game skills into `~/.agents/skills/` and creates the output folders.

Open Pinokio once and finish its first-run setup:

```sh
open ~/Applications/Pinokio.app
```

Run `codex` once and sign in with your ChatGPT account. If you use the ChatGPT desktop app, install it separately from [chatgpt.com/download](https://chatgpt.com/download) and sign in there too. Connected plugins, API credentials, and login state are deliberately not copied from the old computer.

## 3. Install the models

Download the core Hugging Face models used by image, sound-effects, and music workflows:

```sh
./scripts/download-models.sh
```

This downloads FLUX.2 Klein 4B, AudioGen Medium, T5 Large, ACE-Step 1.5, and the ACE-Step 5Hz language model into the standard Hugging Face cache. The first download takes time and several gigabytes. Some model repositories may require accepting their license or signing in to Hugging Face.

Install Phosphene and its LTX video model through Pinokio:

```sh
./scripts/install-phosphene.sh
```

The Phosphene install needs about 27.5 GB for the base engine before first start; about 10.7 GB of core extras downloads afterward. When the install step finishes, click **Start** in Pinokio and wait for Phosphene to report ready. Its panel is at `http://127.0.0.1:8198`. Optional Q8, High, Hailuo H3, YuE2, and character-training models are separate downloads; install those only if you plan to use those features.

## 4. Start the services

Open a terminal in `~/AIStudio` and start ACE-Step's local API:

```sh
cd ~/AIStudio/tools/ACE-Step-1.5
./start_api_server_macos.sh
```

Leave this terminal open while generating music. The API client uses `http://127.0.0.1:8001`. Start Phosphene from Pinokio when you need video generation. MFLUX and AudioGen run on demand.

## 5. Start dmux agents

In another terminal:

```sh
cd ~/AIStudio
dmux
```

Use dmux to create a Codex agent or pane in this repository. Codex CLI must be installed and signed in. Ask an agent to use the matching skill by name; the skills are installed globally, and dmux worktrees can use the shared `~/AIStudio/tools` and `~/AIStudio/outputs` paths.

Example requests:

- **Image:** “Use `$generate-game-art` to make an original equipment concept for a cursed Viking altar. Save it as `cursed-altar-detail`.”
- **Music:** “Use `$generate-game-music` to make a 30-second exploration cue with low strings and distant horns. Save it as `misty-fjord-exploration`.”
- **Sound effect:** “Use `$generate-game-sfx` to make a five-second iron shield impact with a sharp clang and short resonant tail. Save it as `iron-shield-impact`.”
- **Video:** “Use `$generate-game-cinematic` to make a five-second slow establishing shot over a foggy fjord. Save it as `fjord-establishing`.”

The skills route the jobs through the shared GPU scheduler where supported and preserve existing output files. Generated media and JSON sidecars are placed under `~/AIStudio/outputs/images`, `music`, `sfx`, or `video`.

## 6. After setup

- If a generator reports missing weights, rerun `./scripts/download-models.sh` or let that app finish its first-run model download.
- If a service is unavailable, start its app: ACE-Step in its terminal, Phosphene in Pinokio.
- Back up `outputs/` separately if you want to preserve generated assets. It is intentionally not stored in Git.
- Keep the machine on power and avoid starting multiple heavy model downloads or generations at the same time.

