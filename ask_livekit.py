import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from livekit.agents import AgentSession, inference

# Cargar variables de entorno antes de importar el agente.
# Usamos la ubicación de este archivo para que funcione sin importar desde
# qué directorio se ejecute el script importador.
load_dotenv(Path(__file__).parent / ".env.local", override=True)

# Importar el agente del proyecto
from agent import Assistant
from triage import TriageState

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
# Bajar el nivel de logs ruidosos de librerías externas
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("livekit").setLevel(logging.WARNING)
logger = logging.getLogger("ask-livekit")


def _extract_text(chat_item) -> str:
    """Extrae texto plano de un ChatItem de LiveKit."""
    if chat_item.type != "message":
        return ""

    parts = []
    for content in chat_item.content:
        if isinstance(content, str):
            parts.append(content)
        # Ignorar ImageContent/AudioContent por ahora
    return "".join(parts).strip()


async def ask(question: str) -> str:
    # Configurar la sesión con el mismo LLM que usa el agente en producción
    # (se puede sobreescribir con la variable de entorno LLM_MODEL)
    llm_model = os.environ.get("LLM_MODEL", "openai/gpt-4.1-mini")
    session = AgentSession(
        userdata=TriageState(),
        llm=inference.LLM(model=llm_model),
    )

    try:
        await session.start(agent=Assistant())

        handle = session.generate_reply(user_input=question)
        await handle.wait_for_playout()

        # Buscar la última respuesta del asistente
        for item in reversed(handle.chat_items):
            text = _extract_text(item)
            if text:
                return text

        return ""
    finally:
        await session.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Hacer una pregunta de texto al agente de LiveKit.")
    parser.add_argument("question", nargs="+", help="Pregunta para el agente.")
    parser.add_argument(
        "--env",
        default=".env.local",
        help="Archivo de entorno a cargar (default: .env.local).",
    )
    args = parser.parse_args()

    if args.env != ".env.local":
        load_dotenv(args.env, override=True)

    missing = []
    for var in (
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "DATABASE_URL",
        "COHERE_API_KEY",
    ):
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        logger.error("Faltan variables de entorno: %s", ", ".join(missing))
        return 1

    question = " ".join(args.question)
    try:
        answer = asyncio.run(ask(question))
    except Exception as e:
        logger.exception("Error al consultar al agente")
        return 1

    print(answer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
