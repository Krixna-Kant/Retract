"""15 scripted revocation scenarios with hand-labelled expected outcomes.

Each scenario is a small graph, one retraction target, the set of claims that
must lose all support (`invalidated`) and the set that must survive on
independent support (`survived`). Claim text is written so that some
dependencies are implicit (no keyword overlap with the revoked source) and
some keyword matches are unrelated, which is where retrieval baselines fail.

Format:
  sources:   (id, text, revoked)
  decisions: (id, title, status)
  claims:    (id, text, parents, status)   status defaults to PROPOSED
"""

S = "PROPOSED"

SCENARIOS = [
    {
        "name": "01_single_hop",
        "about": "One claim, one source.",
        "sources": [("S1", "Vendor Acme quote: storage costs 2 cents per GB", False)],
        "claims": [("C1", "Acme storage costs 2 cents per GB", ["S1"])],
        "target": "S1", "invalidated": ["C1"], "survived": [],
    },
    {
        "name": "02_multi_hop",
        "about": "A three-claim chain built on one memo.",
        "sources": [("S1", "Capacity memo: the cluster handles 50k rps", False)],
        "claims": [("C1", "The cluster handles 50k rps", ["S1"]),
                   ("C2", "Black Friday traffic fits without scaling", ["C1"]),
                   ("C3", "No extra on-call staff is needed in November", ["C2"])],
        "target": "S1", "invalidated": ["C1", "C2", "C3"], "survived": [],
    },
    {
        "name": "03_independent_support_survives",
        "about": "A claim with two sources survives losing one.",
        "sources": [("S1", "Vendor memo: data is stored in Frankfurt", False),
                    ("S2", "Signed DPA: data residency is Frankfurt", False)],
        "claims": [("C1", "Customer data is stored in Frankfurt", ["S1", "S2"])],
        "target": "S1", "invalidated": [], "survived": ["C1"],
    },
    {
        "name": "04_shared_support",
        "about": "Three claims share a source; one has a second source.",
        "sources": [("S1", "Ops handbook v1: deploys on Tuesday, backups nightly, logs kept 30 days", False),
                    ("S2", "Backup policy: nightly snapshots", False)],
        "claims": [("C1", "Deploys happen on Tuesday", ["S1"]),
                   ("C2", "Backups run nightly", ["S1", "S2"]),
                   ("C3", "Logs are kept for 30 days", ["S1"])],
        "target": "S1", "invalidated": ["C1", "C3"], "survived": ["C2"],
    },
    {
        "name": "05_implicit_dependency",
        "about": "Downstream claims share no keywords with the revoked source.",
        "sources": [("S1", "Vendor Zento promises 99.99% uptime for the checkout API", False)],
        "claims": [("C1", "Zento checkout API uptime is 99.99%", ["S1"]),
                   ("C2", "We do not need a failover path for payments", ["C1"]),
                   ("C3", "Payment incidents can wait for business hours", ["C2"])],
        "target": "S1", "invalidated": ["C1", "C2", "C3"], "survived": [],
    },
    {
        "name": "06_diamond",
        "about": "Two claims from one source both feed a third.",
        "sources": [("S1", "Pricing memo: plan A is 10 EUR, plan B is 20 EUR", False)],
        "claims": [("C1", "Plan A costs 10 EUR", ["S1"]),
                   ("C2", "Plan B costs 20 EUR", ["S1"]),
                   ("C3", "Plan B is exactly double plan A", ["C1", "C2"])],
        "target": "S1", "invalidated": ["C1", "C2", "C3"], "survived": [],
    },
    {
        "name": "07_diamond_with_rescue",
        "about": "One parent dies, the other is independently supported.",
        "sources": [("S1", "Draft spec: login uses SMS codes and passkeys", False),
                    ("S2", "Security review: passkeys are supported", False)],
        "claims": [("C1", "Login uses SMS codes", ["S1"]),
                   ("C2", "Login supports passkeys", ["S1", "S2"]),
                   ("C3", "Users have at least one second factor at login", ["C1", "C2"])],
        "target": "S1", "invalidated": ["C1"], "survived": ["C2", "C3"],
    },
    {
        "name": "08_circular_support",
        "about": "Two claims support each other; their only real root is revoked.",
        "sources": [("S1", "Sales call notes: the API has no rate limit", False)],
        "claims": [("C1", "The partner API has no rate limit", ["S1", "C2"]),
                   ("C2", "Bulk sync can run unthrottled against the partner API", ["C1"])],
        "target": "S1", "invalidated": ["C1", "C2"], "survived": [],
    },
    {
        "name": "09_circular_with_real_root",
        "about": "A cycle that also has an independent live root survives.",
        "sources": [("S1", "Slack: the queue holds 7 days of messages", False),
                    ("S2", "Broker config export: retention 7 days", False)],
        "claims": [("C1", "Queue retention is 7 days", ["S1", "C2"]),
                   ("C2", "Consumers can replay a full week of messages", ["C1", "S2"])],
        "target": "S1", "invalidated": [], "survived": ["C1", "C2"],
    },
    {
        "name": "10_decision_reversal",
        "about": "Reversing a decision retracts what was derived from it.",
        "sources": [],
        "decisions": [("D1", "Freeze all hiring in Q3", "ACTIVE")],
        "claims": [("C1", "No new engineers join in Q3", ["D1"]),
                   ("C2", "The Q3 roadmap must fit the current headcount", ["C1"])],
        "target": "D1", "invalidated": ["C1", "C2"], "survived": [],
    },
    {
        "name": "11_decision_plus_source",
        "about": "A claim backed by a decision and an independent document survives the reversal.",
        "sources": [("S1", "Infra inventory: production runs in eu-west", False)],
        "decisions": [("D1", "Run production in eu-west", "ACTIVE")],
        "claims": [("C1", "Production runs in eu-west", ["D1", "S1"])],
        "target": "D1", "invalidated": [], "survived": ["C1"],
    },
    {
        "name": "12_dead_intermediate_cannot_rescue",
        "about": "A path through an already-invalidated claim is not support.",
        "sources": [("S1", "Runbook v2: restart order is db then api", False),
                    ("S2", "Runbook v1: restart order is api then db", False)],
        "claims": [("C1", "Restart order is api then db", ["S2"], "INVALIDATED"),
                   ("C2", "The api must be restarted before the db", ["S1", "C1"])],
        "target": "S1", "invalidated": ["C2"], "survived": [],
    },
    {
        "name": "13_other_support_already_revoked",
        "about": "Two sources, but the second was revoked earlier.",
        "sources": [("S1", "Email: the SLA credit is 10 percent", False),
                    ("S2", "Old contract: the SLA credit is 10 percent", True)],
        "claims": [("C1", "The SLA credit is 10 percent", ["S1", "S2"])],
        "target": "S1", "invalidated": ["C1"], "survived": [],
    },
    {
        "name": "14_deep_chain",
        "about": "A seven-step chain of inference from one source.",
        "sources": [("S1", "Forecast: revenue grows 40 percent", False)],
        "claims": [("C1", "Revenue grows 40 percent", ["S1"]),
                   ("C2", "We can afford two new teams", ["C1"]),
                   ("C3", "The data team doubles", ["C2"]),
                   ("C4", "The warehouse needs more capacity", ["C3"]),
                   ("C5", "We sign the larger storage contract", ["C4"]),
                   ("C6", "Storage spend rises in Q4", ["C5"]),
                   ("C7", "Q4 margin target is lowered", ["C6"])],
        "target": "S1", "invalidated": ["C1", "C2", "C3", "C4", "C5", "C6", "C7"], "survived": [],
    },
    {
        "name": "15_keyword_trap",
        "about": "Claims that mention the same vendor but rest on other sources are unaffected.",
        "sources": [("S1", "Ledgerly memo: Ledgerly invoices settle in 2 hours", False),
                    ("S2", "Ledgerly contract: Ledgerly is our invoicing vendor", False),
                    ("S3", "Ledgerly status page: Ledgerly supports EUR", False)],
        "claims": [("C1", "Ledgerly invoices settle in 2 hours", ["S1"]),
                   ("C2", "Ledgerly is our invoicing vendor", ["S2"]),
                   ("C3", "Ledgerly supports EUR invoices", ["S3"])],
        "target": "S1", "invalidated": ["C1"], "survived": [],
    },
]


def load_scenario(g, sc: dict) -> None:
    """Write a scenario into an empty graph."""
    from retract.db import create_schema
    create_schema(g)
    g.query("""UNWIND $rows AS r CREATE (:Source {id: r[0], title: r[1], text: r[1], revoked: r[2],
                                                  quarantined: false, kind: 'MEMO'})""",
            {"rows": [list(s) for s in sc.get("sources", [])]})
    g.query("""UNWIND $rows AS r CREATE (:Decision {id: r[0], title: r[1], status: r[2]})""",
            {"rows": [list(d) for d in sc.get("decisions", [])]})
    claims = [{"id": c[0], "text": c[1], "parents": c[2], "status": c[3] if len(c) > 3 else S}
              for c in sc["claims"]]
    g.query("""UNWIND $rows AS r CREATE (:Claim {id: r.id, text: r.text, status: r.status})""", {"rows": claims})
    for label in ("Source", "Claim", "Decision"):
        g.query(f"""UNWIND $rows AS r MATCH (c:Claim {{id: r.id}})
                    UNWIND r.parents AS pid MATCH (t:{label} {{id: pid}})
                    CREATE (c)-[:DERIVED_FROM]->(t)""", {"rows": claims})
