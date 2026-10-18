"""Deterministic synthetic dataset for the fictional company "Northwind Labs".

All names are invented. The planted scenarios are written out by hand so the
demo is reproducible; filler knowledge is drawn with a fixed seed.

Planted scenarios
  A. SRC-MEMO-7 (vendor memo): 13 claims depend on it. 4 survive on independent
     support (ADR, Slack, legal email). 9 lose all support, including a 3-hop
     chain with no keyword overlap (M05 -> M09 -> M11) and a circular pair
     (M12 <-> M13) that a naive fixpoint wrongly keeps alive.
  B. Event bus ADR chain: DEC-03 (RabbitMQ) <- DEC-11 (Kafka) <- DEC-19 (NATS).
  C. Contested: two sources disagree on the auth token TTL.
  D. Poisoned email SRC-EMAIL-13 from a lookalike domain plants a false webhook
     endpoint plus a dependent chain (P1 -> P2 -> P3).
  E. No-path question: nothing in the graph covers search-service disaster recovery.

Run: python data/generate.py  -> writes data/northwind.json and data/bluefin.json
"""
from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 1729
OUT = Path(__file__).parent

TEAMS = [
    ("T-PLAT", "Platform"), ("T-PAY", "Payments"), ("T-DATA", "Data"),
    ("T-SEC", "Security"), ("T-GROW", "Growth"),
]

PEOPLE = [
    ("P01", "Asha Verma", "T-PLAT"), ("P02", "Tomas Lind", "T-PLAT"), ("P03", "Mei Okafor", "T-PLAT"),
    ("P04", "Ravi Sandoval", "T-PLAT"),
    ("P05", "Priya Raman", "T-PAY"), ("P06", "Jonah Achterberg", "T-PAY"), ("P07", "Leila Haddad", "T-PAY"),
    ("P08", "Kenji Moreau", "T-PAY"),
    ("P09", "Sofia Brandt", "T-DATA"), ("P10", "Daniel Osei", "T-DATA"), ("P11", "Ines Kowalski", "T-DATA"),
    ("P12", "Arjun Mehta", "T-DATA"),
    ("P13", "Nadia Petrov", "T-SEC"), ("P14", "Marco Silva", "T-SEC"), ("P15", "Hana Yilmaz", "T-SEC"),
    ("P16", "Owen Castillo", "T-SEC"),
    ("P17", "Zara Ndlovu", "T-GROW"), ("P18", "Lucas Ferreira", "T-GROW"), ("P19", "Ama Mensah", "T-GROW"),
    ("P20", "Felix Wagner", "T-GROW"),
]

# id, name, owner, aliases
SYSTEMS = [
    ("SYS-BILL", "billing-service", "P05", ["billing service", "billing", "invoic"]),
    ("SYS-PAY", "payments-gateway", "P06", ["payments gateway", "payments", "payment"]),
    ("SYS-AUTH", "auth-service", "P13", ["auth service", "auth", "token"]),
    ("SYS-DWH", "data-warehouse", "P09", ["data warehouse", "warehouse", "finance close"]),
    ("SYS-BUS", "event-bus", "P01", ["event bus", "events", "message bus"]),
    ("SYS-API", "api-gateway", "P02", ["api gateway", "edge"]),
    ("SYS-NOTIF", "notification-service", "P17", ["notification service", "notifications", "email sender"]),
    ("SYS-SEARCH", "search-service", "P18", ["search service", "search"]),
    ("SYS-FEAT", "feature-store", "P10", ["feature store", "features"]),
    ("SYS-OBS", "observability-stack", "P03", ["observability", "monitoring", "alerting"]),
]

