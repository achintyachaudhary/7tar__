"""Inspect the structure of the Zerodha Pulse RSS feed."""

import requests
import xml.etree.ElementTree as ET

resp = requests.get(
    "https://pulse.zerodha.com/feed.php",
    timeout=20,
    headers={"User-Agent": "Mozilla/5.0 (gcc stock screener; local dev)"},
)
print("status:", resp.status_code, "| content-type:", resp.headers.get("content-type"))
print("bytes:", len(resp.content))

root = ET.fromstring(resp.content)
channel = root.find("channel")
items = channel.findall("item") if channel is not None else []
print("items:", len(items))

for item in items[:3]:
    print("\n--- item ---")
    for child in item:
        text = (child.text or "").strip().replace("\n", " ")[:160]
        print(f"  <{child.tag}> {text}")
