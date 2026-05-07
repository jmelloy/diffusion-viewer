import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from PIL import Image as PILImage
from sqlalchemy.orm import Session

import models
import schemas

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
THUMBNAIL_DIR = Path(os.environ.get("THUMBNAIL_DIR", "./thumbnails"))


def ensure_thumbnail_dir():
    THUMBNAIL_DIR.mkdir(exist_ok=True)


def find_sidecar(filepath: Path) -> Optional[Path]:
    """Locate a sidecar JSON for an image. Prefers `{stem}.json` (e.g.
    `foo.json` next to `foo.png`), falls back to `{filename}.json`
    (e.g. `foo.png.json`) for ComfyUI-style outputs."""
    for candidate in (
        filepath.with_suffix(".json"),
        filepath.parent / (filepath.name + ".json"),
    ):
        if candidate.exists():
            return candidate
    return None


def parse_sidecar(sidecar_path: Path) -> Dict[str, Any]:
    """Parse a sidecar JSON file and extract structured metadata."""
    try:
        with open(sidecar_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"Failed to parse sidecar {sidecar_path}: {e}")
        return {}

    result: Dict[str, Any] = {"_raw": data}

    # Extract date from common fields. Mage and similar tools use
    # "date_created"; other tools use "created" / "created_at".
    for date_key in (
        "date_created",
        "created_at",
        "created",
        "date",
        "timestamp",
        "creation_time",
        "DateTime",
    ):
        val = data.get(date_key)
        if val:
            try:
                if isinstance(val, (int, float)):
                    result["date_taken"] = datetime.utcfromtimestamp(val)
                else:
                    for fmt in (
                        "%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%dT%H:%M:%SZ",
                        "%Y-%m-%d %H:%M:%S",
                        "%Y:%m:%d %H:%M:%S",
                        "%Y-%m-%d",
                        "%b %d, %Y",  # Mage: "Jan 30, 2025"
                        "%B %d, %Y",  # "January 30, 2025"
                        "%m/%d/%Y",
                        "%Y/%m/%d",
                    ):
                        try:
                            result["date_taken"] = datetime.strptime(
                                str(val).strip(), fmt
                            )
                            break
                        except ValueError:
                            pass
            except Exception:
                pass
            if "date_taken" in result:
                break

    # Extract prompt
    for prompt_key in ("prompt", "Prompt", "positive_prompt", "text_prompt"):
        val = data.get(prompt_key)
        if val and isinstance(val, str):
            result["prompt"] = val
            break
        # ComfyUI format: "prompt" is a node workflow dict
        if val and isinstance(val, dict):
            # Try to extract text from CLIPTextEncode nodes
            for node_id, node in val.items():
                inputs = node.get("inputs", {}) if isinstance(node, dict) else {}
                text = inputs.get("text")
                if text and isinstance(text, str) and len(text) > 10:
                    result["prompt"] = text
                    break
            if "prompt" in result:
                break

    # Stable Diffusion "parameters" block (A1111 format)
    if "parameters" in data and isinstance(data["parameters"], str):
        params = data["parameters"]
        result.setdefault("prompt", params.split("\nNegative prompt:")[0].strip())

    # Extract description
    for desc_key in ("description", "Description", "caption", "title"):
        val = data.get(desc_key)
        if val and isinstance(val, str):
            result["description"] = val
            break

    # Extract model
    for model_key in ("model", "Model", "model_name", "checkpoint", "sd_model"):
        val = data.get(model_key)
        if val and isinstance(val, str):
            result["model"] = val
            break

    return result


def get_image_dimensions(filepath: Path):
    try:
        with PILImage.open(filepath) as img:
            return img.width, img.height
    except Exception:
        return None, None


def create_thumbnail(filepath: Path, thumb_path: Path, max_size: int = 400):
    ensure_thumbnail_dir()
    try:
        with PILImage.open(filepath) as img:
            img.thumbnail((max_size, max_size), PILImage.LANCZOS)
            # Convert RGBA to RGB for JPEG
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path, "JPEG", quality=85, optimize=True)
        return str(thumb_path)
    except Exception as e:
        logger.error(f"Thumbnail creation failed for {filepath}: {e}")
        return None


