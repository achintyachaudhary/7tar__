"""End-to-end smoke test against the running API on localhost:8001."""

import json

import requests

BASE = "http://localhost:8001"

print("1) /api/health")
h = requests.get(f"{BASE}/api/health", timeout=10).json()
print("  ", h)
assert h["ollama"] and h["qdrant"] and h["database"] != "none", "a component is down"

print("\n2) /api/stocks/search?q=relia")
hits = requests.get(f"{BASE}/api/stocks/search", params={"q": "relia"}, timeout=15).json()
print("  ", [(s["symbol"], s["company_name"]) for s in hits[:5]])
assert hits, "no search results"
symbol = hits[0]["symbol"]

print(f"\n3) /api/analyze {symbol} (local LLM — may take a while)")
r = requests.post(f"{BASE}/api/analyze", json={"symbol": symbol}, timeout=900)
r.raise_for_status()
out = r.json()
ps = (out["data"] or {}).get("price_summary")
print("   price_summary:", json.dumps(ps))
print("   news_used:", [n.get("title", "")[:50] for n in out["news_used"]])
print("   report (first 600 chars):\n")
print(out["report"][:600])
assert out["report"], "empty report"

print("\nSMOKE TEST PASSED")
