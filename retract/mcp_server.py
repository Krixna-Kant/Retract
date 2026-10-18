"""RETRACT as an MCP server: any MCP client (Claude Desktop, Cursor, an agent
framework) can pick RETRACT's fixed graph tools. Clients never send Cypher.

Writes stay behind the approval gate: an MCP agent can request an action and
preview its cascade, but only a human approves it (UI or POST /api/actions/{id}/approve).

    python -m retract.mcp_server            # stdio transport
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from retract import engine, tools as T  # noqa: E402
from retract.agents import ingest as ingest_agent  # noqa: E402
from retract.agents.answer import ask as answer_ask  # noqa: E402
from retract.db import graph, list_tenants  # noqa: E402

mcp = FastMCP("retract")


def _g(tenant: str):
    if tenant not in list_tenants():
        raise ValueError(f"unknown tenant {tenant!r}; known: {list_tenants()}")
    return graph(tenant)


@mcp.tool(structured_output=False)
def list_company_graphs() -> list[str]:
    """List the tenant graphs (one isolated FalkorDB graph per company or user)."""
    return list_tenants()


@mcp.tool(structured_output=False)
def ask(question: str, tenant: str = "northwind", user: str = "") -> dict:
    """Answer a question from company memory. Returns an outcome (ANSWER_WITH_PATH, STALE,
    CONTESTED, UNKNOWN_NO_PATH), the answer, the cited sources and the support paths."""
    r = answer_ask(tenant, question, user=user or None)
    return {k: r.get(k) for k in ("outcome", "answer", "sources", "cited", "answer_id")}


@mcp.tool(structured_output=False)
def search_claims(query: str, tenant: str = "northwind", k: int = 8) -> dict:
    """Full-text search over remembered claims, live ones first."""
    return T.search_claims(_g(tenant), query, k)


@mcp.tool(structured_output=False)
def explain_support(claim_id: str, tenant: str = "northwind") -> dict:
    """Why do we believe this claim? Every DERIVED_FROM path to its sources, marked live or dead."""
    return T.explain_support(_g(tenant), claim_id)


@mcp.tool(structured_output=False)
def decision_status(decision_id: str, tenant: str = "northwind") -> dict:
    """Is this decision still in force, what supersedes it, and are its supporting claims alive?"""
    return T.decision_status(_g(tenant), decision_id)


@mcp.tool(structured_output=False)
def who_knows(system: str, tenant: str = "northwind") -> dict:
    """Who owns a system and who authored the live knowledge about it."""
    return T.who_knows(_g(tenant), system)


@mcp.tool(structured_output=False)
def trace_source(source_id: str, tenant: str = "northwind") -> dict:
    """Everything a source supports, and what would die if it were removed."""
    return T.trace_source(_g(tenant), source_id)


@mcp.tool(structured_output=False)
def preview_revocation(target_id: str, action: str = "revoke", tenant: str = "northwind") -> dict:
    """Dry run: revoke/quarantine a source or reverse a decision. Returns claims that lose all
    support, claims that survive (with the path that saves them), decisions at risk, owners to notify."""
    return T.preview_revocation(_g(tenant), target_id, action)


@mcp.tool(structured_output=False)
def blast_radius(tenant: str = "northwind", limit: int = 10) -> list:
    """Rank sources by how much memory would die if each were revoked."""
    return engine.blast_radius(_g(tenant), limit)


@mcp.tool(structured_output=False)
def foundational_sources(tenant: str = "northwind", limit: int = 10) -> list:
    """PageRank over DERIVED_FROM: the sources the most knowledge rests on."""
    return engine.foundational_sources(_g(tenant), limit)


@mcp.tool(structured_output=False)
def bus_factor(tenant: str = "northwind") -> list:
    """Systems whose live knowledge depends on a single person."""
    return engine.bus_factor(_g(tenant))


@mcp.tool(structured_output=False)
def request_action(kind: str, target_id: str, reason: str, tenant: str = "northwind") -> dict:
    """Request a write (revoke, quarantine, reverse). It stays PENDING until a human approves it."""
    return T.request_action(_g(tenant), kind, target_id, reason, requested_by="agent:mcp")


@mcp.tool(structured_output=False)
def list_actions(status: str = "", tenant: str = "northwind") -> list:
    """List requested actions and their status (PENDING, APPROVED, REJECTED)."""
    return T.list_actions(_g(tenant), status or None)


@mcp.tool(structured_output=False)
def ingest_document(text: str, kind: str = "SLACK", title: str = "", author_id: str = "",
                    trust: float = 0.7, tenant: str = "northwind") -> dict:
    """Add a document (Slack, email, ADR, postmortem, memo). Claims are extracted, linked to their
    source, merged with matching memory, and contradictions are flagged."""
    return ingest_agent.ingest(_g(tenant), {"kind": kind, "title": title, "text": text,
                                            "author_id": author_id, "trust": trust})


if __name__ == "__main__":
    mcp.run()
