"""Sidecar JSON discovery + parsing.

Pure module — no database, no ORM, no Pillow. Designed to be liftable verbatim
into photosafe as `app/importers/sidecar.py`.

Supports three sidecar conventions:

* generic: ``{ "prompt": ..., "description": ..., "model": ..., "date": ... }``
* A1111 / Stable Diffusion: ``{ "parameters": "prompt\\nNegative prompt: ..." }``
* ComfyUI: ``{ "prompt": { "<node_id>": { "inputs": {"text": "..."} } } }``
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Date formats tried, in order, when an ISO parse fails.
_DATE_FALLBACK_FORMATS = (
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S",
    "%Y:%m:%d %H:%M:%S",
    "%Y-%m-%d",
    "%b %d, %Y",
    "%B %d, %Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
)

_DATE_KEYS = (
    "date_created",
    "created_at",
    "created",
    "date",
    "timestamp",
    "creation_time",
    "DateTime",
)

_PROMPT_KEYS = ("prompt", "Prompt", "positive_prompt", "text_prompt")
_DESCRIPTION_KEYS = ("description", "Description", "caption", "title")
_MODEL_KEYS = ("model", "Model", "model_name", "checkpoint", "sd_model")


def find_sidecar(filepath: Path) -> Optional[Path]:
    """Locate a sidecar JSON for an image.

    Prefers ``{stem}.json`` (e.g. ``foo.json`` next to ``foo.png``), falls back
    to ``{filename}.json`` (e.g. ``foo.png.json``) for ComfyUI-style outputs.
    """
    for candidate in (
        filepath.with_suffix(".json"),
        filepath.parent / (filepath.name + ".json"),
    ):
        if candidate.exists():
            return candidate
    return None


def _parse_date(val: Any) -> Optional[datetime]:
    if isinstance(val, (int, float)):
        try:
            return datetime.utcfromtimestamp(val)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(val, str):
        return None
    iso_val = val.strip()
    if not iso_val:
        return None
    if iso_val.endswith("Z"):
        iso_val = iso_val[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(iso_val)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        pass
    for fmt in _DATE_FALLBACK_FORMATS:
        try:
            return datetime.strptime(val.strip(), fmt)
        except ValueError:
            continue
    return None


def _extract_prompt(data: Dict[str, Any]) -> Optional[str]:
    for key in _PROMPT_KEYS:
        val = data.get(key)
        if isinstance(val, str) and val:
            return val
        if isinstance(val, dict):
            # ComfyUI: prompt is a node workflow; try CLIPTextEncode `text` inputs.
            for node in val.values():
                if not isinstance(node, dict):
                    continue
                text = (node.get("inputs") or {}).get("text")
                if isinstance(text, str) and len(text) > 10:
                    return text
    # A1111 "parameters" block: prompt is everything before "Negative prompt:".
    params = data.get("parameters")
    if isinstance(params, str):
        return params.split("\nNegative prompt:")[0].strip() or None
    return None


def _extract_first_str(data: Dict[str, Any], keys) -> Optional[str]:
    for key in keys:
        val = data.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def parse_sidecar(sidecar_path: Path) -> Dict[str, Any]:
    """Parse a sidecar JSON file and extract structured metadata.

    Returns a dict with these keys (all optional):

    * ``date_taken`` — naive UTC ``datetime``
    * ``prompt`` — ``str``
    * ``description`` — ``str``
    * ``model`` — ``str``
    * ``_raw`` — the original parsed JSON (preserved for callers that want to
      persist the raw blob in addition to the structured fields)
    """
    try:
        with open(sidecar_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Failed to parse sidecar %s: %s", sidecar_path, e)
        return {}

    if not isinstance(data, dict):
        return {"_raw": data}

    result: Dict[str, Any] = {"_raw": data}

    for key in _DATE_KEYS:
        val = data.get(key)
        if val is None:
            continue
        parsed = _parse_date(val)
        if parsed is not None:
            result["date_taken"] = parsed
            break

    prompt = _extract_prompt(data)
    if prompt:
        result["prompt"] = prompt

    description = _extract_first_str(data, _DESCRIPTION_KEYS)
    if description:
        result["description"] = description

    model = _extract_first_str(data, _MODEL_KEYS)
    if model:
        result["model"] = model

    return result
