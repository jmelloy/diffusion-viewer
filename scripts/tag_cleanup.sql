-- Tag cleanup queries.
--
-- Goal: for each tag, surface its parent and the other tags that ride along
-- on the same images, so we can spot:
--   * redundant tags (tag A always appears with tag B → merge or re-parent)
--   * obvious parent candidates (tag A's images are a strict subset of tag B's)
--   * orphan tags (no parent, but co-occur with a clear cluster)
--
-- Run with: sqlite3 backend/diffusion_viewer.db < scripts/tag_cleanup.sql

.headers on
.mode column

------------------------------------------------------------------------------
-- 1. Tag + parent + co-occurring tag, with counts and overlap ratios.
--    `co_count` is how many images share both tags.
--    `pct_of_tag` is what % of the tag's images also carry the co-tag —
--    values near 100% are the strongest cleanup candidates.
------------------------------------------------------------------------------
WITH tag_counts AS (
    SELECT tag_id, COUNT(*) AS n
    FROM image_tags
    GROUP BY tag_id
)
SELECT
    t.name                                                AS tag,
    p.name                                                AS parent,
    co.name                                               AS co_tag,
    cp.name                                               AS co_tag_parent,
    tc.n                                                  AS tag_uses,
    cc.n                                                  AS co_tag_uses,
    pair.co_count                                         AS co_count,
    ROUND(100.0 * pair.co_count / tc.n, 1)                AS pct_of_tag,
    ROUND(100.0 * pair.co_count / cc.n, 1)                AS pct_of_co_tag
FROM (
    SELECT a.tag_id AS tag_id, b.tag_id AS co_tag_id, COUNT(*) AS co_count
    FROM image_tags a
    JOIN image_tags b ON a.image_id = b.image_id AND a.tag_id <> b.tag_id
    GROUP BY a.tag_id, b.tag_id
) pair
JOIN tags        t  ON t.id  = pair.tag_id
JOIN tags        co ON co.id = pair.co_tag_id
LEFT JOIN tags   p  ON p.id  = t.parent_tag_id
LEFT JOIN tags   cp ON cp.id = co.parent_tag_id
JOIN tag_counts  tc ON tc.tag_id = t.id
JOIN tag_counts  cc ON cc.tag_id = co.id
WHERE pair.co_count >= 5            -- ignore noise
ORDER BY t.name, pct_of_tag DESC, pair.co_count DESC;

------------------------------------------------------------------------------
-- 2. Subsumption candidates: tag A's images are a (near-)subset of tag B's.
--    These are the strongest "merge or re-parent" signals. If pct_of_tag = 100
--    and the parent is NULL or different, B is probably the right parent.
------------------------------------------------------------------------------
WITH tag_counts AS (
    SELECT tag_id, COUNT(*) AS n FROM image_tags GROUP BY tag_id
),
pairs AS (
    SELECT a.tag_id AS tag_id, b.tag_id AS co_tag_id, COUNT(*) AS co_count
    FROM image_tags a
    JOIN image_tags b ON a.image_id = b.image_id AND a.tag_id <> b.tag_id
    GROUP BY a.tag_id, b.tag_id
)
SELECT
    t.name                                          AS tag,
    p.name                                          AS current_parent,
    co.name                                         AS subsumed_by,
    tc.n                                            AS tag_uses,
    cc.n                                            AS co_tag_uses,
    pairs.co_count                                  AS co_count,
    ROUND(100.0 * pairs.co_count / tc.n, 1)         AS pct_of_tag
FROM pairs
JOIN tags        t  ON t.id  = pairs.tag_id
JOIN tags        co ON co.id = pairs.co_tag_id
LEFT JOIN tags   p  ON p.id  = t.parent_tag_id
JOIN tag_counts  tc ON tc.tag_id = t.id
JOIN tag_counts  cc ON cc.tag_id = co.id
WHERE tc.n >= 5                                     -- skip tiny tags
  AND pairs.co_count * 1.0 / tc.n >= 0.9            -- ≥90% overlap
  AND cc.n > tc.n                                   -- co-tag is the broader one
  AND (p.id IS NULL OR p.id <> co.id)               -- not already parented to it
ORDER BY pct_of_tag DESC, tc.n DESC;
