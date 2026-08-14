"""Acceso a pgvector.

Cambios respecto de la versión inline en agent.py:

1. Pool de conexiones en lugar de una única conexión global de módulo. La
   conexión global se compartía entre todos los jobs concurrentes del proceso,
   que es una condición de carrera esperando a pasar.
2. Devuelve el score de similitud, no solo el texto. Sin score el LLM no puede
   distinguir un match bueno de uno malo, y no hay forma de poner un piso.
3. Se adapta al esquema: hoy la tabla es chunks(id, text, embedding) sin
   metadata; después de la migración de Fase 4 tiene source/section/páginas.
   Detecta qué columnas existen una vez y arma el SELECT acorde, así el mismo
   código sirve antes y después de reingestar.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import psycopg2
from pgvector.psycopg2 import register_vector
from psycopg2 import pool as pg_pool

from .config import RagSettings
from .errors import RetrievalError

logger = logging.getLogger("rag.store")

# Columnas opcionales que aparecen después de la migración de Fase 4.
_OPTIONAL_COLUMNS = ("source", "section", "subsection", "page_start", "page_end")


@dataclass
class Fragment:
    text: str
    score: float
    source: str | None = None
    section: str | None = None
    subsection: str | None = None
    page_start: int | None = None
    page_end: int | None = None

    def cita(self) -> str:
        """Etiqueta legible para el contexto del LLM.

        Reemplaza el literal hardcodeado `[GENERAL]` que se emitía antes. No es
        para leérsela a la persona (el prompt lo prohíbe): es para que el modelo
        tenga señal de relevancia y para que los jueces de eval puedan chequear
        grounding por fragmento.
        """
        partes = [p for p in (self.section, self.subsection) if p]
        ubicacion = " > ".join(partes) if partes else "sin sección"
        if self.page_start:
            ubicacion += f" · pág. {self.page_start}"
        return f"{ubicacion} · relevancia {self.score:.2f}"


class ChunkStore:
    def __init__(self, settings: RagSettings) -> None:
        self._settings = settings
        self._pool: pg_pool.ThreadedConnectionPool | None = None
        self._columns: list[str] | None = None
        self._has_hnsw: bool = False
        self._prepared: set[int] = set()

    # -- ciclo de vida ------------------------------------------------------

    def connect(self) -> None:
        """Crea el pool. Bloqueante: llamar desde el setup del proceso, no del turno."""
        if self._pool is not None:
            return
        self._pool = pg_pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=4,
            dsn=self._settings.database_url,
            connect_timeout=5,
        )
        self._columns, self._has_hnsw = self._detect_schema()
        logger.info(
            "pool listo; metadata: %s; índice HNSW: %s",
            [c for c in self._columns if c in _OPTIONAL_COLUMNS] or "ninguna",
            "sí" if self._has_hnsw else "NO (correr migrations/001_chunks.sql parte 1)",
        )

    def close(self) -> None:
        if self._pool is not None:
            self._pool.closeall()
            self._pool = None

    # -- consultas ---------------------------------------------------------

    async def search(self, vector: list[float], limit: int) -> list[Fragment]:
        try:
            return await asyncio.to_thread(self._search_sync, vector, limit)
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError(f"error consultando pgvector: {exc}") from exc

    def _search_sync(self, vector: list[float], limit: int) -> list[Fragment]:
        select_cols = ", ".join(self._select_columns())
        # El vector se referencia UNA sola vez: serializado son ~20 KB, y
        # repetirlo para el ORDER BY duplicaba los bytes que suben por la red.
        # 1 - distancia coseno = similitud coseno, así un número más alto es
        # siempre mejor y el piso de relevancia se lee natural.
        sql = f"""
            SELECT {select_cols}, 1 - dist AS score FROM (
                SELECT {select_cols}, embedding <=> %s::vector AS dist
                FROM {self._settings.table}
                ORDER BY dist ASC
                LIMIT %s
            ) t;
        """
        with self._checkout() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (vector, limit))
                rows = cur.fetchall()

        cols = self._select_columns()
        fragments: list[Fragment] = []
        for row in rows:
            values = dict(zip(cols, row))
            fragments.append(
                Fragment(
                    text=values["text"],
                    score=float(row[-1]),
                    source=values.get("source"),
                    section=values.get("section"),
                    subsection=values.get("subsection"),
                    page_start=values.get("page_start"),
                    page_end=values.get("page_end"),
                )
            )
        return fragments

    async def health(self) -> int:
        """Cantidad de chunks. Para chequear al arrancar que la base responde."""
        def _count() -> int:
            with self._checkout() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT count(*) FROM {self._settings.table};")
                    return int(cur.fetchone()[0])

        try:
            return await asyncio.to_thread(_count)
        except Exception as exc:
            raise RetrievalError(f"la base de protocolos no responde: {exc}") from exc

    # -- internos ----------------------------------------------------------

    def _prepare(self, conn) -> None:
        """Prepara una conexión recién sacada del pool. Una vez por conexión.

        Las tres cosas de acá son puro presupuesto de latencia. La base está en
        Supabase (us-west-2) y desde Argentina cada round trip cuesta ~220 ms,
        así que todo lo que se pueda hacer una vez por conexión en lugar de una
        vez por búsqueda se nota en la llamada.

        - autocommit: el retrieval es solo lectura, no necesita transacciones.
          Sin esto, psycopg2 abre una transacción implícita en cada execute y
          putconn() hace ROLLBACK al devolver la conexión al pool: medido, eso
          llevaba cada búsqueda de ~230 ms a ~690 ms.
        - register_vector: consulta pg_type para resolver el OID del tipo
          vector, o sea otro round trip si se hace en cada búsqueda.
        - hnsw.ef_search: se busca k=20 para rerankear, así que conviene un ef
          más alto que el default. Sin LOCAL, porque queremos que persista en la
          conexión y no viajar con cada query.
        """
        conn.autocommit = True
        register_vector(conn)
        if self._has_hnsw:
            with conn.cursor() as cur:
                cur.execute("SET hnsw.ef_search = 60;")

    def _select_columns(self) -> list[str]:
        assert self._columns is not None, "llamar connect() primero"
        return self._columns

    def _detect_schema(self) -> tuple[list[str], bool]:
        """Columnas presentes y si hay índice vectorial. Un solo round trip."""
        with self._checkout() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 'col:' || column_name FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s
                    UNION ALL
                    SELECT 'idx:' || indexdef FROM pg_indexes
                    WHERE tablename = %s AND indexdef ILIKE '%%hnsw%%';
                    """,
                    (self._settings.table, self._settings.table),
                )
                rows = [r[0] for r in cur.fetchall()]

        present = {r[4:] for r in rows if r.startswith("col:")}
        has_hnsw = any(r.startswith("idx:") for r in rows)
        if "text" not in present:
            raise RetrievalError(
                f"la tabla '{self._settings.table}' no tiene columna 'text'"
            )
        return ["text"] + [c for c in _OPTIONAL_COLUMNS if c in present], has_hnsw

    class _Checkout:
        def __init__(self, owner: ChunkStore) -> None:
            self._owner = owner
            self._conn = None

        def __enter__(self):
            pool = self._owner._pool
            if pool is None:
                raise RetrievalError("el pool de conexiones no está inicializado")
            self._conn = pool.getconn()
            # Preparación una sola vez por conexión. Se rastrea por id() porque
            # los objetos connection de psycopg2 no aceptan atributos
            # arbitrarios; el pool mantiene una referencia fuerte a cada
            # conexión, así que los ids no se reciclan mientras viva el pool.
            if id(self._conn) not in self._owner._prepared:
                self._owner._prepare(self._conn)
                self._owner._prepared.add(id(self._conn))
            return self._conn

        def __exit__(self, exc_type, exc, tb):
            if self._conn is None:
                return False
            if exc_type is not None:
                self._conn.rollback()
            # El pooler de Supabase corta conexiones inactivas; una conexión
            # rota se descarta en lugar de devolverla envenenada al pool.
            broken = self._conn.closed != 0
            self._owner._pool.putconn(self._conn, close=broken)
            self._conn = None
            return False

    def _checkout(self) -> ChunkStore._Checkout:
        return ChunkStore._Checkout(self)
