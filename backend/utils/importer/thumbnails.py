"""Thumbnail + image-dimension helpers.

Pure module — no database, no ORM. Liftable verbatim into photosafe.
The thumbnail directory is supplied by the caller; this module never reads
environment variables.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image as PILImage

logger = logging.getLogger(__name__)


def get_image_dimensions(filepath: Path) -> Tuple[Optional[int], Optional[int]]:
    try:
        with PILImage.open(filepath) as img:
            return img.width, img.height
    except Exception:
        return None, None


def default_thumbnail_path(filepath: Path, thumbnail_dir: Path) -> Path:
    """Stable, collision-resistant thumbnail name for a source image."""
    name = f"{filepath.stem}_{hash(str(filepath)) & 0xFFFFFF:06x}.jpg"
    return thumbnail_dir / name


def create_thumbnail(
    filepath: Path,
    thumb_path: Path,
    max_size: int = 400,
) -> Optional[str]:
    """Generate a JPEG thumbnail. Returns the thumbnail path on success."""
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with PILImage.open(filepath) as img:
            img.thumbnail((max_size, max_size), PILImage.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path, "JPEG", quality=85, optimize=True)
        return str(thumb_path)
    except Exception as e:
        logger.error("Thumbnail creation failed for %s: %s", filepath, e)
        return None
