from huggingface_hub import snapshot_download


MODELS = (
    "black-forest-labs/FLUX.2-klein-4B",
    "facebook/audiogen-medium",
    "t5-large",
    "ACE-Step/Ace-Step1.5",
    "ACE-Step/acestep-5Hz-lm-0.6B",
)

for repo_id in MODELS:
    print(f"\nDownloading {repo_id}", flush=True)
    snapshot_download(repo_id=repo_id)

