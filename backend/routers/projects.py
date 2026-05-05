import re
from collections import defaultdict
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

import models
import schemas
from database import get_db

router = APIRouter(tags=["projects"])


def slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").title()


def normalize_slug(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def _parse_role(tag_name: str, slug: str) -> tuple[str, str] | None:
    """Parse `project:<slug>:<role>:<value>` → (role, value); else None."""
    prefix = f"project:{slug}:"
    if not tag_name.startswith(prefix):
        return None
    rest = tag_name[len(prefix):]
    role, _, value = rest.partition(":")
    if not role or not value:
        return None
    return role, value


def _project_slug(tag_name: str) -> str | None:
    parts = tag_name.split(":")
    if len(parts) == 2 and parts[0] == "project":
        return parts[1]
    return None


def _descendant_tag_ids(db: Session, root_id: int) -> list[int]:
    anchor = (
        select(models.Tag.id)
        .where(models.Tag.id == root_id)
        .cte(name="proj_descendants", recursive=True)
    )
    child = aliased(models.Tag)
    descendants = anchor.union_all(
        select(child.id).where(child.parent_tag_id == anchor.c.id)
    )
    return [r[0] for r in db.execute(select(descendants.c.id)).all()]


def _parent_project_slug(db: Session, tag: models.Tag) -> str | None:
    cursor = tag.parent
    depth = 0
    while cursor is not None and depth < 32:
        slug = _project_slug(cursor.name)
        if slug:
            return slug
        cursor = cursor.parent
        depth += 1
    return None


@router.get("/api/projects", response_model=List[schemas.ProjectInfo])
def list_projects(db: Session = Depends(get_db)):
    project_tags = (
        db.query(models.Tag).filter(models.Tag.name.like("project:%")).all()
    )
    project_tags = [t for t in project_tags if _project_slug(t.name)]

    out = []
    for tag in project_tags:
        slug = _project_slug(tag.name)
        descendant_ids = _descendant_tag_ids(db, tag.id)
        image_count = (
            db.query(models.Image)
            .filter(models.Image.tags.any(models.Tag.id.in_(descendant_ids)))
            .count()
        )
        out.append(
            schemas.ProjectInfo(
                slug=slug,
                name=slug_to_name(slug),
                image_count=image_count,
                parent_slug=_parent_project_slug(db, tag),
            )
        )
    out.sort(key=lambda p: p.slug)
    return out


@router.get("/api/projects/{slug}", response_model=schemas.ProjectDetail)
def get_project(slug: str, db: Session = Depends(get_db)):
    project_tag = (
        db.query(models.Tag).filter(models.Tag.name == f"project:{slug}").first()
    )
    if not project_tag:
        raise HTTPException(status_code=404, detail="Project not found")

    descendant_ids = _descendant_tag_ids(db, project_tag.id)
    images = (
        db.query(models.Image)
        .filter(models.Image.tags.any(models.Tag.id.in_(descendant_ids)))
        .all()
    )

    # roles[role][value] = list[Image]; unroled images go in roles[""][""]
    roles: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for img in images:
        assigned = False
        for tag in img.tags:
            parsed = _parse_role(tag.name, slug)
            if parsed:
                role, value = parsed
                roles[role][value].append(img)
                assigned = True
        if not assigned:
            roles[""][""].append(img)

    children = []
    for child_tag in db.query(models.Tag).filter(
        models.Tag.parent_tag_id == project_tag.id
    ).all():
        child_slug = _project_slug(child_tag.name)
        if not child_slug:
            continue
        child_ids = _descendant_tag_ids(db, child_tag.id)
        child_count = (
            db.query(models.Image)
            .filter(models.Image.tags.any(models.Tag.id.in_(child_ids)))
            .count()
        )
        children.append(
            schemas.ProjectInfo(
                slug=child_slug,
                name=slug_to_name(child_slug),
                image_count=child_count,
                parent_slug=slug,
            )
        )
    children.sort(key=lambda p: p.slug)

    return schemas.ProjectDetail(
        slug=slug,
        name=slug_to_name(slug),
        image_count=len(images),
        parent_slug=_parent_project_slug(db, project_tag),
        children=children,
        roles={k: dict(v) for k, v in roles.items()},
    )


def _ensure_tag(db: Session, name: str, parent: models.Tag | None = None) -> models.Tag:
    tag = db.query(models.Tag).filter(models.Tag.name == name).first()
    if not tag:
        tag = models.Tag(name=name, parent_tag_id=parent.id if parent else None)
        db.add(tag)
        db.flush()
    return tag


@router.post("/api/images/{image_id}/project", response_model=schemas.Image)
def assign_project(image_id: int, body: schemas.ProjectAssignRequest, db: Session = Depends(get_db)):
    img = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    slug = normalize_slug(body.project)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid project name")

    project_tag = _ensure_tag(db, f"project:{slug}")
    if project_tag not in img.tags:
        img.tags.append(project_tag)

    for role, values in body.roles.items():
        role = role.strip().lower()
        if not role:
            continue
        for value in values:
            value = value.strip().lower()
            if not value:
                continue
            tag = _ensure_tag(db, f"project:{slug}:{role}:{value}", parent=project_tag)
            if tag not in img.tags:
                img.tags.append(tag)

    db.commit()
    db.refresh(img)
    return img


@router.delete("/api/images/{image_id}/project", response_model=schemas.Image)
def remove_project(image_id: int, body: schemas.ProjectRemoveRequest, db: Session = Depends(get_db)):
    img = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    slug = normalize_slug(body.project)

    if body.roles:
        for role, values in body.roles.items():
            role = role.strip().lower()
            for value in values:
                value = value.strip().lower()
                tag = db.query(models.Tag).filter(
                    models.Tag.name == f"project:{slug}:{role}:{value}"
                ).first()
                if tag and tag in img.tags:
                    img.tags.remove(tag)
    else:
        prefix = f"project:{slug}"
        to_remove = [
            t for t in img.tags
            if t.name == prefix or t.name.startswith(f"{prefix}:")
        ]
        for tag in to_remove:
            img.tags.remove(tag)

    db.commit()
    db.refresh(img)
    return img
