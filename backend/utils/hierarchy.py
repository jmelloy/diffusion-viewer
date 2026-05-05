"""Tag-hierarchy tools: assign parent_tag_id from curated rules + corpus subsumption."""
import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)


# Curated parent → children. Children that don't yet exist as tags will be
# CREATED if any image's prompt/description mentions them via word-boundary
# regex (used for Clue rooms which are often in prose, not tagged).
CURATED_HIERARCHIES: Dict[str, Dict[str, List[str]]] = {
    "cluedo": {
        # children that should also be tagged on images whose prompt mentions them
        "discover_in_prompt": [
            "study", "library", "kitchen", "ballroom", "conservatory",
            "billiard room", "dining room", "lounge", "hall", "grand staircase",
            "colonel mustard", "miss scarlett", "professor plum",
            "reverend green", "mrs white", "mrs peacock",
            "rope", "lead pipe", "knife", "wrench", "candlestick", "revolver",
        ],
        # children that already exist; just set their parent
        "existing": [
            "cluedo mansion", "victorian cluedo", "noir cluedo",
            "dark victorian", "victorian noir", "mansion",
            "billiard room", "dining room", "grand staircase",
            "hall entryway", "hall entryway foyer", "hall entryway grand hall",
        ],
        # only attach the discover_in_prompt children to images that look like
        # Clue images (prompt/dir mentions "cluedo" or "clue") to avoid false
        # matches like "study" referring to art studies
        "scope_signals": ["cluedo", "clue ", "/clue/", "mage-archive"],
    },
    "pin-up": {
        "discover_in_prompt": [],
        "existing": [
            "vintage pin-up", "pin-up illustration", "gil elvgren",
            "gil elvgren-inspired", "elvgren-inspired",
        ],
        "scope_signals": [],
    },
}


def _get_or_create_tag(db: Session, name: str) -> models.Tag:
    name = name.strip().lower()
    tag = db.query(models.Tag).filter(models.Tag.name == name).first()
    if not tag:
        tag = models.Tag(name=name)
        db.add(tag)
        db.flush()
    return tag


def _image_matches_scope(img: models.Image, signals: List[str]) -> bool:
    """True if any signal substring appears in prompt/description/directory."""
    if not signals:
        return True
    haystack = " ".join(
        s.lower() for s in (img.prompt or "", img.description or "", img.directory or "") if s
    )
    return any(sig in haystack for sig in signals)


def _word_boundary_re(term: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)


def apply_curated_hierarchies(db: Session) -> Dict[str, int]:
    """Create parent tags + missing child tags, set parent_tag_id, attach
    discovered children to images whose prompt mentions them."""
    stats = {"parents_created": 0, "children_parented": 0, "images_tagged": 0}

    for parent_name, cfg in CURATED_HIERARCHIES.items():
        parent = db.query(models.Tag).filter(models.Tag.name == parent_name).first()
        if not parent:
            parent = models.Tag(name=parent_name)
            db.add(parent)
            db.flush()
            stats["parents_created"] += 1

        # 1. Existing children: set their parent if unset (don't override a
        # parent the user has already chosen)
        for child_name in cfg["existing"]:
            child = db.query(models.Tag).filter(models.Tag.name == child_name).first()
            if child and child.id != parent.id and child.parent_tag_id is None:
                child.parent_tag_id = parent.id
                stats["children_parented"] += 1

        # 2. Prompt-discovered children — only attach to images that match
        # the parent's scope signals so "study" doesn't get attached to art
        # studies in unrelated images.
        if not cfg["discover_in_prompt"]:
            continue

        signals = cfg["scope_signals"]
        candidate_images = db.query(models.Image).all()
        in_scope = [img for img in candidate_images if _image_matches_scope(img, signals)]
        logger.info(f"  {parent_name}: scanning {len(in_scope)} in-scope images")

        compiled = [(c, _word_boundary_re(c)) for c in cfg["discover_in_prompt"]]

        for img in in_scope:
            text = " ".join(s for s in (img.prompt or "", img.description or "") if s)
            if not text:
                continue
            existing_tag_names = {t.name for t in img.tags}
            for child_name, pat in compiled:
                if not pat.search(text):
                    continue
                child = _get_or_create_tag(db, child_name)
                if child.parent_tag_id is None and child.id != parent.id:
                    child.parent_tag_id = parent.id
                    stats["children_parented"] += 1
                if child_name not in existing_tag_names:
                    img.tags.append(child)
                    existing_tag_names.add(child_name)
                    stats["images_tagged"] += 1

    db.commit()
    return stats


