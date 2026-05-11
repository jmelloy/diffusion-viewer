"""ORM-free image importer.

Lift-and-shift target: this package contains everything needed to ingest a
diffusion-style image directory (sidecar parsing, thumbnail generation,
file-system walking, metadata extraction) **without** importing the
diffusion-viewer ORM. Photosafe can drop this package in as
``app/importers/diffusion/`` and wire its own ``Photo`` model to the
:class:`ImageInfo` payload.
"""

from .pipeline import build_image_info, walk_image_directory
from .sidecar import IMAGE_EXTENSIONS, find_sidecar, parse_sidecar
from .thumbnails import create_thumbnail, default_thumbnail_path, get_image_dimensions
from .types import ImageInfo

__all__ = [
    "IMAGE_EXTENSIONS",
    "ImageInfo",
    "build_image_info",
    "create_thumbnail",
    "default_thumbnail_path",
    "find_sidecar",
    "get_image_dimensions",
    "parse_sidecar",
    "walk_image_directory",
]
