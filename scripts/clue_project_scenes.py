"""Add project:clue:scene role to images carrying any room/location tag."""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "backend" / "diffusion_viewer.db"

SCENES = [
    "hall", "study", "kitchen", "dining room", "ballroom",
    "library", "billiard room", "conservatory", "lounge",
    "grand staircase", "clue mansion",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    qmarks = ",".join("?" * len(SCENES))
    cur.execute(
        f"""
        SELECT COUNT(DISTINCT image_id) FROM image_tags
        WHERE tag_id IN (SELECT id FROM tags WHERE name IN ({qmarks}))
        """,
        SCENES,
    )
    n = cur.fetchone()[0]
    print(f"Will tag {n} images with project:clue:scene.")

    if not args.execute:
        print("Dry run.")
        return 0

    cur.execute("SELECT id FROM tags WHERE name = 'project:clue'")
    project_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO tags (name, parent_tag_id) VALUES (?, ?)",
        ("project:clue:scene", project_id),
    )
    scene_id = cur.lastrowid

    cur.execute(
        f"""
        INSERT OR IGNORE INTO image_tags (image_id, tag_id)
        SELECT DISTINCT image_id, ?
        FROM image_tags
        WHERE tag_id IN (SELECT id FROM tags WHERE name IN ({qmarks}))
        """,
        (scene_id, *SCENES),
    )
    tagged = cur.rowcount
    cur.execute(
        f"""
        INSERT OR IGNORE INTO image_tags (image_id, tag_id)
        SELECT DISTINCT image_id, ?
        FROM image_tags
        WHERE tag_id IN (SELECT id FROM tags WHERE name IN ({qmarks}))
        """,
        (project_id, *SCENES),
    )
    proj_tagged = cur.rowcount

    conn.commit()
    print(f"Created project:clue:scene (id={scene_id}). Tagged {tagged} images.")
    print(f"Added project:clue to {proj_tagged} additional scene-tagged images.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
