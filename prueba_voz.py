"""Prueba del agente POR VOZ, de punta a punta, sin micrófono.

Entra a una sala de LiveKit como si fuera quien llama, "habla" cada frase con
audio sintetizado (Cartesia) y muestra lo que entendió el STT, lo que respondió
el agente y cuánto tardó en empezar a hablar. Recorre el mismo camino que una
llamada real: VAD, detección de fin de turno, Deepgram, generación anticipada
(preemptive), LLM y TTS. Por eso encuentra fallas que el chat de texto no ve.

Uso:
    python prueba_voz.py                                  # conversación por defecto
    python prueba_voz.py "Sí" "Choqué con una moto" ...   # frases propias
    python prueba_voz.py --agente asistente-emergencias-prueba   # copia local

Para probar cambios sin tocar producción, levantar una copia local con otro
nombre y apuntarle:
    $env:AGENT_NAME="asistente-emergencias-prueba"; python agent.py dev
    python prueba_voz.py --agente asistente-emergencias-prueba
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(".env.local")

from livekit import api, rtc  # noqa: E402
from livekit.agents.utils import http_context  # noqa: E402
from livekit.plugins import cartesia  # noqa: E402

CONVERSACION = [
    "Sí.",
    "Choqué con una moto.",
    "Sí, hay una persona tirada en el piso.",
    "¿Le saco el casco?",
]

_FRAME_MS = 20
# Silencio después de cada frase: más que el max_delay del endpointing (2 s)
# para que el turno se cierre como en una llamada real.
_PAUSA_S = 2.5
# Cuánto silencio del agente cuenta como "terminó de responder".
_FIN_RESPUESTA_S = 3.0


class Llamada:
    def __init__(self, room: rtc.Room, tts: cartesia.TTS) -> None:
        self.room = room
        self.tts = tts
        self.fuente = rtc.AudioSource(tts.sample_rate, 1)
        self.cola: asyncio.Queue[rtc.AudioFrame | None] = asyncio.Queue()
        self.mi_track_sid = ""
        self.fin_de_frase = 0.0
        self.agente: list[tuple[float, str]] = []  # (momento del primer texto, texto final)
        self.stt: list[str] = []
        self._ultimo_agente = 0.0
        self._frase_emitida = asyncio.Event()

    async def publicar(self) -> None:
        track = rtc.LocalAudioTrack.create_audio_track("microfono", self.fuente)
        pub = await self.room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        self.mi_track_sid = pub.sid
        asyncio.create_task(self._emisor())

    async def _emisor(self) -> None:
        """Manda audio sin cortes: la frase cuando hay, silencio cuando no."""
        muestras = self.tts.sample_rate * _FRAME_MS // 1000
        silencio = rtc.AudioFrame(bytes(muestras * 2), self.tts.sample_rate, 1, muestras)
        while True:
            try:
                frame = self.cola.get_nowait()
            except asyncio.QueueEmpty:
                frame = silencio
            if frame is None:  # marca de fin de frase
                # capture_frame solo encola (hasta ~1 s de buffer): el fin real
                # es cuando el audio terminó de salir.
                await self.fuente.wait_for_playout()
                self.fin_de_frase = time.monotonic()
                self._frase_emitida.set()
                continue
            await self.fuente.capture_frame(frame)

    def escuchar_transcripciones(self) -> None:
        async def leer(reader: rtc.TextStreamReader, _identidad: str) -> None:
            attrs = reader.info.attributes or {}
            primero = None
            texto = ""
            async for trozo in reader:
                primero = primero or time.monotonic()
                texto += trozo
            if attrs.get("lk.transcription_final", "true") != "true" or not texto.strip():
                return
            if attrs.get("lk.transcribed_track_id") == self.mi_track_sid:
                self.stt.append(texto.strip())
            else:
                self.agente.append((primero or time.monotonic(), texto.strip()))
                self._ultimo_agente = time.monotonic()

        self.room.register_text_stream_handler(
            "lk.transcription", lambda r, ident: asyncio.create_task(leer(r, ident))
        )

    async def decir(self, texto: str) -> None:
        frames = [ev.frame async for ev in self.tts.synthesize(texto)]
        self._frase_emitida.clear()
        for frame in frames:
            self.cola.put_nowait(frame)
        self.cola.put_nowait(None)
        # esperar a que termine de "sonar" la frase (lo marca el emisor)
        await self._frase_emitida.wait()

    async def esperar_respuesta(self, desde: int, timeout: float = 25.0) -> None:
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if len(self.agente) > desde and time.monotonic() - self._ultimo_agente > _FIN_RESPUESTA_S:
                return
            await asyncio.sleep(0.1)


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("frases", nargs="*", help="lo que dice quien llama, en orden")
    p.add_argument("--agente", default=os.getenv("AGENT_NAME", "asistente-emergencias"))
    args = p.parse_args()
    frases = args.frases or CONVERSACION

    sala = f"prueba-voz-{uuid.uuid4().hex[:6]}"
    token = (
        api.AccessToken(os.environ["LIVEKIT_API_KEY"], os.environ["LIVEKIT_API_SECRET"])
        .with_identity("prueba-voz")
        .with_grants(api.VideoGrants(room_join=True, room=sala, can_publish=True, can_subscribe=True))
        .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=args.agente)]))
        .to_jwt()
    )

    async with http_context.open():
        tts = cartesia.TTS(
            model="sonic-3", language="es", api_key=os.environ["CARTESIA_API_KEY"],
            voice=os.getenv("CARTESIA_VOICE_ID", "b4b8e2af-6139-466e-a93a-30c20d2e1fc5"),
        )
        room = rtc.Room()
        llamada = Llamada(room, tts)
        llamada.escuchar_transcripciones()
        await room.connect(os.environ["LIVEKIT_URL"], token)
        await llamada.publicar()
        print(f"sala {sala} · agente «{args.agente}»\n")

        await llamada.esperar_respuesta(0, timeout=40)
        if not llamada.agente:
            print("✗ el agente no habló (¿está desplegado / corriendo con ese nombre?)")
            await room.disconnect()
            return 1
        print(f"AGENTE: {llamada.agente[0][1]}")

        for frase in frases:
            n_agente, n_stt = len(llamada.agente), len(llamada.stt)
            await llamada.decir(frase)
            fin = llamada.fin_de_frase
            await asyncio.sleep(_PAUSA_S)
            await llamada.esperar_respuesta(n_agente)
            oido = " | ".join(llamada.stt[n_stt:]) or "(nada)"
            nuevas = llamada.agente[n_agente:]
            print(f"\nVOS:    {frase}\n  STT:  {oido}")
            if not nuevas:
                print("AGENTE: ✗ sin respuesta")
                continue
            demora = nuevas[0][0] - fin
            print(f"AGENTE: {' '.join(t for _, t in nuevas)}\n  empezó a hablar {demora:.2f} s después de que terminaste")

        await room.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
