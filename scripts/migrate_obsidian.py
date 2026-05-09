#!/usr/bin/env python3
"""
Flatten the Obsidian AI vault into the diffusion-viewer images tree.

Source layouts handled:

  Old (W##/ULID folder per generation):
      <root>/YYYY/MM Mon/W##/DD (Day)/
          <ULID> - <prompt>/
              _images/<image>.<ext>
              <ULID> - <prompt>.md           # frontmatter: prompt-level
              <image>.<ext>.md               # frontmatter: per-image

  New (one .md per image, sibling to _images/):
      <root>/YYYY/YYYY-MM/DD/
          <slug>-<uuid>.md                   # body links _images/<hash>.<ext>
          _images/<hash>.<ext>

Destination:
      ~/diffusion-viewer/images/YYYY/MM - MonthName/DD - DayName/
          <image>.<ext>
          <image>.<ext>.json                 # combined sidecar

JSON sidecar:
  - Combines frontmatter from prompt-level .md and image-level .md (image
    fields win on conflict). For new-structure docs without frontmatter, the
    body's "## Metadata" and "## Prompt" sections are parsed.
  - "created" is renamed to "created_at".
  - "prompt" is always populated when discoverable.

Run with --dry-run first to preview.
"""

import argparse
import calendar
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".mp4"}

DEFAULT_SOURCE = Path(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/obsidian/AI"
).expanduser()
DEFAULT_DEST = Path("~/diffusion-viewer/images").expanduser()


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------

def _read(md_path: Path) -> str:
    try:
        return md_path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return ""


def parse_frontmatter(md_path: Path) -> dict:
    text = _read(md_path)
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        print(f"  WARN bad yaml in {md_path}: {e}", file=sys.stderr)
        return {}
    return data if isinstance(data, dict) else {}


def parse_body(md_path: Path) -> str:
    text = _read(md_path)
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2]
    return text


_WIKI_LINK = re.compile(r"!\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]")
_MD_LINK = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def find_image_links(md_path: Path) -> list[str]:
    body = parse_body(md_path)
    out = []
    for m in _WIKI_LINK.finditer(body):
        out.append(Path(m.group(1).strip()).name)
    for m in _MD_LINK.finditer(body):
        out.append(Path(m.group(1).strip()).name)
    return out


_METADATA_LINE = re.compile(r"-\s*\*\*([^*]+?):\*\*\s*(.+)")
_PROMPT_BLOCK = re.compile(r"##\s*Prompt\s*\n+>\s*(.+?)(?:\n##|\Z)", re.S)
_TITLE_LINE = re.compile(r"^#\s+(.+?)\s*$", re.M)
_DATE_FORMATS = (
    "%b %d, %Y", "%B %d, %Y",
    "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f",
)


def parse_body_metadata(md_path: Path) -> dict:
    """Pull data out of the structured `## Metadata` / `## Prompt` markdown
    used by new-structure docs without frontmatter."""
    body = parse_body(md_path)
    out: dict = {}

    title_m = _TITLE_LINE.search(body)
    if title_m:
        out["title"] = title_m.group(1).strip()

    for m in _METADATA_LINE.finditer(body):
        key = m.group(1).strip().lower().replace(" ", "_")
        val = m.group(2).strip()
        if key == "dimensions":
            dim_m = re.match(r"(\d+)\s*[x×]\s*(\d+)", val)
            if dim_m:
                out["width"] = int(dim_m.group(1))
                out["height"] = int(dim_m.group(2))
            out["dimensions"] = val
        elif key in ("date_created", "created"):
            out["created"] = _coerce_to_date(val) or val
        elif key == "uuid":
            out["uuid"] = val
        elif key == "cdn_url":
            out["url"] = val
        elif key in ("model", "aspect_ratio"):
            out[key] = val

    pm = _PROMPT_BLOCK.search(body)
    if pm:
        out["prompt"] = pm.group(1).strip()
    elif title_m:
        out.setdefault("prompt", title_m.group(1).strip())

    return out


def _coerce_to_date(value):
    if isinstance(value, (datetime, date)):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace(" ", "T", 1))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Date/path utilities
# ---------------------------------------------------------------------------

_YEAR_RE = re.compile(r"^(\d{4})$")
_YEARMONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_MONTH_RE = re.compile(r"^(\d{2})\s+\w+$")
_DAY_RE = re.compile(r"^(\d{2})(?:\s+\(\w+\))?$")


def date_from_path(path: Path, source: Path):
    """Walk components of ``path`` relative to ``source`` and pull out
    (year, month, day) when they match the known directory naming schemes."""
    try:
        rel = path.relative_to(source)
    except ValueError:
        return None
    year = month = day = None
    for part in rel.parts:
        m = _YEARMONTH_RE.match(part)
        if m:
            year, month = m.group(1), m.group(2)
            continue
        m = _YEAR_RE.match(part)
        if m and not year:
            year = m.group(1)
            continue
        m = _MONTH_RE.match(part)
        if m and not month:
            month = m.group(1)
            continue
        m = _DAY_RE.match(part)
        if m and not day:
            day = m.group(1)
            continue
    if year and month and day:
        try:
            d = date(int(year), int(month), int(day))
        except ValueError:
            return None
        return d
    return None


