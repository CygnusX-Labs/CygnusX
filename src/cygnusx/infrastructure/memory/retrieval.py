"""Rank-based fusion, independent of vector/lexical raw score scales."""

from dataclasses import replace

from cygnusx.infrastructure.memory.fact_store import MemoryFact


def reciprocal_rank_fusion(
    vectors: list[MemoryFact],
    keywords: list[MemoryFact],
    *,
    k: int = 60,
) -> list[MemoryFact]:
    if k < 1:
        raise ValueError("RRF k must be positive")
    facts: dict[int, MemoryFact] = {}
    scores: dict[int, float] = {}
    for lane in (vectors, keywords):
        seen: set[int] = set()
        rank = 0
        for fact in lane:
            if fact.id in seen:
                continue
            seen.add(fact.id)
            rank += 1
            facts.setdefault(fact.id, fact)
            scores[fact.id] = scores.get(fact.id, 0.0) + 1 / (k + rank)
    # Constant two-lane theoretical maximum, not each partition's observed max.
    # This keeps scores comparable when one partition has no vector hits.
    maximum = 2 / (k + 1)
    ranked = sorted(facts, key=lambda identity: scores[identity], reverse=True)
    return [
        replace(facts[identity], similarity=min(1.0, scores[identity] / maximum))
        for identity in ranked
    ]
