"""Auditor agent: keeps claim status consistent with the graph.

Runs after every write. All rules are graph queries:
  1. Contradiction: two live claims with the same `key` and different `value`
     get a CONTRADICTS edge and both become CONTESTED. Nothing is overwritten.
  2. Resolution: a CONTESTED claim with no live contradicting partner is
     un-contested (its rival was retracted).
  3. Confirmation: a PROPOSED claim grounded in >= 2 distinct live roots is
     CONFIRMED (independent corroboration).
  4. Demotion: a CONFIRMED claim left with < 2 grounded roots goes back to
     PROPOSED (its corroboration was retracted).
"""
from __future__ import annotations

from ..db import LIVE_CLAIM_STATUSES, rows
from ..engine import MAX_DEPTH, now

AUDITOR = "agent:auditor"

_ROOTS = f"""
    MATCH p = (c)-[:DERIVED_FROM*1..{MAX_DEPTH}]->(r)
    WHERE NOT r:Claim
      AND ((r:Source AND r.revoked = false AND coalesce(r.quarantined, false) = false)
           OR (r:Decision AND r.status = 'ACTIVE'))
      AND all(n IN nodes(p)[1..-1] WHERE n:Claim AND n.status IN $live)
"""


def run(g) -> dict:
    p = {"live": LIVE_CLAIM_STATUSES, "ts": now(), "agent": AUDITOR}

    contradicted = rows(g, """
        MATCH (a:Claim), (b:Claim)
        WHERE a.key IS NOT NULL AND a.key = b.key AND a.value <> b.value AND a.id < b.id
          AND a.status IN $live AND b.status IN $live
        MERGE (a)-[x:CONTRADICTS]->(b)
        ON CREATE SET x.by = $agent, x.at = $ts
        WITH a, b
        SET a.prev_status = CASE WHEN a.status = 'CONTESTED' THEN a.prev_status ELSE a.status END,
            b.prev_status = CASE WHEN b.status = 'CONTESTED' THEN b.prev_status ELSE b.status END,
            a.status = 'CONTESTED', b.status = 'CONTESTED'
        RETURN a.id AS a, b.id AS b""", p)

    resolved = rows(g, """
        MATCH (c:Claim {status: 'CONTESTED'})
        OPTIONAL MATCH (c)-[:CONTRADICTS]-(o:Claim) WHERE o.status IN $live
        WITH c, count(o) AS rivals WHERE rivals = 0
        SET c.status = 'PROPOSED'
        RETURN c.id AS id""", p)

    confirmed = rows(g, f"""
        MATCH (c:Claim {{status: 'PROPOSED'}})
        {_ROOTS}
        WITH c, count(DISTINCT r) AS roots WHERE roots >= 2
        SET c.status = 'CONFIRMED', c.confirmed_by = $agent, c.confirmed_at = $ts,
            c.confidence = CASE WHEN roots >= 3 THEN 0.95 ELSE 0.85 END
        RETURN c.id AS id""", p)

    confirmed_now = rows(g, f"""
        MATCH (c:Claim {{status: 'CONFIRMED'}})
        {_ROOTS}
        RETURN DISTINCT c.id AS id, count(DISTINCT r) AS roots""", p)
    keep = [r["id"] for r in confirmed_now if r["roots"] >= 2]
    demoted = rows(g, """
        MATCH (c:Claim {status: 'CONFIRMED'}) WHERE NOT c.id IN $keep
        SET c.status = 'PROPOSED', c.confidence = 0.6
        RETURN c.id AS id""", {**p, "keep": keep})

    return {
        "contested": sorted({x for r in contradicted for x in (r["a"], r["b"])}),
        "resolved": [r["id"] for r in resolved],
        "confirmed": [r["id"] for r in confirmed],
        "demoted": [r["id"] for r in demoted],
    }
