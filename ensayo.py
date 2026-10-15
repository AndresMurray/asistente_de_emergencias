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
import os
import re
import sys
import threading
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(".env.local")

from livekit.agents import AgentSession, inference  # noqa: E402
from livekit.agents.utils import http_context  # noqa: E402

from agent import Assistant, create_llm, prewarm  # noqa: E402
from prompts import SALUDO  # noqa: E402
from triage import TriageState  # noqa: E402

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
    "atrapado": [
        "hola, si estoy fuera de la calzada chocaron dos autos",
        "hay una persona atrapada en auto las demas estan bien",
        "no veo si reacciona",
    ],
    "casco": [
        "Hola, estoy a salvo en la banquina. Se cayó un chico en moto, ¿le saco el casco?",
        "Está despierto y se queja del cuello",
    ],
    # Conversación real de la pestaña Test en producción (con el error de tipeo).
    "moto_produccion": [
        "choco una moto",
        "si esta tirado en el piso con el casco",
        "le scao el casco",
        "le saco el casco?",
    ],
    # Segunda conversación real de producción: «sí, una persona» no derivaba.
    "herido_confirmado": [
        "choco una moto",
        "si, una persona",
        "una",
        "si, me pide que le saque el casco",
        "le sangra una pierna mucho",
    ],
    "pregunta_directa": [
        "Choqué de atrás a otro auto en la avenida",
        "No, nadie lastimado. ¿Tengo que mover el auto o lo dejo?",
    ],
    # RCP sostenida: mientras comprime no se le pregunta nada, y al llegar la
    # ayuda se corta.
    "rcp_continua": [
        "Choqué, hay un hombre tirado en la ruta que no respira",
        "Ya empecé a comprimir, ¿a qué ritmo sigo?",
        "Sigo, sigo, estoy cansado",
        "Llegó la ambulancia",
    ],
    # El caso de la prueba por consola: «Sí, respira» en plena RCP tiene que
    # cortar las compresiones (y el metrónomo).
    "rcp_vuelve_a_respirar": [
        "Hay un hombre tirado en la ruta que no respira",
        "Ya estoy comprimiendo",
        "Sí, respira",
    ],
    # Seguimiento de una indicación: el cierre tiene que preguntar por el
    # resultado («¿sigue saliendo sangre?»), no «¿lo pudiste hacer?».
    "seguimiento_hemorragia": [
        "Hubo un choque, un muchacho tiene un tajo en el brazo y sangra",
        "Listo, ya le estoy apretando con una remera",
        "Bajó bastante",
        "Ahora está tranquilo, me habla",
    ],
}


async def correr(nombre: str, turnos: list[str], modelo: str) -> None:
    print(f"\n{'=' * 68}\nESCENARIO: {nombre}\n{'=' * 68}")

    session = AgentSession[TriageState](
        userdata=TriageState(),
        llm=create_llm(modelo),
        max_tool_steps=4,
    )
    await session.start(Assistant())

    try:
        turnos_hechos = [await un_turno(session, turno) for turno in turnos]
        resumen(session.userdata)
        reporte_cierres(turnos_hechos)
    finally:
        await session.aclose()


async def un_turno(session: AgentSession, texto: str) -> tuple[str, bool]:
    """Corre un turno. Devuelve la respuesta y si la persona estaba en RCP."""
    # Se replica el camino de texto tal como está en el back-channel de chat:
    # session.run() no pasa por Agent.on_user_turn_completed, así que el
    # contexto determinístico (riesgo de vida + protocolo) se prepara acá.
    t0 = time.perf_counter()
    entrada, _ = await session.current_agent.preparar_texto(texto)

    print(f"\n>>> {texto}")
    temas = [tc["args"]["tema"] for tc in session.userdata.tool_calls if tc["tool"] == "prefetch_protocolo"]
    print(f"    ⚠  contexto inyectado (temas: {', '.join(temas) or '—'})")
    for tc in session.userdata.tool_calls:
        if tc["tool"] == "respuesta_fija":
            print(f"    ⚡ respuesta fija ({tc['args']['momento']}), sin LLM")
    session.userdata.tool_calls.clear()

    resultado = await session.run(user_input=entrada)
    for ev in resultado.events:
        tipo = type(ev).__name__
        if tipo == "FunctionCallEvent":
            print(f"    → {ev.item.name}({_corto(ev.item.arguments)})")
        elif tipo == "FunctionCallOutputEvent":
            print(f"      {_corto(ev.item.output, 120)}")

    respuestas = [m for m in session.history.messages() if m.role == "assistant"]
    respuesta = (respuestas[-1].text_content or "") if respuestas else ""
    if respuestas:
        print(f"<<< {respuesta}   ({time.perf_counter() - t0:.2f}s)")
    st = session.userdata
    return respuesta, st.respira is False and not st.ayuda_llego


_INVITA = re.compile(r"\b(avisame|contame|decime|avis[aá]|cont[aá]|dec[ií])\b", re.IGNORECASE)
_PUDISTE = re.compile(r"pudiste", re.IGNORECASE)


def _cierre(respuesta: str) -> str:
    """La última oración de la respuesta."""
    oraciones = [o.strip() for o in re.split(r"(?<=[.!?])\s+", respuesta.strip()) if o.strip()]
    return oraciones[-1] if oraciones else ""


def reporte_cierres(turnos: list[tuple[str, bool]]) -> None:
    """Cómo cerró el agente cada turno. Solo informa, no falla.

    Lo que se busca: que cada turno invite a seguir, que «¿Pudiste?» sea la
    excepción, que no repita el mismo cierre y que en RCP no pregunte nada."""
    sin_cierre, pudiste, repetidos, preguntas_en_rcp = [], 0, 0, 0
    anterior = None
    for i, (respuesta, en_rcp) in enumerate(turnos, 1):
        cierre = _cierre(respuesta)
        if _PUDISTE.search(respuesta):
            pudiste += 1
        if en_rcp:
            preguntas_en_rcp += "?" in respuesta
        elif not (cierre.endswith("?") or _INVITA.search(cierre)):
            sin_cierre.append(i)
        if anterior is not None and cierre and cierre.lower() == anterior.lower():
            repetidos += 1
        anterior = cierre
    print(
        f"--- cierres --- sin invitar a seguir: {sin_cierre or 'ninguno'} "
        f"| «pudiste»: {pudiste}/{len(turnos)} | repetidos: {repetidos} "
        f"| preguntas en RCP: {preguntas_en_rcp}"
    )


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
        llm=create_llm(modelo),
        max_tool_steps=4,
    )
    await session.start(Assistant())
    print(f"<<< {SALUDO}\n")
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
    p.add_argument(
        "--modelo",
        default=os.getenv("LLM_MODEL", ""),
        help="modelo del LLM",
    )
    p.add_argument("--verboso", action="store_true", help="mostrar logs internos")
    args = p.parse_args()

    if args.listar:
        for nombre, turnos in ESCENARIOS.items():
            print(f"  {nombre:18} ({len(turnos)} turnos)")
        return

    logging.basicConfig(level=logging.INFO if args.verboso else logging.WARNING)
    print(f"· modelo: {args.modelo}")

    async with http_context.open():
        prewarm(None)  # índice y caché cargados antes del primer turno, como en el agente
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
