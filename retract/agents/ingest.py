"""Ingest agent: turn a Source into PROPOSED claims with DERIVED_FROM edges.

Extraction uses the LLM when one is configured and a rule-based extractor
otherwise. Either way the output is validated against the graph (system ids,
claim ids) before anything is written, and writes use MERGE on ids so
re-ingesting the same source is idempotent.

Corroboration: if a live claim with the same (key, value) already exists, the
agent adds a DERIVED_FROM edge from that claim to the new source instead of
creating a duplicate. The auditor then promotes it to CONFIRMED.
"""
from __future__ import annotations

import hashlib
import re

from .. import llm as L
from ..db import LIVE_CLAIM_STATUSES, SOURCE_KINDS, rows
from ..engine import now
from . import auditor

INGEST = "agent:ingest"

ATTRIBUTES = [
    (r"\b(ttl|expire[sd]?|expiry)\b", "token_ttl"),
    (r"\bwebhook\b.*\b(endpoint|url|https?://)", "webhook_endpoint"),
    (r"\bsignature", "signature_verification"),
    (r"\bretention|retain", "retention"),
    (r"\bregion|residency|data centre|datacenter", "region"),
    (r"\brate limit|requests per second|\brps\b", "rate_limit"),
    (r"\bsla\b|uptime", "sla"),
    (r"\bfailover|fail over|recovery time|\brto\b", "failover_time"),
    (r"\bp99|latency", "latency_target"),
    (r"\bprovider|vendor\b", "provider"),
    (r"\breplica", "replicas"),
    (r"\bon-?call", "oncall"),
    (r"\bdeploy", "deploy_cadence"),
    (r"\bdatabase|postgres|datastore", "datastore"),
]
UNITS = {"minute": "m", "minutes": "m", "min": "m", "mins": "m", "hour": "h", "hours": "h",
         "day": "d", "days": "d", "ms": "ms", "seconds": "s", "second": "s", "%": "%", "rps": "rps"}


def _systems(g) -> list[dict]:
    return rows(g, "MATCH (s:System) RETURN s.id AS id, s.name AS name, s.aliases AS aliases")


def _value(sentence: str) -> str:
    s = sentence.lower()
    url = re.search(r"https?://[^\s,;)]+", s)
    if url:
        return url.group(0).rstrip(".")
    num = re.search(r"(\d+(?:\.\d+)?)\s*(minutes?|mins?|hours?|days?|ms|seconds?|%|rps)\b", s)
    if num:
        return num.group(1) + UNITS.get(num.group(2), num.group(2))
    for word in ("disabled", "enabled", "never", "always", "must not", "must"):
        if word in s:
            return word.replace(" ", "_")
    return hashlib.sha1(re.sub(r"\W+", " ", s).strip().encode()).hexdigest()[:8]


def extract_offline(text: str, systems: list[dict]) -> list[dict]:
    out = []
    for raw in re.split(r"(?<=[.!?])\s+|\n+", text):
        sent = raw.strip(" -*\t")
        if len(sent.split()) < 5 or sent.endswith("?"):
            continue
        low = sent.lower()
        sys_hit = None
        for s in systems:
            names = [s["name"]] + list(s.get("aliases") or [])
            if any(n.lower() in low for n in names):
                sys_hit = s
                break
        if not sys_hit:
            continue
        key = rule_key(sent, sys_hit["name"])
        out.append({"text": sent.rstrip("."), "system_id": sys_hit["id"], "key": key,
                    "value": _value(sent) if key else None, "depends_on": []})
    return out


def rule_key(sentence: str, system_name: str) -> str | None:
    low = sentence.lower()
    for pattern, attr in ATTRIBUTES:
        if re.search(pattern, low):
            return f"{system_name}.{attr}"
    return None


def normalize_value(value) -> str | None:
    """Map free-form values onto the graph's canonical form ('15 minutes' -> '15m')."""
    if value is None:
        return None
    v = str(value).strip().lower()
    canon = _value(v)
    return canon if not re.fullmatch(r"[0-9a-f]{8}", canon) else v


def extract_llm(g, text: str, systems: list[dict]) -> list[dict]:
    hint = rows(g, """
        CALL db.idx.fulltext.queryNodes('Claim', $q) YIELD node, score
        WHERE node.status IN $live
        RETURN node.id AS id, node.text AS text, node.key AS key, node.value AS value LIMIT 15""",
        {"q": _ft_query(text), "live": LIVE_CLAIM_STATUSES})
    keys = sorted(r["key"] for r in rows(g, "MATCH (c:Claim) WHERE c.key IS NOT NULL RETURN DISTINCT c.key AS key"))
    prompt = f"""Extract atomic factual claims from the document below.
Return a JSON array. Each item: {{"text": str, "system_id": one of the system ids or null,
"key": "<system name>.<attribute in snake_case>" or null, "value": short normalized value or null,
"depends_on": [ids of EXISTING claims this claim logically relies on, may be empty]}}.
Rules:
- If the claim is about an attribute that already has a key below, reuse that exact key, so agreements and
  contradictions with existing memory can be detected. Reuse a key only for exactly the same attribute
  (failover time is not latency); otherwise make a new key.
- Values are short and canonical: durations like 15m, 24h, 7d; percentages like 99.99%; URLs verbatim;
  otherwise one or two lowercase words.
- Only include claims stated in the document. At most 8 claims.

Systems: {[{"id": s["id"], "name": s["name"]} for s in systems]}
Existing keys: {keys}
Related existing claims: {hint}

Document:
{text}"""
    items = L.llm_json(prompt, system="You extract claims for a knowledge graph. Reply with JSON only.")
    if not isinstance(items, list):
        return []
    known = set(keys)
    names = {s["id"]: s["name"] for s in systems}
    for it in items:
        if not isinstance(it, dict):
            continue
        sys_name = names.get(it.get("system_id"))
        rk = rule_key(str(it.get("text", "")), sys_name) if sys_name else None
        # A key that touches existing memory decides corroboration and contradiction, so when the
        # LLM and the explicit attribute vocabulary disagree there, the vocabulary wins.
        if rk and it.get("key") != rk and (rk in known or it.get("key") in known):
            it["key"] = rk
        it["value"] = normalize_value(it.get("value"))
    return [it for it in items if isinstance(it, dict)]


