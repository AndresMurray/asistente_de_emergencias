"""Prueba del orquestador POR VOZ, de punta a punta, sin micrófono.

Lo mismo que prueba_voz.py hace contra LiveKit: entra como si fuera quien
llama, «habla» cada frase con audio sintetizado (Deepgram) y muestra lo que
entendió el STT, lo que respondió el agente y cuánto tardó en empezar a hablar.
Recorre el camino completo de una llamada: WebSocket, Deepgram, fin de turno,
borrador anticipado, LLM y TTS.

Con el servidor corriendo (`python -m orquestador`):

    python -m orquestador.prueba_voz                                 # conversación por defecto
    python -m orquestador.prueba_voz "Sí." "Choqué con una moto."    # frases propias
    python -m orquestador.prueba_voz --interrumpir                   # habla encima del agente

Gasta créditos de voz (Deepgram y el TTS del agente): pocas frases por prueba.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import aiohttp
from dotenv import load_dotenv

load_dotenv(".env.local")

from . import acceso  # noqa: E402

CONVERSACION = [
    "Sí.",
    "Choqué con una moto.",
    "Sí, hay una persona tirada en el piso.",
    "¿Le saco el casco?",
]

SAMPLE_RATE = 16000
_BLOQUE_MS = 20
_BLOQUE = SAMPLE_RATE * _BLOQUE_MS // 1000 * 2  # bytes
_SILENCIO = bytes(_BLOQUE)
# Voz distinta a la del agente, para que el STT no las confunda.
_VOZ = "aura-2-javier-es"
# Cuánto silencio del agente cuenta como «terminó de responder».
_FIN_RESPUESTA_S = 1.5


class Llamada:
    def __init__(self, ws: aiohttp.ClientWebSocketResponse, http: aiohttp.ClientSession) -> None:
        self.ws = ws
        self.http = http
        self.cola: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.fin_de_frase = 0.0
        self.frase_emitida = asyncio.Event()
        self.agente: list[tuple[str, bool]] = []  # (texto, interrumpida)
        self.stt: list[str] = []
        self.estado_agente = ""
        self.primer_audio: float | None = None
        self.bytes_de_audio = 0
        self.eventos: list[str] = []
        self.ultimo_cambio = time.monotonic()

    async def emisor(self) -> None:
        """Manda audio sin cortes y en tiempo real: la frase cuando hay, silencio cuando no."""
        siguiente = time.monotonic()
        while True:
            try:
                bloque = self.cola.get_nowait()
            except asyncio.QueueEmpty:
                bloque = _SILENCIO
            if bloque is None:  # marca de fin de frase
                self.fin_de_frase = time.monotonic()
                self.frase_emitida.set()
                continue
            await self.ws.send_bytes(bloque)
            siguiente += _BLOQUE_MS / 1000
            await asyncio.sleep(max(0.0, siguiente - time.monotonic()))

    async def receptor(self) -> None:
        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.BINARY:
                self.bytes_de_audio += len(msg.data)
                if self.primer_audio is None:
                    self.primer_audio = time.monotonic()
                continue
            if msg.type != aiohttp.WSMsgType.TEXT:
                break
            datos = json.loads(msg.data)
            tipo = datos.get("type")
            if tipo == "estado":
                if datos["agente"] != self.estado_agente:
                    self.estado_agente = datos["agente"]
                    self.ultimo_cambio = time.monotonic()
            elif tipo == "transcripcion" and datos.get("final"):
                if datos["rol"] == "usuario":
                    self.stt.append(datos["texto"])
                else:
                    self.agente.append((datos["texto"], bool(datos.get("interrumpida"))))
                self.ultimo_cambio = time.monotonic()
            elif tipo in ("limpiar", "metronomo", "error"):
                self.eventos.append(json.dumps(datos, ensure_ascii=False))
                self.ultimo_cambio = time.monotonic()

    async def sintetizar(self, texto: str) -> bytes:
        async with self.http.post(
            "https://api.deepgram.com/v1/speak",
            params={"model": _VOZ, "encoding": "linear16", "sample_rate": str(SAMPLE_RATE), "container": "none"},
            headers={"Authorization": f"Token {os.environ['DEEPGRAM_API_KEY']}"},
            json={"text": texto},
        ) as resp:
            resp.raise_for_status()
            return await resp.read()

    async def decir(self, pcm: bytes) -> None:
        self.frase_emitida.clear()
        self.primer_audio = None
        for i in range(0, len(pcm), _BLOQUE):
            self.cola.put_nowait(pcm[i : i + _BLOQUE].ljust(_BLOQUE, b"\0"))
        self.cola.put_nowait(None)
        await self.frase_emitida.wait()

    async def esperar_al_agente(self, desde: int, timeout: float = 25.0) -> None:
        """Hasta que el agente respondió algo nuevo y volvió a escuchar."""
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            callado = self.estado_agente == "escuchando" and time.monotonic() - self.ultimo_cambio > _FIN_RESPUESTA_S
            if len(self.agente) > desde and callado:
                return
            await asyncio.sleep(0.05)


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("frases", nargs="*", help="lo que dice quien llama, en orden")
    p.add_argument("--url", default=os.getenv("ORQUESTADOR_URL", "ws://127.0.0.1:8787/ws"))
    p.add_argument(
        "--interrumpir",
        action="store_true",
        help="la última frase se dice encima de la respuesta del agente, para probar la interrupción",
    )
    args = p.parse_args()
    frases = args.frases or CONVERSACION

    async with aiohttp.ClientSession() as http:
        try:
            ws = await http.ws_connect(args.url, max_msg_size=4 * 1024 * 1024)
        except aiohttp.ClientError as exc:
            print(f"✗ no pude conectar con {args.url}: {exc}\n  ¿Está corriendo `python -m orquestador`?")
            return 1
        inicio = {"type": "inicio", "modo": "voz", "sample_rate": SAMPLE_RATE}
        if secreto := os.getenv("ORQUESTADOR_SECRETO"):
            inicio["pase"] = acceso.nuevo_pase(secreto)
        await ws.send_json(inicio)

        llamada = Llamada(ws, http)
        tareas = [asyncio.create_task(llamada.receptor()), asyncio.create_task(llamada.emisor())]
        try:
            await llamada.esperar_al_agente(0, timeout=30)
            if not llamada.agente:
                print("✗ el agente no saludó", *llamada.eventos, sep="\n  ")
                return 1
            print(f"AGENTE: {llamada.agente[0][0]}\n  ({llamada.bytes_de_audio / 48000:.1f} s de audio)")

            for i, frase in enumerate(frases):
                encima = args.interrumpir and i == len(frases) - 1 and i > 0
                audio = await llamada.sintetizar(frase)
                n_agente, n_stt, n_ev = len(llamada.agente), len(llamada.stt), len(llamada.eventos)
                if encima:
                    # Se repite la frase anterior para que el agente vuelva a
                    # hablar, y esta se dice un segundo después de que arranca.
                    await llamada.decir(await llamada.sintetizar(frases[i - 1]))
                    t0 = time.monotonic()
                    while llamada.estado_agente != "hablando" and time.monotonic() - t0 < 15:
                        await asyncio.sleep(0.02)
                    await asyncio.sleep(1.0)
                    n_agente = len(llamada.agente)
                await llamada.decir(audio)
                fin = llamada.fin_de_frase
                await llamada.esperar_al_agente(n_agente + (1 if encima else 0))
                oido = " | ".join(llamada.stt[n_stt:]) or "(nada)"
                print(f"\nVOS:    {frase}{'   [encima del agente]' if encima else ''}\n  STT:  {oido}")
                nuevas = llamada.agente[n_agente:]
                if not nuevas:
                    print("AGENTE: ✗ sin respuesta")
                for texto, interrumpida in nuevas:
                    print(f"AGENTE: {texto}{'   [interrumpida]' if interrumpida else ''}")
                if nuevas and llamada.primer_audio is not None and not encima:
                    print(f"  empezó a hablar {llamada.primer_audio - fin:.2f} s después de que terminaste")
                for evento in llamada.eventos[n_ev:]:
                    print(f"  evento: {evento}")
            await ws.send_json({"type": "fin"})
        finally:
            for tarea in tareas:
                tarea.cancel()
            await asyncio.gather(*tareas, return_exceptions=True)
            await ws.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
