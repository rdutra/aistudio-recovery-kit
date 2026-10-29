---
name: generate-game-art
description: Generate original game artwork with the local MFLUX image pipeline. Use for concept art, character references, equipment, sprites, textures, UI art, and game backgrounds.
metadata:
  short-description: Generate game art with local MFLUX
---

# Generate game art

Use the local MFLUX installation for requested image-generation work. Keep generated source assets under `~/AIStudio/outputs/images/<category>/`; do not import them into a game repository unless explicitly asked. Preserve generated images and never overwrite an existing asset.

## Client and invocation

The reusable wrapper is `~/AIStudio/tools/mflux-client/src/mflux_client.py`. Read `~/AIStudio/tools/mflux-client/README.md` when you need its options. It defaults to FLUX.2 Klein 4B, creates a unique filename and JSON sidecar, and validates PNG structure and dimensions. Example:

```sh
python3 ~/AIStudio/tools/mflux-client/src/mflux_client.py \
  --category characters --output-name norse-warrior-concept \
  --prompt "Full-body Norse warrior concept art, layered wool and weathered leather, bold silhouette, storm-lit fjord, original game art" \
  --width 896 --height 1152 --quantize 4 --steps 4 --seed 41
```

Choose a category from `characters`, `concepts`, `environments`, `equipment`, `sprites`, `textures`, `ui`, or `backgrounds`. The wrapper supports prompt, model, quantization, dimensions, inference steps, seed, filename, and a reference image plus strength. Use `--dry-run` to inspect a command without generation. Confirm the installed CLI/model's capabilities before introducing other options; MFLUX changes over time.

## Art direction and validation

Translate the brief into a clear prompt that describes subject, view, silhouette, materials, palette, lighting, composition, and intended game use. Tailor the framing by workflow: readable single subject for icons, full-body with separated limbs and plain background for modeling references, coherent style and silhouette for sprite components, and edge-conscious composition for tileable textures.

MFLUX does not directly guarantee transparent backgrounds or seamless textures. If transparency is requested, state it in the prompt, then report whether the saved file actually has an alpha channel; use an approved background-removal postprocess when needed. Do not call a texture seamless without comparing opposing edges and checking a tiled preview. Do not call sprites animation-ready without checking frame dimensions, transparency, and pivots. Do not call an image suitable for 3D reconstruction without checking that the requested pose and all required views/features are visible.

The wrapper's JSON sidecar records prompt, model, dimensions, seed, steps, quantization, reference image, and validation information. Its successful completion and an existing non-empty validated output file are required before reporting generation. Report Metal/out-of-memory errors plainly and do not change system memory limits. Avoid concurrent heavy generation with Devstral, ACE-Step, or cinematic generation; do not retain unused models in memory.

Review the selected model's license and output terms before commercial shipping. MFLUX package licensing does not determine the license of each model. The source asset remains outside production Godot assets until explicit approval.
