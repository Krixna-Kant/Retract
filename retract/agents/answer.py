"""Answer agent: a LangGraph loop of router -> tool -> router ... -> answer.

The router chooses the next fixed tool (LLM if configured, deterministic
planner otherwise). The outcome label is never chosen by the LLM: it is
computed from what the graph tools returned:

  ANSWER_WITH_PATH  a relevant live claim has a grounded path to a live root
  CONTESTED         the best relevant claim has a live contradicting rival
  STALE             relevant claims exist but all lost their support
  UNKNOWN_NO_PATH   nothing in memory supports an answer (a valid answer, not an error)

Every answer is written back to the graph as episodic memory:
  (Person)-[:ASKED]->(Answer)-[:CITED]->(Claim), (Agent)-[:WROTE]->(Answer)
so a later revocation can find who was told something that is no longer true.
"""
from __future__ import annotations

import json
import operator
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Callable, TypedDict

from langgraph.graph import END, StateGraph

from .. import llm as L
from .. import tools as T
from ..db import LIVE_CLAIM_STATUSES, graph, rows
from ..engine import now

ANSWER = "agent:answer"
RELEVANT = 0.5
MAX_STEPS = 6
ID_RE = re.compile(r"\b((?:SRC|DEC|C|ACT)-[A-Z0-9\-]+)\b", re.I)


class State(TypedDict, total=False):
    question: str
    tenant: str
    user: str | None
    steps: Annotated[list, operator.add]
    next_call: dict | None
    router_mode: str
    outcome: str
    answer: str
    cited: list
    sources: list
    answer_id: str
    highlight: dict


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

def _called(state, tool, arg=None):
    for s in state.get("steps", []):
        if s["tool"] == tool and (arg is None or arg in json.dumps(s["args"])):
            return True
    return False


def _last(state, tool):
    for s in reversed(state.get("steps", [])):
        if s["tool"] == tool and "error" not in s:
            return s["result"]
    return None


def _systems(g):
    return rows(g, "MATCH (s:System) RETURN s.id AS id, s.name AS name, s.aliases AS aliases")


def plan_offline(g, state: State) -> dict | None:
    q = state["question"]
    low = q.lower()
    ids = [m.upper() for m in ID_RE.findall(q)]
    steps = state.get("steps", [])

    if not steps:
        src = next((i for i in ids if i.startswith(("SRC-", "DEC-"))), None)
        if src and re.search(r"revok|retract|revers|what if|what happens|impact|blast|remove|wrong", low):
            return {"tool": "preview_revocation", "args": {"target_id": src}}
        if src and src.startswith("SRC-") and re.search(r"trace|where|who sent|provenance|trust|suspicious", low):
            return {"tool": "trace_source", "args": {"source_id": src}}
        if re.search(r"who (knows|owns|should i ask|to ask|is the expert)|expert on|ask about", low):
            for s in _systems(g):
                if any(n.lower() in low for n in [s["name"]] + list(s["aliases"] or [])):
                    return {"tool": "who_knows", "args": {"system": s["id"]}}
        claim = next((i for i in ids if i.startswith("C-")), None)
        if claim:
            return {"tool": "explain_support", "args": {"claim_id": claim}}
        dec = next((i for i in ids if i.startswith("DEC-")), None)
        if dec:
            return {"tool": "decision_status", "args": {"decision_id": dec}}
        return {"tool": "search_claims", "args": {"query": q}}

    search = _last(state, "search_claims")
    if search:
        relevant = [c for c in search["claims"] if c["coverage"] >= RELEVANT]
        live = [c for c in relevant if c["live"]]
        dead = [c for c in relevant if not c["live"]]
        wanted = live[:1] + dead[:1]
        for c in wanted:
            if not _called(state, "explain_support", c["id"]):
                return {"tool": "explain_support", "args": {"claim_id": c["id"]}}
        for c in wanted:
            for s in steps:
                if s["tool"] == "explain_support" and s["args"]["claim_id"] == c["id"] and "error" not in s:
                    for d in _decisions_of(s["result"]):
                        if not _called(state, "decision_status", d):
                            return {"tool": "decision_status", "args": {"decision_id": d}}
        for s in steps:
            if s["tool"] == "explain_support" and "error" not in s and s["result"]["claim"]["status"] == "CONTESTED":
                for src in _low_trust_roots(s["result"]):
                    if not _called(state, "trace_source", src):
                        return {"tool": "trace_source", "args": {"source_id": src}}
                for rival in s["result"]["contradicts"]:
                    if not _called(state, "explain_support", rival["id"]):
                        return {"tool": "explain_support", "args": {"claim_id": rival["id"]}}
    return None


