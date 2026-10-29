# Local MFLUX game art client

`src/mflux_client.py` wraps the installed MFLUX 0.24.0 FLUX.2 Klein command, selects an output category under `~/AIStudio/outputs/images`, avoids existing filenames, validates PNG chunk integrity, and writes a JSON metadata sidecar. These outputs are source assets; copy them into a Godot project only after explicit approval.

Example Norse warrior concept:

```sh
python3 src/mflux_client.py --category characters --output-name norse-warrior-concept \
  --prompt "Full-body Norse warrior concept art, layered wool and weathered leather, restrained iron ornament, fur mantle, storm-lit fjord behind, readable silhouette, original game art" \
  --width 896 --height 1152 --quantize 4 --steps 4 --seed 41
```

Inspect an invocation without using the GPU with `--dry-run`. Image-to-image references use MFLUX's `--image PATH STRENGTH` option. Transparency is prompt intent only; this MFLUX path has no direct transparent-output option. The wrapper reports whether the PNG has an alpha channel, and does not claim alpha transparency based on the request. No texture seam or sprite pivot checks are performed.

Tests: `python3 -m unittest discover -s tests`. They use tiny synthetic PNGs and never launch MFLUX.

MFLUX package license metadata identifies MFLUX as MIT, but that is not a grant for every downloaded model. Review the specific model license and output terms for commercial use. The existing `outputs/images/image.png` is 768×768 RGB, but has no readable generation metadata; its model, prompt, seed, and parameters are unknown.
