import re

import requests

from app.config import OLLAMA_URL, OLLAMA_MODEL

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def chat(prompt: str, timeout: int = 600) -> dict:
    """Send a prompt to Ollama and return {'answer': str, 'reasoning': str}.

    deepseek-r1 emits its chain of thought inside <think>...</think>;
    we split that out so the UI can show it separately.
    """
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    response.raise_for_status()
    raw = response.json().get("response", "")

    reasoning = "\n".join(m.strip("\n") for m in THINK_RE.findall(raw)).strip()
    answer = THINK_RE.sub("", raw).strip()
    # Model occasionally leaves an unclosed think block at the start
    if answer.startswith("<think>"):
        answer = answer.split("</think>")[-1].strip()
    return {"answer": answer, "reasoning": reasoning}


def is_available() -> bool:
    try:
        return requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).ok
    except requests.RequestException:
        return False
