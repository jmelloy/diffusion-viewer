"""Datatypes shared across the importer pipeline.

Pure module — no DB, no ORM. The ORM layer maps ``ImageInfo`` onto its own
model (``Image`` in diffusion-viewer, ``Photo`` in photosafe).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class ImageInfo:
    """All metadata extracted from a file + its sidecar, ready to persist."""

    filename: str
    filepath: str
    directory: str
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    date_taken: Optional[datetime] = None
    sidecar_path: Optional[str] = None
    sidecar_raw: Optional[str] = None
    sidecar: Optional[Dict[str, Any]] = None
    prompt: Optional[str] = None
    description: Optional[str] = None
    model: Optional[str] = None
    thumbnail_path: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_sidecar(self) -> bool:
        return self.sidecar_path is not None