def _decisions_of(ex: dict) -> list[str]:
    out = [p["nodes"][-1]["id"] for p in ex["paths"] if p["nodes"][-1]["label"] == "Decision"]
    out += [d["id"] for d in ex["supports_decisions"]]
    return list(dict.fromkeys(out))[:1]


def _low_trust_roots(ex: dict) -> list[str]:
    return list(dict.fromkeys(p["nodes"][-1]["id"] for p in ex["paths"]
                              if p["nodes"][-1]["label"] == "Source" and (p["nodes"][-1].get("trust") or 1) < 0.3))


def plan_llm(state: State) -> dict | None:
    summary = [{"tool": s["tool"], "args": s["args"], "result": s.get("brief", "")} for s in state.get("steps", [])]
    prompt = f"""You are the router of a truth-maintenance memory agent. Pick the next tool call or finish.
Tools (you may ONLY use these, never write queries):
{chr(10).join('- ' + v for k, v in T.TOOL_SPECS.items() if k != 'request_action')}

Guidance: start with search_claims unless the question names an id. Explain the support of the most relevant
claims (live and stale). Check decision_status when a claim rests on a decision. If a claim is CONTESTED and one
source has low trust, trace_source it. Finish once you can say whether the answer is supported, stale, contested
or unknown. At most {MAX_STEPS} steps.

Question: {state['question']}
Steps so far: {json.dumps(summary)[:6000]}

Reply with JSON: {{"tool": "<name>", "args": {{...}}}} or {{"finish": true}}"""
    out = L.llm_json(prompt, system="Reply with one JSON object only.")
    if out.get("finish"):
        return None
    if out.get("tool") not in T.READ_TOOLS:
        raise ValueError(f"router chose unknown tool {out.get('tool')}")
    return {"tool": out["tool"], "args": out.get("args") or {}}


def make_router(g, use_llm: bool):
    def router(state: State) -> dict:
        if len(state.get("steps", [])) >= MAX_STEPS:
            return {"next_call": None}
        mode = "offline"
        call = None
        if use_llm:
            try:
                call = plan_llm(state)
                mode = "llm"
            except Exception:
                call, mode = plan_offline(g, state), "offline (llm failed)"
        else:
            call = plan_offline(g, state)
        if call and any(s["tool"] == call["tool"] and s["args"] == call["args"] for s in state.get("steps", [])):
            call = None
        return {"next_call": call, "router_mode": mode}
    return router


# --------------------------------------------------------------------------
# Tool node
# --------------------------------------------------------------------------

def _brief(tool: str, res: Any) -> str:
    r = res
    if tool == "search_claims":
        return f"{len(r['claims'])} claims: " + "; ".join(
            f"{c['id']} [{c['status']}, cov {c['coverage']}] {c['text'][:70]}" for c in r["claims"][:5])
    if tool == "explain_support":
        return (f"{r['claim']['id']} {r['claim']['status']}, supported={r['supported']}, "
                f"{r['live_paths']} live path(s), roots={r['independent_roots']}, rivals={[c['id'] for c in r['contradicts']]}")
    if tool == "decision_status":
        cur = r["in_force"]["id"] if r["in_force"] else None
        return f"{r['decision']['id']} is {r['decision']['status']}; in force: {cur}; chain {[c['id'] for c in r['chain']]}"
    if tool == "preview_revocation":
        return r["summary"]
    if tool == "who_knows":
        return f"{r['system']['name']} owned by {r['system']['owners']}; experts {[e['name'] for e in r['experts']]}"
    if tool == "trace_source":
        s = r["source"]
        return f"{s['id']} trust={s['trust']} sender={s['sender'] or s['authors']}; {len(r['dependents'])} dependents"
    return str(r)[:200]


