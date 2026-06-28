"""Retrieval selector — lexical + vector (002, T013). FR-007/008, research R9.

Two lanes over the indexes 01-infra already built: lexical ts_rank_cd over
content_fts (GIN), and vector cosine over pgvector embedding (ivfflat). A skill
is "applicable" when cosine ≥ RETRIEVAL_SIM_FLOOR OR it tops the lexical lane.
NOT the deferred P2.5 multi-lane reranker (Constitution XI).
Contract: contracts/retrieval.contract.md
"""
from __future__ import annotations

from dataclasses import dataclass, field

import psycopg

from fenrir.memory.embed import embed, to_pgvector
from fenrir.settings import get_settings


@dataclass
class SkillHit:
    skill_id: str
    name: str
    cosine: float
    lexical_rank: float


@dataclass
class AbstractionHit:
    abstraction_id: str
    cosine: float


@dataclass
class Retrieved:
    skills: list[SkillHit] = field(default_factory=list)
    episode_ids: list[str] = field(default_factory=list)
    top_skill: SkillHit | None = None
    abstractions: list[AbstractionHit] = field(default_factory=list)


def retrieve(conn: psycopg.Connection, query: str, *, limit: int = 5) -> Retrieved:
    """Run both lanes; return applicable skills (verified/stable preferred) + related episodes."""
    s = get_settings()
    vec = to_pgvector(embed(query))

    skills: list[SkillHit] = []
    with conn.cursor() as cur:
        # vector + lexical over skills; cosine distance = embedding <=> query, similarity = 1 - dist
        # skills has no stored content_fts (only the memory tables do) — compute it inline
        cur.execute(
            "SELECT id, name, 1 - (embedding <=> %s::vector) AS cosine, "
            "       ts_rank_cd(to_tsvector('simple', content), plainto_tsquery('simple', %s)) "
            "         AS lexrank "
            "FROM skills WHERE state IN ('stable','testing') "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (vec, query, vec, limit),
        )
        for sid, name, cosine, lexrank in cur.fetchall():
            skills.append(SkillHit(str(sid), name, float(cosine or 0), float(lexrank or 0)))

        # related episodes (vector lane) — for retrieval_frequency bump + context
        cur.execute(
            "SELECT id FROM short_term_memory ORDER BY embedding <=> %s::vector LIMIT %s",
            (vec, limit),
        )
        episode_ids = [str(r[0]) for r in cur.fetchall()]

        # consolidated abstractions (003 C, reuse instrumentation): surface generalized
        # long_term_memory rows produced by competitive replay, so consolidated knowledge is
        # actually reachable by later tasks. Applicable when cosine ≥ RETRIEVAL_SIM_FLOOR.
        cur.execute(
            "SELECT id, 1 - (embedding <=> %s::vector) AS cosine FROM long_term_memory "
            "WHERE memory_type = 'semantic' AND abstraction_level >= 2 AND is_anchor = false "
            "  AND embedding IS NOT NULL "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (vec, vec, limit),
        )
        abstractions = [
            AbstractionHit(str(aid), float(cos or 0))
            for aid, cos in cur.fetchall()
            if float(cos or 0) >= s.RETRIEVAL_SIM_FLOOR
        ]

    # reactivation (003 B, FR-009): surfacing an episode resets its decay clock so
    # forgetting is reversible by renewed relevance. Additive — stored salience untouched.
    if episode_ids:
        from fenrir.memory.salience import reactivate

        reactivate(conn, episode_ids)

    applicable = [
        h for h in skills if h.cosine >= s.RETRIEVAL_SIM_FLOOR or h.lexical_rank > 0
    ]
    applicable.sort(key=lambda h: (h.cosine, h.lexical_rank), reverse=True)
    return Retrieved(
        skills=skills, episode_ids=episode_ids,
        top_skill=applicable[0] if applicable else None,
        abstractions=abstractions,
    )
