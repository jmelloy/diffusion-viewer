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

DB = Path("/data/diffusion_viewer.db")


# The 21 canonical Clue cards (excluding grand staircase, which isn't a card)
SUSPECTS = [
    "colonel mustard",
    "professor plum",
    "miss scarlett",
    "mrs peacock",
    "mrs white",
    "reverend green",
]
WEAPONS = ["knife", "rope", "revolver", "candlestick", "wrench", "lead pipe"]
ROOMS = [
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
CARDS = SUSPECTS + WEAPONS + ROOMS
ROLES = {"suspect": SUSPECTS, "weapon": WEAPONS, "room": ROOMS}


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
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.execute("BEGIN")

    project_id = ensure_tag(cur, "project:Clue", None)

    qmarks = ",".join("?" for _ in CARDS)
    cur.execute(
        """select name, count(*) 
                from image_tags it join tags t on it.tag_id = t.id where t.name in ({}) 
                group by name
                order by count(*) desc""".format(",".join("?" * len(CARDS + ["clue"]))),
        CARDS + ["clue"],
    )
    counts = {row[0]: row[1] for row in cur.fetchall()}
    print("Card counts (via standalone tags):")
    for card in CARDS:
        print(f"  {card}: {counts.get(card, 0)}")

    cur.execute(
        f"""
            INSERT OR IGNORE INTO image_tags (image_id, tag_id)
            SELECT DISTINCT image_id, ?
            FROM image_tags
            WHERE tag_id IN (SELECT id FROM tags WHERE name IN ({qmarks}))
            """,
        (project_id, *CARDS),
    )

    for role, cards in ROLES.items():
        for card in cards:
            tag = f"project:Clue:{role}:{card.title()}"
            tag_id = ensure_tag(cur, tag, project_id)

            cur.execute(
                """
                INSERT OR IGNORE INTO image_tags (image_id, tag_id)
                SELECT DISTINCT image_id, ?
                FROM image_tags
                WHERE tag_id IN (SELECT id FROM tags WHERE name = ?))
                """,
                (tag_id, card),
            )
            rs = cur.execute("SELECT changes()").fetchone()
            print(f"  {tag}: added {rs[0]} new image associations")
    if args.execute:
        print("\nApplied changes to the database.")
        conn.commit()
    else:
        print("\nDry run complete. No changes were made to the database.")
        conn.rollback()


if __name__ == "__main__":
    sys.exit(main())
