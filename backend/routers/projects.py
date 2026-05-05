import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db

router = APIRouter(tags=["projects"])

VALID_ROLES = {"character", "scene", "background", "prop", "concept", "reference", "other"}


def slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").title()


def normalize_slug(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


@router.get("/api/projects", response_model=List[schemas.ProjectInfo])
def list_projects(db: Session = Depends(get_db)):
    tags = db.query(models.Tag).filter(models.Tag.name.like("project:%")).all()

    projects: dict[str, dict] = {}
    for tag in tags:
        parts = tag.name.split(":")
        # Only top-level project tags: "project:<slug>" (exactly 2 parts)
        if len(parts) == 2:
            slug = parts[1]
            count = len(tag.images)
            projects[slug] = {"slug": slug, "name": slug_to_name(slug), "image_count": count}

    return [schemas.ProjectInfo(**p) for p in projects.values()]


@router.get("/api/projects/{slug}", response_model=schemas.ProjectDetail)
def get_project(slug: str, db: Session = Depends(get_db)):
    project_tag = db.query(models.Tag).filter(models.Tag.name == f"project:{slug}").first()

    if not project_tag:
        raise HTTPException(status_code=404, detail="Project not found")

    images_in_project = list(project_tag.images)

    grouped: dict[str, list] = {role: [] for role in VALID_ROLES}

    for img in images_in_project:
        img_tag_names = {t.name for t in img.tags}
        img_roles = [role for role in VALID_ROLES if f"project:{slug}:{role}" in img_tag_names]
        if not img_roles:
            img_roles = ["other"]
        for role in img_roles:
            grouped[role].append(img)

    # Remove empty role buckets
    grouped = {k: v for k, v in grouped.items() if v}

    return schemas.ProjectDetail(
        slug=slug,
        name=slug_to_name(slug),
        image_count=len(images_in_project),
        roles=grouped,
    )


@router.post("/api/images/{image_id}/project", response_model=schemas.Image)
def assign_project(image_id: int, body: schemas.ProjectAssignRequest, db: Session = Depends(get_db)):
    img = db.query(models.Image).filter(models.Image.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")

    slug = normalize_slug(body.project)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid project name")

    tag_names = [f"project:{slug}"]
    for role in body.roles:
        role = role.strip().lower()
        if role in VALID_ROLES:
            tag_names.append(f"project:{slug}:{role}")

    for tag_name in tag_names:
        tag = db.query(models.Tag).filter(models.Tag.name == tag_name).first()
        if not tag:
            tag = models.Tag(name=tag_name)
            db.add(tag)
            db.flush()
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
        for role in body.roles:
            role = role.strip().lower()
            if role not in VALID_ROLES:
                continue
            tag = db.query(models.Tag).filter(models.Tag.name == f"project:{slug}:{role}").first()
            if tag and tag in img.tags:
                img.tags.remove(tag)
    else:
        to_remove = [
            t for t in img.tags
            if t.name == f"project:{slug}" or t.name.startswith(f"project:{slug}:")
        ]
        for tag in to_remove:
            img.tags.remove(tag)

    db.commit()
    db.refresh(img)
    return img