def apply_subsumption(
    db: Session,
    min_child_freq: int = 5,
    confidence: float = 0.95,
) -> Dict[str, int]:
    """Set parent_tag_id by subsumption: A is parent of B if P(A|B) >= confidence,
    freq(A) > freq(B), and B is not a substring artifact of A (e.g. 'line art' /
    'line' bigrams). Skips tags that already have a parent."""
    stats = {"parented": 0, "skipped_substring": 0, "skipped_existing": 0}

    # Load tag → image set
    tag_imgs: Dict[int, Set[int]] = defaultdict(set)
    rows = db.execute(
        models.image_tags.select()
    ).fetchall()
    for row in rows:
        tag_imgs[row.tag_id].add(row.image_id)

    tags = {t.id: t for t in db.query(models.Tag).all()}

    # Compute pair counts (a < b)
    pair_count: Dict[Tuple[int, int], int] = defaultdict(int)
    img_to_tags: Dict[int, List[int]] = defaultdict(list)
    for tid, imgs in tag_imgs.items():
        for img_id in imgs:
            img_to_tags[img_id].append(tid)
    for tid_list in img_to_tags.values():
        tid_list.sort()
        for i in range(len(tid_list)):
            for j in range(i + 1, len(tid_list)):
                pair_count[(tid_list[i], tid_list[j])] += 1

    suggestions: Dict[int, Tuple[int, float]] = {}  # child_id -> (parent_id, score)

    for (a, b), cab in pair_count.items():
        fa = len(tag_imgs[a])
        fb = len(tag_imgs[b])
        if fb < min_child_freq and fa < min_child_freq:
            continue

        for parent_id, child_id, parent_freq, child_freq in (
            (a, b, fa, fb), (b, a, fb, fa),
        ):
            if child_freq < min_child_freq:
                continue
            if parent_freq <= child_freq:
                continue
            p_parent_given_child = cab / child_freq
            if p_parent_given_child < confidence:
                continue
            # Reverse direction must NOT also be ≥ confidence (would mean
            # they're effectively the same tag, not a hierarchy)
            if cab / parent_freq >= confidence:
                continue

            parent_name = tags[parent_id].name
            child_name = tags[child_id].name
            # Skip bigram/substring artifacts: child fully appears inside parent
            # or vice versa as whitespace-delimited tokens
            parent_tokens = set(parent_name.split())
            child_tokens = set(child_name.split())
            if child_tokens.issubset(parent_tokens) or parent_tokens.issubset(child_tokens):
                stats["skipped_substring"] += 1
                continue

            score = p_parent_given_child * (parent_freq - child_freq)
            existing = suggestions.get(child_id)
            if existing is None or score > existing[1]:
                suggestions[child_id] = (parent_id, score)

    # Apply, skipping tags that already have a parent and avoiding cycles
    for child_id, (parent_id, _score) in suggestions.items():
        child = tags[child_id]
        if child.parent_tag_id is not None:
            stats["skipped_existing"] += 1
            continue
        # Prevent self-loops and trivial cycles
        if child_id == parent_id:
            continue
        # If proposed parent's parent is this child, skip (would create cycle)
        proposed = tags[parent_id]
        if proposed.parent_tag_id == child_id:
            continue
        child.parent_tag_id = parent_id
        stats["parented"] += 1

    db.commit()
    return stats


def recompute_parents(db: Session) -> Dict[str, int]:
    curated = apply_curated_hierarchies(db)
    subsumed = apply_subsumption(db)
    logger.info(f"recompute_parents: curated={curated} subsumed={subsumed}")
    return {**{f"curated_{k}": v for k, v in curated.items()},
            **{f"subsumption_{k}": v for k, v in subsumed.items()}}
