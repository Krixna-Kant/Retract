"""HTTP API for RETRACT. Run: uvicorn api.main:app --port 8000"""
from __future__ import annotations

import json
import queue
import sys
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from retract import engine, llm as L, tools as T  # noqa: E402
from retract.agents import AGENTS  # noqa: E402
from retract.agents import answer as answer_agent  # noqa: E402
from retract.agents import ingest as ingest_agent  # noqa: E402
from retract.db import CLAIM_STATUSES, LIVE_CLAIM_STATUSES, graph, list_tenants, rows  # noqa: E402

app = FastAPI(title="RETRACT", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def G(tenant: str):
    if tenant not in list_tenants():
        raise HTTPException(404, f"unknown tenant {tenant!r}")
    return graph(tenant)


def guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except (T.ToolError, ValueError) as e:
        raise HTTPException(400, str(e))


# --------------------------------------------------------------------------
# Read
# --------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "tenants": list_tenants(), "llm": L.provider()}


@app.get("/api/meta")
def meta(tenant: str = "northwind"):
    g = G(tenant)
    counts = rows(g, "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label")
    status = rows(g, "MATCH (c:Claim) RETURN c.status AS status, count(*) AS n ORDER BY status")
    edges = rows(g, "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY type")
    return {"tenant": tenant, "tenants": list_tenants(), "agents": AGENTS, "llm": L.provider(),
            "claim_statuses": CLAIM_STATUSES, "live_statuses": LIVE_CLAIM_STATUSES,
            "counts": {r["label"]: r["n"] for r in counts}, "status": {r["status"]: r["n"] for r in status},
            "edges": {r["type"]: r["n"] for r in edges}}


@app.get("/api/graph")
def full_graph(tenant: str = "northwind", answers: bool = True):
    g = G(tenant)
    labels = ["Claim", "Source", "Decision", "Person", "System", "Team"] + (["Answer"] if answers else [])
    nodes = rows(g, """
        MATCH (n) WHERE labels(n)[0] IN $labels
        RETURN n.id AS id, labels(n)[0] AS label, coalesce(n.name, n.title, n.text, n.question) AS name,
               n.status AS status, n.kind AS kind, n.trust AS trust, n.revoked AS revoked,
               n.quarantined AS quarantined, n.team AS team""", {"labels": labels})
    links = rows(g, """
        MATCH (a)-[r]->(b) WHERE labels(a)[0] IN $labels AND labels(b)[0] IN $labels
        RETURN a.id AS source, b.id AS target, type(r) AS type""", {"labels": labels})
    return {"nodes": nodes, "links": links}


@app.get("/api/node/{node_id}")
def node(node_id: str, tenant: str = "northwind"):
    g = G(tenant)
    kind = engine.node_kind(g, node_id)
    if kind == "Claim":
        return {"kind": kind, **T.explain_support(g, node_id)}
    if kind == "Source":
        return {"kind": kind, **T.trace_source(g, node_id)}
    if kind == "Decision":
        return {"kind": kind, **T.decision_status(g, node_id)}
    other = rows(g, """MATCH (n {id: $id}) RETURN labels(n)[0] AS label, properties(n) AS props""", {"id": node_id})
    if not other:
        raise HTTPException(404, "not found")
    return {"kind": other[0]["label"], "result": other[0]["props"], "nodes": [node_id], "edges": []}


@app.get("/api/targets")
def targets(tenant: str = "northwind"):
    g = G(tenant)
    sources = rows(g, """
        MATCH (s:Source) OPTIONAL MATCH (s)<-[:DERIVED_FROM]-(c:Claim)
        RETURN s.id AS id, s.title AS title, s.kind AS kind, s.trust AS trust, s.revoked AS revoked,
               s.quarantined AS quarantined, s.planted AS planted, count(c) AS dependents
        ORDER BY planted DESC, dependents DESC, id""")
    decisions = rows(g, """
        MATCH (d:Decision) RETURN d.id AS id, d.title AS title, d.status AS status, d.planted AS planted
        ORDER BY planted DESC, id""")
    people = rows(g, "MATCH (p:Person) RETURN p.id AS id, p.name AS name, p.team AS team ORDER BY id")
    return {"sources": sources, "decisions": decisions, "people": people}


@app.get("/api/insights")
def insights(tenant: str = "northwind"):
    g = G(tenant)
    return {"blast_radius": engine.blast_radius(g, 8), "foundational": engine.foundational_sources(g, 8),
            "bus_factor": engine.bus_factor(g)}


@app.get("/api/answers")
def answers(tenant: str = "northwind"):
    g = G(tenant)
    return rows(g, """
        MATCH (a:Answer)
        OPTIONAL MATCH (u:Person)-[:ASKED]->(a)
        OPTIONAL MATCH (a)-[:CITED]->(c:Claim)
        WITH a, u, collect(c) AS cs
        RETURN a.id AS id, a.question AS question, a.outcome AS outcome, a.ts AS ts, u.name AS asked_by,
               [x IN cs | x.id] AS cited,
               [x IN cs WHERE NOT x.status IN $live | x.id] AS no_longer_supported
        ORDER BY a.ts DESC LIMIT 50""", {"live": LIVE_CLAIM_STATUSES})


@app.get("/api/eval")
def eval_results():
    p = ROOT / "eval" / "results.json"
    if not p.exists():
        raise HTTPException(404, "run python -m eval.run_eval first")
    return json.loads(p.read_text(encoding="utf-8"))


@app.get("/api/template")
def dataset_template():
    return json.loads((ROOT / "data" / "template.json").read_text(encoding="utf-8"))


@app.get("/api/mcp")
def mcp_info():
    try:
        import asyncio
        from retract.mcp_server import mcp
        tools = [{"name": t.name, "description": (t.description or "").split("\n")[0]}
                 for t in asyncio.run(mcp.list_tools())]
        err = ""
    except Exception as e:  # mcp not installed
        tools, err = [], str(e)
    config = {"mcpServers": {"retract": {"command": sys.executable, "args": ["-m", "retract.mcp_server"],
                                         "cwd": str(ROOT)}}}
    return {"tools": tools, "config": config, "error": err}


# --------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------

class AskIn(BaseModel):
    tenant: str = "northwind"
    question: str = Field(min_length=2, max_length=500)
    user: str | None = None


@app.post("/api/ask")
def ask(body: AskIn):
    G(body.tenant)
    q: queue.Queue = queue.Queue()

    def work():
        try:
            answer_agent.ask(body.tenant, body.question, user=body.user, emit=q.put)
        except Exception as e:  # surface failures to the UI instead of hanging the stream
            q.put({"type": "error", "message": f"{type(e).__name__}: {e}"})
        q.put(None)

    threading.Thread(target=work, daemon=True).start()

    def stream():
        yield f"data: {json.dumps({'type': 'start', 'question': body.question, 'llm': L.provider()})}\n\n"
        while (ev := q.get()) is not None:
            yield f"data: {json.dumps(ev, default=str)}\n\n"
        yield "data: {\"type\": \"done\"}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/ask/sync")
