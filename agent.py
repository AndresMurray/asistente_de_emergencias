import os
import asyncio
import logging
# pyrefly: ignore [missing-import]
import aiohttp

import psycopg2
from pgvector.psycopg2 import register_vector  # type: ignore
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv 

from livekit import agents  # type: ignore
from livekit.agents import (  # type: ignore
    AgentServer,
    AgentSession,
    Agent,
    RunContext,
    function_tool,
    room_io,
    inference,
)

load_dotenv(".env.local")

logger = logging.getLogger("emergency-agent")

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL no está configurada en .env.local")
TOP_K = int(os.getenv("TOP_K", "3"))

_conn = None


def _get_connection():
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(DATABASE_URL, connect_timeout=5)
        register_vector(_conn)
    return _conn


async def _embed(text: str) -> list[float]:
    cohere_api_key = os.getenv("COHERE_API_KEY")
    if not cohere_api_key:
        logger.error("COHERE_API_KEY no esta configurada en .env.local")
        return []
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.cohere.ai/v1/embed",
            headers={
                "Authorization": f"Bearer {cohere_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            json={
                "texts": [text],
                "model": "embed-multilingual-v3.0",
                "input_type": "search_query",
                "embedding_types": ["float"]
            }
        ) as response:
            if response.status != 200:
                logger.error("Error API Cohere: %s", await response.text())
                return []
            data = await response.json()
            return data["embeddings"]["float"][0]


async def search_similarity(query: str, limit: int = TOP_K) -> str:
    try:
        vector = await _embed(query)
        if not vector:
            return ""
            
        def _fetch_from_db():
            conn = _get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT text
                    FROM chunks
                    ORDER BY embedding <=> %s::vector ASC
                    LIMIT %s;
                    """,
                    (vector, limit),
                )
                return cur.fetchall()
                
        rows = await asyncio.to_thread(_fetch_from_db)
    except Exception as e:
        logger.error("Error en busqueda pgvector: %s", e)
        return ""

    if not rows:
        return ""

    fragments = []
    for row in rows:
        text = row[0]
        fragments.append(f"[GENERAL]\n{text}")

    return "\n\n".join(fragments)


@function_tool
async def buscar_protocolo(_context: RunContext, query: str):
    """Busca en la base de datos vectorial los fragmentos de protocolo
    semanticamente mas relevantes para la consulta del operador de emergencia vial.
    Ejemplo de query: 'que hacer ante un choque con heridos'"""
    logger.info("Tool 'buscar_protocolo' llamado con query: '%s'", query)
    result = await search_similarity(query)
    if not result:
        return "No se encontraron protocolos relevantes en la base de datos."
    return result


SYSTEM_INSTRUCTIONS = (
    "Sos el Asistente de Respuesta Temprana a Emergencias Viales, "
    "un sistema experto que provee informacion operativa rapida y clara "
    "a operadores de emergencia en el lugar del hecho.\n\n"
    "TONO DE VOZ:\n"
    "Hablá siempre en español rioplatense (Argentina/Uruguay). "
    "Usá 'vos' en lugar de 'tú' y conjugá los verbos acordemente "
    "(por ejemplo: 'sos' en vez de 'eres', 'hacés' en vez de 'haces', "
    "'tenés' en vez de 'tienes'). Mantené un tono profesional pero directo.\n\n"
    "OBJETIVO:\n"
    "Brindar informacion operativa inmediata utilizando exclusivamente "
    "los protocolos que recuperes via la herramienta 'buscar_protocolo'.\n\n"
    "REGLAS OBLIGATORIAS:\n"
    "1. Respondé UNICAMENTE usando la informacion presente en el contexto "
    "recuperado con 'buscar_protocolo'.\n"
    "2. No uses conocimientos generales, inferencias ni informacion externa.\n"
    "3. Si la respuesta no esta en el contexto o es insuficiente, respondé: "
    "'No tengo ese procedimiento en mis protocolos de emergencia viales registrados. "
    "Por favor, hacé la consulta pertinente o procedé segun el protocolo general.'\n"
    "4. Bajo ninguna circunstancia inventes procedimientos medicos, de rescate "
    "o seguridad.\n"
    "5. Nunca diagnostiques enfermedades, lesiones ni estados clinicos.\n"
    "6. Nunca recomiendes medicamentos, dosis ni maniobras medicas avanzadas "
    "que no esten explicitas en el contexto.\n"
    "7. Sé extremadamente directo y accionable. Usá frases cortas.\n"
    "8. Priorizá siempre la preservacion de la vida humana y la seguridad "
    "de los intervinientes.\n"
    "9. NO menciones tramites administrativos, pericias judiciales ni "
    "cuestiones burocraticas.\n"
    "10. Si existen multiples procedimientos, respondé solo con el que mejor "
    "coincida con la consulta.\n"
    "11. Respondé como si estuvieras hablando por radio con un operador "
    "en el lugar del siniestro. Sin Markdown, sin viñetas tipograficas, "
    "sin formato especial. Solo voz clara y directa."
)


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=SYSTEM_INSTRUCTIONS,
            tools=[buscar_protocolo],
        )


server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: agents.JobContext):
    logger.info("Conectando al room %s", ctx.room.name)
    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    session = AgentSession(
        stt=inference.STT(model="deepgram/nova-3", language="es"),
        llm=inference.LLM(model="openai/gpt-4o-mini"),
        tts=inference.TTS(
            model="cartesia/sonic-3",
            voice="595f1cfa-bd48-432c-a519-abe83e210398",
        ),
    )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(),
        ),
    )

    from livekit import rtc
    import json

    @ctx.room.on("data_received")
    def on_data_received(data_packet: rtc.DataPacket):
        try:
            payload = json.loads(data_packet.data.decode("utf-8"))
            if payload.get("type") == "chat":
                query = payload.get("message")
                logger.info("Chat recibido: %s", query)

                async def process_chat():
                    try:
                        session.interrupt()
                        await asyncio.sleep(0.2)
                        run_result = session.run(user_input=query)
                        await run_result
                    except (asyncio.CancelledError, Exception) as e:
                        logger.warning("Run de chat interrumpido o fallido: %s", e)
                    
                    messages = session.history.messages()
                    assistant_msgs = [m for m in messages if m.role == "assistant"]
                    reply = assistant_msgs[-1].text_content if assistant_msgs else "No se pudo generar respuesta."
                    logger.info("Respondiendo chat: %s", reply)
                    try:
                        await ctx.room.local_participant.publish_data(
                            payload=json.dumps({"type": "chat_reply", "message": reply}).encode("utf-8"),
                            topic="test-chat"
                        )
                    except Exception as e:
                        logger.error("Error publicando chat_reply: %s", e)

                asyncio.create_task(process_chat())
        except Exception as e:
            logger.error("Error al procesar mensaje de chat: %s", e)

    await session.generate_reply(
        instructions=(
            "Saluda brevemente al operador. Di solo: "
            "'Asistente de emergencias viales activo. "
            "Indicame la situacion.' "
            "No uses herramientas ni busques nada."
        )
    )

    logger.info("Agente iniciado en room %s", ctx.room.name)


if __name__ == "__main__":
    agents.cli.run_app(server)
