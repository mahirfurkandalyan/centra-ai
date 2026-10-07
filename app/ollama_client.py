import json
from collections.abc import Iterator

import httpx
import numpy as np

from . import config


class OllamaError(RuntimeError):
    pass


def _check(r: httpx.Response) -> None:
    """Ollama'nın hata mesajını da göster (ör. model bulunamadı)."""
    if r.is_error:
        r.read()
        raise OllamaError(f"Ollama {r.status_code}: {r.text[:300]}")


def embed(texts: list[str]) -> np.ndarray:
    """Metinleri normalize edilmiş vektörlere çevirir (satır başına bir metin)."""
    r = httpx.post(
        f"{config.OLLAMA_URL}/api/embed",
        json={"model": config.EMBED_MODEL, "input": texts, "keep_alive": config.KEEP_ALIVE},
        timeout=600,
    )
    _check(r)
    vecs = np.asarray(r.json()["embeddings"], dtype=np.float32)
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True).clip(min=1e-9)


def chat_stream(messages: list[dict]) -> Iterator[str]:
    payload = {
        "model": config.CHAT_MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": config.KEEP_ALIVE,
        "options": {"temperature": 0.2, "num_ctx": config.NUM_CTX},
    }
    timeout = httpx.Timeout(None, connect=10)
    with httpx.stream("POST", f"{config.OLLAMA_URL}/api/chat", json=payload, timeout=timeout) as r:
        _check(r)
        for line in r.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            if text := chunk.get("message", {}).get("content"):
                yield text
            if chunk.get("done"):
                break


def health() -> dict:
    try:
        r = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        names = [m["name"] for m in r.json().get("models", [])]
        return {
            "ollama": True,
            "chat_model": any(n.startswith(config.CHAT_MODEL) for n in names),
            "embed_model": any(n.startswith(config.EMBED_MODEL) for n in names),
        }
    except httpx.HTTPError:
        return {"ollama": False, "chat_model": False, "embed_model": False}