def ask_sync(body: AskIn):
    G(body.tenant)
    return answer_agent.ask(body.tenant, body.question, user=body.user)


# --------------------------------------------------------------------------
# Writes (approval-gated)
# --------------------------------------------------------------------------

class PreviewIn(BaseModel):
    tenant: str = "northwind"
    target_id: str
    action: str = "revoke"


@app.post("/api/preview")
def preview(body: PreviewIn):
    return guard(T.preview_revocation, G(body.tenant), body.target_id, body.action)


class ActionIn(BaseModel):
    tenant: str = "northwind"
    kind: str
    target_id: str
    reason: str = ""
    requested_by: str = "human:ui"


@app.post("/api/actions")
def request_action(body: ActionIn):
    return guard(T.request_action, G(body.tenant), body.kind, body.target_id, body.reason, body.requested_by)


@app.get("/api/actions")
def actions(tenant: str = "northwind", status: str | None = None):
    return T.list_actions(G(tenant), status)


class DecideIn(BaseModel):
    tenant: str = "northwind"
    approver: str = "human:ui"


@app.post("/api/actions/{action_id}/approve")
def approve(action_id: str, body: DecideIn):
    return guard(T.approve, G(body.tenant), action_id, body.approver)


@app.post("/api/actions/{action_id}/reject")
def reject(action_id: str, body: DecideIn):
    return guard(T.reject, G(body.tenant), action_id, body.approver)


@app.get("/api/notifications")
def notifications(tenant: str = "northwind"):
    return T.list_notifications(G(tenant))


class SendIn(BaseModel):
    tenant: str = "northwind"
    ids: list[str]


@app.post("/api/notifications/send")
def send(body: SendIn):
    return {"sent": T.send_notifications(G(body.tenant), body.ids)}


class IngestIn(BaseModel):
    tenant: str = "northwind"
    kind: str = "SLACK"
    title: str = ""
    text: str = Field(min_length=10, max_length=8000)
    author_id: str = ""
    sender: str = ""
    trust: float = Field(0.6, ge=0, le=1)


@app.post("/api/ingest")
def ingest(body: IngestIn):
    return guard(ingest_agent.ingest, G(body.tenant), body.model_dump(exclude={"tenant"}))


class ImportIn(BaseModel):
    tenant: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    data: dict


@app.post("/api/import")
def import_dataset(body: ImportIn):
    """Load your own company graph (same shape as data/template.json) into its own tenant."""
    if body.tenant.startswith(("eval", "test")):
        raise HTTPException(400, "tenant names starting with eval/test are reserved")
    from data.load import load
    try:
        return load(body.data, body.tenant)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, f"dataset rejected: {e}")


class ResetIn(BaseModel):
    tenant: str = "northwind"


@app.post("/api/reset")
def reset(body: ResetIn):
    from data.generate import build, build_bluefin
    from data.load import load
    data = {"northwind": build, "bluefin": build_bluefin}.get(body.tenant)
    if not data:
        raise HTTPException(400, "only demo tenants can be reset")
    return load(data())


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
