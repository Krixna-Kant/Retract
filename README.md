# RETRACT: a truth-maintenance graph for agent memory

> Agent memory is easy to write and nearly impossible to *un*-write. When a source turns out to be wrong,
> every claim, decision and answer built on it should go stale, except the ones that still have independent
> support. RETRACT does that with graph traversal in FalkorDB.

Built for the WeMakeDevs × FalkorDB **Graph Hacks** hackathon.
Tracks: **1 (Agentic memory)**, **2 (GraphRAG / knowledge graphs)**, **3 (Graph-native analytics)**.

## Quick start (one command)

Requirements: Docker, Python 3.11+, Node 20+.

```bash
git clone <this repo> && cd Retract_Graph
pip install -r requirements.txt
python run.py --open          # http://127.0.0.1:8000
```

`run.py` starts FalkorDB with `docker compose` if it is not already running. It builds the React UI if `web/dist`
is missing or stale, and loads the demo data if the graph is empty. Then it serves the API and the UI from one
uvicorn process. `python run.py --reset` reloads the demo graphs.

Fully containerised, with no local Python or Node: `docker compose up --build`, then open http://localhost:8000.

LLM keys are optional (see `.env.example`). Copy `.env.example` to `.env` and set `GROQ_API_KEY` and/or
`GEMINI_API_KEY`. With keys, ingest extraction and answer phrasing use the LLM. Without them, everything falls
back to deterministic rules, and the cascade, evaluation and tests never need an LLM.

## The problem

A memo describes the new invoicing vendor, Ledgerly. Agents extract 13 claims from it, decisions get made on
those claims, and answers cite them. Later the memo is retracted. What is now false?

* Keyword or vector search over memory can't tell. The stale claims are still the best text match.
* Deleting "everything downstream" over-deletes. Four of those claims were *independently* confirmed by an ADR,
  a Slack thread or an email.
* Two claims cite each other (a support cycle). Naive fixpoint propagation keeps them alive forever.

## How it works

```
(Claim)-[:DERIVED_FROM]->(Source | Decision | Claim)
(Decision)-[:SUPPORTED_BY]->(Claim)      (Decision)-[:SUPERSEDES]->(Decision)
(Person)-[:OWNS]->(System | Decision)    (Person)-[:AUTHORED]->(Source)
(Claim)-[:ABOUT]->(System)               (Claim)-[:CONTRADICTS]->(Claim)
(Answer)-[:CITED]->(Claim)               (Action)-[:TARGETS|CHANGED]->(...)   (Notification)
```

**Grounded support.** A claim is believed only if a `DERIVED_FROM` path runs through *live* claims to a *live
root*, meaning a non-revoked, non-quarantined Source or an ACTIVE Decision. This is the well-founded semantics of
a justification-based truth-maintenance system (Doyle, 1979). Cycles don't count as support because they never
reach a root. The cascade is one FalkorDB query, which also returns the path that saves each survivor:

```cypher
UNWIND $ids AS cid
MATCH p = (c:Claim {id: cid})-[:DERIVED_FROM*1..8]->(r)
WHERE NOT r:Claim
  AND ((r:Source AND r.revoked = false AND coalesce(r.quarantined,false) = false)
       OR (r:Decision AND r.status = 'ACTIVE')) AND NOT r.id IN $xr
  AND all(n IN nodes(p)[1..-1] WHERE n:Claim AND n.status IN $live AND NOT n.id IN $xc)
WITH cid, p ORDER BY length(p)
RETURN cid, collect([n IN nodes(p) | n.id])[0] AS path
```

Revoking or reversing a node:

1. **Preview.** Collect dependents, re-run grounded support with the target hypothetically removed, and iterate
   to a fixpoint. The result has four parts:
   * claims that lose all support,
   * claims that survive, with the path that saves them,
   * decisions left unsupported or weakened,
   * the people to notify (owners of affected systems and decisions) and the past answers that are now stale.
2. **Approval gate.** Every write is an `Action` node (PENDING → APPROVED/REJECTED). Nothing changes until a
   human approves it. Approving writes `prev_status`, links `(Action)-[:CHANGED]->` to each touched node, drafts
   `Notification` nodes (plus `outbox/<action>.json`) and runs the auditor. Rollback restores everything.
3. **Auditor agent.** Marks a claim CONFIRMED when it has ≥ 2 distinct grounded roots. Adds a `CONTRADICTS` edge
   and marks claims CONTESTED when two live claims share a key with different values. Resolves and demotes claims
   as support changes.

**The answer agent is a LangGraph state machine (`route → call_tool → respond`).** The LLM never writes Cypher.
It can only call fixed, validated tools (`search_claims`, `explain_support`, `decision_status`,
`preview_revocation`, `who_knows`, `owners_at_risk`, `trace_source`). The outcome is computed by rules from the
graph, never by the LLM:

| Outcome | Meaning |
|---|---|
| `ANSWER_WITH_PATH` | A live claim with a grounded support path, which is shown |
| `STALE` | The best match was invalidated or superseded; says by what |
| `CONTESTED` | Live claims disagree; both sides and their sources are shown |
| `UNKNOWN_NO_PATH` | Nothing grounded; RETRACT refuses instead of guessing |

The LLM may rephrase the result. If the rewrite drops any claim or source id, the deterministic answer is used
instead. Every answer is stored as an `Answer` node with `CITED` edges, so when a source is later revoked, past
answers built on it surface as stale (episodic memory).

**Ingest agent.** Extracts atomic claims from new text, using the LLM when a key is set and regex rules
otherwise. Keys and values are normalised against existing memory (`15 minutes` → `15m`, reusing the existing
attribute keys). A new source that repeats a known fact *corroborates* that claim instead of duplicating it,
and a conflicting value is flagged CONTESTED.

**Graph analytics (Track 3).**
* `algo.pageRank` over `DERIVED_FROM` finds the foundational sources.
* Blast radius gives a cascade preview for every source, ranked by how much memory would die.
* Bus factor lists systems whose live knowledge rests on one person's sources.

**Multi-tenant.** One FalkorDB graph per tenant (`tenant_northwind`, `tenant_bluefin`), isolated at the graph level.

## Demo data

`data/generate.py` builds a deterministic synthetic company, *Northwind Labs*: 20 people, 10 systems,
25 decisions, 50 sources and 104 claims. It has planted scenarios:

* **Retracted VP memo (`SRC-MEMO-7`).** Revoking it invalidates 9 claims, including a circular pair. 4 claims
  survive on independent sources, 2 decisions are left unsupported, 3 owners are notified and 3 past answers go stale.
* **Decision chain.** DEC-03 → DEC-11 → DEC-19 is replayed through `SUPERSEDES`, so old answers come back as `STALE`.
* **Contested auth token TTL.** 15m vs 60m comes back as `CONTESTED`, with both sources.
* **Poisoned email (`SRC-EMAIL-13`, trust 0.15).** It contradicts legitimate claims. `trace_source` exposes it,
  and quarantine removes everything it alone supports.

A second tenant, *Bluefin*, proves isolation.

## Evaluation

`python -m eval.run_eval`: 15 synthetic cascade scenarios plus the full Northwind memo case. The task is to
predict exactly which claims must be invalidated when a node is revoked.

| Method | Precision | Recall | F1 | Exact-match scenarios |
|---|---|---|---|---|
| `keyword_topk` (text similarity to the source) | 0.63 | 0.47 | 0.54 | 5/16 |
| `one_hop` (direct dependents only) | 0.67 | 0.50 | 0.57 | 4/16 |
| `transitive` (everything downstream) | 0.77 | 1.00 | 0.87 | 10/16 |
| `naive_fixpoint` (re-check support, iterate) | 1.00 | 0.89 | 0.94 | 14/16 |
| **`retract`** (grounded paths) | **1.00** | **1.00** | **1.00** | **16/16** |

`transitive` over-deletes claims with independent support. `naive_fixpoint` misses circular support. Per-scenario
results are in [`eval/results.md`](eval/results.md). Tests: `python -m pytest -q -p no:asyncio` (41 tests).

## Honest limitations

* Synthetic data. The scenarios are planted, and real extraction quality depends on the LLM.
* `DERIVED_FROM` edges from LLM ingest are only as good as the extraction. Depth is capped at 8 hops.
* Contradiction detection is key/value equality on normalised values, not semantic entailment.
* Notifications are drafted to an outbox and the database. No email or Slack is actually sent.
* No authentication. Tenancy is graph isolation, not access control.

## Related work

* J. Doyle, *A Truth Maintenance System*, Artificial Intelligence 12 (1979). Justification-based TMS and
  well-founded support.
* STALE (arXiv 2605.06527) and RECON (arXiv 2607.16716) study stale and conflicting memory in LLM agents.
  RETRACT makes the dependency structure explicit in a graph, so invalidation is a query, not a guess.

## Layout

```
retract/engine.py      grounded support, cascade preview/apply/rollback, analytics
retract/tools.py       the fixed tool set the agents may call
retract/agents/        answer (LangGraph), ingest, auditor
retract/llm.py         provider chain: Groq → Gemini → OpenAI → Anthropic, with fallback
api/main.py            FastAPI (SSE streaming answers) + serves the built UI
web/                   React + react-force-graph-2d
data/  eval/  tests/   synthetic data, evaluation, tests
run.py                 one-command launcher
```

## AI disclosure

This project was built with AI coding assistance (Cursor with Claude), which helped write the code, tests and
documentation. Design, review, and the decisions about what to build are the author's. At runtime, LLMs (Groq
`openai/gpt-oss-120b`, Google `gemini-2.5-flash`) are used only for claim extraction and answer phrasing. They
never write queries and never decide outcomes.