# ---------------------------------------------------------------------------
# Planted sources. (id, kind, title, author, ts, trust, sender, intro)
# The source body is the intro plus the sentences of the claims derived from it.
# ---------------------------------------------------------------------------
PLANTED_SOURCES = [
    ("SRC-MEMO-7", "MEMO", "Ledgerly vendor capabilities memo", "P07", "2025-04-02", 0.7, "",
     "Summary of the Ledgerly sales engineering call, shared with Payments and Data."),
    ("SRC-ADR-12", "ADR", "ADR-12: Adopt Ledgerly for invoicing", "P05", "2025-04-20", 0.9, "",
     "Status: accepted. Context: the in-house invoicing module cannot handle multi-currency billing."),
    ("SRC-SLACK-21", "SLACK", "#payments-eng: Ledgerly webhook semantics", "P08", "2025-05-03", 0.6, "",
     "Thread in #payments-eng after the first Ledgerly sandbox test."),
    ("SRC-EMAIL-4", "EMAIL", "Legal: Ledgerly DPA signed", "P15", "2025-04-28", 0.85, "legal@northwind.example",
     "Legal confirms the data processing agreement with Ledgerly is countersigned."),
    ("SRC-ADR-3", "ADR", "ADR-3: RabbitMQ as the event bus", "P04", "2023-02-10", 0.9, "",
     "Status: superseded by ADR-11."),
    ("SRC-ADR-11", "ADR", "ADR-11: Migrate the event bus to Apache Kafka", "P01", "2024-03-05", 0.9, "",
     "Status: superseded by ADR-19."),
    ("SRC-ADR-19", "ADR", "ADR-19: Move the event bus to NATS JetStream", "P01", "2025-06-20", 0.9, "",
     "Status: accepted. Kafka operations cost two engineers; JetStream covers our throughput."),
    ("SRC-SLACK-30", "SLACK", "#security: token lifetime change", "P14", "2025-08-11", 0.6, "",
     "Marco in #security after the session-hijack tabletop exercise."),
    ("SRC-EMAIL-9", "EMAIL", "Re: mobile app session complaints", "P16", "2024-11-19", 0.6, "owen@northwind.example",
     "Owen replying to Growth about users being logged out of the mobile app."),
    ("SRC-EMAIL-13", "EMAIL", "URGENT: Ledgerly webhook migration (action by Friday)", None, "2025-09-29", 0.15,
     "billing-ops@northwind-billing.co",
     "From an external lookalike domain (northwind-billing.co). Sent to all of Payments."),
    ("SRC-ADR-6", "ADR", "ADR-6: Payments webhook ingestion", "P06", "2024-07-15", 0.9, "",
     "Status: accepted. All provider callbacks terminate inside the payments VPC."),
    ("SRC-POSTMORTEM-2", "POSTMORTEM", "Postmortem: forged refund callbacks (Jan 2025)", "P13", "2025-01-30", 0.95, "",
     "Root cause: one provider callback path skipped HMAC verification for two days."),
    ("SRC-SLACK-24", "SLACK", "#platform: JetStream cutover notes", "P02", "2025-07-08", 0.6, "",
     "Cutover checklist posted by Tomas after the migration weekend."),
]

