# Scripts

Utility scripts for managing, exporting, and downloading AI-generated image metadata.

## Setup

```bash
pip install -r requirements.txt
playwright install webkit   # required by mage_generate.py and mage_download.py
```

Some scripts depend on local library modules (`lib/`) from the photosafe project.

## Scripts

| Script | Description |
|---|---|
| `mage_generate.py` | Automate image generation on mage.space/advanced using Playwright. Supports single prompts, batch mode from a markdown file, model/ratio selection, and local download. |
| `mage_download.py` | Download all saved images from mage.space/creations with JSON sidecar metadata. Supports collection filtering, resume via manifest, and date-organised output. |
| `extract_dump.py` | Parse a large Apple Photos dump JSON, extract individual records and organise them by date/GUID under `output/` |
| `convert_to_xmp.py` | Convert image metadata JSON files to XMP sidecar files (Dublin Core, EXIF, XMP, Photoshop namespaces) |
| `extract_civit.py` | Fetch generations from the Civitai API (requires `CIVITAI_API_TOKEN`), download images and create XMP sidecars |
| `convert_to_sidecar.py` | Walk a directory of AI-generated images, extract metadata via the appropriate format-specific processor (Mage, ComfyUI, Civitai, Invoke, Leonardo, ...), and write a JSON sidecar next to each image in the canonical shape produced by `mage_download.py` and consumed by the diffusion-viewer scanner. Optionally uses Ollama (gemma3:4b) to extract character-name tags from prompts (`--no-tags` to skip). |
| `invoke.py` | Read an Invoke AI SQLite database and generate JSON/XMP sidecar files for every image |
| `mage.py` | Scrape a Mage.space user gallery (requires browser session cookies), download images and create XMP sidecars |
| `leonardo.py` | Fetch a Leonardo.ai user's generated images via GraphQL API (requires auth token) and download them organised by date |
| `moments.py` | Analyse Apple Photos collections with MLX-VLM (pixtral-12b) and write `moment.yaml` summaries per day — macOS/Apple Silicon only |
| `rename.py` | Rename output directory entries by `cloud_guid`/`uuid` from `apple.json`, organised by date |
| `process_comfyui.py` | Walk a ComfyUI output directory, extract per-image metadata, copy to Obsidian vault, and write JSON sidecars |
| `process_mage.py` | Walk a Mage.space output directory, extract metadata via `lib.mage`, and copy images to Obsidian vault |
| `process_civitai.py` | Walk a Civitai output directory, extract metadata via `lib.civitai`, and copy images to Obsidian vault |
| `process_invoke.py` | Walk an Invoke AI output directory, extract metadata via `lib.invoke`, and copy images to Obsidian vault |
| `process_leonardo.py` | Walk a Leonardo.ai output directory, extract metadata via `lib.leonardo`, and copy images to Obsidian vault |
| `walk_obsidian.py` | Walk an Obsidian vault, locate images inside `_images/` folders, extract YAML frontmatter from sibling Markdown files, and optionally copy images with JSON metadata sidecars to a destination directory |
| `walk.py` | tkinter GUI image viewer for browsing generated images; supports filtering by prompt, copying selected images to a destination folder, and logging viewed images to avoid duplicates |

## Usage

```bash
# Generate a single image
python scripts/mage_generate.py "a cozy cabin at sunset"

# Batch-generate from a markdown prompt file
python scripts/mage_generate.py --batch room-prompts.md --output ./images

# Download all saved mage.space creations
python scripts/mage_download.py --output ./mage-archive --resume

# Download a specific collection
python scripts/mage_download.py --collection "Diffusion" --output ./diffusion-archive
```
