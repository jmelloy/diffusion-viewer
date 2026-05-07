from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

import models
import schemas
from database import get_db
from utils.hierarchy import recompute_parents

router = APIRouter(prefix="/api/tags", tags=["tags"])


def _build_path(tag: models.Tag) -> str:
    parts = [tag.name]
    cursor = tag.parent
    depth = 0
    while cursor is not None and depth < 32:
        parts.append(cursor.name)
        cursor = cursor.parent
        depth += 1
    return " / ".join(reversed(parts))


def _serialize(tag: models.Tag) -> schemas.Tag:
    return schemas.Tag(
        id=tag.id,
        name=tag.name,
        image_count=len(tag.images),
        parent_tag_id=tag.parent_tag_id,
        parent_name=tag.parent.name if tag.parent else None,
        path=_build_path(tag),
    )


def _is_descendant_of(tag: models.Tag, ancestor_id: int) -> bool:
    """Walk up from `tag` and return True if `ancestor_id` appears in its parent chain."""
    cursor = tag.parent
    depth = 0
    while cursor is not None and depth < 32:
        if cursor.id == ancestor_id:
            return True
        cursor = cursor.parent
        depth += 1
    return False


def _validate_parent_assignment(tag: models.Tag, parent_id: int | None, db: Session) -> models.Tag | None:
    if parent_id is None:
        return None
    if parent_id == tag.id:
        raise HTTPException(status_code=400, detail="Tag cannot be its own parent")
    parent = db.query(models.Tag).filter(models.Tag.id == parent_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent tag not found")
    if _is_descendant_of(parent, tag.id):
        raise HTTPException(status_code=400, detail="Would create a cycle")
    return parent


def _merge_into(source: models.Tag, target: models.Tag, db: Session) -> None:
    """Merge `source` tag into `target`: move images and children, then delete source."""
    if source.id == target.id:
        raise HTTPException(status_code=400, detail="Cannot merge a tag into itself")
    # Reject if target is a descendant of source — that would orphan the
    # subtree once source is deleted; user should reparent first.
    if _is_descendant_of(target, source.id):
        raise HTTPException(
            status_code=400,
            detail=f'Target "{target.name}" is a descendant of "{source.name}"; reparent first',
        )

    target_image_ids = {img.id for img in target.images}
    for img in list(source.images):
        if img.id not in target_image_ids:
            img.tags.append(target)
        img.tags.remove(source)

    for child in list(source.children):
        child.parent_tag_id = target.id

    db.delete(source)


# --- Static / collection endpoints (declared before /{tag_id} to avoid any
# router ambiguity with path parameters) -------------------------------------


@router.get("", response_model=List[schemas.Tag])
def list_tags(db: Session = Depends(get_db)):
    tags = db.query(models.Tag).all()
    return [_serialize(t) for t in tags]


@router.post("/merge", response_model=schemas.Tag)
def merge_tags(body: schemas.TagMergeRequest, db: Session = Depends(get_db)):
    """Merge source tag into target tag.

    All images tagged with source are tagged with target (unless already), all
    children of source are reparented to target, and source is deleted.
    """
    source = db.query(models.Tag).filter(models.Tag.id == body.source_tag_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source tag not found")
    target = db.query(models.Tag).filter(models.Tag.id == body.target_tag_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target tag not found")
    _merge_into(source, target, db)
    db.commit()
    db.refresh(target)
    return _serialize(target)


@router.post("/bulk-merge", response_model=dict)
def bulk_merge_tags(body: schemas.TagBulkMergeRequest, db: Session = Depends(get_db)):
    """Merge each tag in `source_tag_ids` into `target_tag_id`."""
    target = db.query(models.Tag).filter(models.Tag.id == body.target_tag_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target tag not found")

    source_ids = [sid for sid in body.source_tag_ids if sid != body.target_tag_id]
    if not source_ids:
        return {"merged": 0, "target_tag_id": target.id}

    sources = db.query(models.Tag).filter(models.Tag.id.in_(source_ids)).all()
    found_ids = {s.id for s in sources}
    missing = [sid for sid in source_ids if sid not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Source tag(s) not found: {missing}")

    # Order so that ancestors are merged after their descendants (process
    # leaves first); otherwise reparenting children mid-loop can shift the
    # tree under us. A simple DFS depth ranking is sufficient for sane trees.
    def depth(tag: models.Tag) -> int:
        d, cursor, seen = 0, tag.parent, set()
        while cursor is not None and cursor.id not in seen and d < 64:
            seen.add(cursor.id)
            cursor = cursor.parent
            d += 1
        return d

    sources.sort(key=depth, reverse=True)

    for src in sources:
        _merge_into(src, target, db)

    db.commit()
    db.refresh(target)
    return {"merged": len(sources), "target_tag_id": target.id}


@router.post("/bulk-delete", response_model=dict)
def bulk_delete_tags(body: schemas.TagBulkDeleteRequest, db: Session = Depends(get_db)):
    if not body.tag_ids:
        return {"deleted": 0}
    tags = db.query(models.Tag).filter(models.Tag.id.in_(body.tag_ids)).all()
    for tag in tags:
        db.delete(tag)
    db.commit()
    return {"deleted": len(tags)}


@router.post("/bulk-parent", response_model=dict)
def bulk_set_parent(body: schemas.TagBulkParentRequest, db: Session = Depends(get_db)):
    """Set the same parent on every tag in `tag_ids`. Pass parent_tag_id=null to clear."""
    if not body.tag_ids:
        return {"updated": 0}

    tags = db.query(models.Tag).filter(models.Tag.id.in_(body.tag_ids)).all()
    found_ids = {t.id for t in tags}
    missing = [tid for tid in body.tag_ids if tid not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Tag(s) not found: {missing}")

    if body.parent_tag_id is not None and body.parent_tag_id in found_ids:
        raise HTTPException(status_code=400, detail="Cannot set a selected tag as the parent of itself")

    for tag in tags:
        _validate_parent_assignment(tag, body.parent_tag_id, db)
        tag.parent_tag_id = body.parent_tag_id

    db.commit()
    return {"updated": len(tags), "parent_tag_id": body.parent_tag_id}


@router.post("/recompute-parents", response_model=dict)
def trigger_recompute_parents(db: Session = Depends(get_db)):
    return recompute_parents(db)


@router.get("/images/{image_id}/tags", response_model=List[schemas.Tag])
def get_image_tags(image_id: int, db: Session = Depends(get_db)):
    img = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    return [_serialize(t) for t in img.tags]


# --- Per-tag endpoints (path parameter routes declared last) ---------------


@router.delete("/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    tag = db.query(models.Tag).filter(models.Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    db.delete(tag)
    db.commit()
    return {"deleted": tag_id}


@router.put("/{tag_id}/parent", response_model=schemas.Tag)
def set_tag_parent(tag_id: int, body: schemas.TagParentUpdate, db: Session = Depends(get_db)):
    tag = db.query(models.Tag).filter(models.Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    _validate_parent_assignment(tag, body.parent_tag_id, db)
    tag.parent_tag_id = body.parent_tag_id
    db.commit()
    db.refresh(tag)
    return _serialize(tag)
