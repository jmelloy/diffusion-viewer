# Scripts

Utility scripts for image generation, downloading, and game diagnostics.

## Installation

```bash
pip install -r scripts/requirements.txt
playwright install webkit   # required by mage_generate.py and mage_download.py
```

## Scripts

| Script | Purpose |
|--------|---------|
| `mage_generate.py` | Automate image generation on mage.space/advanced using Playwright. Supports single prompts, batch mode from a markdown file, model/ratio selection, and local download. |
| `mage_download.py` | Download all saved images from mage.space/creations with JSON sidecar metadata. Supports collection filtering, resume via manifest, and date-organised output. |
| `dump_game.py` | Dump Clue game state, logs, chat, solution, agent memory, and trace from Redis. Outputs human-readable text or JSON. |

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

# List all Clue games in Redis
python scripts/dump_game.py --list-games

# Dump a specific game
python scripts/dump_game.py ABC123 --show-chat --show-cards --show-players
```
