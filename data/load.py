"""Load a validated dataset into its own tenant graph.

All initial claims are written as PROPOSED by the ingest agent. Statuses are
then produced by the engine itself: decision history is replayed through
`engine.apply(..., 'supersede')` and the auditor confirms or contests claims.

Run: python -m data.load            (loads northwind + bluefin)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.generate import build, build_bluefin  # noqa: E402
from data.validate import validate  # noqa: E402
from retract import engine  # noqa: E402
from retract.agents import auditor  # noqa: E402
from retract.db import reset_graph  # noqa: E402


def _ts(date: str) -> int:
    return int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp())


def load(data: dict, tenant: str | None = None) -> dict:
    errors = validate(data)
    if errors:
        raise ValueError("dataset invalid:\n" + "\n".join(errors))
    tenant = tenant or data["tenant"]
    g = reset_graph(tenant)
    q = g.query

    q("UNWIND $rows AS r CREATE (:Team {id: r.id, name: r.name})", {"rows": data["teams"]})
    q("UNWIND $rows AS r CREATE (:Person {id: r.id, name: r.name, team: r.team, email: r.email})",
      {"rows": data["people"]})
    q("UNWIND $rows AS r CREATE (:System {id: r.id, name: r.name, aliases: r.aliases})", {"rows": data["systems"]})
    q("UNWIND $rows AS r CREATE (:Agent {id: r.id, role: r.role})", {"rows": data["agents"]})
    q("""UNWIND $rows AS r CREATE (:Source {id: r.id, kind: r.kind, title: r.title, text: r.text, ts: r.ts,
              trust: r.trust, sender: r.sender, revoked: false, quarantined: false, planted: r.planted})""",
      {"rows": [{**s, "ts": _ts(s["ts"])} for s in data["sources"]]})
    q("""UNWIND $rows AS r CREATE (:Claim {id: r.id, text: r.text, key: r.key, value: r.value,
              status: 'PROPOSED', confidence: 0.6, written_by: 'agent:ingest', created_at: r.ts,
              planted: r.planted})""",
      {"rows": [{**c, "ts": 0} for c in data["claims"]]})
    q("""UNWIND $rows AS r CREATE (:Decision {id: r.id, title: r.title, status: r.status, date: r.date,
              planted: r.planted})""", {"rows": data["decisions"]})
    q("""UNWIND $rows AS r CREATE (:Answer {id: r.id, question: r.question, ts: r.ts, outcome: r.outcome})""",
      {"rows": [{**a, "ts": _ts(a["ts"])} for a in data["answers"]]})

    e = data["edges"]
    for label in ("Source", "Claim", "Decision"):
        q(f"""UNWIND $rows AS r MATCH (c:Claim {{id: r.claim}}) MATCH (t:{label} {{id: r.target}})
              CREATE (c)-[:DERIVED_FROM]->(t)""", {"rows": e["DERIVED_FROM"]})
    q("""UNWIND $rows AS r MATCH (c:Claim {id: r.claim}) MATCH (s:System {id: r.system})
         CREATE (c)-[:ABOUT]->(s)""", {"rows": e["ABOUT"]})
    for label in ("System", "Decision"):
        q(f"""UNWIND $rows AS r MATCH (p:Person {{id: r.person}}) MATCH (t:{label} {{id: r.target}})
              CREATE (p)-[:OWNS]->(t)""", {"rows": e["OWNS"]})
    q("""UNWIND $rows AS r MATCH (p:Person {id: r.person}) MATCH (s:Source {id: r.source})
         CREATE (p)-[:AUTHORED]->(s)""", {"rows": e["AUTHORED"]})
    q("""UNWIND $rows AS r MATCH (p:Person {id: r.person}) MATCH (t:Team {id: r.team})
         CREATE (p)-[:MEMBER_OF]->(t)""", {"rows": e["MEMBER_OF"]})
    q("""UNWIND $rows AS r MATCH (d:Decision {id: r.decision}) MATCH (c:Claim {id: r.claim})
         CREATE (d)-[:SUPPORTED_BY]->(c)""", {"rows": e["SUPPORTED_BY"]})
    q("""UNWIND $rows AS r MATCH (d:Decision {id: r.decision}) MATCH (s:Source {id: r.source})
         CREATE (d)-[:RECORDED_IN]->(s)""", {"rows": e["RECORDED_IN"]})
    q("""MATCH (a:Agent {id: 'agent:ingest'}), (c:Claim) CREATE (a)-[:WROTE]->(c)""")
    q("""UNWIND $rows AS r MATCH (a:Answer {id: r.id}) MATCH (p:Person {id: r.asked_by})
         CREATE (p)-[:ASKED]->(a)
         WITH a, r UNWIND r.cited AS cid MATCH (c:Claim {id: cid}) CREATE (a)-[:CITED]->(c)""",
      {"rows": data["answers"]})
    q("""MATCH (a:Agent {id: 'agent:answer'}), (x:Answer) CREATE (a)-[:WROTE]->(x)""")

    history = []
    for h in data["history"]:
        q("""MATCH (n:Decision {id: $newer}), (o:Decision {id: $older}) CREATE (n)-[:SUPERSEDES]->(o)""", h)
        res = engine.apply(g, h["older"], action="supersede", reason=f"superseded by {h['newer']}",
                           actor="history-replay")
        history.append({"older": h["older"], "newer": h["newer"],
                        "superseded_claims": [c["id"] for c in res["invalidated"]]})
    audit = auditor.run(g)

    stats = g.query("""MATCH (c:Claim) RETURN c.status AS s, count(*) AS n ORDER BY s""").result_set
    return {"tenant": tenant, "audit": audit, "history": history, "claim_status": dict(stats)}


def load_all() -> list[dict]:
    return [load(build()), load(build_bluefin())]


if __name__ == "__main__":
    for r in load_all():
        print(json.dumps(r, indent=1))
