"""El agente por texto, en la terminal, sobre el orquestador propio.

Lo mismo que ensayo.py pero sin LiveKit: misma sesión, mismo triage, mismo
prompt y mismas tools que una llamada por voz, sin STT ni TTS (no gasta
créditos de voz).

    python -m orquestador.consola                      # todos los escenarios guionados
    python -m orquestador.consola --escenario critico  # uno solo
    python -m orquestador.consola --interactivo        # se escribe a mano
    python -m orquestador.consola --listar
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv(".env.local")

import nucleo  # noqa: E402
from escenarios import ESCENARIOS  # noqa: E402
from prompts import SALUDO  # noqa: E402
from rag.session import close_fallback  # noqa: E402

from .llm import LLM, crear_llm  # noqa: E402
from .sesion import Sesion  # noqa: E402


class CanalMudo:
    """En la consola no hay cliente: lo que la sesión manda se descarta."""

    async def audio(self, pcm: bytes) -> None:
        pass

    async def evento(self, datos: dict[str, Any]) -> None:
        pass


def _corto(valor: object, n: int = 95) -> str:
    texto = str(valor).replace("\n", " ")
    return texto if len(texto) <= n else texto[:n] + "…"


async def nueva_sesion(llm: LLM) -> Sesion:
    sesion = Sesion(CanalMudo(), llm=llm)
    await sesion.iniciar(saludar=False)
    sesion.saludo_de_texto()
    return sesion


async def un_turno(sesion: Sesion, texto: str) -> str:
    print(f"\n>>> {texto}")
    t0 = time.perf_counter()
    respuesta = await sesion.turno_de_texto(texto, debug=True)
    for tc in respuesta["tool_calls"]:
        tool = tc["tool"]
        if tool == "prefetch_protocolo":
            print(f"    ⚠  protocolo adjuntado: {tc['args']['tema']} ({tc.get('origen')})")
        elif tool == "respuesta_fija":
            print(f"    ⚡ respuesta fija ({tc['args']['momento']}), sin LLM")
        elif tool == "derivar_a_emergencias":
            print(f"    ☎  aviso al 911 ({tc['args'].get('motivo')})")
        else:
            print(f"    → {tool}({_corto(tc.get('args'))})")
    print(f"<<< {respuesta['message']}   ({time.perf_counter() - t0:.2f}s)")
    return respuesta["message"]


def resumen(sesion: Sesion) -> None:
    st = sesion.estado
    print(f"\n--- estado final ---\n{st.brief()}")
    print(f"crítico: {st.critico()} | derivado: {st.derivado} | listo para derivar: {st.listo_para_derivar()}")


async def correr(nombre: str, turnos: list[str], llm: LLM) -> None:
    print(f"\n{'=' * 68}\nESCENARIO: {nombre}\n{'=' * 68}")
    sesion = await nueva_sesion(llm)
    try:
        for turno in turnos:
            await un_turno(sesion, turno)
        resumen(sesion)
    finally:
        await sesion.cerrar()


async def interactivo(llm: LLM) -> None:
    print("Escribí como si fueras quien llama. Ctrl-C o «salir» para terminar.\n")
    sesion = await nueva_sesion(llm)
    print(f"<<< {SALUDO}")
    try:
        while True:
            try:
                texto = (await asyncio.to_thread(input, "\n>>> ")).strip()
            except EOFError:
                break
            if not texto or texto.lower() in ("salir", "exit", "quit"):
                break
            await un_turno(sesion, texto)
    finally:
        resumen(sesion)
        await sesion.cerrar()


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--escenario", help="nombre de un escenario puntual")
    p.add_argument("--interactivo", action="store_true", help="escribir a mano")
    p.add_argument("--listar", action="store_true", help="listar escenarios")
    p.add_argument("--modelo", default=None, help="modelo del LLM (por defecto, LLM_MODEL)")
    p.add_argument("--verboso", action="store_true", help="mostrar logs internos")
    args = p.parse_args()

    if args.listar:
        for nombre, turnos in ESCENARIOS.items():
            print(f"  {nombre:24} ({len(turnos)} turnos)")
        return
    if args.escenario and args.escenario not in ESCENARIOS:
        sys.exit(f"no existe «{args.escenario}». Opciones: {', '.join(ESCENARIOS)}")

    logging.basicConfig(level=logging.INFO if args.verboso else logging.WARNING)
    llm = crear_llm(args.modelo)
    print(f"· LLM: {llm.cadena}")
    # Índice y caché cargados antes del primer turno, como en el servidor.
    await asyncio.to_thread(nucleo.prewarm)
    try:
        if args.interactivo:
            await interactivo(llm)
        elif args.escenario:
            await correr(args.escenario, ESCENARIOS[args.escenario], llm)
        else:
            for nombre, turnos in ESCENARIOS.items():
                await correr(nombre, turnos, llm)
    finally:
        await llm.cerrar()
        await close_fallback()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n· cortado")