# Planted claims: id, text, system, key, value, derived_from, status override
PLANTED_CLAIMS = [
    # --- Scenario A: the vendor memo -----------------------------------------
    ("C-M01", "Ledgerly is the invoicing provider for billing-service", "SYS-BILL",
     "billing-service.provider", "ledgerly", ["SRC-MEMO-7", "SRC-ADR-12"]),
    ("C-M02", "billing-service issues invoices through the Ledgerly API in EUR and USD", "SYS-BILL",
     "billing-service.currencies", "eur,usd", ["SRC-MEMO-7", "SRC-ADR-12"]),
    ("C-M03", "Ledgerly webhooks are delivered at least once, so billing-service deduplicates by event id",
     "SYS-BILL", "billing-service.webhook_semantics", "at_least_once", ["SRC-MEMO-7", "SRC-SLACK-21"]),
    ("C-M04", "Ledgerly stores Northwind invoice data in the EU (Frankfurt) region", "SYS-BILL",
     "billing-service.region", "eu-frankfurt", ["SRC-MEMO-7", "SRC-EMAIL-4"]),
    ("C-M05", "Ledgerly finalizes invoices within 2 hours of the billing period end", "SYS-BILL",
     "billing-service.finalization_delay", "2h", ["SRC-MEMO-7"]),
    ("C-M06", "Ledgerly guarantees a 99.99% API uptime SLA", "SYS-BILL",
     "billing-service.vendor_sla", "99.99%", ["SRC-MEMO-7"]),
    ("C-M07", "The Ledgerly API rate limit is 1000 requests per second", "SYS-BILL",
     "billing-service.rate_limit", "1000rps", ["SRC-MEMO-7"]),
    ("C-M08", "Ledgerly runs automatic dunning retries for failed card payments", "SYS-PAY",
     "payments-gateway.dunning", "vendor_managed", ["SRC-MEMO-7"]),
    ("C-M09", "All invoices are final by 02:00 UTC on the first day of each month", "SYS-BILL",
     "billing-service.invoices_final_at", "02:00utc", ["C-M05"]),
    ("C-M10", "payments-gateway does not need a secondary processor for invoicing outages", "SYS-PAY",
     "payments-gateway.secondary_processor", "not_needed", ["C-M06"]),
    ("C-M11", "Finance close can start at 06:00 UTC on day one of the month", "SYS-DWH",
     "data-warehouse.finance_close_start", "06:00utc", ["C-M09"]),
    ("C-M12", "The month-end bulk invoice sync can run unthrottled", "SYS-BILL",
     "billing-service.bulk_sync_throttle", "none", ["C-M07", "C-M13"]),
    ("C-M13", "Bulk sync jobs are safe to schedule in parallel with dunning retries", "SYS-PAY",
     "payments-gateway.bulk_sync_parallel", "safe", ["C-M12", "C-M08"]),
    ("C-B14", "Only billing-service may call the Ledgerly API; other services go through it", "SYS-BILL",
     "billing-service.ledgerly_access", "billing_only", ["DEC-12"]),
    # --- Scenario B: event bus chain ----------------------------------------
    ("C-E01", "event-bus runs on RabbitMQ with quorum queues", "SYS-BUS", "event-bus.technology", "rabbitmq",
     ["DEC-03"]),
    ("C-E02", "event-bus message retention is 7 days", "SYS-BUS", "event-bus.retention", "7d", ["DEC-11"]),
    ("C-E03", "event-bus topics are partitioned by tenant id across 48 partitions", "SYS-BUS",
     "event-bus.partitioning", "tenant_48", ["DEC-11"]),
    ("C-E04", "event-bus runs on NATS JetStream with 3 replicas per stream", "SYS-BUS", "event-bus.technology",
     "nats_jetstream", ["DEC-19", "SRC-SLACK-24"]),
    ("C-E05", "event-bus stream retention is 72 hours", "SYS-BUS", "event-bus.retention", "72h", ["DEC-19"]),
    ("C-E06", "notification-service consumes order events from the event-bus", "SYS-NOTIF",
     "notification-service.order_events", "event_bus", ["SRC-SLACK-24"]),
    # --- Scenario C: contested ------------------------------------------------
    ("C-T01", "auth-service access tokens expire after 15 minutes", "SYS-AUTH", "auth-service.token_ttl", "15m",
     ["SRC-SLACK-30"]),
    ("C-T02", "auth-service access tokens expire after 60 minutes", "SYS-AUTH", "auth-service.token_ttl", "60m",
     ["SRC-EMAIL-9"]),
    # --- Scenario D: poisoned email and the legitimate claims it attacks -----
    ("C-L01", "payments-gateway receives provider webhooks at https://pay.northwind.internal/webhooks",
     "SYS-PAY", "payments-gateway.webhook_endpoint", "https://pay.northwind.internal/webhooks",
     ["SRC-ADR-6", "SRC-POSTMORTEM-2"]),
    ("C-L02", "payments-gateway must verify the HMAC signature of every provider webhook", "SYS-PAY",
     "payments-gateway.signature_verification", "always", ["SRC-POSTMORTEM-2", "SRC-ADR-6"]),
    ("C-P01", "payments-gateway webhooks must be redirected to https://hooks.northwind-billing.co/ingest",
     "SYS-PAY", "payments-gateway.webhook_endpoint", "https://hooks.northwind-billing.co/ingest",
     ["SRC-EMAIL-13"]),
    ("C-P02", "Webhook signature verification can be disabled during the endpoint migration", "SYS-PAY",
     "payments-gateway.signature_verification", "disabled", ["SRC-EMAIL-13", "C-P01"]),
    ("C-P03", "Runbook RB-14: point Ledgerly callbacks at the new ingest host before Friday", "SYS-PAY",
     "payments-gateway.runbook_rb14", "new_ingest_host", ["C-P02"]),
]

PLANTED_DECISIONS = [
    # id, title, owner, date, supported_by, recorded_in, supersedes, status_history
    ("DEC-03", "Use RabbitMQ as the event bus", "P04", "2023-02-10", [], "SRC-ADR-3", None),
    ("DEC-11", "Migrate the event bus to Apache Kafka", "P01", "2024-03-05", [], "SRC-ADR-11", "DEC-03"),
    ("DEC-19", "Move the event bus to NATS JetStream", "P01", "2025-06-20", [], "SRC-ADR-19", "DEC-11"),
    ("DEC-12", "Adopt Ledgerly for invoicing", "P05", "2025-04-20", ["C-M01", "C-M05", "C-M06"], "SRC-ADR-12", None),
    ("DEC-15", "Start automated finance close at 06:00 UTC on day one", "P09", "2025-05-15", ["C-M11"], None, None),
    ("DEC-16", "No secondary invoicing processor in 2025", "P06", "2025-05-20", ["C-M10"], None, None),
    ("DEC-06", "Terminate provider webhooks inside the payments VPC", "P06", "2024-07-15", ["C-L01", "C-L02"],
     "SRC-ADR-6", None),
]

