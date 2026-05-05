"""Convert the cluedo tag tree into the project:clue convention.

1. Rename cluedo → project:clue and cluedo {mansion,suspect,weapon,room} → clue ...
2. Create project:clue:character (parented under project:clue for tree display)
3. Tag every image carrying a Clue card (6 suspects + 6 weapons + 9 rooms) with
   project:clue:character.

Dry-run by default. Pass --execute to apply.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "backend" / "diffusion_viewer.db"

RENAMES = [
    ("cluedo",         "project:clue"),
    ("cluedo mansion", "clue mansion"),
    ("cluedo suspect", "clue suspect"),
    ("cluedo weapon",  "clue weapon"),
    ("cluedo room",    "clue room"),
]

# The 21 canonical Clue cards (excluding grand staircase, which isn't a card)
SUSPECTS = ["colonel mustard", "professor plum", "miss scarlett",
            "mrs peacock", "mrs white", "reverend green"]
WEAPONS  = ["knife", "rope", "revolver", "candlestick", "wrench", "lead pipe"]
ROOMS    = ["hall", "study", "kitchen", "dining room", "ballroom",
            "library", "billiard room", "conservatory", "lounge"]
CARDS = SUSPECTS + WEAPONS + ROOMS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    qmarks = ",".join("?" * len(CARDS))
    cur.execute(
        f"""
        SELECT COUNT(DISTINCT image_id)
        FROM image_tags
        WHERE tag_id IN (SELECT id FROM tags WHERE name IN ({qmarks}))
        """,
        CARDS,
    )
    card_image_count = cur.fetchone()[0]

    print("Renames:")
    for old, new in RENAMES:
        cur.execute("SELECT id FROM tags WHERE name = ?", (old,))
        row = cur.fetchone()
        print(f"  {old:<20} → {new:<25} (id={row[0] if row else 'MISSING'})")

    print(f"\nNew tag: project:clue:character (parent=project:clue)")
    print(f"Will tag {card_image_count} images carrying any of the 21 Clue cards "
          f"with project:clue:character.")

    if not args.execute:
        print("\nDry run. Re-run with --execute to apply.")
        return 0

    cur.execute("BEGIN")

    for old, new in RENAMES:
        cur.execute("UPDATE tags SET name = ? WHERE name = ?", (new, old))
        if cur.rowcount != 1:
            conn.rollback()
            print(f"ERROR: rename {old} → {new} affected {cur.rowcount} rows", file=sys.stderr)
            return 1

    cur.execute("SELECT id FROM tags WHERE name = 'project:clue'")
    project_id = cur.fetchone()[0]

    cur.execute(
        f"""
        INSERT OR IGNORE INTO image_tags (image_id, tag_id)
        SELECT DISTINCT image_id, ?
        FROM image_tags
        WHERE tag_id IN (SELECT id FROM tags WHERE name IN ({qmarks}))
        """,
        (project_id, *CARDS),
    )
    project_tagged = cur.rowcount

    cur.execute(
        "INSERT INTO tags (name, parent_tag_id) VALUES (?, ?)",
        ("project:clue:character", project_id),
    )
    character_id = cur.lastrowid

    cur.execute(
        f"""
        INSERT OR IGNORE INTO image_tags (image_id, tag_id)
        SELECT DISTINCT image_id, ?
        FROM image_tags
        WHERE tag_id IN (SELECT id FROM tags WHERE name IN ({qmarks}))
        """,
        (character_id, *CARDS),
    )
    char_tagged = cur.rowcount

    conn.commit()
    print(f"\nRenamed {len(RENAMES)} tags.")
    print(f"Added project:clue to {project_tagged} card-tagged images "
          f"that didn't already have it.")
    print(f"Created project:clue:character (id={character_id}). "
          f"Tagged {char_tagged} images.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
