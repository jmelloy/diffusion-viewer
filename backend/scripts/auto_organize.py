#!/usr/bin/env python3
"""Phased auto-organization CLI: proper nouns → projects → in-project TF-IDF.

Default usage (dry-run, then apply once you like the output):

    python scripts/auto_organize.py clear              --execute
    python scripts/auto_organize.py proper-nouns       # dry-run
    python scripts/auto_organize.py proper-nouns       --execute
    python scripts/auto_organize.py cluster            # dry-run
    python scripts/auto_organize.py cluster            --execute
    python scripts/auto_organize.py project-tags       # dry-run
    python scripts/auto_organize.py project-tags       --execute

Or run the whole pipeline (still dry-run by default):

    python scripts/auto_organize.py all --execute

Knobs you'll most often want to turn:

    --min-noun-count N        drop proper nouns appearing fewer than N times
    --min-cooccurrence N      edge threshold for project seeding
    --cluster-threshold F     cosine sim required to absorb un-named images
    --min-cluster-size N      reject projects smaller than N images
    --min-distinctive F       in/out-cluster TF-IDF ratio for project tags
    --top-n-per-project N     max distinctive terms per project
    --top-n-per-image N       max project tags assigned per image

Pass `--db /path/to/file.db` to point at a non-default SQLite file. Otherwise
honors $DATABASE_URL like the API does.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Make the backend modules importable when running from anywhere.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlmodel import Session, create_engine

from utils import auto_organize as ao


def _open_session(db_arg: str | None) -> Session:
    if db_arg:
        url = f"sqlite:///{db_arg}"
    else:
        url = os.getenv("DATABASE_URL", f"sqlite:///{BACKEND_ROOT / 'diffusion_viewer.db'}")
    print(f"# database: {url}")
    engine = create_engine(url, connect_args={"check_same_thread": False})
    return Session(engine)


# --------------------------------------------------------------------------- #
# Phase printers
# --------------------------------------------------------------------------- #

def _print_proper_nouns(p: ao.ProperNounProposal, limit: int = 40) -> None:
    print(f"Proper nouns: {p.num_nouns} unique → {p.num_links} image links")
    if not p.nouns:
        return
    rows = sorted(p.nouns.items(), key=lambda kv: -len(kv[1]))
    print(f"\n  {'noun':<28} {'images':>7}")
    for name, ids in rows[:limit]:
        print(f"  {name:<28} {len(ids):>7}")
    if len(rows) > limit:
        print(f"  ... +{len(rows) - limit} more")


def _print_projects(p: ao.ProjectsProposal) -> None:
    print(f"\nProjects: {len(p.projects)} clusters, "
          f"{sum(len(pr.image_ids) for pr in p.projects)} images assigned, "
          f"{len(p.unassigned_image_ids)} unassigned")
    for pr in p.projects:
        anchor = pr.seed_nouns[0] if pr.seed_nouns else (pr.name, 0)
        print(f"\n  {pr.name}")
        print(f"    images: {len(pr.image_ids)} "
              f"(anchor: {anchor[1]}, "
              f"absorbed: {pr.absorbed_count})")
        if pr.child_nouns:
            kids = ", ".join(f"{n}({c})" for n, c in pr.child_nouns[:8])
            extra = (f"  +{len(pr.child_nouns) - 8} more"
                     if len(pr.child_nouns) > 8 else "")
            print(f"    scenes/characters: {kids}{extra}")


def _print_project_tags(p: ao.ProjectsProposal, per_project_limit: int = 12) -> None:
    print(f"\nWithin-project TF-IDF terms (top {per_project_limit} per project):")
    for pr in p.projects:
        if not pr.distinctive_terms:
            continue
        print(f"\n  {pr.name} ({len(pr.image_ids)} images)")
        for term, score in pr.distinctive_terms[:per_project_limit]:
            n = len(pr.term_image_map.get(term, []))
            print(f"    {term:<28} score={score:6.3f}  imgs={n}")


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #

def cmd_clear(args, session: Session) -> int:
    if not args.execute:
        n_tags = session.execute(
            __import__("sqlalchemy").text("SELECT COUNT(*) FROM tags")
        ).scalar()
        n_links = session.execute(
            __import__("sqlalchemy").text("SELECT COUNT(*) FROM image_tags")
        ).scalar()
        print(f"Would delete {n_tags} tags and {n_links} image_tags rows.")
        print("Dry run. Re-run with --execute to apply.")
        return 0
    tags, links = ao.clear_all_tags(session)
    print(f"Deleted {tags} tags and {links} image_tags rows.")
    return 0


def cmd_proper_nouns(args, session: Session) -> int:
    proposal = ao.propose_proper_nouns(
        session,
        min_count=args.min_noun_count,
        max_per_image=args.max_per_image,
    )
    _print_proper_nouns(proposal, limit=args.show_top)
    if not args.execute:
        print("\nDry run. Re-run with --execute to apply.")
        return 0
    n = ao.apply_proper_nouns(session, proposal)
    print(f"\nCreated {n} new image_tags links across {proposal.num_nouns} proper-noun tags.")
    return 0


def _seeded_image_ids(session: Session) -> set[int]:
    """Image ids already attached to any tag whose name starts with `project:`."""
    from sqlalchemy import text
    rows = session.execute(text(
        "SELECT DISTINCT it.image_id FROM image_tags it "
        "JOIN tags t ON t.id = it.tag_id "
        "WHERE t.name LIKE 'project:%'"
    )).all()
    return {r[0] for r in rows}


def _allowed_ids_for_cluster(args, session: Session) -> list[int] | None:
    if not getattr(args, "skip_seeded", False):
        return None
    seeded = _seeded_image_ids(session)
    from sqlalchemy import text
    all_rows = session.execute(text("SELECT id FROM images")).all()
    allowed = [r[0] for r in all_rows if r[0] not in seeded]
    print(f"# --skip-seeded: ignoring {len(seeded)} already-projected images, "
          f"clustering over {len(allowed)} leftovers")
    return allowed


def cmd_cluster(args, session: Session) -> int:
    allowed = _allowed_ids_for_cluster(args, session)
    nouns = ao.propose_proper_nouns(
        session,
        min_count=args.min_noun_count,
        max_per_image=args.max_per_image,
        image_ids=allowed,
    )
    proposal = ao.propose_projects(
        session,
        nouns,
        min_anchor_count=args.min_noun_count,
        min_project_size=args.min_project_size,
        scene_absorption_fraction=args.scene_absorption_fraction,
        cooccurrence_overlap=args.cooccurrence_overlap,
        cluster_threshold=args.cluster_threshold,
        min_cluster_size=args.min_cluster_size,
        image_ids=allowed,
    )
    _print_projects(proposal)
    if not args.execute:
        print("\nDry run. Re-run with --execute to apply.")
        return 0
    n = ao.apply_projects(session, proposal)
    print(f"\nAttached {n} new image links to {len(proposal.projects)} project tags.")
    return 0


def cmd_project_tags(args, session: Session) -> int:
    if getattr(args, "discover", False):
        # Unsupervised mode: re-run clustering and emit TF-IDF children for
        # whatever clusters fall out.
        allowed = _allowed_ids_for_cluster(args, session)
        nouns = ao.propose_proper_nouns(
            session,
            min_count=args.min_noun_count,
            max_per_image=args.max_per_image,
            image_ids=allowed,
        )
        proposal = ao.propose_projects(
            session,
            nouns,
            min_anchor_count=args.min_noun_count,
            min_project_size=args.min_project_size,
            scene_absorption_fraction=args.scene_absorption_fraction,
            cooccurrence_overlap=args.cooccurrence_overlap,
            cluster_threshold=args.cluster_threshold,
            min_cluster_size=args.min_cluster_size,
            image_ids=allowed,
        )
    else:
        # Default: load projects already in the DB and add distinctive TF-IDF
        # children to each. Use this after `seeds --execute`.
        proposal = ao.load_projects_from_db(session)
        if not proposal.projects:
            print("No project:* tags found in the DB. Run `seeds --execute` "
                  "or `cluster --execute` first, or pass --discover to run "
                  "unsupervised clustering here.")
            return 1
        print(f"# loaded {len(proposal.projects)} existing projects from DB "
              f"({sum(len(p.image_ids) for p in proposal.projects)} images total)")
    proposal = ao.propose_within_project_tags(
        session,
        proposal,
        top_n_per_project=args.top_n_per_project,
        top_n_per_image=args.top_n_per_image,
        min_distinctive_score=args.min_distinctive,
    )
    _print_project_tags(proposal, per_project_limit=args.show_top)
    if not args.execute:
        print("\nDry run. Re-run with --execute to apply.")
        return 0
    if getattr(args, "discover", False):
        # In discover mode, the project tags don't exist yet — create them.
        ao.apply_projects(session, proposal)
    n = ao.apply_within_project_tags(session, proposal)
    print(f"\nCreated {n} new in-project tag links.")
    return 0


def _print_seeds(proposal: ao.SeedsProposal, show_top: int) -> None:
    print(f"\nSeed projects matched: {len(proposal.projects)}, "
          f"images attached: {sum(len(p.image_ids) for p in proposal.projects)}, "
          f"unmatched: {len(proposal.unmatched_image_ids)}")
    for p in proposal.projects:
        print(f"\n  {p.name}  ({len(p.image_ids)} images)")
        # group role matches by role
        by_role: dict[str, list[ao.SeedRoleMatch]] = {}
        for rm in p.role_matches:
            by_role.setdefault(rm.role or "(flat)", []).append(rm)
        for role, matches in by_role.items():
            top = ", ".join(f"{m.keyword}({len(m.image_ids)})" for m in matches[:show_top])
            extra = f"  +{len(matches)-show_top} more" if len(matches) > show_top else ""
            print(f"    {role:<10} {top}{extra}")


def cmd_seeds(args, session: Session) -> int:
    seeds = ao.load_seeds(args.seeds_file)
    proposal = ao.propose_seeds(session, seeds)
    _print_seeds(proposal, show_top=args.show_top)
    if not args.execute:
        print("\nDry run. Re-run with --execute to apply.")
        return 0
    n = ao.apply_seeds(session, proposal)
    print(f"\nCreated {n} new image_tag links across {len(proposal.projects)} projects.")
    return 0


def cmd_all(args, session: Session) -> int:
    print("== phase 1: clear ==")
    if args.execute:
        tags, links = ao.clear_all_tags(session)
        print(f"Deleted {tags} tags and {links} image_tags rows.\n")
    else:
        print("(dry run — would clear all existing tags)\n")

    print("== phase 2: proper nouns ==")
    nouns = ao.propose_proper_nouns(
        session,
        min_count=args.min_noun_count,
        max_per_image=args.max_per_image,
    )
    _print_proper_nouns(nouns, limit=args.show_top)
    if args.execute:
        n = ao.apply_proper_nouns(session, nouns)
        print(f"-> {n} links applied")

    print("\n== phase 3: cluster projects ==")
    projects = ao.propose_projects(
        session,
        nouns,
        min_noun_count=args.min_noun_count,
        min_cooccurrence=args.min_cooccurrence,
        cluster_threshold=args.cluster_threshold,
        min_cluster_size=args.min_cluster_size,
    )
    _print_projects(projects)
    if args.execute:
        n = ao.apply_projects(session, projects)
        print(f"-> {n} project links applied")

    print("\n== phase 4: per-project distinctive tags ==")
    projects = ao.propose_within_project_tags(
        session,
        projects,
        top_n_per_project=args.top_n_per_project,
        top_n_per_image=args.top_n_per_image,
        min_distinctive_score=args.min_distinctive,
    )
    _print_project_tags(projects, per_project_limit=args.show_top)
    if args.execute:
        n = ao.apply_within_project_tags(session, projects)
        print(f"-> {n} in-project tag links applied")
    else:
        print("\nDry run. Re-run with --execute to apply phases 1-4.")
    return 0


# --------------------------------------------------------------------------- #
# Argparse plumbing
# --------------------------------------------------------------------------- #

def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--execute", action="store_true",
                   help="actually write to the database (default: dry run)")
    p.add_argument("--db", help="SQLite path; overrides $DATABASE_URL")
    p.add_argument("--show-top", type=int, default=40,
                   help="how many rows to print per phase (default: 40)")


def _add_noun_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--min-noun-count", type=int, default=3,
                   help="drop proper nouns appearing fewer than N times (default: 3)")
    p.add_argument("--max-per-image", type=int, default=8,
                   help="cap proper nouns kept per image (default: 8)")


def _add_cluster_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--min-project-size", type=int, default=25,
                   help="proper noun must cover N+ images to be a project; "
                        "smaller anchors become scenes/characters under their "
                        "majority project (default: 25)")
    p.add_argument("--scene-absorption-fraction", type=float, default=0.4,
                   help="fraction of a small anchor's images that must share a "
                        "single project for it to become a child of that project "
                        "(default: 0.4)")
    p.add_argument("--cooccurrence-overlap", type=float, default=0.3,
                   help="anchors are merged into the same project when their "
                        "image-set overlap >= this fraction of the smaller "
                        "anchor's size (default: 0.3)")
    p.add_argument("--cluster-threshold", type=float, default=0.18,
                   help="cosine similarity required to absorb un-named images "
                        "(default: 0.18; raise for tighter clusters)")
    p.add_argument("--min-cluster-size", type=int, default=8,
                   help="reject final clusters smaller than N images (default: 8)")
    # Accepted for back-compat but no longer used by the new clustering.
    p.add_argument("--min-cooccurrence", type=int, default=1,
                   help=argparse.SUPPRESS)


def _add_project_tag_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--top-n-per-project", type=int, default=25,
                   help="max distinctive terms per project (default: 25)")
    p.add_argument("--top-n-per-image", type=int, default=6,
                   help="max project tags applied per image (default: 6)")
    p.add_argument("--min-distinctive", type=float, default=1.5,
                   help="min in-cluster/out-cluster TF-IDF ratio (default: 1.5)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_clear = sub.add_parser("clear", help="wipe all tags + image_tags")
    _add_common(p_clear)
    p_clear.set_defaults(func=cmd_clear)

    p_pn = sub.add_parser("proper-nouns", help="extract proper nouns as flat tags")
    _add_common(p_pn); _add_noun_args(p_pn)
    p_pn.set_defaults(func=cmd_proper_nouns)

    p_cl = sub.add_parser("cluster", help="group images into projects")
    _add_common(p_cl); _add_noun_args(p_cl); _add_cluster_args(p_cl)
    p_cl.add_argument("--skip-seeded", action="store_true",
                      help="ignore images already attached to any project:* tag "
                           "(typically those placed by the seeds command). Useful "
                           "for finding projects you haven't declared in seeds.yaml.")
    p_cl.set_defaults(func=cmd_cluster)

    p_pt = sub.add_parser("project-tags",
                          help="add distinctive TF-IDF tags inside each project")
    _add_common(p_pt); _add_noun_args(p_pt); _add_cluster_args(p_pt); _add_project_tag_args(p_pt)
    p_pt.add_argument("--skip-seeded", action="store_true",
                      help="(--discover only) ignore images already attached to any project:* tag")
    p_pt.add_argument("--discover", action="store_true",
                      help="re-run unsupervised clustering instead of loading "
                           "existing project:* tags from the DB")
    p_pt.set_defaults(func=cmd_project_tags)

    p_all = sub.add_parser("all", help="run all four phases end-to-end")
    _add_common(p_all); _add_noun_args(p_all); _add_cluster_args(p_all); _add_project_tag_args(p_all)
    p_all.set_defaults(func=cmd_all)

    p_seeds = sub.add_parser("seeds",
                             help="attach images to user-declared projects from a YAML seed file")
    _add_common(p_seeds)
    p_seeds.add_argument("--seeds-file",
                         default=str(BACKEND_ROOT / "scripts" / "seeds.yaml"),
                         help="path to seeds.yaml (default: scripts/seeds.yaml)")
    p_seeds.set_defaults(func=cmd_seeds)

    args = parser.parse_args()
    with _open_session(args.db) as session:
        return args.func(args, session)


if __name__ == "__main__":
    sys.exit(main())
