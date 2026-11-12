"""Orquestador de voz propio: atiende una llamada sin LiveKit.

Hace lo que antes hacían la sala de LiveKit, el worker y AgentSession:

    micrófono -> Deepgram (STT) -> fin de turno -> triage (nucleo.py)
              -> LLM (Groq / Gemini / propio) -> TTS (Cartesia / Deepgram) -> parlante

- sesion.py     la llamada: turnos, interrupciones, respuestas, metrónomo.
- stt.py        reconocimiento de voz en vivo.
- llm.py        LLM por streaming, con respaldo entre proveedores.
- tts.py        síntesis de voz, con respaldo entre proveedores.
- herramientas.py  las tools del LLM.
- servidor.py   WebSocket para el navegador (`python -m orquestador`).
- consola.py    la misma sesión por texto, en la terminal.
- prueba_voz.py una llamada de punta a punta con audio sintetizado.

Nada de este paquete importa `livekit`. El triage, los protocolos y las
respuestas fijas son los mismos que usa agent.py: viven en nucleo.py.
"""

from .sesion import Canal, Config, Habla, Sesion

__all__ = ["Canal", "Config", "Habla", "Sesion"]