def date_from_value(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        dt = _coerce_to_date(value)
        if dt:
            return dt.date() if isinstance(dt, datetime) else dt
    return None


def dest_subdir(d: date) -> Path:
    month = f"{d.month:02d} - {calendar.month_name[d.month]}"
    day = f"{d.day:02d} - {calendar.day_name[d.weekday()]}"
    return Path(f"{d.year:04d}") / month / day


# ---------------------------------------------------------------------------
# Job collection
# ---------------------------------------------------------------------------

def collect_jobs(source: Path) -> list[dict]:
    jobs = []
    for images_dir in source.rglob("_images"):
        if not images_dir.is_dir():
            continue
        parent = images_dir.parent
        sibling_mds = sorted(p for p in parent.glob("*.md") if p.is_file())

        # image.ext.md style (old): map by filename
        per_image_md: dict[str, Path] = {}
        for md in sibling_mds:
            stem = md.name[: -len(".md")]
            if Path(stem).suffix.lower() in IMAGE_EXTS:
                per_image_md[stem] = md

        # prompt md = sibling whose name matches the parent folder (old)
        prompt_md = None
        candidate = parent / f"{parent.name}.md"
        if candidate.exists():
            prompt_md = candidate

        # body-link md (new structure): the .md isn't named after the image
        body_link_md: dict[str, Path] = {}
        for md in sibling_mds:
            if md.name[: -len(".md")] == parent.name:
                continue
            stem = md.name[: -len(".md")]
            if Path(stem).suffix.lower() in IMAGE_EXTS:
                continue  # already handled via per_image_md
            for img_name in find_image_links(md):
                body_link_md.setdefault(img_name, md)

        parent_id = None
        # Old structure folders begin with a ULID-like ID followed by " - "
        m = re.match(r"^([0-9A-Z]{10,})\s*-\s*", parent.name)
        if m:
            parent_id = m.group(1)

        path_date = date_from_path(images_dir, source)

        for image_path in sorted(images_dir.iterdir()):
            if not image_path.is_file():
                continue
            if image_path.suffix.lower() not in IMAGE_EXTS:
                continue
            jobs.append({
                "image": image_path,
                "image_md": per_image_md.get(image_path.name)
                          or body_link_md.get(image_path.name),
                "prompt_md": prompt_md,
                "path_date": path_date,
                "parent_id": parent_id,
            })
    return jobs


# ---------------------------------------------------------------------------
# Sidecar building
# ---------------------------------------------------------------------------

NOISY_KEYS = {"cover", "datacards", "concept_override"}


def _serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items() if k not in NOISY_KEYS}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


def build_sidecar(job: dict):
    parent_meta = parse_frontmatter(job["prompt_md"]) if job["prompt_md"] else {}
    image_meta = parse_frontmatter(job["image_md"]) if job["image_md"] else {}

    # New-structure mds may have no frontmatter; pull from body sections.
    if job["image_md"] and not image_meta:
        image_meta = parse_body_metadata(job["image_md"])
    if job["prompt_md"] and not parent_meta:
        parent_meta = parse_body_metadata(job["prompt_md"])

    merged: dict = {}
    merged.update(parent_meta)
    merged.update(image_meta)  # image-level wins

    if "prompt" not in merged:
        for k in ("positive_prompt", "text_prompt"):
            if k in parent_meta:
                merged["prompt"] = parent_meta[k]
                break

    if "created" in merged and "created_at" not in merged:
        merged["created_at"] = merged.pop("created")
    elif "created" in merged:
        merged.pop("created")

    sidecar = _serialize(merged)
    out_date = job["path_date"] or date_from_value(merged.get("created_at"))
    return sidecar, out_date


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run(source: Path, dest: Path, dry_run: bool, overwrite: bool, limit: int | None):
    jobs = collect_jobs(source)
    print(f"discovered {len(jobs)} images under {source}")

    stats = {"copied": 0, "skipped_existing": 0, "no_date": 0, "no_md": 0, "errors": 0}

    for i, job in enumerate(jobs):
        if limit is not None and stats["copied"] >= limit:
            break
        try:
            sidecar, out_date = build_sidecar(job)
        except Exception as e:
            stats["errors"] += 1
            print(f"  ERR build {job['image']}: {e}", file=sys.stderr)
            continue

        if not out_date:
            stats["no_date"] += 1
            print(f"  SKIP no date: {job['image']}", file=sys.stderr)
            continue

        if not job["image_md"] and not job["prompt_md"]:
            stats["no_md"] += 1

        out_dir = dest / dest_subdir(out_date)
        out_image = out_dir / job["image"].name

        if out_image.exists() and not overwrite:
            if job["parent_id"]:
                alt = out_dir / f"{job['parent_id']}_{job['image'].name}"
                if not alt.exists():
                    out_image = alt
                else:
                    stats["skipped_existing"] += 1
                    continue
            else:
                stats["skipped_existing"] += 1
                continue

        if dry_run:
            print(f"DRY {job['image']} -> {out_image}")
            continue

        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(job["image"], out_image)
            json_path = out_image.with_name(out_image.name + ".json")
            json_path.write_text(json.dumps(sidecar, indent=2, default=str))
            stats["copied"] += 1
        except Exception as e:
            stats["errors"] += 1
            print(f"  ERR copy {job['image']}: {e}", file=sys.stderr)

    print(f"stats: {stats}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE,
                    help=f"Source vault root (default: {DEFAULT_SOURCE})")
    ap.add_argument("--dest", type=Path, default=DEFAULT_DEST,
                    help=f"Destination root (default: {DEFAULT_DEST})")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print planned copies without writing anything")
    ap.add_argument("--overwrite", action="store_true",
                    help="Overwrite existing files at destination")
    ap.add_argument("--limit", type=int, default=None,
                    help="Stop after copying N images (for testing)")
    args = ap.parse_args()
    run(args.source, args.dest, args.dry_run, args.overwrite, args.limit)


if __name__ == "__main__":
    main()
