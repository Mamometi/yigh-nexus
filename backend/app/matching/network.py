"""Build a small, readable collaboration network from the existing matching engine.

Scoring is unchanged (engine.score_pair). This module only decides which faculty
and which suggested links to show:
  1. filter faculty (school / research area / priority), skipping profiles with too
     little documented detail to match on;
  2. score every pair inside a candidate pool;
  3. keep the `size` faculty with the strongest suggested links;
  4. keep each node's top `edges_per_node` links (union), above `min_score`.
Edges are algorithm-generated suggestions, never verified collaborations.
"""
from __future__ import annotations

from itertools import combinations

from .config import DEFAULT_MIN_SCORE
from .engine import Profile, score_pair

POOL_CAP = 90  # bound the O(n^2) pairwise scoring


def _richness(p: Profile) -> float:
    return len(p.keywords) + 2 * len(p.priorities) + len(p.regions)


def _primary_priority(p: Profile):
    if not p.priorities:
        return None
    t = max(p.priorities.values(), key=lambda t: t.confidence)
    return {"name": t.name, "confidence": t.label}


def build_network(profiles: dict[int, Profile], weights: dict, *, school: str | None = None,
                  keyword: str | None = None, priority: str | None = None, size: int = 25,
                  edges_per_node: int = 3, min_score: float = DEFAULT_MIN_SCORE,
                  new_connections_only: bool = False) -> dict:
    cands = [p for p in profiles.values()
             if (not school or p.school == school)
             and (not keyword or keyword in p.keywords)
             and (not priority or priority in p.priorities)
             and _richness(p) >= 2]
    pool = sorted(cands, key=_richness, reverse=True)[:POOL_CAP]

    scored = {}
    for a, b in combinations(pool, 2):
        m = score_pair(a, b, weights)
        if m and m["score"] >= min_score and not (new_connections_only and m["already_coauthors"]):
            scored[(a.id, b.id)] = m

    # Pick the faculty whose top-3 suggested links are strongest.
    best: dict[int, list[float]] = {p.id: [] for p in pool}
    for (x, y), m in scored.items():
        best[x].append(m["score"]); best[y].append(m["score"])
    strength = {i: sum(sorted(v, reverse=True)[:3]) for i, v in best.items()}
    chosen = {i for i in sorted(strength, key=strength.get, reverse=True)[:size] if strength[i] > 0}

    # Keep each chosen node's strongest links within the chosen set.
    keep = set()
    for i in chosen:
        mine = sorted(((k, m["score"]) for k, m in scored.items() if i in k and k[0] in chosen and k[1] in chosen),
                      key=lambda t: -t[1])
        keep.update(k for k, _ in mine[:edges_per_node])

    degree = {i: 0 for i in chosen}
    edges = []
    for (x, y) in sorted(keep, key=lambda k: -scored[k]["score"]):
        m = scored[(x, y)]
        degree[x] += 1; degree[y] += 1
        edges.append({"id": f"{x}-{y}", "source": x, "target": y, "score": m["score"],
                      "already_coauthors": m["already_coauthors"], "summary": m["summary"], "highlights": m["highlights"],
                      "breakdown": m["breakdown"], "reasons": m["reasons"]})

    nodes = [{"id": p.id, "name": p.name, "title": p.title, "school": p.school,
              "departments": sorted(p.departments), "primary_priority": _primary_priority(p),
              "priorities": sorted(p.priorities), "keywords": sorted(p.keywords, key=lambda k: -p.keywords[k].confidence)[:6],
              "degree": degree[p.id], "profile_url": p.source_url}
             for p in sorted((profiles[i] for i in chosen), key=lambda p: p.name)]
    return {"nodes": nodes, "edges": edges, "candidates": len(cands), "pool": len(pool)}