def _ft_query(text: str) -> str:
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z0-9]{3,}", text.lower())][:40]
    return "|".join(dict.fromkeys(words)) or "none"


def ingest(g, source: dict, use_llm: bool | None = None) -> dict:
    kind = source.get("kind", "SLACK").upper()
    if kind not in SOURCE_KINDS:
        raise ValueError(f"kind must be one of {SOURCE_KINDS}")
    text = (source.get("text") or "").strip()
    if not text:
        raise ValueError("source text is empty")
    sid = source.get("id") or f"SRC-{kind}-" + hashlib.sha1(text.encode()).hexdigest()[:6].upper()
    ts = now()
    g.query("""
        MERGE (s:Source {id: $id})
        ON CREATE SET s.kind = $kind, s.title = $title, s.text = $text, s.ts = $ts, s.revoked = false,
                      s.quarantined = false, s.trust = $trust, s.sender = $sender
        WITH s
        OPTIONAL MATCH (p:Person {id: $author})
        FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (p)-[:AUTHORED]->(s))""",
            {"id": sid, "kind": kind, "title": source.get("title") or sid, "text": text, "ts": ts,
             "trust": float(source.get("trust", 0.7)), "sender": source.get("sender", ""),
             "author": source.get("author_id", "")})

    systems = _systems(g)
    use_llm = L.available() if use_llm is None else use_llm
    method = "llm" if use_llm else "rules"
    try:
        items = extract_llm(g, text, systems) if use_llm else extract_offline(text, systems)
    except Exception as e:  # LLM failure falls back to rules, never to no-op
        items, method = extract_offline(text, systems), f"rules (llm failed: {type(e).__name__})"

    valid_sys = {s["id"] for s in systems}
    created, corroborated = [], []
    for it in items:
        ctext = str(it.get("text", "")).strip()
        if not ctext:
            continue
        sys_id = it.get("system_id") if it.get("system_id") in valid_sys else None
        key, value = it.get("key"), it.get("value")
        value = str(value).lower() if value is not None else None
        deps = [d for d in (it.get("depends_on") or []) if isinstance(d, str)]
        deps = [r["id"] for r in rows(g, "MATCH (c:Claim) WHERE c.id IN $ids RETURN c.id AS id", {"ids": deps})]

        if key and value:
            same = rows(g, """
                MATCH (c:Claim {key: $key, value: $value}) WHERE c.status IN $live
                MATCH (s:Source {id: $sid})
                MERGE (c)-[:DERIVED_FROM]->(s)
                RETURN c.id AS id""", {"key": key, "value": value, "live": LIVE_CLAIM_STATUSES, "sid": sid})
            if same:
                corroborated += [r["id"] for r in same]
                continue

        cid = "C-" + hashlib.sha1(f"{sid}|{ctext}".encode()).hexdigest()[:6].upper()
        g.query("""
            MATCH (s:Source {id: $sid})
            MERGE (c:Claim {id: $cid})
            ON CREATE SET c.text = $text, c.status = 'PROPOSED', c.confidence = 0.6, c.key = $key,
                          c.value = $value, c.written_by = $agent, c.created_at = $ts
            MERGE (c)-[:DERIVED_FROM]->(s)
            MERGE (a:Agent {id: $agent})
            MERGE (a)-[:WROTE]->(c)
            WITH c
            OPTIONAL MATCH (sys:System {id: $sys})
            FOREACH (_ IN CASE WHEN sys IS NULL THEN [] ELSE [1] END | MERGE (c)-[:ABOUT]->(sys))
            WITH c
            UNWIND $deps AS d
            MATCH (dc:Claim {id: d})
            MERGE (c)-[:DERIVED_FROM]->(dc)""",
                {"sid": sid, "cid": cid, "text": ctext, "key": key, "value": value, "agent": INGEST,
                 "ts": ts, "sys": sys_id or "", "deps": deps or []})
        created.append({"id": cid, "text": ctext, "system_id": sys_id, "key": key, "value": value,
                        "depends_on": deps})

    audit = auditor.run(g)
    return {"source_id": sid, "method": method, "created": created, "corroborated": corroborated,
            "audit": audit}