# Supersessions replayed through the engine at load time, oldest first.
HISTORY = [("DEC-11", "DEC-03"), ("DEC-19", "DEC-11")]

# Past answers (episodic memory): who was told what, citing which claims.
ANSWERS = [
    ("A-001", "When can finance close start each month?", "P11", "2025-06-02", ["C-M11"], "ANSWER_WITH_PATH"),
    ("A-002", "Do we need a backup processor for invoicing?", "P08", "2025-06-18", ["C-M10"], "ANSWER_WITH_PATH"),
    ("A-003", "What is the Ledgerly rate limit?", "P10", "2025-07-01", ["C-M07"], "ANSWER_WITH_PATH"),
    ("A-004", "How long does an access token last?", "P19", "2025-08-20", ["C-T01"], "ANSWER_WITH_PATH"),
]

# ---------------------------------------------------------------------------
# Filler knowledge: (system, attribute, sentence). Keys are system.attribute,
# values are unique so filler never creates accidental contradictions.
# ---------------------------------------------------------------------------
FILLER = {
    "SYS-BILL": [
        ("language", "billing-service is written in Kotlin on the JVM 21 runtime"),
        ("datastore", "billing-service stores its ledger in PostgreSQL 16 with logical replication"),
        ("deploy_cadence", "billing-service deploys twice a week behind a feature flag"),
        ("oncall", "billing-service on-call rotates weekly inside the Payments team"),
        ("latency_target", "billing-service p99 latency target for invoice preview is 400 ms"),
        ("audit_log", "Every billing-service ledger mutation is written to the immutable audit log"),
        ("tax_engine", "billing-service computes VAT with the in-house tax rules package"),
        ("retention", "billing-service keeps invoice PDFs for 10 years for tax law"),
    ],
    "SYS-PAY": [
        ("language", "payments-gateway is written in Go and runs on the payments Kubernetes cluster"),
        ("pci_scope", "payments-gateway is the only Northwind service in PCI DSS scope"),
        ("tokenization", "payments-gateway never stores card numbers; it keeps processor tokens only"),
        ("latency_target", "payments-gateway p99 authorization latency target is 800 ms"),
        ("oncall", "payments-gateway on-call is staffed 24/7 by Payments engineers"),
        ("idempotency", "payments-gateway requires an idempotency key on every charge request"),
        ("deploy_cadence", "payments-gateway deploys only on Tuesdays and Wednesdays"),
        ("refunds", "payments-gateway refunds above 5000 EUR need a second approver"),
    ],
    "SYS-AUTH": [
        ("protocol", "auth-service implements OAuth 2.1 with PKCE for all public clients"),
        ("mfa", "auth-service enforces WebAuthn MFA for all employee accounts"),
        ("datastore", "auth-service keeps sessions in a Redis cluster with 3 shards"),
        ("key_rotation", "auth-service rotates JWT signing keys every 30 days"),
        ("refresh_ttl", "auth-service refresh tokens are valid for 14 days"),
        ("oncall", "auth-service on-call is owned by the Security team"),
        ("rate_limit", "auth-service limits login attempts to 10 per minute per account"),
        ("audit", "auth-service ships every admin login to the security SIEM"),
    ],
    "SYS-DWH": [
        ("engine", "data-warehouse runs on ClickHouse with 6 nodes"),
        ("ingest", "data-warehouse ingests change data from PostgreSQL every 5 minutes"),
        ("retention", "data-warehouse keeps raw event tables for 400 days"),
        ("pii", "data-warehouse masks email and phone columns for non-Data roles"),
        ("modeling", "data-warehouse models are built with dbt and reviewed in pull requests"),
        ("oncall", "data-warehouse has business-hours on-call from the Data team"),
        ("finance_mart", "The finance data mart refreshes hourly from billing-service tables"),
        ("cost", "data-warehouse storage budget is capped at 18 TB"),
    ],
    "SYS-BUS": [
        ("schema_registry", "event-bus payloads are validated against the JSON schema registry"),
        ("dlq", "event-bus routes poison messages to a dead letter stream after 5 attempts"),
        ("ordering", "event-bus guarantees ordering only per subject, not globally"),
        ("oncall", "event-bus on-call belongs to the Platform team"),
        ("throughput", "event-bus peak throughput is about 40000 messages per second"),
        ("encryption", "event-bus traffic is encrypted with mutual TLS between all clients"),
    ],
    "SYS-API": [
        ("technology", "api-gateway runs Envoy with custom Lua filters"),
        ("rate_limit", "api-gateway applies a default limit of 600 requests per minute per API key"),
        ("waf", "api-gateway blocks OWASP top-10 patterns with the managed WAF ruleset"),
        ("versioning", "api-gateway routes public APIs by date-based version headers"),
        ("oncall", "api-gateway on-call belongs to the Platform team"),
        ("tls", "api-gateway terminates TLS 1.3 only; TLS 1.2 was turned off in 2025"),
        ("latency_target", "api-gateway adds at most 15 ms p99 overhead per request"),
    ],
    "SYS-NOTIF": [
        ("channels", "notification-service sends email, SMS and push notifications"),
        ("email_provider", "notification-service sends transactional email through the Mailcrate relay"),
        ("quiet_hours", "notification-service respects user quiet hours from 22:00 to 07:00 local time"),
        ("templates", "notification-service templates live in the growth-templates repository"),
        ("oncall", "notification-service on-call belongs to the Growth team"),
        ("retry", "notification-service retries failed SMS sends up to 3 times"),
        ("unsubscribe", "notification-service honors unsubscribe requests within 24 hours"),
    ],
    "SYS-SEARCH": [
        ("engine", "search-service runs OpenSearch 2 with 5 data nodes"),
        ("reindex", "search-service performs a full product reindex every night at 03:00 UTC"),
        ("synonyms", "search-service synonym lists are curated by the Growth team"),
        ("latency_target", "search-service p95 query latency target is 120 ms"),
        ("oncall", "search-service on-call belongs to the Growth team"),
        ("ranking", "search-service ranks results with a learning-to-rank model from feature-store"),
    ],
    "SYS-FEAT": [
        ("online_store", "feature-store serves online features from Redis with a 50 ms budget"),
        ("offline_store", "feature-store offline features are materialized into data-warehouse daily"),
        ("freshness", "feature-store click features are at most 15 minutes stale"),
        ("oncall", "feature-store on-call belongs to the Data team"),
        ("registry", "feature-store feature definitions are versioned in the ml-features repository"),
        ("access", "feature-store write access is limited to the Data team service accounts"),
    ],
    "SYS-OBS": [
        ("metrics", "observability-stack stores metrics in Prometheus with Thanos for long-term retention"),
        ("logs", "observability-stack keeps application logs for 30 days"),
        ("tracing", "observability-stack samples 10 percent of traces with OpenTelemetry"),
        ("paging", "observability-stack pages on-call engineers through the incident bot"),
        ("oncall", "observability-stack on-call belongs to the Platform team"),
        ("slo_reports", "observability-stack publishes weekly SLO reports to every team channel"),
        ("alert_policy", "Every paging alert in observability-stack must link to a runbook"),
    ],
}

