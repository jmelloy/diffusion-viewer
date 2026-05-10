"""Database-bound wrapper around :mod:`utils.importer`.

This module is the only place where the importer pipeline touches the
diffusion-viewer ORM. The pure logic (sidecar parsing, thumbnail generation,
directory walking, metadata extraction) lives in ``utils/importer/`` and is
liftable into photosafe verbatim; this file is the thin glue that turns an
:class:`ImageInfo` into an ``Image`` row.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

from sqlalchemy.orm import Session

import models
from utils.importer import (
    IMAGE_EXTENSIONS,
    ImageInfo,
    build_image_info,
    create_thumbnail,
    find_sidecar,
    walk_image_directory,
)

logger = logging.getLogger(__name__)

# Re-exported for back-compat with callers that imported these from scanner.
__all__ = [
    "IMAGE_EXTENSIONS",
    "THUMBNAIL_DIR",
    "create_thumbnail",
    "find_sidecar",
    "scan_directory",
    "scan_image_file",
]

THUMBNAIL_DIR = Path(os.environ.get("THUMBNAIL_DIR", "./thumbnails"))


def _upsert(db: Session, info: ImageInfo) -> Tuple[str, int]:
    existing = (
        db.query(models.Image).filter(models.Image.filepath == info.filepath).first()
    )

    if existing:
        existing.filename = info.filename
        existing.directory = info.directory
        existing.width = info.width
        existing.height = info.height
        existing.file_size = info.file_size
        existing.date_taken = info.date_taken
        existing.updated_at = datetime.utcnow()
        existing.sidecar_data = info.sidecar_raw
        existing.sidecar = info.sidecar
        existing.prompt = info.prompt
        existing.description = info.description
        existing.model = info.model
        existing.thumbnail_path = info.thumbnail_path
        db.commit()
        db.refresh(existing)
        return "updated", existing.id

    new_image = models.Image(
        filename=info.filename,
        filepath=info.filepath,
        directory=info.directory,
        width=info.width,
        height=info.height,
        file_size=info.file_size,
        date_taken=info.date_taken,
        sidecar_data=info.sidecar_raw,
        sidecar=info.sidecar,
        prompt=info.prompt,
        description=info.description,
        model=info.model,
        thumbnail_path=info.thumbnail_path,
    )
    db.add(new_image)
    db.commit()
    db.refresh(new_image)
    return "added", new_image.id


def scan_image_file(db: Session, filepath: Path) -> Tuple[str, int]:
    """Ingest (or update) a single image file. Returns ``("added"|"updated", id)``."""
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    info = build_image_info(filepath, thumbnail_dir=THUMBNAIL_DIR)
    return _upsert(db, info)


def scan_directory(db: Session, directory: str) -> Dict[str, int]:
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    directory_path = Path(directory)
    if not directory_path.exists():
        raise ValueError(f"Directory does not exist: {directory}")

    logger.info("Scan starting: %s", directory_path)

    candidates = list(walk_image_directory(directory_path))
    total = len(candidates)
    logger.info("Found %d image files under %s", total, directory_path)

    stats = {"scanned": 0, "added": 0, "updated": 0, "with_sidecar": 0}
    image_ids_processed = []
    progress_every = max(1, min(50, total // 20)) if total else 1

    for idx, filepath in enumerate(candidates, 1):
        stats["scanned"] += 1
        info = build_image_info(filepath, thumbnail_dir=THUMBNAIL_DIR)
        if info.has_sidecar:
            stats["with_sidecar"] += 1
        result, image_id = _upsert(db, info)
        stats[result] += 1
        image_ids_processed.append(image_id)

        if idx % progress_every == 0 or idx == total:
            logger.info(
                "  [%d/%d] added=%d updated=%d sidecars=%d",
                idx,
                total,
                stats["added"],
                stats["updated"],
                stats["with_sidecar"],
            )

    # Auto-tagging is intentionally disabled to avoid noisy tag suggestions
    # during routine scans.
    if image_ids_processed:
        logger.info(
            "Auto-tagging skipped for %d images (disabled).",
            len(image_ids_processed),
        )

    logger.info("Scan complete: %s", stats)
    return stats
