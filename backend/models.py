from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlmodel import Field, Relationship, SQLModel


class ImageTag(SQLModel, table=True):
    __tablename__ = "image_tags"

    image_id: Optional[int] = Field(
        default=None, foreign_key="images.id", primary_key=True
    )
    tag_id: Optional[int] = Field(default=None, foreign_key="tags.id", primary_key=True)


# Backwards-compatible alias for code that operated on the raw association table.
image_tags = ImageTag.__table__


class Image(SQLModel, table=True):
    __tablename__ = "images"

    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    filename: str = Field(nullable=False)
    filepath: str = Field(unique=True, nullable=False)
    directory: str = Field(nullable=False)
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    date_taken: Optional[datetime] = None
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(
        sa_column=Column(
            DateTime,
            default=datetime.utcnow,
            onupdate=datetime.utcnow,
        )
    )
    rating: int = Field(default=0)
    hidden: bool = Field(default=False)
    sidecar_data: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    prompt: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    description: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    model: Optional[str] = None
    thumbnail_path: Optional[str] = None

    tags: List["Tag"] = Relationship(
        back_populates="images",
        link_model=ImageTag,
    )


class Tag(SQLModel, table=True):
    __tablename__ = "tags"

    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    name: str = Field(unique=True, nullable=False, index=True)
    parent_tag_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("tags.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )

    images: List[Image] = Relationship(
        back_populates="tags",
        link_model=ImageTag,
    )
    parent: Optional["Tag"] = Relationship(
        back_populates="children",
        sa_relationship_kwargs={"remote_side": "Tag.id"},
    )
    children: List["Tag"] = Relationship(
        back_populates="parent",
    )