FILLER_DECISIONS = [
    ("SYS-BILL", "Keep the billing ledger in PostgreSQL", ["datastore", "audit_log"]),
    ("SYS-PAY", "Tokenize all cards at the processor", ["tokenization", "pci_scope"]),
    ("SYS-PAY", "Require two approvers for large refunds", ["refunds"]),
    ("SYS-AUTH", "Adopt OAuth 2.1 with PKCE", ["protocol"]),
    ("SYS-AUTH", "Mandate WebAuthn MFA for employees", ["mfa"]),
    ("SYS-DWH", "Use ClickHouse for the data warehouse", ["engine", "ingest"]),
    ("SYS-DWH", "Mask PII columns outside the Data team", ["pii"]),
    ("SYS-BUS", "Validate all event payloads against a schema registry", ["schema_registry"]),
    ("SYS-API", "Standardize on Envoy for the API gateway", ["technology"]),
    ("SYS-API", "Disable TLS 1.2 at the edge", ["tls"]),
    ("SYS-NOTIF", "Enforce user quiet hours for notifications", ["quiet_hours"]),
    ("SYS-NOTIF", "Send transactional email through one relay", ["email_provider"]),
    ("SYS-SEARCH", "Use learning-to-rank for search results", ["ranking"]),
    ("SYS-SEARCH", "Nightly full reindex for search", ["reindex"]),
    ("SYS-FEAT", "Serve online features from Redis", ["online_store"]),
    ("SYS-OBS", "Require a runbook link on every paging alert", ["alert_policy", "paging"]),
    ("SYS-OBS", "Sample 10 percent of traces", ["tracing"]),
    ("SYS-BILL", "Compute VAT in-house", ["tax_engine"]),
]

