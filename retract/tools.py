"""The fixed tool surface. Agents (LLM or rule-based) can only call these.

Every argument is validated against the graph before anything runs, and the
LLM never writes Cypher. Writes that change status or send something never
execute directly: they create a PENDING `Action` node that a human approves.
Approved actions keep an audit trail in the graph:
  (Action)-[:TARGETS]->(Source|Decision|Claim), (Action)-[:CHANGED]->(Claim)

Each tool returns {"result": ..., "nodes": [...], "edges": [[a, b], ...]} so
the UI can light up exactly what the traversal touched.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from . import engine
from .db import LIVE_CLAIM_STATUSES, rows

OUTBOX = Path(__file__).resolve().parent.parent / "outbox"

STOP = {"what", "which", "who", "why", "how", "when", "where", "does", "do", "did", "is", "are", "was", "were",
        "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "our", "we", "us", "it", "its", "be",
        "can", "use", "used", "using", "still", "current", "currently", "now", "today", "this", "that", "there",
        "with", "about", "any", "have", "has", "service", "tell", "me", "know", "should", "much", "many", "long",
        "true", "valid", "right", "correct", "per", "at", "by", "from", "get", "set", "value", "northwind"}
SYNONYMS = {"ttl": ["expire", "lifetime"], "expiry": ["expire"], "lifetime": ["expire"],
            "invoicing": ["invoice"], "provider": ["vendor"], "vendor": ["provider"],
            "url": ["endpoint"], "endpoint": ["webhook"], "uptime": ["sla"], "throttle": ["rate"],
            "queue": ["bus"], "messaging": ["bus"], "close": ["finance"]}


INTENT_ATTRS = {"use": ["technology", "provider", "engine", "language"], "run": ["technology", "engine"],
                 "runs": ["technology", "engine"], "provider": ["provider"], "vendor": ["provider"],
                 "ttl": ["token_ttl"], "expire": ["token_ttl"], "endpoint": ["webhook_endpoint"],
                 "retention": ["retention"], "owns": ["oncall"]}
STATUS_RANK = {"CONFIRMED": 0, "CONTESTED": 1, "PROPOSED": 2}

PAST = {"revoke": "revoked", "quarantine": "quarantined", "reverse": "reversed", "retract": "retracted",
        "supersede": "superseded"}


class ToolError(ValueError):
    pass


def _out(result, nodes=(), edges=()):
    return {"result": result, "nodes": sorted(set(n for n in nodes if n)), "edges": [list(e) for e in edges]}


def _need(g, node_id: str, labels: tuple[str, ...]) -> str:
    if not isinstance(node_id, str) or not re.fullmatch(r"[A-Za-z0-9:_\-]{1,64}", node_id or ""):
        raise ToolError(f"malformed id {node_id!r}")
    kind = engine.node_kind(g, node_id)
    if kind not in labels:
        raise ToolError(f"{node_id} is not a known {'/'.join(labels)}")
    return kind


def terms(text: str) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 1]
    return list(dict.fromkeys(words))


def coverage(question_terms: list[str], text: str) -> float:
    """Fraction of question terms that appear (by 5-char prefix or synonym) in the text."""
    if not question_terms:
        return 0.0
    low = text.lower()
    hit = 0
    for t in question_terms:
        forms = [t] + SYNONYMS.get(t, [])
        if any(f[:5] in low for f in forms):
            hit += 1
    return hit / len(question_terms)


# --------------------------------------------------------------------------
# Read tools
# --------------------------------------------------------------------------

def search_claims(g, query: str, k: int = 8) -> dict:
    """Full-text search over claim text (all statuses), with a relevance coverage score."""
    qt = terms(query)
    if not qt:
        return _out({"query": query, "claims": [], "decisions": []})
    expanded = list(dict.fromkeys(qt + [s for t in qt for s in SYNONYMS.get(t, [])]))
    ft = "|".join(f"{t}*" if len(t) > 3 else t for t in expanded)
    res = rows(g, """
        CALL db.idx.fulltext.queryNodes('Claim', $q) YIELD node, score
        OPTIONAL MATCH (node)-[:ABOUT]->(s:System)
        RETURN node.id AS id, node.text AS text, node.status AS status, node.key AS key,
               node.invalidated_by AS invalidated_by, score, collect(s.name) AS systems
        ORDER BY score DESC LIMIT 60""", {"q": ft})
    intents = {a for w, attrs in INTENT_ATTRS.items() if re.search(rf"\b{w}\b", query.lower()) for a in attrs}
    for r in res:
        r["coverage"] = round(coverage(qt, r["text"] + " " + " ".join(r["systems"])), 2)
        r["text_coverage"] = round(coverage(qt, r["text"]), 2)
        r["live"] = r["status"] in LIVE_CLAIM_STATUSES
        r["intent"] = bool(r["key"] and r["key"].split(".")[-1] in intents)
    res.sort(key=lambda r: (-r["coverage"], -r["intent"], -r["text_coverage"], not r["live"],
                            STATUS_RANK.get(r["status"], 9), -r["score"]))
    live = [r for r in res if r["live"]][:k]
    dead = [r for r in res if not r["live"]][:3]
    res = sorted(live + dead, key=res.index)
    decisions = rows(g, """
        CALL db.idx.fulltext.queryNodes('Decision', $q) YIELD node, score
        RETURN node.id AS id, node.title AS title, node.status AS status, score
        ORDER BY score DESC LIMIT 4""", {"q": ft})
    for d in decisions:
        d["coverage"] = round(coverage(qt, d["title"]), 2)
    return _out({"query": query, "terms": qt, "claims": res, "decisions": decisions},
                nodes=[r["id"] for r in res])


def explain_support(g, claim_id: str) -> dict:
    _need(g, claim_id, ("Claim",))
    ex = engine.explain_support(g, claim_id)
    nodes, edges = [claim_id], []
    for p in ex["paths"]:
        ids = [n["id"] for n in p["nodes"]]
        nodes += ids
        edges += list(zip(ids, ids[1:]))
    for c in ex["contradicts"]:
        nodes.append(c["id"])
        edges.append((claim_id, c["id"]))
    return _out(ex, nodes, edges)


def decision_status(g, decision_id: str) -> dict:
    _need(g, decision_id, ("Decision",))
    st = engine.decision_status(g, decision_id)
    return _out(st, [c["id"] for c in st["chain"]] + [s["id"] for s in st["supported_by"]],
                st["edges"] + [(decision_id, s["id"]) for s in st["supported_by"]])


def preview_revocation(g, target_id: str, action: str = "revoke") -> dict:
    kind = _need(g, target_id, ("Source", "Decision", "Claim"))
    if kind == "Decision" and action == "revoke":
        action = "reverse"
    if kind == "Claim" and action == "revoke":
        action = "retract"
    cas = engine.preview(g, target_id, action).to_dict()
    nodes = [target_id] + [c["id"] for c in cas["invalidated"]] + [c["id"] for c in cas["survived"]]
    for c in cas["survived"]:
        nodes += c["support_path"]
    nodes += [d["id"] for d in cas["decisions_at_risk"] + cas["decisions_weakened"]]
    nodes += [o["id"] for o in cas["owners"]]
    return _out(cas, nodes, cas["edges"])


def owners_at_risk(g, claim_ids: list[str]) -> dict:
    ids = [c for c in claim_ids if isinstance(c, str)]
    known = [r["id"] for r in rows(g, "MATCH (c:Claim) WHERE c.id IN $ids RETURN c.id AS id", {"ids": ids})]
    res = engine.owners_at_risk(g, known)
    return _out(res, known + [r["id"] for r in res])


def who_knows(g, system: str) -> dict:
    res = engine.who_knows(g, system)
    if not res["found"]:
        raise ToolError(f"unknown system {system!r}")
    return _out(res, [res["system"]["id"]] + [e["id"] for e in res["experts"]])


def trace_source(g, source_id: str) -> dict:
    _need(g, source_id, ("Source",))
    res = engine.trace_source(g, source_id)
    nodes = [source_id] + [d["id"] for d in res["dependents"]]
    edges = []
    for d in res["dependents"]:
        edges += list(zip(d["via"], d["via"][1:]))
    for c in res["conflicts"]:
        nodes.append(c["contradicts"])
        edges.append((c["claim"], c["contradicts"]))
    return _out(res, nodes, edges)


# --------------------------------------------------------------------------
# Write tools: always go through a pending Action
# --------------------------------------------------------------------------

def request_action(g, kind: str, target_id: str, reason: str = "", requested_by: str = "agent:answer") -> dict:
    """Create a PENDING action with its preview. Nothing changes until `approve`."""
    if kind not in ("revoke", "quarantine", "reverse", "retract", "rollback"):
        raise ToolError(f"unknown action {kind!r}")
    tkind = _need(g, target_id, ("Source", "Decision", "Claim"))
    if kind in ("revoke", "quarantine") and tkind != "Source":
        raise ToolError(f"{kind} applies to sources; use reverse for decisions, retract for claims")
    if kind == "reverse" and tkind != "Decision":
        raise ToolError("reverse applies to decisions")
    if kind == "rollback":
        affected = rows(g, "MATCH (c:Claim {invalidated_by: $id}) RETURN count(c) AS n", {"id": target_id})[0]["n"]
        summary = f"restore {target_id} and re-ground {affected} claim(s) it took down"
        preview = {"restorable": affected}
    else:
        cas = engine.preview(g, target_id, kind).to_dict()
        summary = cas["summary"]
        preview = {"invalidated": [c["id"] for c in cas["invalidated"]],
                   "survived": [c["id"] for c in cas["survived"]],
                   "owners": [o["name"] for o in cas["owners"]]}
    aid = "ACT-" + uuid.uuid4().hex[:8].upper()
    g.query(f"""
        MATCH (t:{tkind} {{id: $tid}})
        CREATE (a:Action {{id: $id, kind: $kind, target: $tid, reason: $reason, status: 'PENDING',
                           requested_by: $by, created_at: $ts, summary: $summary, preview: $preview}})
        CREATE (a)-[:TARGETS]->(t)""",
            {"id": aid, "kind": kind, "tid": target_id, "reason": reason, "by": requested_by,
             "ts": engine.now(), "summary": summary, "preview": json.dumps(preview)})
    return _out({"action_id": aid, "status": "PENDING", "kind": kind, "target": target_id, "summary": summary,
                 "preview": preview, "note": "Requires human approval before anything changes."},
                [target_id] + preview.get("invalidated", []))


def list_actions(g, status: str | None = None) -> list[dict]:
    return rows(g, """
        MATCH (a:Action) WHERE $status IS NULL OR a.status = $status
        RETURN a.id AS id, a.kind AS kind, a.target AS target, a.reason AS reason, a.status AS status,
               a.summary AS summary, a.created_at AS created_at, a.decided_at AS decided_at,
               a.approved_by AS approved_by, a.drift AS drift
        ORDER BY a.created_at DESC""", {"status": status})


def approve(g, action_id: str, approver: str = "human") -> dict:
    act = rows(g, "MATCH (a:Action {id: $id}) RETURN a.kind AS kind, a.target AS target, a.reason AS reason, "
                  "a.status AS status, a.preview AS preview", {"id": action_id})
    if not act:
        raise ToolError(f"unknown action {action_id}")
    a = act[0]
    if a["status"] != "PENDING":
        raise ToolError(f"action {action_id} is {a['status']}")
    if a["kind"] == "rollback":
        result = engine.rollback(g, a["target"])
        changed, drift = result["restored"], False
    else:
        result = engine.apply(g, a["target"], action=a["kind"], reason=a["reason"] or "", actor=approver)
        changed = [c["id"] for c in result["invalidated"]]
        drift = sorted(changed) != sorted(json.loads(a["preview"]).get("invalidated", []))
        result["notifications"] = draft_notifications(g, result, action_id)
    g.query("""
        MATCH (a:Action {id: $id})
        SET a.status = 'APPROVED', a.approved_by = $by, a.decided_at = $ts, a.drift = $drift
        WITH a UNWIND $changed AS cid MATCH (c:Claim {id: cid}) CREATE (a)-[:CHANGED]->(c)""",
            {"id": action_id, "by": approver, "ts": engine.now(), "changed": changed, "drift": drift})
    result["action_id"] = action_id
    result["drift"] = drift
    return result


def reject(g, action_id: str, approver: str = "human") -> dict:
    res = rows(g, """MATCH (a:Action {id: $id, status: 'PENDING'})
                     SET a.status = 'REJECTED', a.approved_by = $by, a.decided_at = $ts
                     RETURN a.id AS id""", {"id": action_id, "by": approver, "ts": engine.now()})
    if not res:
        raise ToolError(f"no pending action {action_id}")
    return {"action_id": action_id, "status": "REJECTED"}


def draft_notifications(g, cascade: dict, action_id: str) -> list[dict]:
    """One DRAFT notification per affected owner and per person who received a now-stale answer."""
    target = cascade["target"]
    verb = PAST.get(cascade["action"], cascade["action"])
    drafts = []
    for o in cascade["owners"]:
        lines = [f"{target['id']} ({target.get('title')}) was {verb}."]
        if o.get("claims"):
            lines.append(f"{len(o['claims'])} claim(s) about {', '.join(o['owns']) or 'your systems'} "
                         f"lost all support: {', '.join(o['claims'])}.")
        if o.get("decisions"):
            lines.append(f"Decisions you own that relied on them: {', '.join(o['decisions'])}.")
        drafts.append({"to": o["id"], "name": o["name"], "email": o.get("email"),
                       "subject": f"[RETRACT] Knowledge you own changed: {target['id']}", "body": " ".join(lines),
                       "claims": o.get("claims", [])})
    for a in cascade.get("stale_answers", []):
        if not a.get("asked_by"):
            continue
        drafts.append({"to_name": a["asked_by"], "name": a["asked_by"],
                       "subject": f"[RETRACT] An answer you received is no longer supported",
                       "body": f"On {a['ts']} you asked \"{a['question']}\". The answer cited {', '.join(a['cited'])}, "
                               f"which lost its support when {target['id']} was {verb}.",
                       "claims": a["cited"], "answer": a["id"]})
    out = []
    for d in drafts:
        nid = "N-" + uuid.uuid4().hex[:8].upper()
        g.query("""
            CREATE (n:Notification {id: $id, subject: $subject, body: $body, status: 'DRAFT', created_at: $ts,
                                    action: $action, recipient: $name})
            WITH n
            OPTIONAL MATCH (p:Person) WHERE p.id = $to OR p.name = $name
            FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | CREATE (n)-[:TO]->(p))
            WITH n UNWIND $claims AS cid MATCH (c:Claim {id: cid}) CREATE (n)-[:CONCERNS]->(c)""",
                {"id": nid, "subject": d["subject"], "body": d["body"], "ts": engine.now(), "action": action_id,
                 "to": d.get("to", ""), "name": d["name"], "claims": d["claims"]})
        out.append({"id": nid, **d})
    if out:
        OUTBOX.mkdir(exist_ok=True)
        (OUTBOX / f"{action_id}.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out


def list_notifications(g) -> list[dict]:
    return rows(g, """
        MATCH (n:Notification)
        OPTIONAL MATCH (n)-[:TO]->(p:Person)
        OPTIONAL MATCH (n)-[:CONCERNS]->(c:Claim)
        RETURN n.id AS id, n.subject AS subject, n.body AS body, n.status AS status, n.created_at AS created_at,
               n.action AS action, coalesce(p.name, n.recipient) AS to, p.email AS email, collect(c.id) AS claims
        ORDER BY n.created_at DESC""")


def send_notifications(g, ids: list[str]) -> int:
    res = rows(g, """UNWIND $ids AS nid MATCH (n:Notification {id: nid, status: 'DRAFT'})
                     SET n.status = 'SENT', n.sent_at = $ts RETURN count(n) AS n""", {"ids": ids, "ts": engine.now()})
    return res[0]["n"] if res else 0


READ_TOOLS = {
    "search_claims": search_claims,
    "explain_support": explain_support,
    "decision_status": decision_status,
    "preview_revocation": preview_revocation,
    "owners_at_risk": owners_at_risk,
    "who_knows": who_knows,
    "trace_source": trace_source,
}

TOOL_SPECS = {
    "search_claims": "search_claims(query: str) - full-text search of remembered claims, all statuses",
    "explain_support": "explain_support(claim_id: str) - every DERIVED_FROM path from a claim to its sources",
    "decision_status": "decision_status(decision_id: str) - supersession chain and the decision in force",
    "preview_revocation": "preview_revocation(target_id: str) - dry run: what loses support if a source/decision is retracted",
    "owners_at_risk": "owners_at_risk(claim_ids: list[str]) - owners of systems those claims are about",
    "who_knows": "who_knows(system: str) - owners and people whose sources ground live claims about a system",
    "trace_source": "trace_source(source_id: str) - provenance, trust and everything built on a source",
    "request_action": "request_action(kind: revoke|quarantine|reverse|retract|rollback, target_id: str, reason: str) - "
                      "propose a write; a human must approve it",
}
