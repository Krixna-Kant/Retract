"""Validate a generated dataset before it is loaded: every edge endpoint exists,
ids are unique, every claim has 1-3 DERIVED_FROM targets, and the planted
scenarios have the shape the demo and the tests rely on."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def validate(data: dict) -> list[str]:
    errors: list[str] = []
    ids: dict[str, str] = {}
    for label, key in (("Team", "teams"), ("Person", "people"), ("System", "systems"), ("Source", "sources"),
                       ("Claim", "claims"), ("Decision", "decisions"), ("Agent", "agents"), ("Answer", "answers")):
        for n in data[key]:
            if n["id"] in ids:
                errors.append(f"duplicate id {n['id']} ({ids[n['id']]} and {label})")
            ids[n["id"]] = label

    def need(node_id, labels, ctx):
        if ids.get(node_id) not in labels:
            errors.append(f"{ctx}: {node_id!r} is not a {'/'.join(labels)}")

    e = data["edges"]
    for r in e["DERIVED_FROM"]:
        need(r["claim"], ["Claim"], "DERIVED_FROM.claim")
        need(r["target"], ["Source", "Claim", "Decision"], "DERIVED_FROM.target")
        if r["claim"] == r["target"]:
            errors.append(f"self-support on {r['claim']}")
    for r in e["ABOUT"]:
        need(r["claim"], ["Claim"], "ABOUT.claim")
        need(r["system"], ["System"], "ABOUT.system")
    for r in e["OWNS"]:
        need(r["person"], ["Person"], "OWNS.person")
        need(r["target"], ["System", "Decision"], "OWNS.target")
    for r in e["AUTHORED"]:
        need(r["person"], ["Person"], "AUTHORED.person")
        need(r["source"], ["Source"], "AUTHORED.source")
    for r in e["MEMBER_OF"]:
        need(r["person"], ["Person"], "MEMBER_OF.person")
        need(r["team"], ["Team"], "MEMBER_OF.team")
    for r in e["SUPPORTED_BY"]:
        need(r["decision"], ["Decision"], "SUPPORTED_BY.decision")
        need(r["claim"], ["Claim"], "SUPPORTED_BY.claim")
    for r in e["RECORDED_IN"]:
        need(r["decision"], ["Decision"], "RECORDED_IN.decision")
        need(r["source"], ["Source"], "RECORDED_IN.source")
    for h in data["history"]:
        need(h["newer"], ["Decision"], "history.newer")
        need(h["older"], ["Decision"], "history.older")
    for a in data["answers"]:
        need(a["asked_by"], ["Person"], "answer.asked_by")
        for c in a["cited"]:
            need(c, ["Claim"], "answer.cited")

    support = Counter(r["claim"] for r in e["DERIVED_FROM"])
    for c in data["claims"]:
        if not 1 <= support[c["id"]] <= 3:
            errors.append(f"{c['id']} has {support[c['id']]} DERIVED_FROM targets (need 1-3)")
    if len({r["claim"] for r in e["ABOUT"]}) != len(data["claims"]):
        errors.append("every claim needs exactly one ABOUT system")

    if data["tenant"] == "northwind":
        memo = {r["claim"] for r in e["DERIVED_FROM"] if r["target"] == "SRC-MEMO-7"}
        if len(memo) != 8:
            errors.append(f"SRC-MEMO-7 should have 8 direct dependents, has {len(memo)}")
        keys = Counter(c["key"] for c in data["claims"] if c["key"])
        if keys["auth-service.token_ttl"] != 2:
            errors.append("contested TTL scenario missing")
        if not any(s["id"] == "SRC-EMAIL-13" and s["trust"] < 0.3 for s in data["sources"]):
            errors.append("poisoned email missing or trusted")
    return errors


if __name__ == "__main__":
    paths = sys.argv[1:] or [str(Path(__file__).parent / n) for n in ("northwind.json", "bluefin.json")]
    bad = False
    for p in paths:
        errs = validate(json.loads(Path(p).read_text(encoding="utf-8")))
        print(f"{Path(p).name}: {'OK' if not errs else f'{len(errs)} error(s)'}")
        for err in errs:
            print("  -", err)
        bad |= bool(errs)
    sys.exit(1 if bad else 0)