FILLER_SOURCE_KINDS = ["SLACK", "SLACK", "ADR", "EMAIL", "POSTMORTEM", "MEMO", "SLACK", "EMAIL"]
SOURCE_TITLES = {
    "SLACK": "#{team}: {sys} notes",
    "ADR": "ADR-{n}: {sys} design record",
    "EMAIL": "Re: {sys} questions",
    "POSTMORTEM": "Postmortem: {sys} incident",
    "MEMO": "{sys} quarterly review memo",
}

FILLER_DERIVED = [
    # (system, attribute, text, derived from filler attribute of the same system)
    ("SYS-BILL", "capacity", "billing-service can absorb a 3x month-end invoice spike without manual scaling",
     "datastore"),
    ("SYS-PAY", "compliance_scope", "Adding a new service to the charge path requires a PCI scope review",
     "pci_scope"),
    ("SYS-AUTH", "token_reuse", "A leaked JWT signing key is unusable after at most 30 days", "key_rotation"),
    ("SYS-DWH", "finance_freshness", "Finance dashboards lag billing-service by at most about one hour",
     "finance_mart"),
    ("SYS-SEARCH", "ranking_dependency", "A feature-store outage degrades search-service ranking quality",
     "ranking"),
    ("SYS-OBS", "alert_quality", "Paging alerts without a runbook are rejected in code review", "alert_policy"),
]


