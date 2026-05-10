"""add uuid, deleted_at, sidecar JSONB to images

Revision ID: 7a2c1f4e8b3d
Revises: d37fcb9f4a72
Create Date: 2026-05-10 00:00:00.000000

Photosafe-alignment migration. Adds:

* `images.uuid` — stable secondary identifier (canonical PK in the eventual
  photosafe merge).
* `images.deleted_at` — photosafe-style soft-delete tombstone, backfilled
  from the existing `hidden` flag.
* `images.sidecar` — structured JSON payload (JSONB on Postgres), backfilled
  from the existing `sidecar_data` TEXT column.

The legacy `sidecar_data` and `hidden` columns are kept for backward
compatibility; they will be dropped in a follow-up after readers are migrated.
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "7a2c1f4e8b3d"
down_revision: Union[str, Sequence[str], None] = "d37fcb9f4a72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    json_type = postgresql.JSONB() if is_postgres else sa.JSON()

    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.add_column(sa.Column("uuid", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("sidecar", json_type, nullable=True))

    # Backfill uuid for existing rows.
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        op.execute(
            "UPDATE images SET uuid = gen_random_uuid()::text WHERE uuid IS NULL"
        )
    else:
        connection = op.get_bind()
        rows = connection.execute(
            sa.text("SELECT id FROM images WHERE uuid IS NULL")
        ).fetchall()
        for (image_id,) in rows:
            connection.execute(
                sa.text("UPDATE images SET uuid = :u WHERE id = :i"),
                {"u": str(uuid.uuid4()), "i": image_id},
            )

    # Backfill deleted_at from the legacy `hidden` flag. Use updated_at as a
    # best-effort tombstone time; created_at as final fallback.
    op.execute(
        "UPDATE images "
        "SET deleted_at = COALESCE(updated_at, created_at) "
        "WHERE hidden = TRUE AND deleted_at IS NULL"
    )

    # Backfill sidecar JSONB from the legacy text column.
    if is_postgres:
        op.execute(
            "UPDATE images "
            "SET sidecar = sidecar_data::jsonb "
            "WHERE sidecar_data IS NOT NULL AND sidecar IS NULL"
        )
    else:
        # SQLite: sa.JSON stores JSON-as-text, so a straight copy is fine.
        op.execute(
            "UPDATE images "
            "SET sidecar = sidecar_data "
            "WHERE sidecar_data IS NOT NULL AND sidecar IS NULL"
        )

    # Lock down uuid: NOT NULL + unique index.
    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.alter_column("uuid", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_index("ix_images_uuid", ["uuid"], unique=True)
        batch_op.create_index("ix_images_deleted_at", ["deleted_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.drop_index("ix_images_deleted_at")
        batch_op.drop_index("ix_images_uuid")
        batch_op.drop_column("sidecar")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("uuid")
