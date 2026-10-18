import pytest

from eval.scenarios import SCENARIOS, load_scenario
from retract import engine
from retract.agents import auditor, ingest
from retract.db import graph, reset_graph, rows


def status(g, cid):
    return rows(g, "MATCH (c:Claim {id: $id}) RETURN c.status AS s", {"id": cid})[0]["s"]


def statuses(g):
    return {r["id"]: r["s"] for r in rows(g, "MATCH (c:Claim) RETURN c.id AS id, c.status AS s")}


@pytest.fixture()
def scenario_graph(request):
    sc = request.param
    g = reset_graph(f"test_{sc['name'][:2]}")
    load_scenario(g, sc)
    yield g, sc
    g.delete()


@pytest.mark.parametrize("scenario_graph", SCENARIOS, ids=[s["name"] for s in SCENARIOS], indirect=True)
def test_scenario_preview(scenario_graph):
    g, sc = scenario_graph
    before = statuses(g)
    cas = engine.preview(g, sc["target"])
    assert sorted(c["id"] for c in cas.invalidated) == sorted(sc["invalidated"])
    assert sorted(c["id"] for c in cas.survived) == sorted(sc["survived"])
    assert statuses(g) == before, "preview must not write"


@pytest.mark.parametrize("scenario_graph", SCENARIOS, ids=[s["name"] for s in SCENARIOS], indirect=True)
def test_scenario_apply_then_rollback(scenario_graph):
    g, sc = scenario_graph
    auditor.run(g)
    before = statuses(g)
    engine.apply(g, sc["target"])
    after = statuses(g)
    for cid in sc["invalidated"]:
        assert after[cid] == "INVALIDATED"
    for cid in sc["survived"]:
        assert after[cid] in ("PROPOSED", "CONFIRMED", "CONTESTED")
    engine.rollback(g, sc["target"])
    assert statuses(g) == before


def test_survivors_carry_their_independent_path(northwind):
    cas = engine.preview(northwind, "SRC-MEMO-7")
    roots = {c["id"]: c["support_root"] for c in cas.survived}
    assert roots == {"C-M01": "SRC-ADR-12", "C-M02": "SRC-ADR-12", "C-M03": "SRC-SLACK-21",
                     "C-M04": "SRC-EMAIL-4"}
    for c in cas.survived:
        assert "SRC-MEMO-7" not in c["support_path"]


def test_memo_cascade_impact(northwind):
    cas = engine.preview(northwind, "SRC-MEMO-7")
    assert len(cas.invalidated) == 9 and len(cas.survived) == 4
    assert {d["id"] for d in cas.decisions_at_risk} == {"DEC-15", "DEC-16"}
    assert {d["id"] for d in cas.decisions_weakened} == {"DEC-12"}
    assert {o["name"] for o in cas.owners} == {"Priya Raman", "Jonah Achterberg", "Sofia Brandt"}
    assert {a["id"] for a in cas.stale_answers} == {"A-001", "A-002", "A-003"}
    deep = next(c for c in cas.invalidated if c["id"] == "C-M11")
    assert deep["via"] == ["C-M11", "C-M09", "C-M05", "SRC-MEMO-7"]


def test_apply_and_rollback_memo(northwind):
    before = statuses(northwind)
    engine.apply(northwind, "SRC-MEMO-7", reason="figures were for the Enterprise tier")
    assert all(status(northwind, f"C-M{i:02d}") == "INVALIDATED" for i in range(5, 14))
    assert status(northwind, "C-M01") == "PROPOSED", "auditor demotes: corroboration was lost"
    engine.rollback(northwind, "SRC-MEMO-7")
    assert statuses(northwind) == before


def test_loaded_state_from_history_replay(northwind):
    s = statuses(northwind)
    assert s["C-E01"] == s["C-E02"] == s["C-E03"] == "SUPERSEDED"
    assert s["C-E04"] == "CONFIRMED" and s["C-E05"] == "PROPOSED"
    assert s["C-T01"] == s["C-T02"] == "CONTESTED"


def test_decision_in_force(northwind):
    st = engine.decision_status(northwind, "DEC-03")
    assert [c["id"] for c in st["chain"]] == ["DEC-03", "DEC-11", "DEC-19"]
    assert st["in_force"]["id"] == "DEC-19" and not st["is_current"]
    assert engine.decision_status(northwind, "DEC-19")["is_current"]


def test_poison_quarantine_resolves_contest_and_rolls_back(northwind):
    assert status(northwind, "C-L01") == "CONTESTED"
    engine.apply(northwind, "SRC-EMAIL-13", action="quarantine", reason="lookalike domain")
    assert {status(northwind, c) for c in ("C-P01", "C-P02", "C-P03")} == {"QUARANTINED"}
    assert status(northwind, "C-L01") == "CONFIRMED"
    assert status(northwind, "C-L02") == "CONFIRMED"
    engine.rollback(northwind, "SRC-EMAIL-13")
    assert status(northwind, "C-P03") == "PROPOSED"
    assert status(northwind, "C-L01") == "CONTESTED"


def test_explain_support_marks_dead_paths(northwind):
    engine.apply(northwind, "SRC-MEMO-7")
    ex = engine.explain_support(northwind, "C-M01")
    assert ex["supported"] and ex["independent_roots"] == ["SRC-ADR-12"]
    assert any(not p["live"] for p in ex["paths"])
    assert not engine.explain_support(northwind, "C-M11")["supported"]


def test_ingest_corroborates_instead_of_duplicating(northwind):
    n_before = len(statuses(northwind))
    res = ingest.ingest(northwind, {"kind": "SLACK", "title": "#security: TTL", "author_id": "P15",
                                    "text": "Confirming: auth-service access tokens expire after 15 minutes."},
                        use_llm=False)
    assert res["corroborated"] == ["C-T01"] and not res["created"]
    assert len(statuses(northwind)) == n_before
    assert len(engine.explain_support(northwind, "C-T01")["independent_roots"]) == 2


def test_ingest_new_claim_contradiction(northwind):
    res = ingest.ingest(northwind, {"kind": "EMAIL", "title": "retention", "author_id": "P02",
                                    "text": "The event-bus stream retention is 24 hours from next week."},
                        use_llm=False)
    assert len(res["created"]) == 1
    new = res["created"][0]["id"]
    assert status(northwind, new) == "CONTESTED" and status(northwind, "C-E05") == "CONTESTED"


def test_tenant_isolation(northwind):
    from data.generate import build_bluefin
    from data.load import load
    load(build_bluefin(), tenant="test_bluefin")
    bf = graph("test_bluefin")
    try:
        assert engine.node_kind(bf, "SRC-MEMO-7") is None
        engine.apply(northwind, "SRC-MEMO-7")
        assert set(statuses(bf).values()) == {"PROPOSED"}
    finally:
        bf.delete()


def test_blast_radius_ranks_memo_first(northwind):
    top = engine.blast_radius(northwind, limit=3)
    assert top[0]["id"] == "SRC-MEMO-7" and top[0]["would_invalidate"] == 9
