"""HTTP API for the photosafe-style ``albums`` tables.

Coexists with the legacy ``/api/projects`` routes (which read the
``project:<slug>`` tag convention directly). The materializer in
:mod:`utils.albums` keeps the two views in sync.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from utils.albums import (
    MaterializeStats,
    materialize_project_tags,
)

router = APIRouter(prefix="/api/albums", tags=["albums"])


def _normalize_slug(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").title()


def _album_by_slug(db: Session, slug: str, *, include_deleted: bool = False) -> models.Album:
    q = db.query(models.Album).filter(models.Album.slug == slug)
    if not include_deleted:
        q = q.filter(models.Album.deleted_at.is_(None))
    album = q.first()
    if album is None:
        raise HTTPException(status_code=404, detail=f"Album not found: {slug}")
    return album


def _to_info(
    db: Session,
    album: models.Album,
    *,
    image_count: Optional[int] = None,
    role_count: Optional[int] = None,
) -> schemas.AlbumInfo:
    if image_count is None:
        image_count = (
            db.query(func.count(models.AlbumPhoto.image_id))
            .filter(models.AlbumPhoto.album_id == album.id)
            .scalar()
            or 0
        )
    if role_count is None:
        role_count = (
            db.query(func.count(models.AlbumRole.id))
            .filter(models.AlbumRole.album_id == album.id)
            .scalar()
            or 0
        )
    parent_slug: Optional[str] = None
    if album.parent_album_id is not None:
        parent = (
            db.query(models.Album)
            .filter(models.Album.id == album.parent_album_id)
            .first()
        )
        if parent is not None:
            parent_slug = parent.slug
    return schemas.AlbumInfo(
        id=album.id,
        uuid=album.uuid,
        slug=album.slug,
        name=album.name,
        description=album.description,
        parent_album_id=album.parent_album_id,
        parent_slug=parent_slug,
        image_count=image_count,
        role_count=role_count,
        deleted_at=album.deleted_at,
    )


@router.get("", response_model=List[schemas.AlbumInfo])
def list_albums(
    parent_slug: Optional[str] = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(models.Album)
    if not include_deleted:
        q = q.filter(models.Album.deleted_at.is_(None))
    if parent_slug is not None:
        if parent_slug == "":
            q = q.filter(models.Album.parent_album_id.is_(None))
        else:
            parent = (
                db.query(models.Album).filter(models.Album.slug == parent_slug).first()
            )
            if parent is None:
                raise HTTPException(status_code=404, detail="Parent album not found")
            q = q.filter(models.Album.parent_album_id == parent.id)
    albums = q.order_by(models.Album.slug).all()

    # One pass for image counts so we don't N+1.
    counts: dict[int, int] = dict(
        db.execute(
            select(models.AlbumPhoto.album_id, func.count(models.AlbumPhoto.image_id))
            .where(models.AlbumPhoto.album_id.in_([a.id for a in albums] or [0]))
            .group_by(models.AlbumPhoto.album_id)
        ).all()
    )
    role_counts: dict[int, int] = dict(
        db.execute(
            select(models.AlbumRole.album_id, func.count(models.AlbumRole.id))
            .where(models.AlbumRole.album_id.in_([a.id for a in albums] or [0]))
            .group_by(models.AlbumRole.album_id)
        ).all()
    )
    return [
        _to_info(
            db,
            a,
            image_count=counts.get(a.id, 0),
            role_count=role_counts.get(a.id, 0),
        )
        for a in albums
    ]


@router.get("/{slug}", response_model=schemas.AlbumDetail)
def get_album(slug: str, db: Session = Depends(get_db)):
    album = _album_by_slug(db, slug)

    image_ids = [
        r[0]
        for r in db.execute(
            select(models.AlbumPhoto.image_id).where(
                models.AlbumPhoto.album_id == album.id
            )
        ).all()
    ]
    images = (
        db.query(models.Image)
        .filter(models.Image.id.in_(image_ids))
        .order_by(
            models.Image.rating.desc().nullslast(),
            models.Image.date_taken.desc().nullslast(),
        )
        .all()
        if image_ids
        else []
    )

    roles = (
        db.query(models.AlbumRole)
        .filter(models.AlbumRole.album_id == album.id)
        .order_by(models.AlbumRole.role, models.AlbumRole.value)
        .all()
    )

    children = (
        db.query(models.Album)
        .filter(
            models.Album.parent_album_id == album.id,
            models.Album.deleted_at.is_(None),
        )
        .order_by(models.Album.slug)
        .all()
    )

    info = _to_info(db, album, image_count=len(image_ids), role_count=len(roles))
    return schemas.AlbumDetail(
        **info.model_dump(),
        children=[_to_info(db, c) for c in children],
        roles=[schemas.AlbumRoleInfo.model_validate(r) for r in roles],
        images=images,
    )


@router.post("", response_model=schemas.AlbumInfo, status_code=201)
def create_album(body: schemas.AlbumCreate, db: Session = Depends(get_db)):
    slug = _normalize_slug(body.slug or body.name)
    if not slug:
        raise HTTPException(status_code=400, detail="Slug or name is required")
    existing = db.query(models.Album).filter(models.Album.slug == slug).first()
    if existing is not None:
        if existing.deleted_at is not None:
            existing.deleted_at = None
            existing.name = body.name or existing.name
            existing.description = body.description or existing.description
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return _to_info(db, existing)
        raise HTTPException(
            status_code=409, detail=f"Album already exists: {slug}"
        )

    parent_id: Optional[int] = None
    if body.parent_slug:
        parent = _album_by_slug(db, body.parent_slug)
        parent_id = parent.id

    album = models.Album(
        slug=slug,
        name=body.name,
        description=body.description,
        parent_album_id=parent_id,
    )
    db.add(album)
    db.commit()
    db.refresh(album)
    return _to_info(db, album, image_count=0, role_count=0)


@router.patch("/{slug}", response_model=schemas.AlbumInfo)
def update_album(
    slug: str, body: schemas.AlbumUpdate, db: Session = Depends(get_db)
):
    album = _album_by_slug(db, slug)
    if body.name is not None:
        album.name = body.name
    if body.description is not None:
        album.description = body.description
    if body.parent_slug is not None:
        if body.parent_slug == "":
            album.parent_album_id = None
        else:
            parent = _album_by_slug(db, body.parent_slug)
            if parent.id == album.id:
                raise HTTPException(
                    status_code=400, detail="An album cannot be its own parent"
                )
            album.parent_album_id = parent.id
    album.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(album)
    return _to_info(db, album)


@router.delete("/{slug}", response_model=schemas.AlbumInfo)
def delete_album(slug: str, db: Session = Depends(get_db)):
    album = _album_by_slug(db, slug)
    now = datetime.utcnow()
    album.deleted_at = now
    album.updated_at = now
    db.commit()
    db.refresh(album)
    return _to_info(db, album)


@router.post("/{slug}/photos", response_model=schemas.AlbumInfo)
def link_photos(
    slug: str,
    body: schemas.AlbumPhotoLinkRequest,
    db: Session = Depends(get_db),
):
    album = _album_by_slug(db, slug)
    if not body.image_ids:
        return _to_info(db, album)

    existing = {
        r[0]
        for r in db.execute(
            select(models.AlbumPhoto.image_id).where(
                models.AlbumPhoto.album_id == album.id,
                models.AlbumPhoto.image_id.in_(body.image_ids),
            )
        ).all()
    }
    valid_ids = {
        r[0]
        for r in db.execute(
            select(models.Image.id).where(models.Image.id.in_(body.image_ids))
        ).all()
    }
    for image_id in body.image_ids:
        if image_id in existing or image_id not in valid_ids:
            continue
        db.add(models.AlbumPhoto(album_id=album.id, image_id=image_id))
    album.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(album)
    return _to_info(db, album)


@router.delete("/{slug}/photos/{image_id}", response_model=schemas.AlbumInfo)
def unlink_photo(slug: str, image_id: int, db: Session = Depends(get_db)):
    album = _album_by_slug(db, slug)
    db.query(models.AlbumPhoto).filter(
        models.AlbumPhoto.album_id == album.id,
        models.AlbumPhoto.image_id == image_id,
    ).delete(synchronize_session=False)
    album.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(album)
    return _to_info(db, album)


@router.post("/{slug}/roles", response_model=schemas.AlbumRoleInfo, status_code=201)
def add_role(
    slug: str, body: schemas.AlbumRoleCreate, db: Session = Depends(get_db)
):
    album = _album_by_slug(db, slug)
    role = body.role.strip()
    value = body.value.strip()
    if not role or not value:
        raise HTTPException(status_code=400, detail="role and value are required")

    existing = (
        db.query(models.AlbumRole)
        .filter(
            models.AlbumRole.album_id == album.id,
            models.AlbumRole.role == role,
            models.AlbumRole.value == value,
        )
        .first()
    )
    if existing is not None:
        return schemas.AlbumRoleInfo.model_validate(existing)

    row = models.AlbumRole(album_id=album.id, role=role, value=value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return schemas.AlbumRoleInfo.model_validate(row)


@router.delete("/{slug}/roles/{role_id}", response_model=schemas.AlbumInfo)
def remove_role(slug: str, role_id: int, db: Session = Depends(get_db)):
    album = _album_by_slug(db, slug)
    deleted = (
        db.query(models.AlbumRole)
        .filter(
            models.AlbumRole.id == role_id,
            models.AlbumRole.album_id == album.id,
        )
        .delete(synchronize_session=False)
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Role not found on album")
    album.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(album)
    return _to_info(db, album)


@router.post("/sync", response_model=schemas.AlbumSyncStats)
def sync_from_project_tags(db: Session = Depends(get_db)):
    """Run the materializer that maps ``project:<slug>[:role:value]`` tags
    into ``albums`` / ``album_roles`` / ``album_photos``.

    Idempotent. Safe to call repeatedly (e.g. after a scan).
    """
    stats: MaterializeStats = materialize_project_tags(db)
    return schemas.AlbumSyncStats(
        albums_created=stats.albums_created,
        albums_updated=stats.albums_updated,
        roles_created=stats.roles_created,
        photos_linked=stats.photos_linked,
    )
