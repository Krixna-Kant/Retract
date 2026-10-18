"""Check every configured LLM provider: latency and a JSON round-trip.

Run: python scripts/llm_check.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retract import llm as L  # noqa: E402

PROMPT = 'Return exactly this JSON array and nothing else: [{"text": "ok", "value": "15m"}]'

if __name__ == "__main__":
    print("provider chain:", L.provider() or "none (offline)")
    for p in L.providers() * 2:
        t = time.time()
        try:
            out = L._call(p, PROMPT, "Reply with JSON only.", 0.0)
            print(f"{p:10s} {time.time() - t:5.1f}s  {out.strip()[:80]!r}")
        except Exception as e:
            print(f"{p:10s} {time.time() - t:5.1f}s  FAILED {type(e).__name__}: {str(e)[:200]}")
