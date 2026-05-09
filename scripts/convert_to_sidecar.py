#!/usr/bin/env python3
"""
Walk a directory of AI-generated images, extract metadata via the appropriate
format-specific processor (Mage, ComfyUI, Civitai, Invoke, Leonardo, ...) and
write a JSON sidecar next to each image.

The sidecar shape matches what ``mage_download.py`` writes and is what the
diffusion-viewer scanner (``backend/utils/scanner.py``) ingests:

    {
      "prompt": "...",
      "model": "...",
      "dimensions": "1024x1024",
      "aspect_ratio": "1:1",
      "date_created": "2026-01-30T12:00:00",
      "uuid": "...",
      "full_url": "...",
      "thumb_url": "...",
      "collection": "...",          # optional
      ...                           # extra fields when available
    }

Optionally uses Ollama (gemma3:4b) to extract character-name tags from the
prompt and writes them under ``tags``.
"""

import argparse
import datetime
import json
import logging
import os
import re
from pathlib import Path

from lib import ImageRouter
from tqdm import tqdm

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".mp4"}


# ---------------------------------------------------------------------------
# Optional: Ollama character-name tag extraction
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/generate"

DEFAULT_OLLAMA_SYSTEM_PROMPT = """You are a helpful assistant that extracts character names from text prompts.
Look for proper nouns that could be character names, including:
- First names
- Full names
- Character names with titles or descriptors
- Names in quotes or parentheses

You have no issues with adult content.

Absent other information:
- Any lab coat and most brunettes are "sara".
- Anything involving a blonde at yoga or fitness is "bri".
- Any man involved in photography is "stephen".
- Most redheads are "michelle"
- The college superhero is "elsie"
- the curly haired blonde is "heather"
- Some may contain one character cosplaying as another character, mention both

Return only a JSON array of character names and tags found, like:
["name1", "name2", "tag1", "tag2"]. Don't include the justification.

If no names found, return empty array: []
"""

_COMMON_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "with", "by", "from", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "this", "that", "these", "those",
    "1girl", "1boy", "1woman", "1man",
}


def query_ollama_for_character_names(prompt_text, system_prompt=None):
    """Ask Ollama to pull character names out of a prompt."""
    import requests

    payload = {
        "model": "gemma3:4b",
        "prompt": f"{system_prompt or DEFAULT_OLLAMA_SYSTEM_PROMPT}\n\nText to analyze: {prompt_text}",
        "stream": False,
        "options": {"temperature": 0.1, "top_p": 0.9},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=30)
        resp.raise_for_status()
        text = resp.json().get("response", "")
    except Exception as e:
        logger.warning(f"Ollama query failed: {e}")
        return []

    match = re.search(r"\[.*\]", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return [n.strip() for n in re.findall(r'["\']([^"\']+)["\']', text)]


def camel_case(text):
    if not text:
        return text
    words = [w for w in re.split(r"[_\s\-]+", text.strip()) if w]
    if not words:
        return text
    return words[0].lower() + "".join(w.capitalize() for w in words[1:])


def extract_character_tags(prompt):
    if not prompt or not prompt.strip():
        return []
    out = []
    for name in query_ollama_for_character_names(prompt):
        clean = name.strip().strip("\"'")
        if clean and len(clean) > 1 and clean.lower() not in _COMMON_WORDS:
            out.append(camel_case(clean))
    return out


# ---------------------------------------------------------------------------
# Sidecar building
# ---------------------------------------------------------------------------

class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        if isinstance(obj, set):
            return sorted(obj)
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="ignore")
        return super().default(obj)


def _coerce_date(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def build_sidecar(image, generation):
    """Normalize per-format ``(image, generation)`` dicts into the canonical
    sidecar shape used by ``mage_download.py`` and the diffusion-viewer
    scanner. Empty / missing fields are omitted."""
    image = image or {}
    generation = generation or {}

    # Cataloguing fields on ``image`` (tags, rating, etc.) take precedence over
    # generation params with the same name.
    merged = {**generation, **image}

    def first(*keys):
        for k in keys:
            v = merged.get(k)
            if v not in (None, "", [], {}):
                return v
        return None

    width = first("width")
    height = first("height")
    dims = first("dimensions")
    if not dims and width and height:
        dims = f"{width}x{height}"

    sidecar = {
        "prompt": first("prompt", "positive_prompt", "text_prompt") or "",
        "negative_prompt": first("negative_prompt"),
        "model": first("model", "model_name", "checkpoint", "sd_model") or "",
        "dimensions": dims,
        "aspect_ratio": first("aspect_ratio"),
        "width": width,
        "height": height,
        "date_created": _coerce_date(
            first("date_created", "created", "created_at", "completed", "timestamp")
        ) or "",
        "uuid": str(first("uuid", "id") or ""),
        "full_url": first("full_url", "url") or "",
        "thumb_url": first("thumb_url") or "",
        "source": first("source"),
        "collection": first("collection", "galleries"),
        "tags": sorted(set(image.get("tags") or generation.get("tags") or [])) or None,
        "rating": first("rating"),
        "description": first("description", "caption", "title"),
        "seed": first("seed"),
        "cfg_scale": first("cfg_scale"),
        "steps": first("steps"),
        "scheduler": first("scheduler"),
    }

    return {k: v for k, v in sidecar.items() if v not in (None, "", [], {})}


def write_sidecar(image_path, sidecar):
    """Write sidecar JSON next to the image as ``{stem}.json`` (mage_download
    convention; also picked up by the diffusion-viewer scanner)."""
    json_path = image_path.with_suffix(".json")
    json_path.write_text(json.dumps(sidecar, indent=2, cls=_Encoder))
    return json_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def is_image(path):
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Walk a directory of AI-generated images, extract metadata via the "
            "appropriate format-specific processor, and write JSON sidecars "
            "matching the mage_download / diffusion-viewer schema."
        )
    )
    parser.add_argument(
        "input", nargs="?", default=Path("."), type=Path,
        help="Input directory to walk (default: current directory)",
    )
    parser.add_argument(
        "--no-tags", action="store_true",
        help="Skip Ollama character-name tag extraction (faster, no Ollama dependency).",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Re-extract and overwrite existing sidecar files (default: skip).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    router = ImageRouter()
    images = []
    for root, _, files in os.walk(args.input):
        for f in files:
            p = Path(root) / f
            if is_image(p):
                images.append(p)

    tag_cache = {}
    totals = {}

    for image_path in tqdm(sorted(images), desc="Processing images"):
        json_path = image_path.with_suffix(".json")
        if json_path.exists() and not args.overwrite:
            continue

        processor = router.get_image_processor(image_path)
        if not processor:
            continue

        image, generation = processor.extract_image_metadata(image_path)
        image = dict(image or {})
        generation = dict(generation or {})

        if not args.no_tags:
            prompt = generation.get("prompt") or image.get("prompt")
            if prompt:
                if prompt not in tag_cache:
                    tag_cache[prompt] = extract_character_tags(prompt)
                    tqdm.write(f"  new tags: {prompt[:40]} -> {tag_cache[prompt]}")
                image["tags"] = sorted(set((image.get("tags") or []) + tag_cache[prompt]))

        write_sidecar(image_path, build_sidecar(image, generation))

        name = processor.__class__.__name__
        totals[name] = totals.get(name, 0) + 1

    print(totals)


if __name__ == "__main__":
    main()