def scan_image_file(db: Session, filepath: Path) -> str:
    """Ingest (or update) a single image file. Returns 'added' or 'updated'."""
    ensure_thumbnail_dir()
    fname = filepath.name
    root_str = str(filepath.parent)

    sidecar_path = find_sidecar(filepath)
    sidecar_meta: Dict[str, Any] = {}
    sidecar_raw: Optional[str] = None
    if sidecar_path is not None:
        sidecar_meta = parse_sidecar(sidecar_path)
        raw = sidecar_meta.pop("_raw", None)
        if raw is not None:
            sidecar_raw = json.dumps(raw)

    try:
        file_size = filepath.stat().st_size
    except Exception:
        file_size = None

    width, height = get_image_dimensions(filepath)
    date_taken = sidecar_meta.get("date_taken")
    if date_taken is None:
        try:
            mtime = filepath.stat().st_mtime
            date_taken = datetime.utcfromtimestamp(mtime)
        except Exception:
            pass

    thumb_name = f"{filepath.stem}_{hash(str(filepath)) & 0xFFFFFF:06x}.jpg"
    thumb_path = THUMBNAIL_DIR / thumb_name

    existing = (
        db.query(models.Image).filter(models.Image.filepath == str(filepath)).first()
    )

    if existing:
        existing.filename = fname
        existing.directory = root_str
        existing.width = width
        existing.height = height
        existing.file_size = file_size
        existing.date_taken = date_taken
        existing.updated_at = datetime.utcnow()
        existing.sidecar_data = sidecar_raw
        existing.prompt = sidecar_meta.get("prompt")
        existing.description = sidecar_meta.get("description")
        existing.model = sidecar_meta.get("model")
        existing.thumbnail_path = str(thumb_path)
        db.commit()
        db.refresh(existing)
        return "updated", existing.id
    else:
        new_image = models.Image(
            filename=fname,
            filepath=str(filepath),
            directory=root_str,
            width=width,
            height=height,
            file_size=file_size,
            date_taken=date_taken,
            sidecar_data=sidecar_raw,
            prompt=sidecar_meta.get("prompt"),
            description=sidecar_meta.get("description"),
            model=sidecar_meta.get("model"),
            thumbnail_path=str(thumb_path),
        )
        db.add(new_image)
        db.commit()
        db.refresh(new_image)
        return "added", new_image.id


def scan_directory(db: Session, directory: str) -> Dict[str, int]:
    ensure_thumbnail_dir()
    directory_path = Path(directory)
    if not directory_path.exists():
        raise ValueError(f"Directory does not exist: {directory}")

    logger.info(f"Scan starting: {directory_path}")

    # First pass: enumerate candidate image files so we can report progress.
    candidates: list[Path] = []
    for root, dirs, files in os.walk(directory_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            if Path(fname).suffix.lower() in IMAGE_EXTENSIONS:
                candidates.append(Path(root) / fname)

    total = len(candidates)
    logger.info(f"Found {total} image files under {directory_path}")

    stats = {"scanned": 0, "added": 0, "updated": 0, "with_sidecar": 0}
    image_ids_processed = []
    progress_every = max(1, min(50, total // 20)) if total else 1

    for idx, filepath in enumerate(candidates, 1):
        stats["scanned"] += 1
        if find_sidecar(filepath):
            stats["with_sidecar"] += 1
        result, image_id = scan_image_file(db, filepath)
        stats[result] += 1
        image_ids_processed.append(image_id)

        if idx % progress_every == 0 or idx == total:
            logger.info(
                f"  [{idx}/{total}] added={stats['added']} "
                f"updated={stats['updated']} sidecars={stats['with_sidecar']}"
            )

    # Run auto-tagging on processed images
    if image_ids_processed:
        logger.info(f"Auto-tagging {len(image_ids_processed)} images...")
        try:
            from utils.tfidf import auto_tag_images

            auto_tag_images(db, image_ids=image_ids_processed)
        except Exception as e:
            logger.warning(f"Auto-tagging failed: {e}")

    logger.info(f"Scan complete: {stats}")
    return stats
