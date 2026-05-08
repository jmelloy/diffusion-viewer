"""Merge duplicate tag clusters into a canonical tag.

For each cluster: copy image_tags rows from sources onto the canonical (skipping
duplicates via INSERT OR IGNORE), re-parent any child tags pointing at a source
to the canonical, then delete the sources.

Dry-run by default. Pass --execute to apply.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "backend" / "diffusion_viewer.db"

# (canonical_name, [source_names_to_merge_in])
CLUSTERS: list[tuple[str, list[str]]] = [
    ("cluedo",           ["victorian noir", "noir"]),
]


def name_to_id(cur: sqlite3.Cursor, names: list[str]) -> dict[str, int]:
    qmarks = ",".join("?" * len(names))
    cur.execute(f"SELECT name, id FROM tags WHERE name IN ({qmarks})", names)
    return {n: i for n, i in cur.fetchall()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    plans = []
    for canonical_name, sources in CLUSTERS:
        all_names = [canonical_name] + sources
        ids = name_to_id(cur, all_names)
        missing = [n for n in all_names if n not in ids]
        if missing:
            print(f"[skip] {canonical_name}: missing tags {missing}", file=sys.stderr)
            continue
        canonical_id = ids[canonical_name]
        source_ids = [ids[n] for n in sources]

        qmarks = ",".join("?" * len(source_ids))
        cur.execute(
            f"""
            SELECT COUNT(DISTINCT it.image_id)
            FROM image_tags it
            WHERE it.tag_id IN ({qmarks})
              AND it.image_id NOT IN (SELECT image_id FROM image_tags WHERE tag_id = ?)
            """,
            (*source_ids, canonical_id),
        )
        new_links = cur.fetchone()[0]
        cur.execute(
            f"SELECT COUNT(*) FROM image_tags WHERE tag_id IN ({qmarks})",
            source_ids,
        )
        src_links = cur.fetchone()[0]
        cur.execute(
            f"SELECT COUNT(*) FROM tags WHERE parent_tag_id IN ({qmarks})",
            source_ids,
        )
        kids = cur.fetchone()[0]

        plans.append((canonical_name, canonical_id, sources, source_ids,
                      new_links, src_links, kids))

    print(f"{'canonical':<20} {'sources':<60} {'+links':>7} {'src_links':>10} {'kids':>5}")
    for cn, _, sources, _, new_links, src_links, kids in plans:
        print(f"{cn:<20} {', '.join(sources):<60.60} {new_links:>7} {src_links:>10} {kids:>5}")

    if not args.execute:
        print("\nDry run. Re-run with --execute to apply.")
        return 0

    cur.execute("BEGIN")
    total_added = total_removed = total_reparented = total_deleted = 0
    for cn, canonical_id, _, source_ids, _, _, _ in plans:
        qmarks = ",".join("?" * len(source_ids))
        cur.execute(
            f"""
            INSERT OR IGNORE INTO image_tags (image_id, tag_id)
            SELECT DISTINCT image_id, ? FROM image_tags WHERE tag_id IN ({qmarks})
            """,
            (canonical_id, *source_ids),
        )
        total_added += cur.rowcount
        cur.execute(
            f"UPDATE tags SET parent_tag_id = ? WHERE parent_tag_id IN ({qmarks})",
            (canonical_id, *source_ids),
        )
        total_reparented += cur.rowcount
        cur.execute(
            f"DELETE FROM image_tags WHERE tag_id IN ({qmarks})", source_ids,
        )
        total_removed += cur.rowcount
        cur.execute(
            f"DELETE FROM tags WHERE id IN ({qmarks})", source_ids,
        )
        total_deleted += cur.rowcount
    conn.commit()
    print(f"\nAdded {total_added} canonical links, removed {total_removed} source links, "
          f"re-parented {total_reparented} child tags, deleted {total_deleted} source tags.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
