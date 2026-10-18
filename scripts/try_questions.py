"""Ask the demo questions against a tenant and print outcome + answer.

Run: python scripts/try_questions.py [tenant]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retract.agents.answer import ask  # noqa: E402

QUESTIONS = [
    "Why do we use Ledgerly for billing, and is it still current?",
    "What do we use for the event bus, and is it current?",
    "What is the auth token TTL?",
    "What is the payments webhook endpoint?",
    "When can finance close start each month?",
    "What is the disaster recovery RTO for search-service?",
    "Who knows about the billing-service?",
    "What happens if SRC-MEMO-7 is revoked?",
    "Trace SRC-EMAIL-13",
]

if __name__ == "__main__":
    tenant = sys.argv[1] if len(sys.argv) > 1 else "northwind"
    for q in QUESTIONS:
        r = ask(tenant, q, user="P11")
        print(f"\n=== {q}\n[{r['outcome']}] ({r['router_mode']}) tools: {[s['tool'] for s in r['steps']]}")
        print(r["answer"])
