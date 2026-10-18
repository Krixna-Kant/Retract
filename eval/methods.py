"""Methods compared in the mini evaluation. Each returns the predicted set of
claims that lose validity when `target` is retracted.

  keyword_topk     retrieval only: full-text top-k claims similar to the revoked text
  llm_topk         retrieval + LLM judgement (the common "RAG memory" approach)
  one_hop          graph, direct dependents only, no support check
  transitive       graph, every descendant, no support check
  naive_fixpoint   graph, iterate "has at least one live parent" to a fixpoint
  retract          graph, grounded support (the RETRACT engine)
"""
from __future__ import annotations

import re

from retract import engine, llm as L
from retract.db import LIVE_CLAIM_STATUSES, rows

STOP = {"the", "a", "an", "is", "are", "of", "for", "to", "in", "on", "and", "or", "our", "we", "be", "by",
        "can", "with", "per", "all", "no", "not", "it", "at", "as", "from", "this", "that", "has", "have"}


def _target_text(g, target: str) -> str:
    r = rows(g, """MATCH (n) WHERE (n:Source OR n:Decision OR n:Claim) AND n.id = $id
                   RETURN coalesce(n.text, n.title) AS t""", {"id": target})
    return r[0]["t"] if r else ""


def _ft(text: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 2]
    return "|".join(dict.fromkeys(words)) or "none"


def keyword_topk(g, target: str, k: int = 3) -> set[str]:
    res = rows(g, """
        CALL db.idx.fulltext.queryNodes('Claim', $q) YIELD node, score
        WHERE node.status IN $live
        RETURN node.id AS id, score ORDER BY score DESC LIMIT $k""",
        {"q": _ft(_target_text(g, target)), "live": LIVE_CLAIM_STATUSES, "k": k})
    return {r["id"] for r in res}


def llm_topk(g, target: str, k: int = 8) -> set[str]:
    text = _target_text(g, target)
    cands = rows(g, """
        CALL db.idx.fulltext.queryNodes('Claim', $q) YIELD node, score
        WHERE node.status IN $live
        RETURN node.id AS id, node.text AS text ORDER BY score DESC LIMIT $k""",
        {"q": _ft(text), "live": LIVE_CLAIM_STATUSES, "k": k})
    if not cands:
        return set()
    prompt = (f"A document our agent relied on has been retracted as wrong:\n\"{text}\"\n\n"
              f"Here are claims from the agent's memory:\n"
              + "\n".join(f"- {c['id']}: {c['text']}" for c in cands)
              + "\n\nWhich of these claims are no longer valid because of the retraction? "
                "Reply with a JSON array of claim ids only.")
    try:
        ids = L.llm_json(prompt)
    except Exception:
        return set()
    valid = {c["id"] for c in cands}
    return {i for i in ids if i in valid} if isinstance(ids, list) else set()


def one_hop(g, target: str) -> set[str]:
    return {r["id"] for r in rows(g, """
        MATCH (t {id: $id})<-[:DERIVED_FROM]-(c:Claim) WHERE c.status IN $live RETURN c.id AS id""",
        {"id": target, "live": LIVE_CLAIM_STATUSES})}


def transitive(g, target: str) -> set[str]:
    return {r["id"] for r in rows(g, f"""
        MATCH (t {{id: $id}})<-[:DERIVED_FROM*1..{engine.MAX_DEPTH}]-(c:Claim) WHERE c.status IN $live
        RETURN DISTINCT c.id AS id""", {"id": target, "live": LIVE_CLAIM_STATUSES})}


def naive_fixpoint(g, target: str) -> set[str]:
    """Flip a claim when none of its direct parents is live; repeat until stable."""
    cands = sorted(transitive(g, target))
    dead: set[str] = set()
    while True:
        res = rows(g, """
            UNWIND $ids AS cid
            MATCH (c:Claim {id: cid})
            OPTIONAL MATCH (c)-[:DERIVED_FROM]->(t)
            WHERE NOT t.id IN $dead
              AND ((t:Source AND t.revoked = false AND coalesce(t.quarantined, false) = false)
                   OR (t:Decision AND t.status = 'ACTIVE')
                   OR (t:Claim AND t.status IN $live))
            WITH c, count(t) AS live_parents WHERE live_parents = 0
            RETURN c.id AS id""",
            {"ids": [c for c in cands if c not in dead], "dead": sorted(dead | {target}),
             "live": LIVE_CLAIM_STATUSES})
        new = {r["id"] for r in res}
        if not new:
            return dead
        dead |= new


def retract(g, target: str) -> set[str]:
    return {c["id"] for c in engine.preview(g, target).invalidated}


METHODS = {
    "keyword_topk": keyword_topk,
    "llm_topk": llm_topk,
    "one_hop": one_hop,
    "transitive": transitive,
    "naive_fixpoint": naive_fixpoint,
    "retract": retract,
}
