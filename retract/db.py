"""FalkorDB connection, tenancy and schema.

One FalkorDB instance holds one graph per tenant (`tenant_<name>`), so tenants
are isolated at the graph level, not by a WHERE clause.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache

from falkordb import FalkorDB

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

TENANT_PREFIX = "tenant_"
_TENANT_RE = re.compile(r"^[a-z0-9_]{1,40}$")

# Live-definition constants. Every query in the engine reads these, so the
# definition of "live" exists in exactly one place.
LIVE_CLAIM_STATUSES = ["PROPOSED", "CONFIRMED", "CONTESTED"]
DEAD_CLAIM_STATUSES = ["SUPERSEDED", "INVALIDATED", "QUARANTINED"]
CLAIM_STATUSES = LIVE_CLAIM_STATUSES + DEAD_CLAIM_STATUSES
DECISION_STATUSES = ["ACTIVE", "SUPERSEDED", "REVERSED"]
SOURCE_KINDS = ["ADR", "SLACK", "EMAIL", "POSTMORTEM", "MEMO"]

INDEXED_LABELS = ["Claim", "Source", "Decision", "Person", "System", "Agent", "Team", "Answer", "Action", "Notification"]


@lru_cache(maxsize=1)
def client() -> FalkorDB:
    kwargs = {
        "host": os.getenv("FALKORDB_HOST", "localhost"),
        "port": int(os.getenv("FALKORDB_PORT", "6379")),
    }
    if os.getenv("FALKORDB_USERNAME"):
        kwargs["username"] = os.getenv("FALKORDB_USERNAME")
    if os.getenv("FALKORDB_PASSWORD"):
        kwargs["password"] = os.getenv("FALKORDB_PASSWORD")
    return FalkorDB(**kwargs)


def graph_name(tenant: str) -> str:
    tenant = tenant.removeprefix(TENANT_PREFIX)
    if not _TENANT_RE.match(tenant):
        raise ValueError(f"invalid tenant name: {tenant!r}")
    return TENANT_PREFIX + tenant


def graph(tenant: str):
    return client().select_graph(graph_name(tenant))


def list_tenants() -> list[str]:
    return sorted(
        g.removeprefix(TENANT_PREFIX) for g in client().list_graphs() if g.startswith(TENANT_PREFIX)
    )


def rows(g, cypher: str, params: dict | None = None) -> list[dict]:
    """Run a query and return rows as dicts keyed by the RETURN aliases."""
    res = g.query(cypher, params or {})
    header = [h[1] if isinstance(h, (list, tuple)) else h for h in res.header]
    return [dict(zip(header, r)) for r in res.result_set]


def create_schema(g) -> None:
    """Range indexes on ids plus full-text indexes for retrieval."""
    for label in INDEXED_LABELS:
        _safe(g, f"CREATE INDEX FOR (n:{label}) ON (n.id)")
    _safe(g, "CREATE INDEX FOR (c:Claim) ON (c.status)")
    _safe(g, "CREATE FULLTEXT INDEX FOR (c:Claim) ON (c.text)")
    _safe(g, "CREATE FULLTEXT INDEX FOR (d:Decision) ON (d.title)")
    _safe(g, "CREATE FULLTEXT INDEX FOR (s:Source) ON (s.title, s.text)")


def _safe(g, cypher: str) -> None:
    try:
        g.query(cypher)
    except Exception as e:  # index already exists
        if "already" not in str(e).lower():
            raise


def reset_graph(tenant: str):
    g = graph(tenant)
    try:
        g.delete()
    except Exception:
        pass
    g = graph(tenant)
    create_schema(g)
    return g
