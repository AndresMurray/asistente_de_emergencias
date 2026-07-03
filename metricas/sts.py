"""
Semantic Text Similarity usando embeddings de Ollama.
"""

import math
import requests

OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "paraphrase-multilingual"


def get_embedding(text: str) -> list[float]:
    response = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBED_MODEL, "input": text},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["embeddings"][0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x ** 2 for x in a))
    norm_b = math.sqrt(sum(x ** 2 for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def sts(texto_a: str, texto_b: str) -> float:
    return cosine_similarity(get_embedding(texto_a), get_embedding(texto_b))
