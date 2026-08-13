"""Ensayo del agente por texto, sin sala, sin micrófono y sin telefonía.

Para qué: iterar el prompt y el flujo de triage rápido y barato. Corre el
Assistant REAL —el mismo prompt, las mismas tools, el mismo retriever— usando
AgentSession.run(), que funciona sin sala porque `start()` acepta room opcional.
Comparado con `agent.py console`, esto no gasta STT ni TTS y no necesita hablarle
a la máquina, así que se pueden probar veinte variantes de prompt en el tiempo
que lleva una llamada.

Lo que NO cubre, y por eso hay que probar en console antes de la demo: el
reconocimiento de voz (los keyterms), el corte de turno, las interrupciones y
cómo suena la voz.

Uso:
    python ensayo.py                      # corre los escenarios guionados
    python ensayo.py --interactivo         # se escribe a mano
    python ensayo.py --escenario critico   # uno solo
    python ensayo.py --listar
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv

load_dotenv(".env.local")

from livekit.agents import AgentSession, inference  # noqa: E402
from livekit.agents.utils import http_context  # noqa: E402

import telephony  # noqa: E402
from agent import Assistant  # noqa: E402
from triage import AVISO_CRITICO, TriageState, procesar_turno_usuario  # noqa: E402

# Escenarios pensados para ejercitar los caminos que importan, incluidos los que
# tienen que fallar de forma segura.
ESCENARIOS: dict[str, list[str]] = {
    "critico": [
        "Choqué con la moto en la ruta 2 kilómetro 40, estoy en la banquina",
        "Hay un señor tirado en el asfalto, no se mueve y no respira",
        "Ya le hice las compresiones, ¿ahora qué?",
    ],
    "hemorragia": [
        "Hola, hubo un choque en Camino Centenario y 514, en Berisso",
        "Una chica se está desangrando de la pierna, sale mucha sangre",
        "Le puse una remera apretando, ¿está bien?",
    ],
    "leve": [
        "Tuve un roce con otro auto en la autopista La Plata Buenos Aires",
        "Nadie está lastimado, solo estamos asustados",
        "¿Tengo que mover el auto o lo dejo?",
    ],
    "fuera_de_alcance": [
        "Hola, quería saber cuánto sale la VTV",
        "¿Y el seguro me cubre el granizo?",
    ],
    "sin_ubicacion": [
        "¡Hay un accidente terrible, vengan rápido!",
        "No sé dónde estoy, pero hay gente lastimada",
        "Mandá la ambulancia ya",
    ],
}


async def correr(nombre: str, turnos: list[str], modelo: str) -> None:
    print(f"\n{'=' * 68}\nESCENARIO: {nombre}\n{'=' * 68}")

    session = AgentSession[TriageState](
        userdata=TriageState(),
        llm=inference.LLM(
            model=modelo,
            extra_kwargs={"temperature": 0.2, "parallel_tool_calls": True},
        ),
        tools=[telephony.toolset()],
        max_tool_steps=5,
    )
    await session.start(Assistant())

    try:
        for turno in turnos:
            await un_turno(session, turno)
        resumen(session.userdata)
    finally:
        await session.aclose()


async def un_turno(session: AgentSession, texto: str) -> None:
    # Se replica el camino de texto tal como está en el back-channel de chat:
    # session.run() no pasa por Agent.on_user_turn_completed, así que la
    # detección determinística de riesgo de vida hay que invocarla acá.
    senal = procesar_turno_usuario(texto, session.userdata)
    entrada = texto if not senal else f"{texto}\n\n[{AVISO_CRITICO.format(senal=senal)}]"

    print(f"\n>>> {texto}")
    if senal:
        print(f"    ⚠  señal crítica: «{senal}»")

    resultado = await session.run(user_input=entrada)
    for ev in resultado.events:
        tipo = type(ev).__name__
        if tipo == "FunctionCallEvent":
            print(f"    → {ev.item.name}({_corto(ev.item.arguments)})")
        elif tipo == "FunctionCallOutputEvent":
            print(f"      {_corto(ev.item.output, 120)}")

    respuestas = [m for m in session.history.messages() if m.role == "assistant"]
    if respuestas:
        print(f"<<< {respuestas[-1].text_content}")


def resumen(st: TriageState) -> None:
    print(f"\n--- estado final ---\n{st.brief()}")
    print(
        f"crítico: {st.critico()} | derivado: {st.derivado} "
        f"| listo para derivar: {st.listo_para_derivar()}"
    )
    faltan = st.faltantes()
    print(f"faltan: {', '.join(faltan) if faltan else 'nada'}")


def _corto(valor, n: int = 95) -> str:
    texto = str(valor).replace("\n", " ")
    return texto if len(texto) <= n else texto[:n] + "…"


async def interactivo(modelo: str) -> None:
    print("Escribí como si fueras quien llama. Ctrl-D o 'salir' para terminar.\n")
    session = AgentSession[TriageState](
        userdata=TriageState(),
        llm=inference.LLM(
            model=modelo,
            extra_kwargs={"temperature": 0.2, "parallel_tool_calls": True},
        ),
        tools=[telephony.toolset()],
        max_tool_steps=5,
    )
    await session.start(Assistant())
    try:
        while True:
            try:
                texto = input("\n>>> ").strip()
            except EOFError:
                break
            if not texto or texto.lower() in ("salir", "exit", "quit"):
                break
            await un_turno(session, texto)
        resumen(session.userdata)
    finally:
        await session.aclose()


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--escenario", help="nombre de un escenario puntual")
    p.add_argument("--interactivo", action="store_true", help="escribir a mano")
    p.add_argument("--listar", action="store_true", help="listar escenarios")
    p.add_argument("--modelo", default="openai/gpt-4.1-mini", help="modelo del gateway")
    p.add_argument("--verboso", action="store_true", help="mostrar logs internos")
    args = p.parse_args()

    if args.listar:
        for nombre, turnos in ESCENARIOS.items():
            print(f"  {nombre:18} ({len(turnos)} turnos)")
        return

    logging.basicConfig(level=logging.INFO if args.verboso else logging.WARNING)

    if telephony.modo_simulado():
        print("· derivación al 911 EN MODO SIMULADO (no se llama a ningún teléfono)")
    print(f"· modelo: {args.modelo}")

    async with http_context.open():
        if args.interactivo:
            await interactivo(args.modelo)
        elif args.escenario:
            if args.escenario not in ESCENARIOS:
                sys.exit(
                    f"no existe '{args.escenario}'. Opciones: {', '.join(ESCENARIOS)}"
                )
            await correr(args.escenario, ESCENARIOS[args.escenario], args.modelo)
        else:
            for nombre, turnos in ESCENARIOS.items():
                await correr(nombre, turnos, args.modelo)


if __name__ == "__main__":
    asyncio.run(main())
