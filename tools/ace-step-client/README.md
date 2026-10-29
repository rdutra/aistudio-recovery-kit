# ACE-Step 1.5 client

A standalone Python client for the ACE-Step API at http://127.0.0.1:8001.
It submits text-to-music jobs, polls status, downloads the generated MP3, and
writes a JSON sidecar with the prompt, requested duration, task ID, and server
result. Existing output files are never overwritten.

## Install

From this directory:

    python3 -m venv .venv
    . .venv/bin/activate
    python -m pip install -e .

## Generate

    ace-step --prompt "Dreamy ambient piano under a night sky" --duration 30 --output-name night-sky

Add `--thinking` to enable the server-side 5Hz language model for music code
generation. This matches the Gradio UI when its thinking option is enabled:

    ace-step --prompt "Dreamy ambient piano under a night sky" --duration 30 --output-name night-sky --thinking

Files are written to ~/AIStudio/outputs/music/night-sky.mp3 and
~/AIStudio/outputs/music/night-sky.json. Override the API or directory with
--api-url and --output-dir. If the server has API key authentication, set
ACE_STEP_API_KEY or pass --api-key.

## Tests

Run python -m unittest discover -s tests. Tests mock all HTTP responses and
never invoke GPU generation.
