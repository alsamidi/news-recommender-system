"""Topic selection for the 0-view feed (PRD addendum v1.2).

Contract (approved scope decisions C1–C7):

- **C1** Only a regular user with zero `view` events is affected. Personas and
  anyone with history never see this feed.
- **C3/C4** Candidate SELECTION only. No `POST /recommend` call, no scores, no
  re-ranking: every list here is a filtered slice of the frozen popularity
  ranking built once at startup (`services/popular.py`).
- **C5** Preferences are profile data (`user_topics`), never events. They never
  reach the research pipeline or ALS.
- **C6** The moment the user has one `view`, the v1.1 priority order resumes
  and the preference becomes inert.
- **C7** The label is "Populer di topik pilihanmu" — popularity within a
  topic, not model output.

Why the chip set is measured, not curated by taste
--------------------------------------------------
`TOPIC_LABELS` is the deterministic rule from addendum §3, reproduced against
the active corpus:

    chips = categories with >= 50 train-viewed items in the effective band
            minus {Berita, Info Tempo, Bersponsor}

`Berita` is a catch-all that personalizes nothing; `Info Tempo` is an editorial
service bucket; `Bersponsor` is sponsored content. The excluded categories are
either below the pool threshold (Otomotif, Investigasi) or empty in the band
(Pemilu, Ramadan). `test_topics.py` re-derives the set from the parquet files,
so a corpus re-lock that changes the answer fails loudly instead of silently
dropping a chip.

Canonical order matters: `position` in `user_topics` is this order, not click
order, because an HTML multi-select submits in DOM order.
"""
from __future__ import annotations

# Order = addendum §3 TABLE order (band size descending): 4,862 Berita is
# excluded, then Politik 2,339 ... Lingkungan 420, Teroka 413, Tekno-Sains 395.
# The addendum's prose summary listed Tekno-Sains before Lingkungan/Teroka,
# contradicting its own table; the measured table wins, and `test_topics.py`
# re-derives this exact order from the parquet. Do not sort alphabetically:
# `position` is persisted, so reordering rewrites every stored row.
TOPIC_LABELS: tuple[str, ...] = (
    "Politik",
    "Hukum",
    "Ekonomi",
    "Multimedia",
    "Olahraga",
    "Hiburan",
    "Internasional",
    "Lingkungan",
    "Teroka",
    "Tekno-Sains",
    "Kolom",
    "Cek Fakta",
)

# Upper bound, not an optimum. With a 12-card feed and q = ceil(12/m), the
# per-topic share is 12/m: 12 at m=1, 6 at m=2, 4 at m=3, 3 at m=4, 2 at m=5-6,
# 1 at m=7-12. The cap moved from 3 to 5 in v1.3 (owner decision) so a user can
# express a broader interest set while every chosen topic still gets >= 2 of
# 12 cards; beyond m=6 a topic drops to a single card and the slice stops
# reading as a preference. Full measured table: PRD addendum v1.2 §4.1.
MAX_TOPICS = 5
FEED_SIZE = 12

# Labels excluded by decision, with the reason kept next to the rule so the
# exclusion cannot be mistaken for an accident of the measurement.
NOT_OFFERED: dict[str, str] = {
    "Berita": "catch-all label; no personalisation",
    "Info Tempo": "editorial service bucket, not an interest",
    "Bersponsor": "sponsored content",
}

MIN_SEEN_FOR_CHIP = 50  # addendum §3 offer rule


class TopicUnavailable(ValueError):
    """Raised when a submitted label is not an offered chip."""


def canonicalize(labels) -> list[str]:
    """Validate submitted labels and return them in canonical order.

    Raises `TopicUnavailable` for anything outside the chip set. Duplicates
    collapse, because the same chip submitted twice is one preference.
    """
    submitted = {str(label) for label in labels if str(label)}
    unknown = submitted - set(TOPIC_LABELS)
    if unknown:
        raise TopicUnavailable(", ".join(sorted(unknown)))
    return [label for label in TOPIC_LABELS if label in submitted]


def slice_by_topic(popular_nids, catalog_category: dict[str, str],
                   labels: list[str]) -> list[str]:
    """Interleave the frozen popular list per topic, then top up globally.

    Exact definition from addendum §4:

    1. ``q = ceil(10 / m)`` per topic.
    2. Take the first ``q`` nids of each topic slice; interleave round-robin.
    3. If fewer than 10 remain, top up from the global frozen list, skipping
       nids already taken. A topped-up item is not labelled specially.
    4. Output gate is v1.1's: filter history -> dedupe -> keep order -> max 10.

    ``popular_nids`` must already be the frozen, catalog-only ranking; this
    function only filters and interleaves, so it cannot invent an order.
    """
    if not labels:
        return []

    q = -(-FEED_SIZE // len(labels))  # ceil division, integer maths only
    per_topic: dict[str, list[str]] = {label: [] for label in labels}
    for nid in popular_nids:
        category = catalog_category.get(nid)
        bucket = per_topic.get(category)
        if bucket is None:
            continue
        if len(bucket) < q:
            bucket.append(nid)
        if all(len(b) >= q for b in per_topic.values()):
            break

    picked: list[str] = []
    seen: set[str] = set()
    for rank in range(q):
        for label in labels:
            bucket = per_topic[label]
            if rank < len(bucket) and bucket[rank] not in seen:
                seen.add(bucket[rank])
                picked.append(bucket[rank])
                if len(picked) == FEED_SIZE:
                    return picked

    for nid in popular_nids:
        if nid in seen:
            continue
        seen.add(nid)
        picked.append(nid)
        if len(picked) == FEED_SIZE:
            break
    return picked
