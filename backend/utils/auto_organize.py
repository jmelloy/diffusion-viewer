"""Phased auto-organization of the image library into proper nouns + projects.

Pipeline (each phase is independent — run via scripts/auto_organize.py):

    1. clear              wipe all tags + image_tags
    2. proper-nouns       extract capitalized names/places/brands as flat tags
    3. cluster            union-find on proper-noun co-occurrence → seed projects;
                          absorb un-named images by TF-IDF centroid cosine
    4. project-tags       per-project TF-IDF (in-cluster vs rest) → project children

Each phase returns a `Proposal` describing what *would* change. Call
`apply_*` to commit. Phases share the same heuristics as utils/tfidf.py so
the existing per-scan auto-tagger stays consistent.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import delete
from sqlalchemy.orm import Session

import models
from utils.tfidf import (
    DIFFUSION_STOP_WORDS,
    SKLEARN_STOP_WORDS,
    _clean_text,
    _extract_proper_nouns,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Proposals — every phase returns one of these. The CLI prints them; the
# caller decides whether to apply.
# --------------------------------------------------------------------------- #

@dataclass
class ProperNounProposal:
    """Per-noun mapping of `noun -> image_ids` to be tagged with that noun.

    Description and prompt extractions are tracked separately because
    descriptions tend to carry user-curated project/scene labels while prompts
    carry character/style cues from the model. Clustering uses both.
    """
    nouns: Dict[str, List[int]] = field(default_factory=dict)
    # corpus-wide counts, kept for reporting / clustering
    counts: Counter = field(default_factory=Counter)
    # source-specific maps
    description_nouns: Dict[str, List[int]] = field(default_factory=dict)
    prompt_nouns: Dict[str, List[int]] = field(default_factory=dict)

    @property
    def num_nouns(self) -> int:
        return len(self.nouns)

    @property
    def num_links(self) -> int:
        return sum(len(ids) for ids in self.nouns.values())


@dataclass
class ProjectProposal:
    name: str                                 # e.g. "project:Emilia"
    image_ids: List[int]
    seed_nouns: List[Tuple[str, int]]         # (noun, in-cluster count) sorted desc
    absorbed_count: int = 0                   # images added via centroid match
    # Proper nouns demoted to children of this project (scenes / sub-characters).
    # Each entry is (noun, image_count) and the noun has its own image_ids in
    # `child_noun_images` below — those nouns become tags parented under this
    # project at apply time.
    child_nouns: List[Tuple[str, int]] = field(default_factory=list)
    child_noun_images: Dict[str, List[int]] = field(default_factory=dict)
    # Filled in by phase 4 (project-tags):
    distinctive_terms: List[Tuple[str, float]] = field(default_factory=list)
    term_image_map: Dict[str, List[int]] = field(default_factory=dict)


@dataclass
class ProjectsProposal:
    projects: List[ProjectProposal] = field(default_factory=list)
    unassigned_image_ids: List[int] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Phase 1: clear
# --------------------------------------------------------------------------- #

def clear_all_tags(db: Session) -> Tuple[int, int]:
    """Wipe every tag + every image_tags row. Returns (tags_deleted, links_deleted)."""
    links = db.execute(delete(models.ImageTag)).rowcount or 0
    # Detach parent_tag_id references so DELETE doesn't trip the FK ordering.
    db.query(models.Tag).update({models.Tag.parent_tag_id: None})
    tags = db.query(models.Tag).delete()
    db.commit()
    return tags, links


# --------------------------------------------------------------------------- #
# Phase 2: proper nouns
# --------------------------------------------------------------------------- #

def _build_text_corpus(
    db: Session, image_ids: Optional[Sequence[int]] = None
) -> List[Tuple[int, str, str]]:
    """Return (image_id, cleaned_text, original_text). Mirrors tfidf._build_corpus."""
    q = db.query(models.Image)
    if image_ids:
        q = q.filter(models.Image.id.in_(list(image_ids)))
    rows = []
    for img in q.all():
        parts = []
        if img.prompt:
            parts.append(img.prompt)
        if img.description:
            parts.append(img.description)
        original = " ".join(parts).strip()
        if original:
            rows.append((img.id, _clean_text(original), original))
    return rows


def _build_split_corpus(
    db: Session, image_ids: Optional[Sequence[int]] = None
) -> List[Tuple[int, str, str]]:
    """Return (image_id, prompt_text, description_text). Either may be empty."""
    q = db.query(models.Image)
    if image_ids:
        q = q.filter(models.Image.id.in_(list(image_ids)))
    rows = []
    for img in q.all():
        prompt = (img.prompt or "").strip()
        desc = (img.description or "").strip()
        if prompt or desc:
            rows.append((img.id, prompt, desc))
    return rows


def propose_proper_nouns(
    db: Session,
    min_count: int = 2,
    max_per_image: int = 8,
    image_ids: Optional[Sequence[int]] = None,
) -> ProperNounProposal:
    """Extract proper nouns separately from prompt and description fields.

    Filters the same way utils/tfidf does:
      * drops singletons (count < min_count) when corpus is large enough
      * drops single-token candidates whose lowercase form is roughly as
        common as the capitalized one (sentence-starters)

    Returns a proposal whose `description_nouns` and `prompt_nouns` reflect
    each source, plus a `nouns` dict that combines both for tagging.
    """
    corpus = _build_split_corpus(db, image_ids)
    if not corpus:
        return ProperNounProposal()

    per_image_desc: Dict[int, List[str]] = {}
    per_image_prompt: Dict[int, List[str]] = {}
    counts: Counter = Counter()
    for img_id, prompt, description in corpus:
        d = _extract_proper_nouns(description) if description else []
        p = _extract_proper_nouns(prompt) if prompt else []
        per_image_desc[img_id] = d
        per_image_prompt[img_id] = p
        for n in set(d) | set(p):
            counts[n] += 1

    # lowercase frequency on the combined cleaned text — used to reject
    # sentence-starters that look capitalized but appear lowercase elsewhere
    lower_counts: Counter = Counter()
    for _img_id, prompt, description in corpus:
        combined = _clean_text(f"{prompt} {description}")
        for w in re.findall(r"\b[a-z]{3,}\b", combined):
            lower_counts[w] += 1

    def is_likely_proper(noun: str) -> bool:
        toks = noun.split()
        if len(toks) > 1:
            return True
        cap = counts[noun]
        low = lower_counts.get(toks[0].lower(), 0)
        return cap >= max(2, low * 3)

    big_corpus = len(corpus) >= 10

    def _accept(per_image_map: Dict[int, List[str]]) -> Dict[str, List[int]]:
        out: Dict[str, List[int]] = defaultdict(list)
        for img_id, nouns in per_image_map.items():
            ranked = sorted(set(nouns), key=lambda n: (-counts[n], -len(n)))
            kept = 0
            for noun in ranked:
                if kept >= max_per_image:
                    break
                if big_corpus and counts[noun] < min_count:
                    continue
                if not is_likely_proper(noun):
                    continue
                tag_name = noun.lower()
                if tag_name in DIFFUSION_STOP_WORDS:
                    continue
                out[tag_name].append(img_id)
                kept += 1
        return {k: sorted(set(v)) for k, v in out.items()}

    desc = _accept(per_image_desc)
    prompt = _accept(per_image_prompt)

    # Combined map for tagging — union per noun.
    combined: Dict[str, Set[int]] = defaultdict(set)
    for src in (desc, prompt):
        for noun, ids in src.items():
            combined[noun].update(ids)

    return ProperNounProposal(
        nouns={k: sorted(v) for k, v in combined.items()},
        counts=counts,
        description_nouns=desc,
        prompt_nouns=prompt,
    )


def apply_proper_nouns(db: Session, proposal: ProperNounProposal) -> int:
    """Create flat tags for every noun in the proposal and attach images.

    Returns the number of new (image_id, tag_id) links created.
    """
    if not proposal.nouns:
        return 0
    tag_by_name: Dict[str, models.Tag] = {
        t.name: t for t in db.query(models.Tag).filter(models.Tag.name.in_(proposal.nouns.keys()))
    }
    created_links = 0
    for name, image_ids in proposal.nouns.items():
        tag = tag_by_name.get(name)
        if tag is None:
            tag = models.Tag(name=name)
            db.add(tag)
            db.flush()
            tag_by_name[name] = tag
        existing = {img.id for img in tag.images}
        for img_id in image_ids:
            if img_id in existing:
                continue
            img = db.get(models.Image, img_id)
            if img is None:
                continue
            img.tags.append(tag)
            created_links += 1
    db.commit()
    return created_links


# --------------------------------------------------------------------------- #
# Phase 3: cluster into projects
# --------------------------------------------------------------------------- #

class _UnionFind:
    def __init__(self, items: Iterable[str]):
        self.parent = {x: x for x in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _build_cooccurrence(
    nouns_proposal: ProperNounProposal,
    min_noun_count: int,
) -> Tuple[Dict[Tuple[str, str], int], Set[str]]:
    """Pair counts and the set of nouns that pass min_noun_count."""
    keep = {n for n, c in nouns_proposal.counts.items()
            if c >= min_noun_count and n.lower() in nouns_proposal.nouns}
    # invert: image_id -> set(nouns)
    image_to_nouns: Dict[int, Set[str]] = defaultdict(set)
    for noun, image_ids in nouns_proposal.nouns.items():
        if noun not in {k.lower() for k in keep}:
            continue
        for img_id in image_ids:
            image_to_nouns[img_id].add(noun)

    pair_counts: Dict[Tuple[str, str], int] = Counter()
    for nouns in image_to_nouns.values():
        if len(nouns) < 2:
            continue
        ordered = sorted(nouns)
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                pair_counts[(ordered[i], ordered[j])] += 1
    return pair_counts, {n.lower() for n in keep}


def _name_for_cluster(
    cluster_nouns: Sequence[str],
    cluster_noun_counts: Counter,
    used_names: Set[str],
) -> str:
    """Pick a project name from the most prominent proper noun(s)."""
    ranked = sorted(cluster_nouns, key=lambda n: (-cluster_noun_counts[n], n))
    for noun in ranked:
        candidate = "project:" + noun.title().replace("_", " ")
        if candidate not in used_names:
            return candidate
    # fall back to numbered if every option collides
    n = 1
    while True:
        candidate = f"project:Group{n:02d}"
        if candidate not in used_names:
            return candidate
        n += 1


def propose_projects(
    db: Session,
    nouns_proposal: ProperNounProposal,
    min_anchor_count: int = 3,
    min_project_size: int = 25,
    scene_absorption_fraction: float = 0.4,
    cluster_threshold: float = 0.18,
    min_cluster_size: int = 5,
    cooccurrence_overlap: float = 0.3,
    image_ids: Optional[Sequence[int]] = None,
    min_noun_count: int = 3,
    min_cooccurrence: int = 1,
) -> ProjectsProposal:
    """Cluster images into projects via cooccurrence-merged anchors.

    Step A — anchors: every proper noun (description- or prompt-derived) with
    at least `min_anchor_count` images becomes an anchor.

    Step B — merge: union-find anchors whose image sets overlap. An edge is
    drawn when |A ∩ B| / min(|A|, |B|) >= `cooccurrence_overlap`. Each
    connected component becomes a project candidate. Within a component the
    project's canonical name is taken from the biggest description-anchored
    member, else the biggest prompt-anchored member.

    Step C — scene absorption: any singleton-component anchor whose image set
    overlaps an existing project at >= `scene_absorption_fraction` becomes a
    child of that project (its images join the project). This catches
    description-only labels (like "Behind Closed Doors") that share no
    proper noun with anyone but textually live inside a bigger project.

    Step D — un-anchored images: TF-IDF centroid match against every
    project; attach if cosine >= `cluster_threshold`.

    Step E — drop projects smaller than `min_cluster_size`. Anchors smaller
    than `min_project_size` whose component is a singleton stay as flat
    proper-noun tags rather than becoming projects.
    """
    del min_noun_count, min_cooccurrence  # legacy CLI flags, ignored
    if not nouns_proposal.nouns:
        return ProjectsProposal()

    # Restrict every per-image set to `image_ids` if given, so cluster can
    # ignore images already covered by seed projects.
    allowed: Optional[Set[int]] = set(image_ids) if image_ids is not None else None

    def _filter(ids: Iterable[int]) -> Set[int]:
        if allowed is None:
            return set(ids)
        return {i for i in ids if i in allowed}

    desc_nouns = {n: list(_filter(ids)) for n, ids in nouns_proposal.description_nouns.items()}
    prompt_nouns = {n: list(_filter(ids)) for n, ids in nouns_proposal.prompt_nouns.items()}

    # ---- Step A: gather anchors ----
    # Stored as: {noun: (source, image_ids_set)} — description wins if a
    # noun appears in both sources.
    anchors: Dict[str, Tuple[str, Set[int]]] = {}
    for n, ids in prompt_nouns.items():
        if len(ids) >= min_anchor_count:
            anchors[n] = ("prompt", set(ids))
    for n, ids in desc_nouns.items():
        if len(ids) >= min_anchor_count:
            existing = anchors.get(n, (None, set()))[1]
            anchors[n] = ("desc", existing | set(ids))

    if not anchors:
        return ProjectsProposal()

    # ---- Step B: union-find merge by image-set overlap ----
    uf = _UnionFind(anchors.keys())
    anchor_list = list(anchors.items())
    for i in range(len(anchor_list)):
        n_i, (_src_i, ids_i) = anchor_list[i]
        for j in range(i + 1, len(anchor_list)):
            n_j, (_src_j, ids_j) = anchor_list[j]
            smaller = min(len(ids_i), len(ids_j))
            if smaller == 0:
                continue
            overlap = len(ids_i & ids_j)
            if overlap >= max(2, smaller * cooccurrence_overlap):
                uf.union(n_i, n_j)

    # Group anchors by component
    components: Dict[str, List[str]] = defaultdict(list)
    for n in anchors:
        components[uf.find(n)].append(n)

    # ---- Step B (continued): build initial projects from each component ----
    # Project name = biggest desc-anchored member; tie-break to longest noun.
    image_to_project: Dict[int, str] = {}
    project_anchor_of: Dict[str, str] = {}  # project_name -> primary anchor noun
    project_member_anchors: Dict[str, List[str]] = {}  # project_name -> all anchor nouns
    project_image_sets: Dict[str, Set[int]] = defaultdict(set)
    scene_to_parent: Dict[str, str] = {}

    for root, member_nouns in components.items():
        # Pick the canonical anchor: biggest desc, else biggest prompt
        desc_members = [m for m in member_nouns if anchors[m][0] == "desc"]
        chosen_pool = desc_members or member_nouns
        primary = max(chosen_pool, key=lambda m: (len(anchors[m][1]), len(m)))
        # Aggregate image set across the whole component
        all_imgs: Set[int] = set()
        for m in member_nouns:
            all_imgs |= anchors[m][1]
        # If primary anchor has < min_project_size images AND component is a
        # singleton, defer this anchor to Step C (it might attach as a child
        # of an existing project).
        if len(member_nouns) == 1 and len(all_imgs) < min_project_size:
            continue
        # Keep as a project candidate
        project_anchor_of[primary] = primary
        project_member_anchors[primary] = member_nouns
        project_image_sets[primary] = all_imgs
        for img_id in all_imgs:
            image_to_project.setdefault(img_id, primary)
        for m in member_nouns:
            if m != primary:
                scene_to_parent[m] = primary

    # ---- Step C: absorb singleton small anchors via image-set overlap ----
    # Process largest-first so big "scenes" attach before small ones.
    candidates = sorted(
        (n for n, mem in components.items()
         if len(components[n]) == 1
         and components[n][0] not in project_anchor_of
         and components[n][0] not in scene_to_parent),
        key=lambda r: -len(anchors[components[r][0]][1]),
    )
    for root in candidates:
        noun = components[root][0]
        ids = anchors[noun][1]
        if not ids:
            continue
        # Find best matching project by overlap with project's full image set
        best_proj = None
        best_overlap = 0
        for proj_name, proj_imgs in project_image_sets.items():
            overlap = len(ids & proj_imgs)
            if overlap > best_overlap:
                best_overlap = overlap
                best_proj = proj_name
        if best_proj is None:
            continue
        if best_overlap < max(1, len(ids) * scene_absorption_fraction):
            continue
        # Absorb
        scene_to_parent[noun] = best_proj
        project_member_anchors[best_proj].append(noun)
        project_image_sets[best_proj] |= ids
        for img_id in ids:
            image_to_project.setdefault(img_id, best_proj)

    project_anchors: Set[str] = set(project_anchor_of)

    # ---- Step D: TF-IDF centroid absorption for un-anchored images ----
    corpus = _build_text_corpus(db, image_ids=image_ids)
    all_ids = {row[0] for row in corpus}
    if corpus and project_anchors:
        ids_list = [c[0] for c in corpus]
        texts = [c[1] for c in corpus]
        try:
            vec = TfidfVectorizer(
                stop_words=SKLEARN_STOP_WORDS,
                max_features=2000,
                ngram_range=(1, 2),
                min_df=2,
                max_df=0.6,
                sublinear_tf=True,
                token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b",
            )
            tfidf = vec.fit_transform(texts)
        except ValueError:
            tfidf = None
        if tfidf is not None:
            id_to_row = {img_id: i for i, img_id in enumerate(ids_list)}
            project_image_sets: Dict[str, Set[int]] = defaultdict(set)
            for img_id, proj in image_to_project.items():
                project_image_sets[proj].add(img_id)
            centroids: Dict[str, np.ndarray] = {}
            for proj, imgs in project_image_sets.items():
                rows = [id_to_row[i] for i in imgs if i in id_to_row]
                if rows:
                    centroids[proj] = np.asarray(tfidf[rows].mean(axis=0)).ravel()
            if centroids:
                proj_names = list(centroids.keys())
                centroid_matrix = np.vstack([centroids[p] for p in proj_names])
                unassigned_rows = [i for i in range(len(ids_list))
                                   if ids_list[i] not in image_to_project]
                if unassigned_rows:
                    sims = cosine_similarity(tfidf[unassigned_rows], centroid_matrix)
                    best_idx = sims.argmax(axis=1)
                    best_val = sims.max(axis=1)
                    for k, row_i in enumerate(unassigned_rows):
                        if best_val[k] >= cluster_threshold:
                            image_to_project[ids_list[row_i]] = proj_names[best_idx[k]]

    # ---- Step E: build proposals, apply min_cluster_size filter ----
    project_image_sets = defaultdict(set)
    for img_id, proj in image_to_project.items():
        project_image_sets[proj].add(img_id)

    used_names: Set[str] = set()
    projects: List[ProjectProposal] = []
    # Sort largest-first so the most populous cluster gets first dibs on a name.
    for noun in sorted(project_image_sets.keys(),
                       key=lambda n: -len(project_image_sets[n])):
        if noun not in project_anchors:
            continue
        img_ids = sorted(project_image_sets[noun])
        if len(img_ids) < min_cluster_size:
            continue
        # Assemble the canonical project name.
        name = _name_for_cluster([noun], Counter({noun: len(img_ids)}), used_names)
        used_names.add(name)
        # Children of this project: anchors absorbed into it (scenes, characters)
        children = [(n, len(anchors[n][1])) for n, parent in scene_to_parent.items()
                    if parent == noun]
        children.sort(key=lambda t: -t[1])
        child_images = {n: sorted(anchors[n][1]) for n, _ in children}
        # Seeds = the anchor + its absorbed children, with image counts
        seed_nouns = [(noun, len(anchors[noun][1]))] + children
        # absorbed_count = images that didn't come in via this anchor or its
        # absorbed children
        seed_image_set: Set[int] = set(anchors[noun][1])
        for n, _ in children:
            seed_image_set.update(anchors[n][1])
        absorbed = len(set(img_ids) - seed_image_set)
        projects.append(ProjectProposal(
            name=name,
            image_ids=img_ids,
            seed_nouns=seed_nouns,
            absorbed_count=absorbed,
            child_nouns=children,
            child_noun_images=child_images,
        ))

    assigned: Set[int] = set()
    for p in projects:
        assigned.update(p.image_ids)
    unassigned = sorted(all_ids - assigned)

    return ProjectsProposal(projects=projects, unassigned_image_ids=unassigned)


def apply_projects(db: Session, proposal: ProjectsProposal) -> int:
    """Create the project tags, attach images, and parent absorbed proper-noun
    children under their project. Returns links created.
    """
    created_links = 0
    for project in proposal.projects:
        tag = db.query(models.Tag).filter(models.Tag.name == project.name).first()
        if tag is None:
            tag = models.Tag(name=project.name, parent_tag_id=None)
            db.add(tag)
            db.flush()
        existing = {img.id for img in tag.images}
        for img_id in project.image_ids:
            if img_id in existing:
                continue
            img = db.get(models.Image, img_id)
            if img is None:
                continue
            img.tags.append(tag)
            created_links += 1

        # Parent any absorbed proper-noun child tags under this project.
        for child_noun, _count in project.child_nouns:
            child = db.query(models.Tag).filter(models.Tag.name == child_noun).first()
            if child is None:
                # propose_proper_nouns may not have been applied yet; create it.
                child = models.Tag(name=child_noun, parent_tag_id=tag.id)
                db.add(child)
                db.flush()
            else:
                child.parent_tag_id = tag.id
    db.commit()
    return created_links


# --------------------------------------------------------------------------- #
# Phase 4: per-project TF-IDF
# --------------------------------------------------------------------------- #

def propose_within_project_tags(
    db: Session,
    proposal: ProjectsProposal,
    top_n_per_project: int = 25,
    top_n_per_image: int = 6,
    min_distinctive_score: float = 1.5,
) -> ProjectsProposal:
    """For each project, find terms whose mean in-cluster TF-IDF is `min_distinctive_score`x
    higher than their mean out-of-cluster TF-IDF. Tags chosen this way become
    candidate children of the project. Then pick the top `top_n_per_image`
    candidates per image as that image's project-scoped tag set.

    Mutates `proposal.projects` in place by populating `distinctive_terms`
    and `term_image_map`. Returns the same proposal for chaining.
    """
    if not proposal.projects:
        return proposal

    corpus = _build_text_corpus(db)
    if not corpus:
        return proposal

    ids = [c[0] for c in corpus]
    texts = [c[1] for c in corpus]
    id_to_row = {img_id: i for i, img_id in enumerate(ids)}

    try:
        vec = TfidfVectorizer(
            stop_words=SKLEARN_STOP_WORDS,
            max_features=3000,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.5,
            sublinear_tf=True,
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b",
        )
        tfidf = vec.fit_transform(texts).tocsc()
    except ValueError as e:
        logger.warning(f"Per-project TF-IDF failed: {e}")
        return proposal
    feature_names = vec.get_feature_names_out()

    # Track which proper-noun tag names were *already used* as project names —
    # we don't want to re-tag them as children of their own project.
    project_name_lower = {p.name.split(":", 1)[1].lower() for p in proposal.projects}

    for project in proposal.projects:
        in_rows = [id_to_row[i] for i in project.image_ids if i in id_to_row]
        if not in_rows:
            continue
        out_rows = [r for r in range(len(ids)) if r not in set(in_rows)]
        if not out_rows:
            continue

        # Mean TF-IDF per term, in-cluster vs out-cluster.
        in_mean = np.asarray(tfidf[in_rows].mean(axis=0)).ravel()
        out_mean = np.asarray(tfidf[out_rows].mean(axis=0)).ravel()
        # Distinctiveness ratio with smoothing so rare-but-only-in-cluster wins.
        ratio = in_mean / (out_mean + 1e-4)
        # Require some absolute presence to avoid noise.
        mask = (in_mean > 0.005) & (ratio >= min_distinctive_score)
        candidate_idx = np.where(mask)[0]
        # Rank candidates by in_mean * log(ratio) — favors common-and-distinctive.
        scored = sorted(
            (
                (i, float(in_mean[i] * np.log1p(ratio[i])))
                for i in candidate_idx
            ),
            key=lambda t: -t[1],
        )

        kept: List[Tuple[str, float]] = []
        for fi, score in scored:
            term = feature_names[fi]
            if term in DIFFUSION_STOP_WORDS:
                continue
            if re.fullmatch(r"[0-9\s]+", term):
                continue
            if term in project_name_lower:
                continue
            kept.append((term, score))
            if len(kept) >= top_n_per_project:
                break
        project.distinctive_terms = kept

        # Per-image: rank the project's distinctive terms by raw tf-idf row score.
        if not kept:
            continue
        kept_indices = [
            int(np.where(feature_names == term)[0][0]) for term, _ in kept
        ]
        sub = tfidf[:, kept_indices].tocsr()
        term_to_imgs: Dict[str, List[int]] = defaultdict(list)
        for img_id in project.image_ids:
            r = id_to_row.get(img_id)
            if r is None:
                continue
            row_scores = sub[r].toarray().ravel()
            top = np.argsort(row_scores)[::-1][:top_n_per_image]
            for k in top:
                if row_scores[k] <= 0:
                    break
                term_to_imgs[kept[k][0]].append(img_id)
        project.term_image_map = {t: sorted(set(v)) for t, v in term_to_imgs.items()}

    return proposal


# --------------------------------------------------------------------------- #
# Seed-driven attribution: user declares projects + their keywords; we attach
# images by scanning prompt + description. Sub-categories (character / scene /
# weapon, etc.) become intermediate parent tags.
# --------------------------------------------------------------------------- #

@dataclass
class SeedRoleMatch:
    role: str                        # "" for flat keywords (no role)
    keyword: str                     # the matched keyword, lowercased
    image_ids: List[int]


@dataclass
class SeedProjectProposal:
    name: str                        # "project:Alien Encounter"
    image_ids: List[int]             # union of all keyword matches
    role_matches: List[SeedRoleMatch] = field(default_factory=list)


@dataclass
class SeedsProposal:
    projects: List[SeedProjectProposal] = field(default_factory=list)
    unmatched_image_ids: List[int] = field(default_factory=list)

    @property
    def num_links(self) -> int:
        return sum(len(p.image_ids) for p in self.projects) + sum(
            len(rm.image_ids) for p in self.projects for rm in p.role_matches
        )


def _compile_keyword_regex(keyword: str) -> "re.Pattern[str]":
    # Whole-word, case-insensitive. Multi-word phrases match exactly with
    # internal whitespace flexible (any run of whitespace).
    parts = [re.escape(p) for p in keyword.lower().split() if p]
    if not parts:
        return re.compile(r"a^")  # never matches
    body = r"\s+".join(parts)
    return re.compile(rf"\b{body}\b", re.IGNORECASE)


def propose_seeds(
    db: Session,
    seeds: List[Dict],   # list of {name, roles?, keywords?}
) -> SeedsProposal:
    """Match each image against the seed projects' keywords.

    For every keyword that matches an image's prompt or description, the
    image is attached to that project AND that keyword gets recorded under
    the role it appeared under (or the flat `keywords` bucket).

    An image can match multiple projects (and is attached to each).
    """
    if not seeds:
        return SeedsProposal()

    # Build (project_idx, role, keyword, regex) tuples for fast scan
    matchers: List[Tuple[int, str, str, "re.Pattern[str]"]] = []
    for idx, spec in enumerate(seeds):
        for role, kws in (spec.get("roles") or {}).items():
            for kw in kws or []:
                matchers.append((idx, role, kw.lower(), _compile_keyword_regex(kw)))
        for kw in spec.get("keywords") or []:
            matchers.append((idx, "", kw.lower(), _compile_keyword_regex(kw)))

    if not matchers:
        return SeedsProposal()

    corpus = _build_split_corpus(db)
    if not corpus:
        return SeedsProposal()

    # project_idx -> {(role, keyword): set(image_ids)}
    per_project_role_kw: Dict[int, Dict[Tuple[str, str], Set[int]]] = defaultdict(
        lambda: defaultdict(set)
    )
    project_image_ids: Dict[int, Set[int]] = defaultdict(set)
    matched_images: Set[int] = set()

    for img_id, prompt, description in corpus:
        haystack = f"{prompt}\n{description}"
        for proj_idx, role, kw, rx in matchers:
            if rx.search(haystack):
                per_project_role_kw[proj_idx][(role, kw)].add(img_id)
                project_image_ids[proj_idx].add(img_id)
                matched_images.add(img_id)

    projects: List[SeedProjectProposal] = []
    for idx, spec in enumerate(seeds):
        if idx not in project_image_ids:
            continue
        role_matches = [
            SeedRoleMatch(role=role, keyword=kw, image_ids=sorted(ids))
            for (role, kw), ids in sorted(
                per_project_role_kw[idx].items(),
                key=lambda kv: (-len(kv[1]), kv[0]),
            )
        ]
        projects.append(SeedProjectProposal(
            name=f"project:{spec['name']}",
            image_ids=sorted(project_image_ids[idx]),
            role_matches=role_matches,
        ))

    all_ids = {img_id for (img_id, _, _) in corpus}
    unmatched = sorted(all_ids - matched_images)
    return SeedsProposal(projects=projects, unmatched_image_ids=unmatched)


def apply_seeds(db: Session, proposal: SeedsProposal) -> int:
    """Create project + role + keyword tags and attach images.

    Hierarchy:  project:Name ─ project:Name:role ─ keyword
    """
    created_links = 0
    for project in proposal.projects:
        proj_tag = db.query(models.Tag).filter(models.Tag.name == project.name).first()
        if proj_tag is None:
            proj_tag = models.Tag(name=project.name, parent_tag_id=None)
            db.add(proj_tag)
            db.flush()
        existing_proj_imgs = {img.id for img in proj_tag.images}
        for img_id in project.image_ids:
            if img_id in existing_proj_imgs:
                continue
            img = db.get(models.Image, img_id)
            if img is None:
                continue
            img.tags.append(proj_tag)
            created_links += 1

        # Cache role tags by name to avoid repeated lookups.
        role_tags: Dict[str, models.Tag] = {}

        def _get_role_tag(role: str) -> Optional[models.Tag]:
            if not role:
                return None
            full_name = f"{project.name}:{role}"
            if full_name in role_tags:
                return role_tags[full_name]
            t = db.query(models.Tag).filter(models.Tag.name == full_name).first()
            if t is None:
                t = models.Tag(name=full_name, parent_tag_id=proj_tag.id)
                db.add(t)
                db.flush()
            elif t.parent_tag_id != proj_tag.id:
                t.parent_tag_id = proj_tag.id
            role_tags[full_name] = t
            return t

        for rm in project.role_matches:
            parent_id = (_get_role_tag(rm.role) or proj_tag).id
            kw_tag = db.query(models.Tag).filter(models.Tag.name == rm.keyword).first()
            if kw_tag is None:
                kw_tag = models.Tag(name=rm.keyword, parent_tag_id=parent_id)
                db.add(kw_tag)
                db.flush()
            elif kw_tag.parent_tag_id is None or (
                rm.role and kw_tag.parent_tag_id != parent_id
            ):
                kw_tag.parent_tag_id = parent_id
            existing_kw_imgs = {img.id for img in kw_tag.images}
            for img_id in rm.image_ids:
                if img_id in existing_kw_imgs:
                    continue
                img = db.get(models.Image, img_id)
                if img is None:
                    continue
                img.tags.append(kw_tag)
                created_links += 1
    db.commit()
    return created_links


def load_seeds(path: str) -> List[Dict]:
    """Load a seeds YAML file. Returns the `projects` list."""
    import yaml  # local import — only the seeds command needs it
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("projects") or []


def apply_within_project_tags(
    db: Session, proposal: ProjectsProposal
) -> int:
    """Create child tags under each project tag and link images. Returns links created."""
    created_links = 0
    project_tag_by_name = {
        t.name: t for t in db.query(models.Tag).filter(
            models.Tag.name.in_([p.name for p in proposal.projects])
        )
    }
    for project in proposal.projects:
        if not project.term_image_map:
            continue
        parent = project_tag_by_name.get(project.name)
        if parent is None:
            # apply_projects must run first
            logger.warning(f"Project tag {project.name} not found; skipping.")
            continue
        # Pre-fetch all child tag names that already exist
        child_names = list(project.term_image_map.keys())
        existing_children = {
            t.name: t for t in db.query(models.Tag).filter(models.Tag.name.in_(child_names))
        }
        for term, image_ids in project.term_image_map.items():
            child = existing_children.get(term)
            if child is None:
                child = models.Tag(name=term, parent_tag_id=parent.id)
                db.add(child)
                db.flush()
                existing_children[term] = child
            elif child.parent_tag_id is None:
                # Adopt orphan tags into this project
                child.parent_tag_id = parent.id
            existing_links = {img.id for img in child.images}
            for img_id in image_ids:
                if img_id in existing_links:
                    continue
                img = db.get(models.Image, img_id)
                if img is None:
                    continue
                img.tags.append(child)
                created_links += 1
    db.commit()
    return created_links
