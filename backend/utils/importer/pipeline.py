"""Build an :class:`ImageInfo` for a single file, or walk a directory tree.

Pure module — combines :mod:`sidecar` and :mod:`thumbnails`. The caller owns
persistence; ``build_image_info`` does not touch any database.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from .sidecar import IMAGE_EXTENSIONS, find_sidecar, parse_sidecar
from .thumbnails import create_thumbnail, default_thumbnail_path, get_image_dimensions
from .types import ImageInfo

logger = logging.getLogger(__name__)


def walk_image_directory(directory: Path) -> Iterator[Path]:
    """Yield candidate image files under *directory*, skipping dotdirs."""
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if Path(fname).suffix.lower() in IMAGE_EXTENSIONS:
                yield Path(root) / fname


def build_image_info(
    filepath: Path,
    *,
    thumbnail_dir: Optional[Path] = None,
    make_thumbnail: bool = True,
    thumbnail_max_size: int = 400,
) -> ImageInfo:
    """Extract sidecar + filesystem metadata and (optionally) build a thumbnail.

    Pure with respect to the database — no DB sessions, no model objects.
    """
    filepath = Path(filepath)
    sidecar_path = find_sidecar(filepath)
    sidecar_meta: dict = {}
    sidecar_raw: Optional[str] = None
    sidecar_obj: Optional[dict] = None
    if sidecar_path is not None:
        sidecar_meta = parse_sidecar(sidecar_path)
        raw = sidecar_meta.pop("_raw", None)
        if raw is not None:
            sidecar_obj = raw if isinstance(raw, dict) else None
            sidecar_raw = json.dumps(raw)

    try:
        file_size: Optional[int] = filepath.stat().st_size
    except Exception:
        file_size = None

    width, height = get_image_dimensions(filepath)

    date_taken = sidecar_meta.get("date_taken")
    if date_taken is None:
        try:
            mtime = filepath.stat().st_mtime
            date_taken = datetime.utcfromtimestamp(mtime)
        except Exception:
            date_taken = None

    thumbnail_path: Optional[str] = None
    if make_thumbnail and thumbnail_dir is not None:
        thumb_path = default_thumbnail_path(filepath, Path(thumbnail_dir))
        thumbnail_path = create_thumbnail(
            filepath, thumb_path, max_size=thumbnail_max_size
        )
        if thumbnail_path is None:
            # Even if PIL failed, record the intended path so the ORM row has a
            # stable value rather than leaving it NULL.
            thumbnail_path = str(thumb_path)

    return ImageInfo(
        filename=filepath.name,
        filepath=str(filepath),
        directory=str(filepath.parent),
        width=width,
        height=height,
        file_size=file_size,
        date_taken=date_taken,
        sidecar_path=str(sidecar_path) if sidecar_path else None,
        sidecar_raw=sidecar_raw,
        sidecar=sidecar_obj,
        prompt=sidecar_meta.get("prompt"),
        description=sidecar_meta.get("description"),
        model=sidecar_meta.get("model"),
        thumbnail_path=thumbnail_path,
    )
