#!/usr/bin/env python3
"""
Migrate data from a SQLite database to the PostgreSQL database.

Usage:
    python sqlite_to_postgres.py --sqlite /path/to/old.db [--postgres-url postgresql+psycopg2://...]

The script:
1. Reads all rows from SQLite (images, tags, image_tags)
2. Runs alembic migrations on the target Postgres DB (creates schema if needed)
3. Inserts data, preserving original IDs and restarting sequences afterward
"""

import argparse
import os
import sys

import sqlalchemy as sa
from sqlalchemy import text


POSTGRES_URL_DEFAULT = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://diffusion:diffusion@localhost:5432/diffusion_viewer",
)


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "n", "off", ""}:
            return False
    return bool(value)


def migrate(sqlite_path: str, postgres_url: str, dry_run: bool = False) -> None:
    print(f"Source SQLite : {sqlite_path}")
    print(f"Target Postgres: {postgres_url}")

    sqlite_engine = sa.create_engine(f"sqlite:///{sqlite_path}")
    pg_engine = sa.create_engine(postgres_url, pool_pre_ping=True)

    with sqlite_engine.connect() as src, pg_engine.connect() as dst:
        # ------------------------------------------------------------------ #
        # Tags (must come before images due to self-referential FK, and       #
        # before image_tags)                                                   #
        # ------------------------------------------------------------------ #
        tags = src.execute(text("SELECT id, name, parent_tag_id FROM tags")).fetchall()
        print(f"Found {len(tags)} tags")

        # Insert tags without parent first (two-pass to handle self-ref FK)
        tags_no_parent = [t for t in tags if t.parent_tag_id is None]
        tags_with_parent = [t for t in tags if t.parent_tag_id is not None]

        if not dry_run:
            if tags_no_parent:
                dst.execute(
                    text(
                        "INSERT INTO tags (id, name, parent_tag_id) VALUES (:id, :name, :parent_tag_id) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    [dict(t._mapping) for t in tags_no_parent],
                )
            if tags_with_parent:
                dst.execute(
                    text(
                        "INSERT INTO tags (id, name, parent_tag_id) VALUES (:id, :name, :parent_tag_id) "
                        "ON CONFLICT (id) DO NOTHING"
                    ),
                    [dict(t._mapping) for t in tags_with_parent],
                )
            print(f"  Inserted {len(tags)} tags")

        # ------------------------------------------------------------------ #
        # Images                                                               #
        # ------------------------------------------------------------------ #
        images = src.execute(
            text(
                "SELECT id, filename, filepath, directory, width, height, file_size, "
                "date_taken, created_at, updated_at, rating, hidden, sidecar_data, "
                "prompt, description, model, thumbnail_path FROM images"
            )
        ).fetchall()
        print(f"Found {len(images)} images")

        if not dry_run and images:
            image_payload = []
            for row in images:
                payload_row = dict(row._mapping)
                payload_row["hidden"] = _to_bool(payload_row.get("hidden"))
                image_payload.append(payload_row)

            dst.execute(
                text(
                    "INSERT INTO images (id, filename, filepath, directory, width, height, "
                    "file_size, date_taken, created_at, updated_at, rating, hidden, "
                    "sidecar_data, prompt, description, model, thumbnail_path) "
                    "VALUES (:id, :filename, :filepath, :directory, :width, :height, "
                    ":file_size, :date_taken, :created_at, :updated_at, :rating, :hidden, "
                    ":sidecar_data, :prompt, :description, :model, :thumbnail_path) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                image_payload,
            )
            print(f"  Inserted {len(images)} images")

        # ------------------------------------------------------------------ #
        # image_tags                                                           #
        # ------------------------------------------------------------------ #
        image_tags = src.execute(
            text("SELECT image_id, tag_id FROM image_tags")
        ).fetchall()
        print(f"Found {len(image_tags)} image_tag rows")

        if not dry_run and image_tags:
            dst.execute(
                text(
                    "INSERT INTO image_tags (image_id, tag_id) VALUES (:image_id, :tag_id) "
                    "ON CONFLICT DO NOTHING"
                ),
                [dict(r._mapping) for r in image_tags],
            )
            print(f"  Inserted {len(image_tags)} image_tag rows")

        # ------------------------------------------------------------------ #
        # Reset sequences so new inserts get correct IDs                      #
        # ------------------------------------------------------------------ #
        if not dry_run:
            for table, col in [("images", "id"), ("tags", "id")]:
                dst.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), "
                        f"COALESCE((SELECT MAX({col}) FROM {table}), 1))"
                    )
                )
            print("Sequences reset")

        if not dry_run:
            dst.commit()
            print("Committed.")
        else:
            print("Dry run — no changes written.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite → PostgreSQL")
    parser.add_argument(
        "--sqlite",
        required=True,
        help="Path to the source SQLite database file",
    )
    parser.add_argument(
        "--postgres-url",
        default=POSTGRES_URL_DEFAULT,
        help="SQLAlchemy URL for the target PostgreSQL database (defaults to DATABASE_URL env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read from SQLite and print counts without writing to Postgres",
    )
    args = parser.parse_args()

    if not os.path.exists(args.sqlite):
        print(f"ERROR: SQLite file not found: {args.sqlite}", file=sys.stderr)
        sys.exit(1)

    migrate(args.sqlite, args.postgres_url, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
