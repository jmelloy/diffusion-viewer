import math
import os
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import or_, and_, func, select
from sqlalchemy.orm import Session, aliased
from PIL import Image as PILImage

import models
import schemas
from database import get_db
from utils.scanner import scan_directory, create_thumbnail, THUMBNAIL_DIR
from utils.security import get_current_user

router = APIRouter(prefix="/api/images", tags=["images"])

# Sub-router for endpoints that must remain unauthenticated so browser
# <img> tags (which can't carry an Authorization header) keep working.
files_router = APIRouter(prefix="/api/images", tags=["images"])


def apply_filters(
    query, db: Session, q, tags, min_rating, show_hidden, date_from, date_to
):
    if not show_hidden:
        query = query.filter(models.Image.hidden == False)

    if min_rating is not None and min_rating > -999:
        query = query.filter(models.Image.rating >= min_rating)
    elif not show_hidden:
        # By default hide thumbs-down (rating == -1)
        query = query.filter(models.Image.rating > -1)

    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                models.Image.filename.ilike(like),
                models.Image.prompt.ilike(like),
                models.Image.description.ilike(like),
                models.Image.sidecar_data.ilike(like),
            )
        )

    if tags:
        for idx, tag_name in enumerate(tags):
            anchor = (
                select(models.Tag.id)
                .where(models.Tag.name == tag_name)
                .cte(name=f"tag_descendants_{idx}", recursive=True)
            )
            child = aliased(models.Tag)
            descendants = anchor.union(
                select(child.id).where(child.parent_tag_id == anchor.c.id)
            )
            query = query.filter(
                models.Image.tags.any(models.Tag.id.in_(select(descendants.c.id)))
            )

    if date_from:
        query = query.filter(models.Image.date_taken >= date_from)
    if date_to:
        query = query.filter(models.Image.date_taken <= date_to)

    return query


@router.get("", response_model=schemas.ImageListResponse)
def list_images(
    q: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(None),
    min_rating: int = Query(-999),
    show_hidden: bool = Query(False),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("date_taken"),
    sort_dir: str = Query("desc"),
    db: Session = Depends(get_db),
):
    from datetime import datetime, timedelta

    def parse_dt(s, end_of_day=False):
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            pass
        try:
            d = datetime.strptime(s, "%Y-%m-%d")
            # A bare date as date_to should be inclusive of the whole day.
            return d + timedelta(days=1) - timedelta(microseconds=1) if end_of_day else d
        except ValueError:
            return None

    date_from_dt = parse_dt(date_from)
    date_to_dt = parse_dt(date_to, end_of_day=True)

    query = db.query(models.Image)
    query = apply_filters(
        query, db, q, tags or [], min_rating, show_hidden, date_from_dt, date_to_dt
    )

    total = query.count()

    # In filtered views (search, tag search), default to ordering by rating desc
    # then date desc, so thumbs-up (rating=10) comes first, stars (2-6) next,
    # unrated, then thumbs-down (-1) last when shown. The explicit sort dropdown
    # in the gallery still wins when no filters are active.
    filtered = bool(q) or bool(tags)
    if filtered:
        query = query.order_by(
            models.Image.rating.desc().nullslast(),
            models.Image.date_taken.desc().nullslast(),
        )
    else:
        sort_column = {
            "date_taken": models.Image.date_taken,
            "created_at": models.Image.created_at,
            "rating": models.Image.rating,
            "filename": models.Image.filename,
        }.get(sort_by, models.Image.date_taken)

        if sort_dir == "asc":
            query = query.order_by(sort_column.asc().nullslast())
        else:
            query = query.order_by(sort_column.desc().nullslast())

    offset = (page - 1) * limit
    items = query.offset(offset).limit(limit).all()
    pages = math.ceil(total / limit) if total > 0 else 1

    return schemas.ImageListResponse(items=items, total=total, page=page, pages=pages)


@router.get("/dates", response_model=list)
def get_dates(db: Session = Depends(get_db)):
    results = (
        db.query(
            func.date(models.Image.date_taken).label("date"),
            func.count(models.Image.id).label("count"),
        )
        .filter(models.Image.date_taken != None)
        .filter(models.Image.hidden == False)
        .group_by(func.date(models.Image.date_taken))
        .order_by(func.date(models.Image.date_taken).desc())
        .all()
    )
    return [{"date": str(row.date), "count": row.count} for row in results]


@router.get("/{image_id}", response_model=schemas.Image)
def get_image(image_id: int, db: Session = Depends(get_db)):
    img = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    return img


@files_router.get("/{image_id}/file")
def serve_image_file(image_id: int, db: Session = Depends(get_db)):
    img = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    if not os.path.exists(img.filepath):
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(img.filepath)


