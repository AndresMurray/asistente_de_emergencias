"""Índice en memoria del corpus.

Por qué: el corpus son ~170 fragmentos. Buscar por coseno en numpy sobre esa
matriz tarda menos de un milisegundo, mientras que cada consulta a Supabase
(us-west-2) cuesta ~450 ms de red desde Argentina. La base sigue siendo la
fuente de verdad: se lee UNA vez al arrancar el proceso y después el turno no
toca la red para buscar.

Además trae una búsqueda léxica (BM25) que no depende de ningún servicio
externo. Es el respaldo para cuando el embedding de la consulta falla (Google
devuelve 429 con frecuencia en el plan gratuito): una búsqueda por palabras un
poco menos precisa es mucho mejor que decirle a alguien con un herido que el
manual no responde.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace

import numpy as np

from .store import Fragment


def texto_hash(texto: str) -> str:
    """Identidad estable de un fragmento, independiente del id de la base."""
    return hashlib.sha1(texto.strip().encode("utf-8")).hexdigest()[:16]


# --- normalización para la búsqueda léxica ---------------------------------

_STOPWORDS = frozenset(
    """a al algo algun alguna algunas alguno algunos ante antes aqui asi aun
    cada como con contra cual cuando de del desde donde dos e el ella ellas
    ellos en entre era es esa esas ese eso esos esta estan estar este esto
    estos fue fueron ha hace hacia han hasta hay la las le les lo los mas me
    mi mientras muy nada ni no nos o otra otras otro otros para pero poco por
    porque que quien se ser si sin sobre su sus tambien tan tanto te tiene
    tienen todo todos tu un una unas uno unos y ya yo""".split()
)


def _sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )


def tokenizar(texto: str) -> list[str]:
    """Tokens normalizados: minúsculas, sin acentos, sin stopwords, con un
    stemming de prefijo (6 letras) que alcanza para juntar "hemorragia" con
    "hemorragias" o "comprimir" con "compresiones" sin traer un stemmer."""
    palabras = re.findall(r"[a-z0-9ñ]+", _sin_acentos(texto.lower()))
    return [p[:6] for p in palabras if len(p) > 2 and p not in _STOPWORDS]


@dataclass
class _Doc:
    fragment: Fragment
    hash: str
    tf: Counter
    largo: int


class MemoryIndex:
    """Matriz de embeddings normalizados + índice BM25 del mismo corpus."""

    def __init__(self, fragments: list[Fragment], embeddings: list[list[float]]) -> None:
        if len(fragments) != len(embeddings):
            raise ValueError("fragmentos y embeddings no coinciden")
        self._fragments = fragments
        matriz = np.asarray(embeddings, dtype=np.float32)
        normas = np.linalg.norm(matriz, axis=1, keepdims=True)
        normas[normas == 0] = 1.0
        self._matriz = matriz / normas
        self._por_hash = {texto_hash(f.text): i for i, f in enumerate(fragments)}

        # BM25: se indexa texto + sección, porque el título de la sección suele
        # tener exactamente la palabra que dice quien llama ("hemorragias").
        self._docs: list[_Doc] = []
        df: Counter = Counter()
        for f in fragments:
            toks = tokenizar(" ".join(filter(None, (f.section, f.subsection, f.text))))
            tf = Counter(toks)
            df.update(tf.keys())
            self._docs.append(_Doc(f, texto_hash(f.text), tf, len(toks)))
        n = max(len(self._docs), 1)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._largo_medio = sum(d.largo for d in self._docs) / n

    def __len__(self) -> int:
        return len(self._fragments)

    # -- semántica ----------------------------------------------------------

    def buscar_vector(self, vector: list[float], limite: int) -> list[Fragment]:
        """Top-k por similitud coseno. Devuelve copias con el score puesto."""
        v = np.asarray(vector, dtype=np.float32)
        norma = float(np.linalg.norm(v)) or 1.0
        scores = self._matriz @ (v / norma)
        orden = np.argsort(-scores)[:limite]
        return [replace(self._fragments[i], score=float(scores[i])) for i in orden]

    def por_hash(self, h: str, score: float) -> Fragment | None:
        i = self._por_hash.get(h)
        return None if i is None else replace(self._fragments[i], score=score)

    # -- léxica -------------------------------------------------------------

    def buscar_lexico(
        self, consulta: str, limite: int, min_cobertura: float = 0.35
    ) -> list[Fragment]:
        """BM25 para ordenar; el score que se devuelve es la cobertura de la
        consulta (idf de los términos encontrados / idf total, 0 a 1), que se
        lee como relevancia y sirve de piso: sin ese piso, cualquier fragmento
        que comparta una palabra suelta pasaría como resultado."""
        todos = list(dict.fromkeys(tokenizar(consulta)))
        terminos = [t for t in todos if t in self._idf]
        if not terminos:
            return []
        # Una palabra que el corpus no tiene cuenta como la más rara: si la
        # consulta es sobre algo que el manual no trata, la cobertura baja.
        idf_max = max(self._idf.values())
        idf_total = sum(self._idf.get(t, idf_max) for t in todos)
        k1, b = 1.5, 0.75
        puntuados = []
        for d in self._docs:
            bm25 = 0.0
            cubierto = 0.0
            for t in terminos:
                f = d.tf.get(t, 0)
                if not f:
                    continue
                cubierto += self._idf[t]
                bm25 += self._idf[t] * f * (k1 + 1) / (
                    f + k1 * (1 - b + b * d.largo / self._largo_medio)
                )
            if bm25 > 0:
                cobertura = cubierto / idf_total if idf_total else 0.0
                puntuados.append((bm25, cobertura, d))
        puntuados.sort(key=lambda x: x[0], reverse=True)
        return [
            replace(d.fragment, score=round(cob, 3))
            for _, cob, d in puntuados[:limite]
            if cob >= min_cobertura
        ]
