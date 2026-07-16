"""
CLI para comparar dos textos usando STS.

Uso:
    python sts.py "texto uno" "texto dos"
"""

import sys
from metricas.sts import sts

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Uso: python sts.py \"texto uno\" \"texto dos\"")
        sys.exit(1)

    texto_a, texto_b = sys.argv[1], sys.argv[2]
    score = sts(texto_a, texto_b)

    a_display = texto_a[:80] + ("…" if len(texto_a) > 80 else "")
    b_display = texto_b[:80] + ("…" if len(texto_b) > 80 else "")

    print(f"\n  Texto A: {a_display}")
    print(f"  Texto B: {b_display}")
    print(f"\n  Similitud: {score:.4f}  ({score * 100:.1f}%)\n")
