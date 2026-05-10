"""add albums, album_photos, album_roles

Revision ID: 9b4f3e7d8a2c
Revises: 7a2c1f4e8b3d
Create Date: 2026-05-10 00:00:00.000000

Photosafe-alignment migration. Introduces a first-class ``albums`` concept
alongside the existing ``project:<slug>[:role:value]`` tag convention so the
two can coexist while callers migrate.

The legacy `project:*` tags are not removed by this migration. A separate
materializer (`utils.albums.materialize_project_tags`) backfills `albums`
from those tags and can be run idempotently.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b4f3e7d8a2c"
down_revision: Union[str, Sequence[str], None] = "7a2c1f4e8b3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "albums",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("uuid", sa.String(length=36), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_album_id", sa.Integer(), nullable=True),
        sa.Column("source_tag_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_album_id"], ["albums.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["source_tag_id"], ["tags.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("albums", schema=None) as batch_op:
        batch_op.create_index("ix_albums_uuid", ["uuid"], unique=True)
        batch_op.create_index("ix_albums_slug", ["slug"], unique=True)
        batch_op.create_index(
            "ix_albums_parent_album_id", ["parent_album_id"], unique=False
        )
        batch_op.create_index(
            "ix_albums_source_tag_id", ["source_tag_id"], unique=False
        )

    op.create_table(
        "album_photos",
        sa.Column("album_id", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("added_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["album_id"], ["albums.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("album_id", "image_id"),
    )

    op.create_table(
        "album_roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("album_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["album_id"], ["albums.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "album_id", "role", "value", name="uq_album_roles_album_role_value"
        ),
    )
    with op.batch_alter_table("album_roles", schema=None) as batch_op:
        batch_op.create_index(
            "ix_album_roles_album_id", ["album_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("album_roles", schema=None) as batch_op:
        batch_op.drop_index("ix_album_roles_album_id")
    op.drop_table("album_roles")
    op.drop_table("album_photos")
    with op.batch_alter_table("albums", schema=None) as batch_op:
        batch_op.drop_index("ix_albums_source_tag_id")
        batch_op.drop_index("ix_albums_parent_album_id")
        batch_op.drop_index("ix_albums_slug")
        batch_op.drop_index("ix_albums_uuid")
    op.drop_table("albums")
