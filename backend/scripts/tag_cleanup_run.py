"""Apply the tag cleanup candidate list.

Reads scripts/tag_cleanup_candidates.txt — every non-blank, non-comment line
whose first column is a tag id is treated as a deletion target. Also removes
any zero-use, no-children "leaf" tags by name (the trailing list in the
candidates file is documentation; the names are baked in here).

Dry-run by default. Pass --execute to actually delete.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "backend" / "diffusion_viewer.db"
CANDIDATES = ROOT / "scripts" / "tag_cleanup_candidates.txt"

ZERO_USE_LEAVES: list[str] = []


def parse_ids(path: Path) -> list[int]:
    ids = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        first = s.split("\t", 1)[0].split(None, 1)[0]
        if first.isdigit():
            ids.append(int(first))
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="actually delete (default: dry run)")
    args = ap.parse_args()

    ids_from_file = parse_ids(CANDIDATES)
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    placeholders = ",".join("?" * len(ZERO_USE_LEAVES))
    cur.execute(
        f"SELECT id FROM tags WHERE name IN ({placeholders})", ZERO_USE_LEAVES
    )
    ids_from_leaves = [r[0] for r in cur.fetchall()]

    target_ids = sorted(set(ids_from_file) | set(ids_from_leaves))
    if not target_ids:
        print("No targets.", file=sys.stderr)
        return 1

    qmarks = ",".join("?" * len(target_ids))
    cur.execute(
        f"""
        SELECT t.id, t.name, COALESCE(p.name, ''),
               (SELECT COUNT(*) FROM image_tags it WHERE it.tag_id = t.id),
               (SELECT COUNT(*) FROM tags ch WHERE ch.parent_tag_id = t.id)
        FROM tags t LEFT JOIN tags p ON p.id = t.parent_tag_id
        WHERE t.id IN ({qmarks})
        ORDER BY t.name
        """,
        target_ids,
    )
    rows = cur.fetchall()

    total_links = sum(r[3] for r in rows)
    total_orphan_kids = sum(r[4] for r in rows)
    print(f"Targets: {len(rows)} tags, {total_links} image_tags links, "
          f"{total_orphan_kids} child tags will be re-parented to NULL")
    print()
    print(f"{'id':>4}  {'name':<28} {'parent':<20} {'uses':>5} {'kids':>4}")
    for r in rows:
        print(f"{r[0]:>4}  {r[1]:<28.28} {r[2]:<20.20} {r[3]:>5} {r[4]:>4}")

    if not args.execute:
        print("\nDry run. Re-run with --execute to apply.")
        return 0

    cur.execute("BEGIN")
    cur.execute(f"UPDATE tags SET parent_tag_id = NULL WHERE parent_tag_id IN ({qmarks})", target_ids)
    reparented = cur.rowcount
    cur.execute(f"DELETE FROM image_tags WHERE tag_id IN ({qmarks})", target_ids)
    unlinked = cur.rowcount
    cur.execute(f"DELETE FROM tags WHERE id IN ({qmarks})", target_ids)
    deleted = cur.rowcount
    conn.commit()
    print(f"\nDeleted {deleted} tags, removed {unlinked} image_tags rows, "
          f"re-parented {reparented} child tags to NULL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
