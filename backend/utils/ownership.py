"""Ownership-visibility helpers.

Rows with `user_id IS NULL` (legacy data, watcher-created images, admin
script output) are visible to every authenticated user. Rows with a
non-null `user_id` are only visible to / mutable by that owner.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_

import models


def visible_image_filter(user: models.User):
    return or_(models.Image.user_id == user.id, models.Image.user_id.is_(None))


def visible_tag_filter(user: models.User):
    return or_(models.Tag.user_id == user.id, models.Tag.user_id.is_(None))


def user_can_mutate(owner_id: Optional[int], user: models.User) -> bool:
    return owner_id is None or owner_id == user.id


def require_image_access(img: Optional[models.Image], user: models.User) -> models.Image:
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    if not user_can_mutate(img.user_id, user):
        raise HTTPException(status_code=404, detail="Image not found")
    return img


def require_tag_access(tag: Optional[models.Tag], user: models.User) -> models.Tag:
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    if not user_can_mutate(tag.user_id, user):
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag
