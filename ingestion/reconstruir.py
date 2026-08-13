"""Reconstruye el texto del documento desde los chunks que están en la base.

Por qué existe: el PDF original (COMPORTAMIENTO-EN-CASO-DE-ACCIDENTE-PRIMEROS-
AUXILIOS.pdf) no está en el repo — data/raw/ está gitignoreado y vacío, y el
único JSON trackeado tiene 3 chunks mock. Sin el PDF no se puede re-extraer.

Pero sí se puede recuperar el documento: el chunker viejo dejaba 50 caracteres de
overlap entre chunks consecutivos, y medido, los 287 pares de la tabla comparten
ese overlap sin excepción. Des-overlapeando la cadena sale un documento continuo
de ~116 mil caracteres con la prosa y la puntuación intactas.

Qué se perdió y hay que tener en cuenta:
- Los newlines: solo 15 de 288 chunks los conservan. La estructura de párrafos no
  está, así que los headings hay que detectarlos inline y no con regex ancorados
  a línea (^...$ con re.M encuentra CERO headings en el texto reconstruido).
- Unos 288 puntos de fin de oración, en los viejos puntos de corte, porque
  _split_recursive descartaba el separador ". " al partir.
- La basura de índice y los "TEMA 3 Pág. N" vienen incluidos, pero es justo lo
  que la limpieza saca igual.

Re-extraer del PDF sigue siendo mejor (da páginas y párrafos reales). Esto es el
plan B que permite arreglar el chunking hoy en lugar de esperar el archivo.

Uso:
    python -m ingestion.reconstruir                    # a stdout
    python -m ingestion.reconstruir -o data/processed/corpus.txt
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg2
from dotenv import load_dotenv

# Overlap mínimo que se busca entre chunks consecutivos. El chunker viejo usaba
# chunk_overlap=50, pero se prueba desde más arriba hacia abajo para tolerar
# variaciones y quedarse con el solape más largo posible.
OVERLAP_MAX = 200
OVERLAP_MIN = 10


def traer_chunks(database_url: str, tabla: str = "chunks") -> list[str]:
    conn = psycopg2.connect(database_url, connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT text FROM {tabla} ORDER BY id;")
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def des_overlapear(chunks: list[str]) -> tuple[str, int, int]:
    """Une la cadena de chunks quitando el solape.

    Devuelve (texto, uniones_limpias, uniones_totales). Si algún par no comparte
    solape se une con un espacio y se cuenta como sucia, para que quede visible
    en lugar de pasar desapercibido.
    """
    if not chunks:
        return "", 0, 0

    acumulado = chunks[0]
    limpias = 0
    for siguiente in chunks[1:]:
        mejor = 0
        tope = min(len(acumulado), OVERLAP_MAX)
        for n in range(tope, OVERLAP_MIN - 1, -1):
            if siguiente.startswith(acumulado[-n:]):
                mejor = n
                break
        if mejor:
            acumulado += siguiente[mejor:]
            limpias += 1
        else:
            acumulado += " " + siguiente
    return acumulado, limpias, len(chunks) - 1


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-o", "--salida", help="archivo donde escribir (default: stdout)")
    p.add_argument("--tabla", default="chunks", help="tabla de origen")
    args = p.parse_args()

    load_dotenv(".env.local")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        sys.exit("ERROR: falta DATABASE_URL (ver .env.example)")

    chunks = traer_chunks(database_url, args.tabla)
    texto, limpias, total = des_overlapear(chunks)

    print(
        f"[reconstruir] {len(chunks)} chunks -> {len(texto):,} caracteres "
        f"| uniones por solape: {limpias}/{total}",
        file=sys.stderr,
    )
    if total and limpias < total:
        print(
            f"[reconstruir] OJO: {total - limpias} uniones sin solape, unidas con "
            "espacio. Puede faltar texto entre esos chunks.",
            file=sys.stderr,
        )

    if args.salida:
        os.makedirs(os.path.dirname(args.salida) or ".", exist_ok=True)
        with open(args.salida, "w", encoding="utf-8") as f:
            f.write(texto)
        print(f"[reconstruir] escrito en {args.salida}", file=sys.stderr)
    else:
        sys.stdout.write(texto)


if __name__ == "__main__":
    main()