def make_tool_node(g, emit: Callable[[dict], None] | None):
    def tool_node(state: State) -> dict:
        call = state["next_call"]
        t0 = time.perf_counter()
        step = {"tool": call["tool"], "args": call["args"]}
        try:
            fn = T.READ_TOOLS[call["tool"]]
            out = fn(g, **call["args"])
            step.update(result=out["result"], nodes=out["nodes"], edges=out["edges"],
                        brief=_brief(call["tool"], out["result"]))
        except (T.ToolError, TypeError) as e:
            step.update(error=str(e), nodes=[], edges=[], brief=f"error: {e}")
        step["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if emit:
            emit({"type": "step", "tool": step["tool"], "args": step["args"], "brief": step["brief"],
                  "nodes": step["nodes"], "edges": step["edges"], "ms": step["ms"], "router": state.get("router_mode")})
        return {"steps": [step], "next_call": None}
    return tool_node


# --------------------------------------------------------------------------
# Answer node
# --------------------------------------------------------------------------

def _fmt_path(p: dict) -> str:
    return " -> ".join(f"{n['id']}" for n in p["nodes"])


def _date(ts) -> str:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return str(ts)


def decide(g, state: State) -> dict:
    steps = [s for s in state.get("steps", []) if "error" not in s]
    explained = {s["result"]["claim"]["id"]: s["result"] for s in steps if s["tool"] == "explain_support"}
    decisions = {s["result"]["decision"]["id"]: s["result"] for s in steps if s["tool"] == "decision_status"}
    search = next((s["result"] for s in steps if s["tool"] == "search_claims"), None)
    first = steps[0] if steps else None
    lines: list[str] = []
    cited: list[str] = []
    sources: list[dict] = []

    if first and first["tool"] in ("preview_revocation", "who_knows", "trace_source") or (
            first and first["tool"] == "decision_status" and not search):
        r = first["result"]
        if first["tool"] == "preview_revocation":
            lines.append(f"Dry run for {r['target']['id']} ({r['target']['title']}): {r['summary']}.")
            if r["invalidated"]:
                lines.append("Would lose all support: " + ", ".join(c["id"] for c in r["invalidated"]) + ".")
            for c in r["survived"]:
                lines.append(f"{c['id']} survives via {' -> '.join(c['support_path'])}.")
            if r["owners"]:
                lines.append("Owners to notify: " + ", ".join(o["name"] for o in r["owners"]) + ".")
            lines.append("Nothing was changed. Applying this needs human approval.")
        elif first["tool"] == "who_knows":
            s = r["system"]
            lines.append(f"{s['name']} is owned by {', '.join(s['owners']) or 'nobody on record'}.")
            if r["experts"]:
                lines.append("People whose documents ground live claims about it: " + ", ".join(
                    f"{e['name']} ({e['team']}, {e['live_claims']} claims)" for e in r["experts"][:5]) + ".")
        elif first["tool"] == "trace_source":
            s = r["source"]
            lines.append(f"{s['id']} \"{s['title']}\" kind={s['kind']} trust={s['trust']}"
                         f"{' sender=' + s['sender'] if s['sender'] else ''}"
                         f"{' authors=' + ', '.join(s['authors']) if s['authors'] else ' (no internal author)'}.")
            lines.append(f"{len(r['dependents'])} claim(s) rest on it: " + ", ".join(d["id"] for d in r["dependents"]) + ".")
            if r["conflicts"]:
                lines.append("It conflicts with: " + ", ".join(f"{c['contradicts']}" for c in r["conflicts"]) + ".")
        else:
            lines += _decision_lines(r)
        return {"outcome": "ANSWER_WITH_PATH", "answer": " ".join(lines), "cited": cited, "sources": sources}

    asked = [s["args"]["claim_id"] for s in steps if s["tool"] == "explain_support"][:1] if not search else []
    relevant_ids = asked or [c["id"] for c in (search["claims"] if search else []) if c["coverage"] >= RELEVANT]
    relevant = [explained[i] for i in relevant_ids if i in explained]

    if not relevant:
        near = search["claims"][:2] if search else []
        text = "No claim in memory has a supporting path for this question, so I will not guess."
        if near:
            text += " Nearest (not relevant enough): " + "; ".join(f"{c['id']} \"{c['text']}\"" for c in near) + "."
        return {"outcome": "UNKNOWN_NO_PATH", "answer": text, "cited": [], "sources": []}

    live = [e for e in relevant if e["supported"]]
    best = live[0] if live else relevant[0]
    rivals_live = [c for c in best["contradicts"] if c["status"] in LIVE_CLAIM_STATUSES]

    def src_line(ex):
        out = []
        for p in ex["paths"]:
            if p["live"]:
                root = p["nodes"][-1]
                sources.append({"id": root["id"], "title": root["text"], "label": root["label"], "trust": root.get("trust")})
                out.append(f"{_fmt_path(p)} ({root['text']}{', trust ' + str(root['trust']) if root.get('trust') is not None else ''})")
        return out

    if live and best["claim"]["status"] == "CONTESTED" and rivals_live:
        outcome = "CONTESTED"
        lines.append(f"Memory disagrees. {best['claim']['id']}: \"{best['claim']['text']}\".")
        for r in rivals_live:
            lines.append(f"Versus {r['id']}: \"{r['text']}\".")
        for ex in [best] + [explained[r["id"]] for r in rivals_live if r["id"] in explained]:
            for sl in src_line(ex):
                lines.append(f"{ex['claim']['id']} rests on {sl}.")
            cited.append(ex["claim"]["id"])
        low = [s for s in sources if s["label"] == "Source" and (s.get("trust") or 1) < 0.3]
        if low:
            lines.append(f"Warning: {', '.join(dict.fromkeys(s['id'] for s in low))} has very low trust; "
                         f"consider quarantining it (needs approval).")
    elif live:
        outcome = "ANSWER_WITH_PATH"
        for ex in live[:1]:
            lines.append(f"{ex['claim']['text']} [{ex['claim']['id']}, {ex['claim']['status']}].")
            for sl in src_line(ex)[:2]:
                lines.append(f"Why: {sl}.")
            cited.append(ex["claim"]["id"])
    else:
        outcome = "STALE"
        for ex in relevant[:2]:
            c = ex["claim"]
            lines.append(f"I used to believe \"{c['text']}\" [{c['id']}], but it is {c['status']}"
                         f"{' because ' + c['invalidated_by'] + ' lost its validity' if c.get('invalidated_by') else ''}.")
            reason = _revocation_reason(g, c.get("invalidated_by"))
            if reason:
                lines.append(reason)
        lines.append("I will not answer from unsupported memory.")

    for d in decisions.values():
        lines += _decision_lines(d)
    stale_related = [e for e in relevant if not e["supported"] and e not in live] if outcome != "STALE" else []
    if stale_related:
        lines.append("Older memory no longer in force: " + "; ".join(
            f"{e['claim']['id']} \"{e['claim']['text']}\" ({e['claim']['status']})" for e in stale_related[:3]) + ".")
    return {"outcome": outcome, "answer": " ".join(lines), "cited": cited, "sources": sources}


def _decision_lines(d: dict) -> list[str]:
    dec = d["decision"]
    if d["is_current"]:
        out = [f"Decision {dec['id']} \"{dec['title']}\" is in force ({dec['date']})."]
    elif d["in_force"]:
        cur = d["in_force"]
        out = [f"Decision {dec['id']} \"{dec['title']}\" is {dec['status']}; the decision in force is "
               f"{cur['id']} \"{cur['title']}\" ({cur['date']}). Chain: "
               + " -> ".join(c["id"] for c in d["chain"]) + "."]
    else:
        out = [f"Decision {dec['id']} is {dec['status']} and nothing active replaces it."]
    if d["supported_by"] and d["live_support"] == 0:
        out.append(f"Warning: none of the claims supporting {dec['id']} are still valid.")
    return out


def _revocation_reason(g, target_id: str | None) -> str:
    if not target_id:
        return ""
    r = rows(g, """
        MATCH (n) WHERE (n:Source OR n:Decision) AND n.id = $id
        OPTIONAL MATCH (a:Action {target: $id, status: 'APPROVED'})
        RETURN coalesce(n.title, n.id) AS title, coalesce(n.revoked_reason, n.change_reason) AS reason,
               a.approved_by AS by, a.decided_at AS at ORDER BY a.decided_at DESC LIMIT 1""", {"id": target_id})
    if not r:
        return ""
    x = r[0]
    out = f"{target_id} \"{x['title']}\""
    if x["reason"]:
        out += f" was retracted: {x['reason']}"
    if x["by"]:
        out += f" (approved by {x['by']} on {_date(x['at'])})"
    return out + "."


def phrase(question: str, decided: dict) -> str:
    """Optional: let the LLM rewrite the answer more naturally, without adding facts."""
    if not L.available():
        return decided["answer"]
    try:
        text = L.llm(
            f"Question: {question}\nOutcome: {decided['outcome']}\nFacts (the ONLY facts you may use, keep every "
            f"id in brackets):\n{decided['answer']}\n\nRewrite as a concise, clear answer of at most 5 sentences. "
            f"Do not add any fact, number or name that is not above. Keep the claim and source ids.",
            system="You phrase answers for a memory system. Never invent facts.")
        text = re.sub(r"[\u2010-\u2015\u2212]", "-", text).strip()
        ids = set(re.findall(r"\b(?:C|SRC|DEC|A|ACT)-[A-Z0-9-]*[A-Z0-9]\b", decided["answer"]))
        if not text or any(i not in text for i in ids):
            return decided["answer"]
        return text
    except Exception:
        return decided["answer"]


def make_answer_node(g, emit):
    def answer_node(state: State) -> dict:
        decided = decide(g, state)
        text = phrase(state["question"], decided)
        aid = "A-" + uuid.uuid4().hex[:6].upper()
        g.query("""
            CREATE (a:Answer {id: $id, question: $q, outcome: $outcome, text: $text, ts: $ts})
            MERGE (ag:Agent {id: $agent})
            CREATE (ag)-[:WROTE]->(a)
            WITH a
            OPTIONAL MATCH (p:Person {id: $user})
            FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | CREATE (p)-[:ASKED]->(a))
            WITH a UNWIND $cited AS cid MATCH (c:Claim {id: cid}) CREATE (a)-[:CITED]->(c)""",
                {"id": aid, "q": state["question"], "outcome": decided["outcome"], "text": text, "ts": now(),
                 "agent": ANSWER, "user": state.get("user") or "", "cited": decided["cited"]})
        nodes, edges = set(), []
        for s in state.get("steps", []):
            nodes.update(s.get("nodes", []))
            edges += s.get("edges", [])
        result = {"outcome": decided["outcome"], "answer": text, "cited": decided["cited"],
                  "sources": list({s["id"]: s for s in decided["sources"]}.values()), "answer_id": aid,
                  "highlight": {"nodes": sorted(nodes), "edges": edges}}
        if emit:
            emit({"type": "answer", **result})
        return result
    return answer_node


def build(g, use_llm: bool, emit=None):
    sg = StateGraph(State)
    sg.add_node("route", make_router(g, use_llm))
    sg.add_node("call_tool", make_tool_node(g, emit))
    sg.add_node("respond", make_answer_node(g, emit))
    sg.set_entry_point("route")
    sg.add_conditional_edges("route", lambda s: "call_tool" if s.get("next_call") else "respond",
                             {"call_tool": "call_tool", "respond": "respond"})
    sg.add_edge("call_tool", "route")
    sg.add_edge("respond", END)
    return sg.compile()


def ask(tenant: str, question: str, user: str | None = None, emit=None, use_llm: bool | None = None) -> dict:
    g = graph(tenant)
    if use_llm is None:
        use_llm = L.available() and os.getenv("LLM_ROUTER", "off").lower() in ("on", "1", "true")
    app = build(g, use_llm, emit)
    final = app.invoke({"question": question, "tenant": tenant, "user": user, "steps": []},
                       config={"recursion_limit": 4 * MAX_STEPS})
    return {k: final.get(k) for k in ("outcome", "answer", "cited", "answer_id", "highlight", "router_mode")} | {
        "steps": [{k: v for k, v in s.items() if k != "result"} for s in final.get("steps", [])],
        "sources": final.get("sources"),
    }
