"""Run the mini evaluation: every method on every scenario, precision/recall of
the predicted invalidated set. Writes eval/results.md and eval/results.json.

Run: python -m eval.run_eval
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.methods import METHODS  # noqa: E402
from eval.scenarios import SCENARIOS, load_scenario  # noqa: E402
from retract import llm as L  # noqa: E402
from retract.db import graph, reset_graph  # noqa: E402

OUT = Path(__file__).parent


def score(pred: set[str], gold: set[str]) -> tuple[int, int, int]:
    return len(pred & gold), len(pred - gold), len(gold - pred)


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def northwind_case() -> dict:
    """The planted SRC-MEMO-7 case on the full demo graph, reloaded fresh."""
    from data.generate import build
    from data.load import load
    load(build(), tenant="eval_northwind")
    gold = {f"C-M{i:02d}" for i in range(5, 14)}
    return {"name": "16_northwind_memo (full graph)", "target": "SRC-MEMO-7", "invalidated": sorted(gold),
            "tenant": "eval_northwind"}


def run(include_llm: bool | None = None) -> dict:
    include_llm = L.available() if include_llm is None else include_llm
    methods = {k: v for k, v in METHODS.items() if include_llm or k != "llm_topk"}
    cases = []
    for sc in SCENARIOS:
        tenant = f"eval_{sc['name'][:2]}"
        load_scenario(reset_graph(tenant), sc)
        cases.append({**sc, "tenant": tenant})
    cases.append(northwind_case())

    per_case, totals = [], {m: [0, 0, 0, 0] for m in methods}  # tp, fp, fn, exact
    for case in cases:
        g = graph(case["tenant"])
        gold = set(case["invalidated"])
        row = {"scenario": case["name"], "gold": sorted(gold)}
        for name, fn in methods.items():
            pred = fn(g, case["target"])
            tp, fp, fn_ = score(pred, gold)
            totals[name][0] += tp
            totals[name][1] += fp
            totals[name][2] += fn_
            totals[name][3] += int(pred == gold)
            row[name] = {"pred": sorted(pred), "tp": tp, "fp": fp, "fn": fn_, "exact": pred == gold}
        per_case.append(row)
        g.delete()

    summary = {}
    for name, (tp, fp, fn_, exact) in totals.items():
        p, r, f = prf(tp, fp, fn_)
        summary[name] = {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3),
                         "exact": exact, "cases": len(cases)}
    result = {"llm_provider": L.provider(), "summary": summary, "cases": per_case}
    (OUT / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (OUT / "results.md").write_text(to_markdown(result), encoding="utf-8")
    return result


def to_markdown(result: dict) -> str:
    s = result["summary"]
    lines = ["| Method | Precision | Recall | F1 | Exact-match scenarios |", "|---|---|---|---|---|"]
    for name, m in s.items():
        lines.append(f"| `{name}` | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} | "
                     f"{m['exact']}/{m['cases']} |")
    lines += ["", "Per scenario (exact match of the invalidated set):", "",
              "| Scenario | " + " | ".join(f"`{n}`" for n in s) + " |",
              "|---|" + "---|" * len(s)]
    for c in result["cases"]:
        cells = []
        for n in s:
            r = c[n]
            cells.append("yes" if r["exact"] else f"no (+{r['fp']} / -{r['fn']})")
        lines.append(f"| {c['scenario']} | " + " | ".join(cells) + " |")
    lines += ["", "`+x / -y` = x false positives, y missed claims.",
              f"LLM provider for `llm_topk`: {result['llm_provider'] or 'not run (no key configured)'}"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    res = run()
    print(to_markdown(res))