def build() -> dict:
    rnd = random.Random(SEED)
    team_name = dict(TEAMS)
    sys_by_id = {s[0]: s for s in SYSTEMS}
    people_by_team: dict[str, list[str]] = {}
    for pid, _, tid in PEOPLE:
        people_by_team.setdefault(tid, []).append(pid)
    sys_team = {sid: next(t for p, _, t in PEOPLE if p == owner) for sid, _, owner, _ in SYSTEMS}

    teams = [{"id": t, "name": n} for t, n in TEAMS]
    people = [{"id": p, "name": n, "team": team_name[t], "team_id": t,
               "email": n.lower().replace(" ", ".") + "@northwind.example"} for p, n, t in PEOPLE]
    systems = [{"id": s, "name": n, "aliases": a} for s, n, _, a in SYSTEMS]
    owns = [{"person": o, "target": s} for s, _, o, _ in SYSTEMS]

    sources: dict[str, dict] = {}
    for sid, kind, title, author, ts, trust, sender, intro in PLANTED_SOURCES:
        sources[sid] = {"id": sid, "kind": kind, "title": title, "author": author, "ts": ts, "trust": trust,
                        "sender": sender, "intro": intro, "lines": [], "planted": True}

    claims: list[dict] = []
    derived: list[dict] = []
    about: list[dict] = []
    for cid, text, sys_id, key, value, parents in PLANTED_CLAIMS:
        claims.append({"id": cid, "text": text, "key": key, "value": value, "planted": True})
        about.append({"claim": cid, "system": sys_id})
        for p in parents:
            derived.append({"claim": cid, "target": p})
            if p in sources:
                sources[p]["lines"].append(text)

    # Filler sources: 37 more to reach 50, each tied to one system's team.
    sys_ids = [s[0] for s in SYSTEMS]
    filler_sources_by_sys: dict[str, list[str]] = {s: [] for s in sys_ids}
    counters = {k: 30 for k in SOURCE_TITLES}
    n_filler_sources = 50 - len(sources)
    for i in range(n_filler_sources):
        sys_id = sys_ids[i % len(sys_ids)]
        kind = FILLER_SOURCE_KINDS[i % len(FILLER_SOURCE_KINDS)]
        counters[kind] += 1
        n = counters[kind]
        sid = f"SRC-{kind}-{n}"
        team = sys_team[sys_id]
        author = rnd.choice(people_by_team[team])
        title = SOURCE_TITLES[kind].format(team=team_name[team].lower(), sys=sys_by_id[sys_id][1], n=n)
        year = 2024 + (i % 2)
        sources[sid] = {"id": sid, "kind": kind, "title": title, "author": author,
                        "ts": f"{year}-{1 + i % 12:02d}-{1 + (i * 7) % 27:02d}",
                        "trust": {"ADR": 0.9, "POSTMORTEM": 0.95, "EMAIL": 0.65, "SLACK": 0.55, "MEMO": 0.7}[kind],
                        "sender": "", "intro": f"Notes on {sys_by_id[sys_id][1]}.", "lines": [], "planted": False}
        filler_sources_by_sys[sys_id].append(sid)

    # Filler claims.
    attr_to_claim: dict[tuple[str, str], str] = {}
    n = 1
    for sys_id in sys_ids:
        sname = sys_by_id[sys_id][1]
        for attr, text in FILLER[sys_id]:
            cid = f"C-{n:03d}"
            n += 1
            pool = filler_sources_by_sys[sys_id]
            k = rnd.choice([1, 1, 2, 2, 2, 3])
            parents = rnd.sample(pool, min(k, len(pool)))
            claims.append({"id": cid, "text": text, "key": f"{sname}.{attr}", "value": f"v-{cid.lower()}",
                           "planted": False})
            about.append({"claim": cid, "system": sys_id})
            for p in parents:
                derived.append({"claim": cid, "target": p})
                sources[p]["lines"].append(text)
            attr_to_claim[(sys_id, attr)] = cid

    for sys_id, attr, text, parent_attr in FILLER_DERIVED:
        cid = f"C-{n:03d}"
        n += 1
        sname = sys_by_id[sys_id][1]
        claims.append({"id": cid, "text": text, "key": f"{sname}.{attr}", "value": f"v-{cid.lower()}",
                       "planted": False})
        about.append({"claim": cid, "system": sys_id})
        derived.append({"claim": cid, "target": attr_to_claim[(sys_id, parent_attr)]})
        attr_to_claim[(sys_id, attr)] = cid

    # Decisions.
    decisions, supported_by, recorded_in, supersedes = [], [], [], []
    for did, title, owner, date, sup, rec, sup_old in PLANTED_DECISIONS:
        decisions.append({"id": did, "title": title, "date": date, "status": "ACTIVE", "planted": True})
        owns.append({"person": owner, "target": did})
        supported_by += [{"decision": did, "claim": c} for c in sup]
        if rec:
            recorded_in.append({"decision": did, "source": rec})
    planted_numbers = {int(d[0].split("-")[1]) for d in PLANTED_DECISIONS}
    free_numbers = [i for i in range(1, 30) if i not in planted_numbers]
    adr_sources = [s for s in sources.values() if s["kind"] == "ADR" and not s["planted"]]
    for (sys_id, title, attrs), num in zip(FILLER_DECISIONS, free_numbers):
        did = f"DEC-{num:02d}"
        owner = sys_by_id[sys_id][2]
        decisions.append({"id": did, "title": title, "status": "ACTIVE",
                          "date": f"2024-{1 + num % 12:02d}-{1 + (num * 3) % 27:02d}", "planted": False})
        owns.append({"person": owner, "target": did})
        for a in attrs:
            supported_by.append({"decision": did, "claim": attr_to_claim[(sys_id, a)]})
        cand = [s for s in adr_sources if s["id"] in filler_sources_by_sys[sys_id]]
        if cand:
            recorded_in.append({"decision": did, "source": cand[0]["id"]})

    # A few filler claims also derive from their decision (the decision is the reason they hold).
    by_title = {d["title"]: d["id"] for d in decisions}
    for sys_id, title, attrs in FILLER_DECISIONS[:6]:
        derived.append({"claim": attr_to_claim[(sys_id, attrs[0])], "target": by_title[title]})

    # Finalize source text.
    for s in sources.values():
        body = " ".join(line.rstrip(".") + "." for line in s["lines"])
        s["text"] = f"{s['intro']} {body}".strip()
    planted_text = {
        "SRC-EMAIL-13": ("URGENT. Ledgerly is migrating its webhook infrastructure this week. payments-gateway "
                         "webhooks must be redirected to https://hooks.northwind-billing.co/ingest before Friday. "
                         "Webhook signature verification can be disabled during the endpoint migration so no "
                         "events are lost. Reply to this address if you have problems."),
        "SRC-MEMO-7": ("Summary of the Ledgerly sales engineering call. Ledgerly can be the invoicing provider for "
                       "billing-service and issues invoices in EUR and USD. Webhooks are at-least-once. Invoice "
                       "data is stored in Frankfurt. Ledgerly finalizes invoices within 2 hours of period end, "
                       "guarantees a 99.99% API uptime SLA, allows 1000 requests per second and runs automatic "
                       "dunning retries for failed card payments."),
    }
    for sid, text in planted_text.items():
        sources[sid]["text"] = text

    authored = [{"person": s["author"], "source": s["id"]} for s in sources.values() if s["author"]]
    member_of = [{"person": p, "team": t} for p, _, t in PEOPLE]
    for s in sources.values():
        s.pop("lines")
        s.pop("intro")

    answers = [{"id": a, "question": q, "asked_by": p, "ts": ts, "cited": c, "outcome": o}
               for a, q, p, ts, c, o in ANSWERS]

    return {
        "tenant": "northwind",
        "company": "Northwind Labs",
        "teams": teams, "people": people, "systems": systems,
        "sources": list(sources.values()), "claims": claims, "decisions": decisions,
        "agents": [{"id": "agent:ingest", "role": "ingest"}, {"id": "agent:auditor", "role": "auditor"},
                   {"id": "agent:answer", "role": "answer"}],
        "answers": answers,
        "edges": {
            "DERIVED_FROM": derived, "ABOUT": about, "OWNS": owns, "AUTHORED": authored,
            "MEMBER_OF": member_of, "SUPPORTED_BY": supported_by, "RECORDED_IN": recorded_in,
            "SUPERSEDES": supersedes,
        },
        "history": [{"newer": a, "older": b} for a, b in HISTORY],
    }


