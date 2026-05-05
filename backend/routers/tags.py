from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List

import models
import schemas
from database import get_db
from utils.hierarchy import recompute_parents

router = APIRouter(prefix="/api/tags", tags=["tags"])


def _serialize(tag: models.Tag) -> schemas.Tag:
    return schemas.Tag(
        id=tag.id,
        name=tag.name,
        image_count=len(tag.images),
        parent_tag_id=tag.parent_tag_id,
        parent_name=tag.parent.name if tag.parent else None,
    )


@router.get("", response_model=List[schemas.Tag])
def list_tags(db: Session = Depends(get_db)):
    tags = db.query(models.Tag).all()
    return [_serialize(t) for t in tags]


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
    if body.parent_tag_id is not None:
        if body.parent_tag_id == tag_id:
            raise HTTPException(status_code=400, detail="Tag cannot be its own parent")
        parent = db.query(models.Tag).filter(models.Tag.id == body.parent_tag_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent tag not found")
        # Walk up from the proposed parent to detect cycles
        cursor = parent
        depth = 0
        while cursor is not None and depth < 32:
            if cursor.id == tag_id:
                raise HTTPException(status_code=400, detail="Would create a cycle")
            cursor = cursor.parent
            depth += 1
    tag.parent_tag_id = body.parent_tag_id
    db.commit()
    db.refresh(tag)
    return _serialize(tag)


@router.post("/recompute-parents", response_model=dict)
def trigger_recompute_parents(db: Session = Depends(get_db)):
    return recompute_parents(db)


@router.get("/images/{image_id}/tags", response_model=List[schemas.Tag])
def get_image_tags(image_id: int, db: Session = Depends(get_db)):
    img = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    return [_serialize(t) for t in img.tags]
