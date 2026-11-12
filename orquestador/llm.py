"""LLM por streaming contra cualquier API compatible con la de OpenAI.

Reemplaza a livekit.plugins.openai / google y al FallbackAdapter. Groq, Gemini
(por su endpoint compatible) y un servidor local como Ollama hablan el mismo
protocolo, así que alcanza con un cliente y una lista de proveedores.

El respaldo funciona como en agent.py: si un proveedor falla ANTES de emitir
nada, el mismo turno sale por el siguiente. Si falla a mitad de la respuesta no
se puede empezar de nuevo con otro modelo (parte ya se dijo): se corta ahí.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger("orquestador.llm")

GROQ_URL = "https://api.groq.com/openai/v1"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GROQ_MODELO = "openai/gpt-oss-120b"


class LLMError(RuntimeError):
    """Ningún proveedor pudo generar la respuesta."""


@dataclass
class Texto:
    delta: str


@dataclass
class LlamadaTool:
    id: str = ""
    nombre: str = ""
    argumentos: str = ""

    def args(self) -> dict[str, Any]:
        """Los argumentos como dict. Levanta ValueError si el modelo mandó algo que no es un objeto JSON."""
        datos = json.loads(self.argumentos or "{}")
        if not isinstance(datos, dict):
            raise ValueError("los argumentos no son un objeto JSON")
        return datos


@dataclass
class Tools:
    llamadas: list[LlamadaTool]


@dataclass
class Uso:
    """Lo que costó una llamada al LLM. Llega una vez, al final del stream."""

    proveedor: str = ""
    modelo: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None
    tokens_per_second: float | None = None
    # Segundos hasta el primer token (texto o tool).
    ttft: float | None = None


Evento = Texto | Tools | Uso


@dataclass
class Proveedor:
    nombre: str
    modelo: str
    base_url: str
    api_key: str
    # Parámetros extra de chat.completions.create (p. ej. reasoning_effort).
    extra: dict[str, Any] = field(default_factory=dict)
    # Gemini rechaza parallel_tool_calls en su endpoint compatible.
    tools_en_paralelo: bool = True
    _cliente: AsyncOpenAI | None = field(default=None, repr=False)

    def cliente(self, espera_s: float) -> AsyncOpenAI:
        if self._cliente is None:
            plazo = httpx.Timeout(espera_s, connect=5.0)
            self._cliente = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                # Sin reintentos del SDK: un reintento son segundos de silencio.
                # Si falla, se pasa al proveedor siguiente.
                max_retries=0,
                timeout=plazo,
                http_client=httpx.AsyncClient(
                    timeout=plazo,
                    # httpx cierra una conexión ociosa a los 5 s, y entre un
                    # turno y el siguiente pasa más que eso (el agente habla,
                    # la persona piensa): cada turno pagaba de nuevo el saludo
                    # TLS. Con dos minutos, la llamada entera usa una conexión.
                    limits=httpx.Limits(max_keepalive_connections=4, keepalive_expiry=120.0),
                ),
            )
        return self._cliente


class LLM:
    def __init__(
        self, proveedores: list[Proveedor], *, temperatura: float = 0.1, espera_s: float = 10.0
    ) -> None:
        if not proveedores:
            raise ValueError("hace falta al menos un proveedor de LLM")
        self._proveedores = proveedores
        self._temperatura = temperatura
        # Plazo sin recibir nada del proveedor. Gemini rechaza plazos menores a 10 s.
        self._espera_s = espera_s

    @property
    def modelo(self) -> str:
        return self._proveedores[0].modelo

    @property
    def cadena(self) -> str:
        return " -> ".join(f"{p.nombre}:{p.modelo}" for p in self._proveedores)

    async def precalentar(self) -> None:
        """Abre la conexión con el proveedor principal antes del primer turno.
        Es un pedido que no gasta tokens; si falla no pasa nada."""
        p = self._proveedores[0]
        try:
            await p.cliente(self._espera_s).models.list()
        except Exception as exc:
            logger.debug("no pude precalentar %s: %s", p.nombre, exc)

    async def generar(
        self, mensajes: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[Evento]:
        """Stream de una respuesta: tramos de Texto, a lo sumo un Tools y un Uso al final."""
        ultimo: Exception | None = None
        for proveedor in self._proveedores:
            emitio = False
            try:
                async for evento in self._stream(proveedor, mensajes, tools):
                    emitio = True
                    yield evento
                return
            except Exception as exc:
                ultimo = exc
                if emitio:
                    raise LLMError(f"{proveedor.nombre} se cortó a mitad de la respuesta: {exc}") from exc
                logger.warning("LLM %s falló antes de responder (%s); pruebo el siguiente", proveedor.nombre, exc)
        raise LLMError(f"ningún proveedor de LLM respondió: {ultimo}") from ultimo

    async def _stream(
        self, p: Proveedor, mensajes: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> AsyncIterator[Evento]:
        kwargs: dict[str, Any] = {
            "model": p.modelo,
            "messages": mensajes,
            "temperature": self._temperatura,
            "stream": True,
            "stream_options": {"include_usage": True},
            **p.extra,
        }
        if tools:
            kwargs["tools"] = tools
            if p.tools_en_paralelo:
                kwargs["parallel_tool_calls"] = True

        uso = Uso(proveedor=p.nombre, modelo=p.modelo)
        t0 = time.monotonic()
        primero: float | None = None
        parciales: dict[int, LlamadaTool] = {}

        stream = await p.cliente(self._espera_s).chat.completions.create(**kwargs)
        async for chunk in stream:
            _leer_uso(chunk, uso)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            if delta.content:
                primero = primero or time.monotonic()
                yield Texto(delta.content)
            for tc in delta.tool_calls or []:
                primero = primero or time.monotonic()
                llamada = parciales.setdefault(tc.index or 0, LlamadaTool())
                if tc.id:
                    llamada.id = tc.id
                if tc.function is not None:
                    if tc.function.name:
                        llamada.nombre = tc.function.name
                    if tc.function.arguments:
                        llamada.argumentos += tc.function.arguments

        fin = time.monotonic()
        if primero is not None:
            uso.ttft = primero - t0
        if uso.completion_tokens and fin > t0:
            # Sobre el pedido entero: los tokens de razonamiento se generan antes
            # del primero visible, y contarlos solo desde ahí inflaba el número.
            uso.tokens_per_second = uso.completion_tokens / (fin - t0)
        if parciales:
            llamadas = [parciales[i] for i in sorted(parciales)]
            for llamada in llamadas:
                # Algún proveedor no manda id: el mensaje de resultado lo necesita.
                llamada.id = llamada.id or f"call_{uuid.uuid4().hex[:12]}"
            yield Tools(llamadas)
        yield uso

    async def cerrar(self) -> None:
        for p in self._proveedores:
            if p._cliente is not None:
                await p._cliente.close()
                p._cliente = None


def _leer_uso(chunk: Any, uso: Uso) -> None:
    """El uso llega en `usage` (OpenAI, Gemini) o en `x_groq.usage` (Groq)."""
    datos = getattr(chunk, "usage", None)
    if datos is None:
        x_groq = getattr(chunk, "x_groq", None)
        datos = x_groq.get("usage") if isinstance(x_groq, dict) else getattr(x_groq, "usage", None)
    if datos is None:
        return

    def campo(nombre: str) -> Any:
        return datos.get(nombre) if isinstance(datos, dict) else getattr(datos, nombre, None)

    uso.prompt_tokens = campo("prompt_tokens") or uso.prompt_tokens
    uso.completion_tokens = campo("completion_tokens") or uso.completion_tokens
    uso.total_tokens = campo("total_tokens") or uso.total_tokens
    detalles = campo("prompt_tokens_details")
    if detalles is not None:
        cacheados = detalles.get("cached_tokens") if isinstance(detalles, dict) else getattr(detalles, "cached_tokens", None)
        if cacheados is not None:
            uso.cached_tokens = cacheados


def _apagado(valor: str | None) -> bool:
    return (valor or "").strip().lower() in {"0", "off", "false", "no"}


def crear_llm(modelo: str | None = None) -> LLM:
    """Arma la cadena de proveedores desde el entorno, con el mismo criterio que
    create_llm de agent.py pero sin el gateway de LiveKit.

    - LLM_BASE_URL (+ LLM_API_KEY, LLM_MODEL): un servidor propio compatible con
      OpenAI (Ollama, vLLM, LM Studio). Va primero.
    - GROQ_API_KEY: Groq, el proveedor principal.
    - GEMINI_API_KEY: respaldo (o principal con LLM_PROVIDER=gemini).
    LLM_FALLBACK=off deja solo el primero.
    """
    groq_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ")
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    preferido = os.getenv("LLM_PROVIDER", "").strip().lower()
    modelo = (modelo or os.getenv("LLM_MODEL", "")).strip()
    gemini_modelo = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    quiere_gemini = preferido in {"google", "gemini"} or "gemini" in modelo.lower()

    proveedores: list[Proveedor] = []

    base_url = os.getenv("LLM_BASE_URL", "").strip()
    if base_url:
        proveedores.append(Proveedor(
            nombre="propio",
            modelo=modelo or "llama3.1",
            base_url=base_url,
            api_key=os.getenv("LLM_API_KEY") or "sin-clave",
        ))

    groq = gemini = None
    if groq_key:
        mod = modelo if modelo and not quiere_gemini and not base_url else GROQ_MODELO
        extra: dict[str, Any] = {}
        if "gpt-oss" in mod:
            # gpt-oss razona antes de responder: con el esfuerzo por defecto
            # eran ~2,5 s por llamada; con "low", ~0,6 s (medido en agent.py).
            extra["reasoning_effort"] = os.getenv("LLM_REASONING_EFFORT", "low")
        groq = Proveedor(nombre="groq", modelo=mod, base_url=GROQ_URL, api_key=groq_key, extra=extra)
    if gemini_key:
        mod = modelo if "gemini" in modelo.lower() and not base_url else gemini_modelo
        gemini = Proveedor(
            nombre="gemini", modelo=mod, base_url=GEMINI_URL, api_key=gemini_key, tools_en_paralelo=False
        )

    orden = [gemini, groq] if quiere_gemini else [groq, gemini]
    proveedores += [p for p in orden if p is not None]

    if not proveedores:
        raise RuntimeError(
            "No hay LLM configurado: definí GROQ_API_KEY, GEMINI_API_KEY o LLM_BASE_URL en .env.local"
        )
    if _apagado(os.getenv("LLM_FALLBACK", "on")):
        proveedores = proveedores[:1]

    llm = LLM(proveedores)
    logger.info("LLM: %s", llm.cadena)
    return llm