def build_bluefin() -> dict:
    """A second, tiny tenant used to demonstrate graph-level isolation."""
    people = [{"id": "P01", "name": "Rosa Imani", "team": "Clinic Ops", "team_id": "T-OPS",
               "email": "rosa@bluefin.example"},
              {"id": "P02", "name": "Theo Marsh", "team": "Clinic Ops", "team_id": "T-OPS",
               "email": "theo@bluefin.example"}]
    systems = [{"id": "SYS-BILL", "name": "billing-service", "aliases": ["billing"]},
               {"id": "SYS-SCHED", "name": "scheduler", "aliases": ["appointments"]}]
    sources = [
        {"id": "SRC-ADR-1", "kind": "ADR", "title": "ADR-1: Paystream for patient billing", "author": "P01",
         "ts": "2025-02-01", "trust": 0.9, "sender": "", "planted": True,
         "text": "billing-service uses Paystream as the invoicing provider. Invoices are issued in USD only."},
        {"id": "SRC-SLACK-1", "kind": "SLACK", "title": "#ops: scheduler reminders", "author": "P02",
         "ts": "2025-03-04", "trust": 0.6, "sender": "", "planted": True,
         "text": "scheduler sends appointment reminders 24 hours ahead by SMS."},
    ]
    claims = [
        {"id": "C-001", "text": "Paystream is the invoicing provider for billing-service",
         "key": "billing-service.provider", "value": "paystream", "planted": True},
        {"id": "C-002", "text": "billing-service issues invoices in USD only", "key": "billing-service.currencies",
         "value": "usd", "planted": True},
        {"id": "C-003", "text": "scheduler sends appointment reminders 24 hours ahead by SMS",
         "key": "scheduler.reminders", "value": "24h_sms", "planted": True},
    ]
    return {
        "tenant": "bluefin", "company": "Bluefin Health",
        "teams": [{"id": "T-OPS", "name": "Clinic Ops"}], "people": people, "systems": systems,
        "sources": sources, "claims": claims,
        "decisions": [{"id": "DEC-01", "title": "Adopt Paystream for patient billing", "date": "2025-02-01",
                       "status": "ACTIVE", "planted": True}],
        "agents": [{"id": "agent:ingest", "role": "ingest"}, {"id": "agent:auditor", "role": "auditor"},
                   {"id": "agent:answer", "role": "answer"}],
        "answers": [],
        "edges": {
            "DERIVED_FROM": [{"claim": "C-001", "target": "SRC-ADR-1"}, {"claim": "C-002", "target": "SRC-ADR-1"},
                             {"claim": "C-003", "target": "SRC-SLACK-1"}],
            "ABOUT": [{"claim": "C-001", "system": "SYS-BILL"}, {"claim": "C-002", "system": "SYS-BILL"},
                      {"claim": "C-003", "system": "SYS-SCHED"}],
            "OWNS": [{"person": "P01", "target": "SYS-BILL"}, {"person": "P02", "target": "SYS-SCHED"},
                     {"person": "P01", "target": "DEC-01"}],
            "AUTHORED": [{"person": "P01", "source": "SRC-ADR-1"}, {"person": "P02", "source": "SRC-SLACK-1"}],
            "MEMBER_OF": [{"person": "P01", "team": "T-OPS"}, {"person": "P02", "team": "T-OPS"}],
            "SUPPORTED_BY": [{"decision": "DEC-01", "claim": "C-001"}],
            "RECORDED_IN": [{"decision": "DEC-01", "source": "SRC-ADR-1"}],
            "SUPERSEDES": [],
        },
        "history": [],
    }


if __name__ == "__main__":
    for name, data in (("northwind", build()), ("bluefin", build_bluefin())):
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        e = data["edges"]
        print(f"{path.name}: {len(data['people'])} people, {len(data['systems'])} systems, "
              f"{len(data['decisions'])} decisions, {len(data['sources'])} sources, {len(data['claims'])} claims, "
              f"{sum(len(v) for v in e.values())} edges")
