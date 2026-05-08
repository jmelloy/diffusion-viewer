"""Replace bare project:clue:character / project:clue:scene tags with
value-specific role tags like project:clue:character:miss scarlett.

For each image carrying the bare role tag, look at its standalone tags
(suspects, weapons, rooms, scenes) and add a project:clue:<role>:<value>
tag for each match. Then delete the bare role tags entirely.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "backend" / "diffusion_viewer.db"

# 21 cards — assigned to the "character" role
CARDS = [
    "colonel mustard",
    "professor plum",
    "miss scarlett",
    "mrs peacock",
    "mrs white",
    "reverend green",
    "knife",
    "rope",
    "revolver",
    "candlestick",
    "wrench",
    "lead pipe",
    "hall",
    "study",
    "kitchen",
    "dining room",
    "ballroom",
    "library",
    "billiard room",
    "conservatory",
    "lounge",
]

# Locations — assigned to the "scene" role
SCENES = [
    "hall",
    "study",
    "kitchen",
    "dining room",
    "ballroom",
    "library",
    "billiard room",
    "conservatory",
    "lounge",
    "grand staircase",
    "clue mansion",
]


def ensure_tag(cur, name: str, parent_id: int | None) -> int:
    cur.execute("SELECT id FROM tags WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO tags (name, parent_tag_id) VALUES (?, ?)",
        (name, parent_id),
    )
    return cur.lastrowid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    project_id = ensure_tag(cur, "project:Clue", None)

    plans = [("character", CARDS), ("scene", SCENES)]
    for role, values in plans:
        bare_name = f"project:Clue:{role}"
        cur.execute("SELECT id FROM tags WHERE name = ?", (bare_name,))
        bare = cur.fetchone()
        if not bare:
            print(f"[skip] {bare_name}: no such tag")
            continue
        bare_id = bare[0]

        qmarks = ",".join("?" * len(values))
        cur.execute(
            f"""
            SELECT t.name, COUNT(DISTINCT it.image_id)
            FROM image_tags it
            JOIN tags t ON t.id = it.tag_id
            WHERE t.name IN ({qmarks})
              AND it.image_id IN (SELECT image_id FROM image_tags WHERE tag_id = ?)
            GROUP BY t.name
            ORDER BY 2 DESC
            """,
            (*values, bare_id),
        )
        breakdown = cur.fetchall()
        print(f"\n{role}: would create {len(breakdown)} value-tags")
        for name, n in breakdown:
            print(f"  project:Clue:{role}:{name.title()}  ({n} images)")

    if not args.execute:
        print("\nDry run.")
        return 0

    cur.execute("BEGIN")
    total_added = 0
    total_dropped_links = 0
    for role, values in plans:
        bare_name = f"project:clue:{role}"
        cur.execute("SELECT id FROM tags WHERE name = ?", (bare_name,))
        bare = cur.fetchone()
        if not bare:
            continue
        bare_id = bare[0]

        for value in values:
            cur.execute("SELECT id FROM tags WHERE name = ?", (value,))
            row = cur.fetchone()
            if not row:
                continue
            value_tag_id = row[0]

            # Images that have BOTH the bare role tag AND this value tag
            cur.execute(
                """
                SELECT DISTINCT a.image_id
                FROM image_tags a
                JOIN image_tags b ON a.image_id = b.image_id
                WHERE a.tag_id = ? AND b.tag_id = ?
                """,
                (bare_id, value_tag_id),
            )
            image_ids = [r[0] for r in cur.fetchall()]
            if not image_ids:
                continue

            new_tag_id = ensure_tag(cur, f"project:clue:{role}:{value}", project_id)
            cur.executemany(
                "INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                [(iid, new_tag_id) for iid in image_ids],
            )
            total_added += len(image_ids)

        # Drop the bare role tag entirely
        cur.execute("DELETE FROM image_tags WHERE tag_id = ?", (bare_id,))
        total_dropped_links += cur.rowcount
        cur.execute("DELETE FROM tags WHERE id = ?", (bare_id,))

    conn.commit()
    print(
        f"\nAdded {total_added} value-specific role links. "
        f"Removed {total_dropped_links} bare-role links + 2 bare role tags."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
