import re
import logging
from collections import Counter
from typing import Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

import models

logger = logging.getLogger(__name__)

# Terms common in diffusion prompts / generic descriptions that carry little
# discriminating signal. Kept lowercase; matched against TF-IDF features.
DIFFUSION_STOP_WORDS = {
    # quality / boilerplate
    "masterpiece", "best", "quality", "high", "ultra", "detailed", "realistic",
    "photorealistic", "4k", "8k", "hd", "uhd", "sharp", "focus", "beautiful",
    "amazing", "perfect", "awesome", "good", "great", "nice", "fine", "excellent",
    "intricate", "highly", "extremely", "very", "most", "highly detailed",
    "best quality", "resolution", "render", "rendering",
    "cinematic", "lighting", "light", "shadow", "shadows", "studio", "professional",
    "illustration", "artwork", "art", "digital", "style", "styled", "trending",
    "artstation", "deviantart", "pixiv", "concept", "negative", "prompt",
    "lora", "checkpoint", "steps", "cfg", "sampler", "seed", "size",
    # body parts and anatomy that show up in almost every portrait prompt
    "eyes", "eye", "hair", "face", "skin", "lips", "mouth", "nose", "ears",
    "teeth", "tongue", "neck", "shoulders", "shoulder", "chest", "back",
    "arms", "arm", "hands", "hand", "fingers", "finger", "legs", "leg",
    "feet", "foot", "body", "head", "expression", "features",
    # ubiquitous descriptive filler
    "looking", "wearing", "standing", "sitting", "holding", "behind", "front",
    "side", "above", "below", "near", "next", "across", "view", "shot",
    "scene", "image", "picture", "photo", "background", "foreground",
    "color", "colors", "colored", "white", "black", "dark", "bright",
    "soft", "smooth", "gentle", "subtle", "small", "large", "wide", "long",
    "young", "old", "tall", "short",
}

# Words to exclude from proper-noun extraction (capitalized but not names).
PROPER_NOUN_BLOCKLIST = {
    "A", "An", "The", "And", "Or", "But", "In", "On", "At", "Of", "To", "For",
    "With", "By", "From", "As", "Is", "Are", "Was", "Were", "Be", "Been",
    "Her", "His", "Their", "She", "He", "They", "It", "This", "That",
    "Behind", "Above", "Below", "Near", "Next", "Across",
    "Negative", "Positive", "Prompt",
}

SKLEARN_STOP_WORDS = "english"

# Capitalized word or multi-word phrase: "Emilia", "Studio Ghibli",
# "Hatsune Miku". Disallows the leading word being a sentence-starter
# blocklist member.
PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)*\b")


