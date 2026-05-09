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
| `convert_to_markdown.py` | Convert image metadata JSON to Obsidian-compatible Markdown with YAML frontmatter; uses Ollama (gemma3:4b) to extract character names from prompts |
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
| `auto_organize.py` | Phased rebuild of the tag tree from prompts/descriptions: clear → proper-noun extraction → project clustering (proper-noun co-occurrence + TF-IDF centroid absorption) → per-project distinctive TF-IDF tags. Dry-run by default; `--execute` to apply. |

## Auto-organize workflow

`auto_organize.py` rebuilds the tag tree when you've cleared tags (or want to
re-do them from scratch). It runs in four phases — each is dry-run by default
so you can tune the knobs before committing:

```bash
# 1. wipe the existing tag graph
python scripts/auto_organize.py clear --execute

# 2. extract capitalized names/places/brands as flat tags
python scripts/auto_organize.py proper-nouns --execute

# 3. group images into projects via proper-noun co-occurrence,
#    then absorb un-named images by TF-IDF cosine similarity
python scripts/auto_organize.py cluster --execute

# 4. add distinctive in-project TF-IDF terms as children of each project
python scripts/auto_organize.py project-tags --execute

# or run all four in one go (still dry-run unless --execute)
python scripts/auto_organize.py all --execute
```

Common knobs to tweak when proposals look off:

| Flag | What it does |
|---|---|
| `--min-noun-count` | drop proper nouns below N occurrences (default 3) |
| `--min-cooccurrence` | edge weight required to merge two nouns into the same project (default 2) |
| `--cluster-threshold` | cosine similarity required to absorb a noun-less image into a project (default 0.18) |
| `--min-cluster-size` | reject project clusters smaller than N images (default 8) |
| `--min-distinctive` | in-cluster vs out-cluster TF-IDF ratio for a term to count as distinctive (default 1.5) |
| `--top-n-per-project` / `--top-n-per-image` | caps on distinctive terms per project / per image |
| `--db PATH` | run against a specific SQLite file (otherwise honors `$DATABASE_URL`) |

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
