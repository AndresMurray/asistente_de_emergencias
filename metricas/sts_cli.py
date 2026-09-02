#!/usr/bin/env python3
"""STS (Semantic Textual Similarity) entre dos strings por CLI.

Uso:
    python metricas/sts_cli.py "texto uno" "texto dos"
    python metricas/sts_cli.py --gemini "texto uno" "texto dos"

Usa Cohere por defecto (embed-multilingual-v3.0). Con --gemini usa
gemini-embedding-001 (Google AI).
"""

import argparse
import asyncio
import math
import os
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env.local", override=True)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def embed_cohere(text: str) -> List[float]:
    import aiohttp

    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        sys.exit("ERROR: falta COHERE_API_KEY en .env.local")

    payload = {
        "texts": [text],
        "model": "embed-multilingual-v3.0",
        "input_type": "search_document",
        "embedding_types": ["float"],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.cohere.ai/v1/embed",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                sys.exit(f"ERROR Cohere ({resp.status}): {body[:300]}")
            data = await resp.json()
            return data["embeddings"]["float"][0]


async def embed_gemini(text: str) -> List[float]:
    import aiohttp

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        sys.exit("ERROR: falta GEMINI_API_KEY en .env.local")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={api_key}"
    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text}]},
        "taskType": "RETRIEVAL_QUERY",
        "outputDimensionality": 768,
    }
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                sys.exit(f"ERROR Gemini ({resp.status}): {body[:300]}")
            data = await resp.json()
            return data["embedding"]["values"]


async def sts(a: str, b: str, proveedor: str) -> float:
    if proveedor == "gemini":
        emb_a, emb_b = await embed_gemini(a), await embed_gemini(b)
    else:
        emb_a, emb_b = await embed_cohere(a), await embed_cohere(b)
    return cosine_similarity(emb_a, emb_b)


def main():
    parser = argparse.ArgumentParser(description="STS entre dos strings")
    parser.add_argument("texto_a", help="Primer string")
    parser.add_argument("texto_b", help="Segundo string")
    parser.add_argument(
        "--gemini",
        action="store_true",
        help="Usar Gemini en lugar de Cohere",
    )
    args = parser.parse_args()

    proveedor = "gemini" if args.gemini else "cohere"
    score = asyncio.run(sts(args.texto_a, args.texto_b, proveedor))

    print(f"Proveedor: {proveedor}")
    print(f"Texto A:   {args.texto_a}")
    print(f"Texto B:   {args.texto_b}")
    print(f"STS:       {score:.4f}")


if __name__ == "__main__":
    main()