@files_router.get("/{image_id}/thumbnail")
def serve_thumbnail(image_id: int, db: Session = Depends(get_db)):
    img = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    thumb_path = Path(img.thumbnail_path) if img.thumbnail_path else None
    if thumb_path and thumb_path.exists():
        return FileResponse(str(thumb_path), media_type="image/jpeg")

    # Fallback: generate thumbnail on demand
    if not os.path.exists(img.filepath):
        raise HTTPException(status_code=404, detail="Source file not found")

    THUMBNAIL_DIR.mkdir(exist_ok=True)
    thumb_name = f"{Path(img.filepath).stem}_{hash(img.filepath) & 0xFFFFFF:06x}.jpg"
    thumb_path = THUMBNAIL_DIR / thumb_name
    result = create_thumbnail(Path(img.filepath), thumb_path)
    if result:
        img.thumbnail_path = str(thumb_path)
        db.commit()
        return FileResponse(str(thumb_path), media_type="image/jpeg")

    # Last resort: serve original
    return FileResponse(img.filepath)


@router.put("/{image_id}/rating", response_model=schemas.Image)
def update_rating(
    image_id: int, rating_update: schemas.RatingUpdate, db: Session = Depends(get_db)
):
    img = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    img.rating = rating_update.rating
    if rating_update.rating == -1:
        img.hidden = True
    else:
        img.hidden = False
    from datetime import datetime

    img.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(img)
    return img


@router.post("/{image_id}/tags", response_model=schemas.Image)
def add_tags(
    image_id: int,
    body: schemas.TagsAddRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    img = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    for tag_name in body.tag_names:
        tag_name = tag_name.strip().lower()
        if not tag_name:
            continue
        tag = db.query(models.Tag).filter(models.Tag.name == tag_name).first()
        if not tag:
            tag = models.Tag(name=tag_name, user_id=current_user.id)
            db.add(tag)
            db.flush()
        if tag not in img.tags:
            img.tags.append(tag)

    db.commit()
    db.refresh(img)
    return img


@router.delete("/{image_id}/tags/{tag_name}", response_model=schemas.Image)
def remove_tag(image_id: int, tag_name: str, db: Session = Depends(get_db)):
    img = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    tag = db.query(models.Tag).filter(models.Tag.name == tag_name).first()
    if tag and tag in img.tags:
        img.tags.remove(tag)
        db.commit()
        db.refresh(img)
    return img


@router.post("/bulk-tag", response_model=dict)
def bulk_tag(
    body: schemas.BulkTagRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    images = db.query(models.Image).filter(models.Image.id.in_(body.image_ids)).all()
    tags = []
    for tag_name in body.tag_names:
        tag_name = tag_name.strip().lower()
        if not tag_name:
            continue
        tag = db.query(models.Tag).filter(models.Tag.name == tag_name).first()
        if not tag:
            tag = models.Tag(name=tag_name, user_id=current_user.id)
            db.add(tag)
            db.flush()
        tags.append(tag)

    for img in images:
        for tag in tags:
            if tag not in img.tags:
                img.tags.append(tag)

    db.commit()
    return {"tagged": len(images), "tags_added": len(tags)}


@router.post("/bulk-remove-tag", response_model=dict)
def bulk_remove_tag(body: schemas.BulkRemoveTagRequest, db: Session = Depends(get_db)):
    images = db.query(models.Image).filter(models.Image.id.in_(body.image_ids)).all()
    tag = db.query(models.Tag).filter(models.Tag.name == body.tag_name).first()
    if not tag:
        return {"untagged": 0}
    count = 0
    for img in images:
        if tag in img.tags:
            img.tags.remove(tag)
            count += 1
    db.commit()
    return {"untagged": count}


@router.post("/bulk-rating", response_model=dict)
def bulk_rating(body: schemas.BulkRatingRequest, db: Session = Depends(get_db)):
    from datetime import datetime

    images = db.query(models.Image).filter(models.Image.id.in_(body.image_ids)).all()
    for img in images:
        img.rating = body.rating
        img.hidden = body.rating == -1
        img.updated_at = datetime.utcnow()
    db.commit()
    return {"rated": len(images), "rating": body.rating}


@router.post("/scan", response_model=dict)
def scan(
    body: schemas.ScanRequest = schemas.ScanRequest(),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    import os

    directory = body.directory or os.environ.get("IMAGE_DIR")
    if not directory:
        raise HTTPException(
            status_code=400, detail="No directory specified and IMAGE_DIR is not set"
        )
    try:
        stats = scan_directory(db, directory, user_id=current_user.id)
        return stats
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")


@router.delete("/{image_id}", response_model=schemas.Image)
def delete_image(image_id: int, db: Session = Depends(get_db)):
    img = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    img.hidden = True
    from datetime import datetime

    img.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(img)
    return img