def _clean_text(text: str) -> str:
    """Normalize text for TF-IDF."""
    text = text.lower()
    text = re.sub(r"[<>\[\]{}()|\\/:;\"'`~@#$%^&*+=]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _strip_for_proper_nouns(text: str) -> str:
    """Strip punctuation but preserve case so PROPER_NOUN_RE can match.

    Slashes and similar token-joining punctuation are replaced with " . " so
    PROPER_NOUN_RE can't pull `Hall/Entryway` into a single multi-word phrase
    (the leading `.` breaks the multi-word continuation in the regex).
    """
    text = re.sub(r"[<>\[\]{}()|\\/:;\"'`~@#$%^&*+=]", " . ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_proper_nouns(text: str) -> List[str]:
    """Pull capitalized words and phrases from original-case text."""
    if not text:
        return []
    cleaned = _strip_for_proper_nouns(text)
    found = []
    for match in PROPER_NOUN_RE.finditer(cleaned):
        phrase = match.group(0)
        # Filter: at least one token must be outside the blocklist
        tokens = phrase.split()
        if all(t in PROPER_NOUN_BLOCKLIST for t in tokens):
            continue
        # Single tokens that are blocklisted (e.g. a sentence-leading "The")
        if len(tokens) == 1 and tokens[0] in PROPER_NOUN_BLOCKLIST:
            continue
        found.append(phrase)
    return found


def _build_corpus(
    db: Session, image_ids: Optional[List[int]] = None
) -> List[Tuple[int, str, str]]:
    """Return list of (image_id, cleaned_text, original_text) tuples."""
    query = db.query(models.Image)
    if image_ids:
        query = query.filter(models.Image.id.in_(image_ids))

    corpus = []
    for img in query.all():
        parts = []
        if img.prompt:
            parts.append(img.prompt)
        if img.description:
            parts.append(img.description)
        original = " ".join(parts).strip()
        if original:
            corpus.append((img.id, _clean_text(original), original))
    return corpus


def auto_tag_images(
    db: Session,
    image_ids: Optional[List[int]] = None,
    top_n: int = 8,
    max_proper_nouns: int = 5,
):
    """
    Tag images via two complementary signals:
      1. TF-IDF over prompts/descriptions for distinctive content terms.
      2. Capitalized phrases from the original text as proper-noun tags
         (character/place/brand names).
    """
    corpus = _build_corpus(db, image_ids)
    if len(corpus) < 2:
        logger.info("Not enough images with text for TF-IDF; skipping.")
        return

    ids = [c[0] for c in corpus]
    texts = [c[1] for c in corpus]
    originals = [c[2] for c in corpus]

    # Proper-noun extraction is independent of TF-IDF. Track corpus-wide counts
    # so we can drop one-off matches that are likely OCR/typo noise.
    per_image_proper: List[List[str]] = [_extract_proper_nouns(o) for o in originals]
    proper_counts: Counter = Counter()
    for nouns in per_image_proper:
        for n in set(nouns):
            proper_counts[n] += 1

    # Sentence-starters ("Bold", "Half", "Playing") look capitalized but also
    # appear lowercase elsewhere in the corpus. Real proper nouns ("Emilia",
    # "Bauhaus") almost never appear lowercased. Filter single-word candidates
    # whose lowercase form is roughly as common as the capitalized one.
    lowercase_word_counts: Counter = Counter()
    for cleaned_text in texts:
        for word in re.findall(r"\b[a-z]{3,}\b", cleaned_text):
            lowercase_word_counts[word] += 1

    def _is_likely_proper(noun: str) -> bool:
        tokens = noun.split()
        # Multi-word capitalized phrases are reliable signals on their own.
        if len(tokens) > 1:
            return True
        word = tokens[0].lower()
        cap = proper_counts[noun]
        low = lowercase_word_counts.get(word, 0)
        # Allow if capitalized clearly dominates (3x) — real names rarely
        # appear lowercase.
        return cap >= max(2, low * 3)

    try:
        vectorizer = TfidfVectorizer(
            stop_words=SKLEARN_STOP_WORDS,
            max_features=500,
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.4,
            sublinear_tf=True,
            token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b",
        )
        tfidf_matrix = vectorizer.fit_transform(texts)
    except ValueError as e:
        # Tiny corpora can fail min_df > max_df; fall back to looser settings.
        logger.warning(f"TF-IDF strict pass failed ({e}); retrying with loose settings.")
        try:
            vectorizer = TfidfVectorizer(
                stop_words=SKLEARN_STOP_WORDS,
                max_features=500,
                ngram_range=(1, 2),
                min_df=1,
                max_df=1.0,
                sublinear_tf=True,
                token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b",
            )
            tfidf_matrix = vectorizer.fit_transform(texts)
        except Exception as e2:
            logger.warning(f"TF-IDF vectorization failed: {e2}")
            return
    except Exception as e:
        logger.warning(f"TF-IDF vectorization failed: {e}")
        return

    feature_names = vectorizer.get_feature_names_out()

    tag_cache: Dict[str, models.Tag] = {}

    def get_or_create_tag(name: str) -> models.Tag:
        if name in tag_cache:
            return tag_cache[name]
        tag = db.query(models.Tag).filter(models.Tag.name == name).first()
        if not tag:
            tag = models.Tag(name=name)
            db.add(tag)
            db.flush()
        tag_cache[name] = tag
        return tag

    for idx, image_id in enumerate(ids):
        img = db.query(models.Image).filter(models.Image.id == image_id).first()
        if img is None:
            continue

        existing_tag_names: Set[str] = {t.name for t in img.tags}

        # --- TF-IDF terms ---
        row = tfidf_matrix[idx].toarray()[0]
        top_indices = np.argsort(row)[::-1]
        assigned = 0
        for fi in top_indices:
            if assigned >= top_n:
                break
            score = row[fi]
            if score == 0:
                break
            term = feature_names[fi]
            if term in DIFFUSION_STOP_WORDS:
                continue
            if re.fullmatch(r"[0-9\s]+", term):
                continue
            if term in existing_tag_names:
                assigned += 1
                continue
            tag = get_or_create_tag(term)
            img.tags.append(tag)
            existing_tag_names.add(term)
            assigned += 1

        # --- Proper nouns ---
        # Rank this image's proper nouns by corpus frequency (more shared = more
        # likely a real recurring entity), break ties by phrase length.
        nouns = sorted(
            set(per_image_proper[idx]),
            key=lambda n: (-proper_counts[n], -len(n)),
        )
        added_nouns = 0
        for noun in nouns:
            if added_nouns >= max_proper_nouns:
                break
            # Drop singletons in larger corpora — likely sentence-starters.
            if proper_counts[noun] < 2 and len(ids) >= 10:
                continue
            if not _is_likely_proper(noun):
                continue
            tag_name = noun.lower()
            if tag_name in DIFFUSION_STOP_WORDS:
                continue
            if tag_name in existing_tag_names:
                added_nouns += 1
                continue
            tag = get_or_create_tag(tag_name)
            img.tags.append(tag)
            existing_tag_names.add(tag_name)
            added_nouns += 1

    db.commit()
    logger.info(
        f"Auto-tagged {len(ids)} images "
        f"(proper nouns seen: {len(proper_counts)})."
    )
