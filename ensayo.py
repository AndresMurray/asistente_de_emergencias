"""Ensayo del agente por texto, sin sala, sin micrófono y sin telefonía.

Para qué: iterar el prompt y el flujo de triage rápido y barato. Corre el
Assistant REAL —el mismo prompt, las mismas tools, el mismo retriever— usando
AgentSession.run(), que funciona sin sala porque `start()` acepta room opcional.
Comparado con `agent.py console`, esto no gasta STT ni TTS y no necesita hablarle
a la máquina, así que se pueden probar veinte variantes de prompt en el tiempo
que lleva una llamada.

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
import threading

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(".env.local")

from livekit.agents import AgentSession, inference  # noqa: E402
from livekit.agents.utils import http_context  # noqa: E402

from agent import Assistant  # noqa: E402
from triage import (
    AVISO_CRITICO,
    TriageState,
    generar_aviso_critico,
    procesar_turno_usuario,
)  # noqa: E402

# Escenarios pensados para ejercitar los caminos que importan, incluidos los que
# tienen que fallar de forma segura.
ESCENARIOS: dict[str, list[str]] = {
    "inconsciente_respira": [
        "Choqué contra otro auto, estoy en la banquina",
        "El acompañante quedó inconsciente, no me responde",
        "Sí, se le mueve el pecho, está respirando",
    ],
    "inconsciente_no_respira": [
        "Choqué contra otro auto, estoy en la banquina",
        "El acompañante está inconsciente y no responde",
        "No, no se mueve el pecho y no respira",
    ],
    "critico": [
        "Choqué con la moto, estoy en la banquina",
        "Hay un señor tirado en el asfalto, no se mueve y no respira",
        "Ya le hice las compresiones, ¿ahora qué?",
    ],
    "hemorragia": [
        "Hola, hubo un choque múltiple",
        "Una chica se está desangrando de la pierna, sale mucha sangre",
        "Le puse una remera apretando, ¿está bien?",
    ],
    "leve": [
        "Tuve un roce con otro auto",
        "Nadie está lastimado, solo estamos asustados",
        "¿Tengo que mover el auto o lo dejo?",
    ],
    "fuera_de_alcance": [
        "Hola, quería saber cuánto sale la VTV",
        "¿Y el seguro me cubre el granizo?",
    ],
    "con_riesgo": [
        "Chocamos contra un poste",
        "No hay nadie herido pero sale humo y olor a combustible del motor",
        "¿Qué hacemos?",
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
    aviso = generar_aviso_critico(senal, session.userdata) if senal else ""
    entrada = texto if not senal else f"{texto}\n\n[{aviso}]"

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


async def _leer(prompt: str) -> str | None:
    """Lee una línea de stdin sin bloquear el event loop."""
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[str | None] = loop.create_future()

    def leer() -> None:
        try:
            texto = input(prompt)
        except (EOFError, KeyboardInterrupt):
            texto = None
        loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result(texto))

    threading.Thread(target=leer, daemon=True).start()
    return await fut


async def interactivo(modelo: str) -> None:
    print("Escribí como si fueras quien llama. Ctrl-C, Ctrl-D o 'salir' para terminar.\n")
    session = AgentSession[TriageState](
        userdata=TriageState(),
        llm=inference.LLM(
            model=modelo,
            extra_kwargs={"temperature": 0.2, "parallel_tool_calls": True},
        ),
        max_tool_steps=5,
    )
    await session.start(Assistant())
    try:
        while True:
            texto = await _leer("\n>>> ")
            if texto is None:
                break
            texto = texto.strip()
            if not texto or texto.lower() in ("salir", "exit", "quit"):
                break
            await un_turno(session, texto)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n· corte manual")
    finally:
        resumen(session.userdata)
        try:
            await session.aclose()
        except (asyncio.CancelledError, Exception):
            pass


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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n· cortado")
