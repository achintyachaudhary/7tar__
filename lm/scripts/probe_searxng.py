"""Check whether the local SearXNG instance exposes the JSON API."""

import json
import requests

BASE = "http://localhost:8080"

# 1) is it up at all?
try:
    r = requests.get(BASE, timeout=8)
    print("root:", r.status_code, "| content-type:", r.headers.get("content-type"))
except Exception as exc:
    print("root request failed:", exc)
    raise SystemExit(1)

# 2) JSON search API
try:
    r = requests.get(
        f"{BASE}/search",
        params={"q": "Reliance Industries share price", "format": "json"},
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 (gcc lm probe)"},
    )
    print("\n/search?format=json:", r.status_code, "| content-type:", r.headers.get("content-type"))
    if r.status_code == 200 and "json" in (r.headers.get("content-type") or ""):
        data = r.json()
        results = data.get("results", [])
        print("number_of_results:", data.get("number_of_results"))
        print("results returned:", len(results))
        for res in results[:3]:
            print("\n--- result ---")
            print("  title:  ", (res.get("title") or "")[:90])
            print("  url:    ", res.get("url"))
            print("  engine: ", res.get("engine"))
            print("  content:", (res.get("content") or "")[:140])
    else:
        print("JSON not enabled. First 200 chars of body:")
        print(r.text[:200])
except Exception as exc:
    print("json search failed:", exc)
