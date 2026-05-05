"""Replace project:clue:character:* and project:clue:scene:* with the
real Clue roles: suspect, weapon, room.

clue mansion and grand staircase don't fit any of the three — they stay
as standalone tags and land in the project's "(no role)" bucket.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "backend" / "diffusion_viewer.db"

GROUPS: dict[str, list[str]] = {
    "suspect": ["colonel mustard", "professor plum", "miss scarlett",
                "mrs peacock", "mrs white", "reverend green"],
    "weapon":  ["knife", "rope", "revolver", "candlestick", "wrench", "lead pipe"],
    "room":    ["hall", "study", "kitchen", "dining room", "ballroom",
                "library", "billiard room", "conservatory", "lounge"],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT id FROM tags WHERE name = 'project:clue'")
    project_id = cur.fetchone()[0]

    cur.execute(
        "SELECT id, name FROM tags WHERE name LIKE 'project:clue:character:%' OR name LIKE 'project:clue:scene:%'"
    )
    stale = cur.fetchall()
    print(f"Will delete {len(stale)} stale role-value tags (character:* / scene:*)")

    plans = []
    for role, values in GROUPS.items():
        for value in values:
            cur.execute("SELECT id FROM tags WHERE name = ?", (value,))
            row = cur.fetchone()
            if not row:
                continue
            value_tag_id = row[0]
            cur.execute(
                "SELECT COUNT(*) FROM image_tags WHERE tag_id = ?", (value_tag_id,)
            )
            n = cur.fetchone()[0]
            plans.append((role, value, value_tag_id, n))
            print(f"  project:clue:{role}:{value}  ← {n} images via standalone tag")

    if not args.execute:
        print("\nDry run.")
        return 0

    cur.execute("BEGIN")

    stale_ids = [r[0] for r in stale]
    if stale_ids:
        qmarks = ",".join("?" * len(stale_ids))
        cur.execute(f"DELETE FROM image_tags WHERE tag_id IN ({qmarks})", stale_ids)
        cur.execute(f"DELETE FROM tags WHERE id IN ({qmarks})", stale_ids)

    total_added = 0
    for role, value, value_tag_id, _ in plans:
        new_name = f"project:clue:{role}:{value}"
        cur.execute("SELECT id FROM tags WHERE name = ?", (new_name,))
        row = cur.fetchone()
        if row:
            new_id = row[0]
        else:
            cur.execute(
                "INSERT INTO tags (name, parent_tag_id) VALUES (?, ?)",
                (new_name, project_id),
            )
            new_id = cur.lastrowid

        cur.execute(
            """
            INSERT OR IGNORE INTO image_tags (image_id, tag_id)
            SELECT image_id, ? FROM image_tags WHERE tag_id = ?
            """,
            (new_id, value_tag_id),
        )
        total_added += cur.rowcount

    conn.commit()
    print(f"\nDeleted {len(stale_ids)} stale tags. "
          f"Added {total_added} new role-value links.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
