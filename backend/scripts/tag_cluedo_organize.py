"""Organize cluedo tags under suspect/weapon/room intermediate parents.

Creates 3 new tags under `cluedo` and re-parents the existing flat children.
Dry-run by default. Pass --execute to apply.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "backend" / "diffusion_viewer.db"

GROUPS: dict[str, list[str]] = {
    "cluedo suspect": [
        "colonel mustard", "professor plum", "miss scarlett",
        "mrs peacock", "mrs white", "reverend green",
    ],
    "cluedo weapon": [
        "knife", "rope", "revolver", "candlestick", "wrench", "lead pipe",
    ],
    "cluedo room": [
        "hall", "study", "kitchen", "dining room", "ballroom", "library",
        "billiard room", "conservatory", "lounge", "grand staircase",
    ],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    cur.execute("SELECT id FROM tags WHERE name = 'cluedo'")
    row = cur.fetchone()
    if not row:
        print("ERROR: cluedo tag not found", file=sys.stderr)
        return 1
    cluedo_id = row[0]

    plans = []
    for group_name, child_names in GROUPS.items():
        qmarks = ",".join("?" * len(child_names))
        cur.execute(
            f"SELECT name, id FROM tags WHERE name IN ({qmarks})", child_names
        )
        existing = dict(cur.fetchall())
        missing = [n for n in child_names if n not in existing]
        if missing:
            print(f"[warn] {group_name}: missing children {missing}", file=sys.stderr)
        plans.append((group_name, [(n, existing[n]) for n in child_names if n in existing]))

    print(f"{'group':<18} {'count':>5}  children")
    for group_name, children in plans:
        print(f"{group_name:<18} {len(children):>5}  {', '.join(n for n, _ in children)}")

    if not args.execute:
        print("\nDry run. Re-run with --execute to apply.")
        return 0

    cur.execute("BEGIN")
    for group_name, children in plans:
        cur.execute(
            "INSERT INTO tags (name, parent_tag_id) VALUES (?, ?)",
            (group_name, cluedo_id),
        )
        new_id = cur.lastrowid
        child_ids = [cid for _, cid in children]
        qmarks = ",".join("?" * len(child_ids))
        cur.execute(
            f"UPDATE tags SET parent_tag_id = ? WHERE id IN ({qmarks})",
            (new_id, *child_ids),
        )
        print(f"  {group_name} (id={new_id}): re-parented {cur.rowcount} children")
    conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
