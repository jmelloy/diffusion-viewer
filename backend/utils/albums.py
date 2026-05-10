"""Materialize legacy ``project:*`` tags into the new `albums` tables.

Idempotent. Designed to run on demand (CLI / one-off) or as part of a
post-scan hook. The legacy tags are *not* deleted — both the tag-based and
album-based projections of the same data coexist until callers are migrated.

A tag named ``project:<slug>`` becomes an :class:`Album` (slug = ``<slug>``).
A tag named ``project:<slug>:<role>:<value>`` becomes an :class:`AlbumRole`
row on that album. Tag parentage on ``project:<parent>:project:<child>`` (or
``project:<parent>:<child>`` patterns used by the existing organizer) is
preserved as ``Album.parent_album_id``.

Photos carrying any ``project:<slug>`` tag (or any of its descendants) are
linked into the corresponding album via ``album_photos``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

import models

logger = logging.getLogger(__name__)


PROJECT_PREFIX = "project:"


@dataclass
class MaterializeStats:
    albums_created: int = 0
    albums_updated: int = 0
    roles_created: int = 0
    photos_linked: int = 0


def _slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").title()


def _normalize_slug(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _parse_tag(name: str) -> Optional[Tuple[str, Optional[str], Optional[str]]]:
    """Parse a project tag name.

    Returns ``(slug, role, value)``:

    * ``project:<slug>`` → ``(slug, None, None)``
    * ``project:<slug>:<role>:<value>`` → ``(slug, role, value)``
    * anything else → ``None``
    """
    if not name.startswith(PROJECT_PREFIX):
        return None
    parts = name.split(":")
    # ["project", slug] → top-level project tag
    if len(parts) == 2 and parts[1]:
        return parts[1], None, None
    # ["project", slug, role, value, ...] → role tag
    if len(parts) >= 4 and parts[1] and parts[2] and parts[3]:
        role = parts[2]
        value = ":".join(parts[3:])
        return parts[1], role, value
    return None


def _descendant_tag_ids(db: Session, root_id: int) -> List[int]:
    anchor = (
        select(models.Tag.id)
        .where(models.Tag.id == root_id)
        .cte(name="alb_desc", recursive=True)
    )
    child = aliased(models.Tag)
    descendants = anchor.union(
        select(child.id).where(child.parent_tag_id == anchor.c.id)
    )
    return [r[0] for r in db.execute(select(descendants.c.id)).all()]


def materialize_project_tags(db: Session) -> MaterializeStats:
    """Walk all ``project:*`` tags and materialize them into albums + roles.

    Idempotent: re-running picks up new tags/photos and leaves existing
    `albums`/`album_roles` rows untouched if nothing changed.
    """
    stats = MaterializeStats()
    now = datetime.utcnow()

    project_tags: List[models.Tag] = (
        db.query(models.Tag)
        .filter(models.Tag.name.like(f"{PROJECT_PREFIX}%"))
        .all()
    )

    # Pass 1: create/update one Album per top-level `project:<slug>` tag.
    slug_to_album: Dict[str, models.Album] = {}
    top_level_tags: Dict[str, models.Tag] = {}
    for tag in project_tags:
        parsed = _parse_tag(tag.name)
        if not parsed:
            continue
        slug, role, _ = parsed
        if role is not None:
            continue
        top_level_tags[slug] = tag

        album = db.query(models.Album).filter(models.Album.slug == slug).first()
        if album is None:
            album = models.Album(
                slug=slug,
                name=_slug_to_name(slug),
                source_tag_id=tag.id,
            )
            db.add(album)
            db.flush()
            stats.albums_created += 1
        else:
            changed = False
            if album.source_tag_id != tag.id:
                album.source_tag_id = tag.id
                changed = True
            if album.deleted_at is not None:
                album.deleted_at = None
                changed = True
            if changed:
                album.updated_at = now
                stats.albums_updated += 1
        slug_to_album[slug] = album

    # Pass 2: parent hierarchy. If a top-level project tag is parented under
    # another project tag, mirror that on the album.
    for slug, tag in top_level_tags.items():
        album = slug_to_album[slug]
        parent_album_id: Optional[int] = None
        cursor = tag.parent
        depth = 0
        while cursor is not None and depth < 32:
            parsed = _parse_tag(cursor.name)
            if parsed and parsed[1] is None:
                parent_album = slug_to_album.get(parsed[0])
                if parent_album is not None and parent_album.id != album.id:
                    parent_album_id = parent_album.id
                break
            cursor = cursor.parent
            depth += 1
        if album.parent_album_id != parent_album_id:
            album.parent_album_id = parent_album_id
            album.updated_at = now
            stats.albums_updated += 1

    # Pass 3: roles. Each `project:<slug>:<role>:<value>` tag becomes an
    # AlbumRole row on the corresponding album.
    existing_roles: Set[Tuple[int, str, str]] = {
        (r.album_id, r.role, r.value)
        for r in db.query(models.AlbumRole).all()
    }
    for tag in project_tags:
        parsed = _parse_tag(tag.name)
        if not parsed:
            continue
        slug, role, value = parsed
        if role is None or value is None:
            continue
        album = slug_to_album.get(slug)
        if album is None:
            # Role tag references an unknown project; skip rather than guess.
            logger.debug("Skipping role tag with no parent album: %s", tag.name)
            continue
        key = (album.id, role, value)
        if key in existing_roles:
            continue
        db.add(models.AlbumRole(album_id=album.id, role=role, value=value))
        existing_roles.add(key)
        stats.roles_created += 1

    db.flush()

    # Pass 4: photo membership. For each album, find all images carrying any
    # descendant tag of its source `project:<slug>` tag, and insert any
    # missing `album_photos` rows.
    for slug, album in slug_to_album.items():
        if album.source_tag_id is None:
            continue
        descendant_ids = _descendant_tag_ids(db, album.source_tag_id)
        image_ids = [
            r[0]
            for r in db.execute(
                select(models.Image.id)
                .where(models.Image.tags.any(models.Tag.id.in_(descendant_ids)))
                .distinct()
            ).all()
        ]
        if not image_ids:
            continue
        existing_links: Set[int] = {
            r[0]
            for r in db.execute(
                select(models.AlbumPhoto.image_id).where(
                    models.AlbumPhoto.album_id == album.id
                )
            ).all()
        }
        for image_id in image_ids:
            if image_id in existing_links:
                continue
            db.add(models.AlbumPhoto(album_id=album.id, image_id=image_id))
            stats.photos_linked += 1

    db.commit()
    logger.info("materialize_project_tags: %s", stats)
    return stats
