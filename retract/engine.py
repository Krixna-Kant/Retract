"""The truth-maintenance engine. Every decision here is a graph traversal.

Live definition (single source of truth):
  * a Source is live if revoked = false and quarantined = false
  * a Decision is live if status = 'ACTIVE'
  * a Claim is live if status in LIVE_CLAIM_STATUSES
  * a Claim is SUPPORTED (grounded) if there is a DERIVED_FROM path from it to a
    live Source or live Decision whose every intermediate node is a live Claim.
  * a live Claim with no grounded path loses its support and is retracted.

Grounded (well-founded) support is stricter than "at least one live parent":
two claims that only support each other are not supported, which a naive
one-hop fixpoint gets wrong (see eval/, method `naive_fixpoint`).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from .db import DEAD_CLAIM_STATUSES, LIVE_CLAIM_STATUSES, rows

MAX_DEPTH = 8

# A root that can ground a claim. `$xr` = roots hypothetically retracted.
ROOT_LIVE = (
    "((r:Source AND r.revoked = false AND coalesce(r.quarantined, false) = false)"
    " OR (r:Decision AND r.status = 'ACTIVE')) AND NOT r.id IN $xr"
)
# Intermediate nodes on a support path. `$xc` = claims hypothetically retracted.
MIDDLE_LIVE = "all(n IN nodes(p)[1..-1] WHERE n:Claim AND n.status IN $live AND NOT n.id IN $xc)"

RETRACTABLE = ("Source", "Decision", "Claim")
STATUS_FOR_ACTION = {"revoke": "INVALIDATED", "quarantine": "QUARANTINED", "reverse": "INVALIDATED",
                     "supersede": "SUPERSEDED", "retract": "INVALIDATED"}


def now() -> int:
    return int(time.time())


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------

def node_kind(g, node_id: str) -> str | None:
    """Return the label of a retractable node, using the id index per label."""
    for label in RETRACTABLE:
        if rows(g, f"MATCH (n:{label} {{id: $id}}) RETURN n.id AS id", {"id": node_id}):
            return label
    return None


def node_summary(g, node_id: str) -> dict | None:
    kind = node_kind(g, node_id)
    if not kind:
        return None
    r = rows(g, f"""
        MATCH (n:{kind} {{id: $id}})
        RETURN n.id AS id, coalesce(n.title, n.text) AS title, n.kind AS source_kind,
               n.status AS status, n.revoked AS revoked, n.quarantined AS quarantined,
               n.trust AS trust""", {"id": node_id})[0]
    r["kind"] = kind
    return r


# --------------------------------------------------------------------------
# Support
# --------------------------------------------------------------------------

def grounded_paths(g, claim_ids: list[str], xr: list[str] = (), xc: list[str] = ()) -> dict[str, list[str]]:
    """For each claim, the shortest grounded support path (node ids, claim first).

    Claims missing from the result have no grounded support under the
    hypothetical retraction of roots `xr` and claims `xc`.
    """
    if not claim_ids:
        return {}
    res = rows(g, f"""
        UNWIND $ids AS cid
        MATCH p = (c:Claim {{id: cid}})-[:DERIVED_FROM*1..{MAX_DEPTH}]->(r)
        WHERE NOT r:Claim AND {ROOT_LIVE} AND {MIDDLE_LIVE}
        WITH cid, p ORDER BY length(p)
        WITH cid, collect([n IN nodes(p) | n.id])[0] AS path
        RETURN cid, path""",
        {"ids": list(claim_ids), "xr": list(xr), "xc": list(xc), "live": LIVE_CLAIM_STATUSES})
    return {r["cid"]: r["path"] for r in res}


def explain_support(g, claim_id: str, limit: int = 12) -> dict:
    """Why do we believe this claim? All support paths to roots, marked live/dead."""
    claim = rows(g, """
        MATCH (c:Claim {id: $id})
        OPTIONAL MATCH (c)-[:ABOUT]->(s:System)
        OPTIONAL MATCH (a:Agent)-[:WROTE]->(c)
        RETURN c.id AS id, c.text AS text, c.status AS status, c.confidence AS confidence,
               c.invalidated_by AS invalidated_by, collect(DISTINCT s.name) AS systems,
               collect(DISTINCT a.id) AS written_by""", {"id": claim_id})
    if not claim:
        return {"found": False, "claim_id": claim_id}
    paths = rows(g, f"""
        MATCH p = (c:Claim {{id: $id}})-[:DERIVED_FROM*1..{MAX_DEPTH}]->(r)
        WHERE NOT r:Claim
        WITH p, r, length(p) AS hops
        ORDER BY hops LIMIT $limit
        RETURN [n IN nodes(p) | {{id: n.id, label: labels(n)[0], text: coalesce(n.title, n.text),
                                  status: n.status, revoked: n.revoked, quarantined: n.quarantined,
                                  kind: n.kind, trust: n.trust}}] AS nodes,
               hops,
               ((r:Source AND r.revoked = false AND coalesce(r.quarantined, false) = false)
                 OR (r:Decision AND r.status = 'ACTIVE'))
               AND all(n IN nodes(p)[1..-1] WHERE n.status IN $live) AS live""",
        {"id": claim_id, "limit": limit, "live": LIVE_CLAIM_STATUSES})
    contradicts = rows(g, """
        MATCH (c:Claim {id: $id})-[:CONTRADICTS]-(o:Claim)
        RETURN DISTINCT o.id AS id, o.text AS text, o.status AS status""", {"id": claim_id})
    decisions = rows(g, """
        MATCH (d:Decision)-[:SUPPORTED_BY]->(c:Claim {id: $id})
        RETURN d.id AS id, d.title AS title, d.status AS status""", {"id": claim_id})
    c = claim[0]
    live_paths = [p for p in paths if p["live"]]
    return {
        "found": True,
        "claim": c,
        "supported": bool(live_paths) and c["status"] in LIVE_CLAIM_STATUSES,
        "paths": paths,
        "live_paths": len(live_paths),
        "independent_roots": sorted({p["nodes"][-1]["id"] for p in live_paths}),
        "contradicts": contradicts,
        "supports_decisions": decisions,
    }


# --------------------------------------------------------------------------
# The cascade
# --------------------------------------------------------------------------

@dataclass
class Cascade:
    target: dict
    action: str
    new_status: str
    invalidated: list[dict] = field(default_factory=list)
    survived: list[dict] = field(default_factory=list)
    decisions_at_risk: list[dict] = field(default_factory=list)
    decisions_weakened: list[dict] = field(default_factory=list)
    owners: list[dict] = field(default_factory=list)
    stale_answers: list[dict] = field(default_factory=list)
    edges: list[list[str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "target": self.target, "action": self.action, "new_status": self.new_status,
            "invalidated": self.invalidated, "survived": self.survived,
            "decisions_at_risk": self.decisions_at_risk, "decisions_weakened": self.decisions_weakened,
            "owners": self.owners, "stale_answers": self.stale_answers, "edges": self.edges,
            "summary": f"{len(self.invalidated)} lose all support, {len(self.survived)} survive on "
                       f"independent support, {len(self.decisions_at_risk)} decision(s) left unsupported, "
                       f"{len(self.owners)} owner(s) to notify",
        }


def dependents(g, kind: str, target_id: str) -> list[dict]:
    """Every live claim that (transitively) derives from the target, with its shortest path to it.

    `via` is claim-first (claim -> ... -> target), like support paths.
    """
    res = rows(g, f"""
        MATCH p = (t:{kind} {{id: $id}})<-[:DERIVED_FROM*1..{MAX_DEPTH}]-(c:Claim)
        WHERE c.status IN $live
        WITH c, p ORDER BY length(p)
        WITH c, collect(p)[0] AS sp
        RETURN c.id AS id, c.text AS text, c.status AS status, length(sp) AS hops,
               [n IN nodes(sp) | n.id] AS via,
               [r IN relationships(sp) | [startNode(r).id, endNode(r).id]] AS edges
        ORDER BY hops, id""", {"id": target_id, "live": LIVE_CLAIM_STATUSES})
    for r in res:
        r["via"] = r["via"][::-1]
    return res


def preview(g, target_id: str, action: str = "revoke") -> Cascade:
    """Dry run: which claims lose all grounded support if `target_id` is retracted. Writes nothing."""
    target = node_summary(g, target_id)
    if not target:
        raise ValueError(f"unknown node {target_id!r}")
    kind = target["kind"]
    xr = [target_id] if kind in ("Source", "Decision") else []
    xc = [target_id] if kind == "Claim" else []

    deps = dependents(g, kind, target_id)
    support = grounded_paths(g, [d["id"] for d in deps], xr=xr, xc=xc)

    cas = Cascade(target=target, action=action, new_status=STATUS_FOR_ACTION.get(action, "INVALIDATED"))
    edge_set = set()
    for d in deps:
        for e in d.pop("edges"):
            edge_set.add(tuple(e))
        if d["id"] in support:
            path = support[d["id"]]
            d["support_path"] = path
            d["support_root"] = path[-1]
            cas.survived.append(d)
        else:
            cas.invalidated.append(d)
    for s in cas.survived:
        p = s["support_path"]
        edge_set.update(zip(p, p[1:]))
    cas.edges = [list(e) for e in sorted(edge_set)]

    dead = [d["id"] for d in cas.invalidated] + xc
    _impact(g, cas, dead)
    return cas


def _impact(g, cas: Cascade, dead: list[str]) -> None:
    """Who and what is affected by a set of claims dying: decisions, owners, past answers."""
    if not dead:
        return
    decisions = rows(g, """
        MATCH (d:Decision)-[:SUPPORTED_BY]->(c:Claim)
        WHERE c.id IN $dead AND d.status = 'ACTIVE'
        WITH DISTINCT d
        OPTIONAL MATCH (d)-[:SUPPORTED_BY]->(o:Claim)
        WHERE o.status IN $live AND NOT o.id IN $dead
        OPTIONAL MATCH (owner:Person)-[:OWNS]->(d)
        RETURN d.id AS id, d.title AS title, count(DISTINCT o) AS remaining_support,
               collect(DISTINCT owner.name) AS owners
        ORDER BY id""", {"dead": dead, "live": LIVE_CLAIM_STATUSES})
    cas.decisions_at_risk = [d for d in decisions if d["remaining_support"] == 0]
    cas.decisions_weakened = [d for d in decisions if d["remaining_support"] > 0]

    system_owners = rows(g, """
        MATCH (c:Claim)-[:ABOUT]->(s:System)<-[:OWNS]-(p:Person)
        WHERE c.id IN $dead
        RETURN p.id AS id, p.name AS name, p.team AS team, p.email AS email,
               collect(DISTINCT s.name) AS owns, collect(DISTINCT c.id) AS claims""", {"dead": dead})
    decision_owners = rows(g, """
        MATCH (p:Person)-[:OWNS]->(d:Decision)
        WHERE d.id IN $ids
        RETURN p.id AS id, p.name AS name, p.team AS team, p.email AS email,
               collect(DISTINCT d.id) AS decisions""", {"ids": [d["id"] for d in decisions]})
    owners: dict[str, dict] = {}
    for o in system_owners:
        owners[o["id"]] = {**o, "decisions": []}
    for o in decision_owners:
        owners.setdefault(o["id"], {**o, "owns": [], "claims": []})["decisions"] = o["decisions"]
    cas.owners = sorted(owners.values(), key=lambda o: (-len(o["claims"]), o["name"]))

    cas.stale_answers = rows(g, """
        MATCH (a:Answer)-[:CITED]->(c:Claim) WHERE c.id IN $dead
        OPTIONAL MATCH (u:Person)-[:ASKED]->(a)
        RETURN a.id AS id, a.question AS question, a.ts AS ts, u.name AS asked_by,
               collect(DISTINCT c.id) AS cited
        ORDER BY ts DESC""", {"dead": dead})


def apply(g, target_id: str, action: str = "revoke", reason: str = "", actor: str = "human") -> dict:
    """Write a retraction. Recomputes the cascade at apply time (never trusts a stale preview)."""
    cas = preview(g, target_id, action)
    kind = cas.target["kind"]
    ts = now()
    params = {"id": target_id, "reason": reason, "ts": ts, "actor": actor}
    if kind == "Source":
        flag = "quarantined" if action == "quarantine" else "revoked"
        g.query(f"""MATCH (s:Source {{id: $id}})
                    SET s.{flag} = true, s.revoked_reason = $reason, s.revoked_at = $ts, s.revoked_by = $actor""",
                params)
    elif kind == "Decision":
        new = "SUPERSEDED" if action == "supersede" else "REVERSED"
        g.query("""MATCH (d:Decision {id: $id})
                   SET d.prev_status = d.status, d.status = $new, d.changed_at = $ts, d.change_reason = $reason""",
                {**params, "new": new})
    else:
        g.query("""MATCH (c:Claim {id: $id})
                   SET c.prev_status = c.status, c.status = 'INVALIDATED', c.invalidated_at = $ts,
                       c.invalidated_by = $id, c.cascade = false""", params)

    ids = [c["id"] for c in cas.invalidated]
    if ids:
        g.query("""
            UNWIND $ids AS cid
            MATCH (c:Claim {id: cid}) WHERE c.status IN $live
            SET c.prev_status = c.status, c.status = $status, c.invalidated_at = $ts,
                c.invalidated_by = $id, c.cascade = true""",
                {"ids": ids, "live": LIVE_CLAIM_STATUSES, "status": cas.new_status, "ts": ts, "id": target_id})
    from .agents import auditor  # local import: auditor depends on engine
    audit = auditor.run(g)
    out = cas.to_dict()
    out["applied_at"] = ts
    out["audit"] = audit
    return out


def rollback(g, target_id: str) -> dict:
    """Undo a retraction: restore the target, then re-ground claims bottom-up until fixpoint."""
    kind = node_kind(g, target_id)
    if not kind:
        raise ValueError(f"unknown node {target_id!r}")
    if kind == "Source":
        g.query("""MATCH (s:Source {id: $id})
                   SET s.revoked = false, s.quarantined = false, s.revoked_reason = null""", {"id": target_id})
    elif kind == "Decision":
        g.query("""MATCH (d:Decision {id: $id}) WHERE d.prev_status IS NOT NULL
                   SET d.status = d.prev_status, d.prev_status = null""", {"id": target_id})
    else:
        g.query("""MATCH (c:Claim {id: $id}) WHERE c.prev_status IS NOT NULL
                   SET c.status = c.prev_status, c.prev_status = null, c.invalidated_by = null""",
                {"id": target_id})
    restored = restore_grounded(g)
    from .agents import auditor
    audit = auditor.run(g)
    return {"target": target_id, "restored": restored, "audit": audit}


def restore_grounded(g) -> list[str]:
    """Fixpoint: cascade-retracted claims that have regained a grounded path come back.

    Each round restores claims whose support path is grounded through currently
    live claims; restoring them can ground their dependents in the next round.
    """
    restored: list[str] = []
    while True:
        cands = [r["id"] for r in rows(g, """
            MATCH (c:Claim) WHERE c.cascade = true AND c.status IN $dead RETURN c.id AS id""",
            {"dead": DEAD_CLAIM_STATUSES})]
        back = list(grounded_paths(g, cands).keys())
        if not back:
            return restored
        g.query("""
            UNWIND $ids AS cid MATCH (c:Claim {id: cid})
            SET c.status = coalesce(c.prev_status, 'PROPOSED'), c.prev_status = null,
                c.invalidated_by = null, c.invalidated_at = null, c.cascade = false""", {"ids": back})
        restored += back


# --------------------------------------------------------------------------
# Decisions
# --------------------------------------------------------------------------

def decision_status(g, decision_id: str) -> dict:
    """Supersession chain around a decision and the decision currently in force."""
    chain = rows(g, """
        MATCH (d:Decision {id: $id})-[:SUPERSEDES*0..10]-(n:Decision)
        OPTIONAL MATCH (o:Person)-[:OWNS]->(n)
        RETURN DISTINCT n.id AS id, n.title AS title, n.status AS status, n.date AS date,
               collect(DISTINCT o.name) AS owners
        ORDER BY date""", {"id": decision_id})
    if not chain:
        return {"found": False, "decision_id": decision_id}
    current = rows(g, """
        MATCH (d:Decision {id: $id})<-[:SUPERSEDES*0..10]-(n:Decision)
        WHERE n.status = 'ACTIVE'
        RETURN n.id AS id, n.title AS title, n.date AS date ORDER BY n.date DESC LIMIT 1""",
        {"id": decision_id})
    edges = rows(g, """
        MATCH (d:Decision {id: $id})-[:SUPERSEDES*0..10]-(n:Decision)
        MATCH (n)-[:SUPERSEDES]->(m:Decision)
        RETURN DISTINCT n.id AS newer, m.id AS older""", {"id": decision_id})
    support = rows(g, """
        MATCH (d:Decision {id: $id})-[:SUPPORTED_BY]->(c:Claim)
        RETURN c.id AS id, c.text AS text, c.status AS status""", {"id": decision_id})
    asked = next(c for c in chain if c["id"] == decision_id)
    cur = current[0] if current else None
    return {
        "found": True,
        "decision": asked,
        "chain": chain,
        "edges": [[e["newer"], e["older"]] for e in edges],
        "in_force": cur,
        "is_current": bool(cur and cur["id"] == decision_id),
        "supported_by": support,
        "live_support": sum(1 for s in support if s["status"] in LIVE_CLAIM_STATUSES),
    }


# --------------------------------------------------------------------------
# Company-brain queries
# --------------------------------------------------------------------------

def owners_at_risk(g, claim_ids: list[str]) -> list[dict]:
    return rows(g, """
        MATCH (c:Claim)-[:ABOUT]->(sys:System)<-[:OWNS]-(p:Person)
        WHERE c.id IN $ids
        RETURN p.id AS id, p.name AS name, p.team AS team, count(DISTINCT c) AS n,
               collect(DISTINCT sys.name) AS systems
        ORDER BY n DESC, name""", {"ids": list(claim_ids)})


def who_knows(g, system: str) -> dict:
    """Owners of a system plus people whose authored sources ground live claims about it."""
    sys_rows = rows(g, """
        MATCH (s:System) WHERE s.id = $q OR toLower(s.name) = toLower($q)
        OPTIONAL MATCH (o:Person)-[:OWNS]->(s)
        RETURN s.id AS id, s.name AS name, collect(DISTINCT o.name) AS owners""", {"q": system})
    if not sys_rows:
        return {"found": False, "system": system}
    s = sys_rows[0]
    experts = rows(g, """
        MATCH (s:System {id: $id})<-[:ABOUT]-(c:Claim)-[:DERIVED_FROM*1..4]->(src:Source)<-[:AUTHORED]-(p:Person)
        WHERE c.status IN $live AND src.revoked = false AND coalesce(src.quarantined, false) = false
        RETURN p.id AS id, p.name AS name, p.team AS team, count(DISTINCT c) AS live_claims,
               collect(DISTINCT src.id) AS sources
        ORDER BY live_claims DESC, name LIMIT 8""", {"id": s["id"], "live": LIVE_CLAIM_STATUSES})
    return {"found": True, "system": s, "experts": experts}


def blast_radius(g, limit: int = 10) -> list[dict]:
    """Rank live sources by how many claims would lose all support if each were revoked.

    These are the single points of failure in the company's knowledge.
    """
    sources = rows(g, """
        MATCH (s:Source) WHERE s.revoked = false AND coalesce(s.quarantined, false) = false
        OPTIONAL MATCH (s)<-[:DERIVED_FROM]-(c:Claim)
        RETURN s.id AS id, s.title AS title, s.kind AS kind, s.trust AS trust, count(c) AS direct
        ORDER BY direct DESC""")
    out = []
    for s in sources:
        if not s["direct"]:
            continue
        cas = preview(g, s["id"])
        s["would_invalidate"] = len(cas.invalidated)
        s["would_survive"] = len(cas.survived)
        s["decisions_at_risk"] = len(cas.decisions_at_risk)
        out.append(s)
    out.sort(key=lambda x: (-x["would_invalidate"], -x["direct"]))
    return out[:limit]


def foundational_sources(g, limit: int = 10) -> list[dict]:
    """PageRank over DERIVED_FROM: rank roots by how much knowledge flows from them."""
    res = rows(g, """
        CALL algo.pageRank(NULL, 'DERIVED_FROM') YIELD node, score
        WITH node, score WHERE node:Source OR node:Decision
        RETURN node.id AS id, coalesce(node.title, node.id) AS title, labels(node)[0] AS label, score
        ORDER BY score DESC LIMIT $limit""", {"limit": limit})
    return res


def bus_factor(g) -> list[dict]:
    """Per system: how many distinct people authored the live sources its live claims rest on."""
    return rows(g, f"""
        MATCH (s:System)<-[:ABOUT]-(c:Claim)-[:DERIVED_FROM*1..{MAX_DEPTH}]->(src:Source)<-[:AUTHORED]-(p:Person)
        WHERE c.status IN $live AND src.revoked = false AND coalesce(src.quarantined, false) = false
        WITH s, collect(DISTINCT p.name) AS knowers, count(DISTINCT c) AS claims
        OPTIONAL MATCH (o:Person)-[:OWNS]->(s)
        RETURN s.id AS id, s.name AS system, size(knowers) AS bus_factor, knowers, claims,
               collect(o.name) AS owners
        ORDER BY bus_factor, system""", {"live": LIVE_CLAIM_STATUSES})


def trace_source(g, source_id: str) -> dict:
    """Provenance of a source: who authored it, its trust, and everything built on it."""
    src = rows(g, """
        MATCH (s:Source {id: $id})
        OPTIONAL MATCH (p:Person)-[:AUTHORED]->(s)
        RETURN s.id AS id, s.title AS title, s.kind AS kind, s.trust AS trust, s.sender AS sender,
               s.revoked AS revoked, s.quarantined AS quarantined, s.text AS text,
               collect(p.name) AS authors""", {"id": source_id})
    if not src:
        return {"found": False, "source_id": source_id}
    deps = dependents(g, "Source", source_id)
    for d in deps:
        d.pop("edges", None)
    conflicts = rows(g, f"""
        MATCH (s:Source {{id: $id}})<-[:DERIVED_FROM*1..{MAX_DEPTH}]-(c:Claim)-[:CONTRADICTS]-(o:Claim)
        RETURN DISTINCT c.id AS claim, o.id AS contradicts, o.text AS other_text""", {"id": source_id})
    return {"found": True, "source": src[0], "dependents": deps, "conflicts": conflicts}


def to_json(obj) -> str:
    return json.dumps(obj, default=str)
