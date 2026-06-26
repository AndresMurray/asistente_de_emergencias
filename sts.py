"""
Compara dos textos usando Semantic Text Similarity vía el modelo
paraphrase-multilingual ya corriendo en Ollama.

Uso:
    python sts.py "texto uno" "texto dos"
"""

import sys
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
    return dot / (norm_a * norm_b)


def sts(texto_a: str, texto_b: str) -> float:
    emb_a = get_embedding(texto_a)
    emb_b = get_embedding(texto_b)
    return cosine_similarity(emb_a, emb_b)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python sts.py \"texto uno\" \"texto dos\"")
        sys.exit(1)

    texto_a, texto_b = sys.argv[1], sys.argv[2]

    score = sts(texto_a, texto_b)

    print(f"\n  Texto A: {texto_a[:80]}")
    print(f"  Texto B: {texto_b[:80]}")
    print(f"\n  Similitud: {score:.4f}  ({score * 100:.1f}%)\n")
