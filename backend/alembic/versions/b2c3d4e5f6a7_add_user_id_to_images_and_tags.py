"""add user_id to images and tags

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-09 20:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_images_user_id"), ["user_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_images_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("tags", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_tags_user_id"), ["user_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_tags_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("tags", schema=None) as batch_op:
        batch_op.drop_constraint("fk_tags_user_id_users", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_tags_user_id"))
        batch_op.drop_column("user_id")

    with op.batch_alter_table("images", schema=None) as batch_op:
        batch_op.drop_constraint("fk_images_user_id_users", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_images_user_id"))
        batch_op.drop_column("user_id")
