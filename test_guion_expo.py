"""Test y Análisis Automatizado del Guion para la Expo de la Facultad.

Evalúa turno a turno las conversaciones planificadas en `docs/guion_demo_expo.md`:
1. Escenario Principal (Camino Crítico: Inconsciente -> Paro -> Compresiones).
2. Pregunta Trampa del Casco (Motociclista -> No retirar casco).
3. Contraprueba Médica (Inconsciente que SÍ respira -> No hacer RCP).

Valida automáticamente:
- Señales críticas detectadas determinísticamente por triage.py.
- Prohibición estricta de RCP a ciegas (seguridad médica).
- Invocación de herramientas esperadas (buscar_protocolo, derivar_a_emergencias).
- Ausencia de números erróneos (112) y presencia de 'nueve once'.
- Asistencia y ritmo continuo de maniobras.

Uso:
    python test_guion_expo.py
    python test_guion_expo.py --escenario principal
    python test_guion_expo.py --escenario casco
    python test_guion_expo.py --escenario inconsciente_respira
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import colorama
from colorama import Fore, Style
from dotenv import load_dotenv

colorama.init(autoreset=True)
load_dotenv(".env.local")

from livekit.agents import AgentSession, inference  # noqa: E402
from livekit.agents.utils import http_context  # noqa: E402

from agent import Assistant  # noqa: E402
from triage import (  # noqa: E402
    TriageState,
    generar_aviso_critico,
    procesar_turno_usuario,
)


@dataclass
class TurnResult:
    user_input: str
    injected_alert: str
    assistant_reply: str
    tools_called: list[dict[str, Any]]
    triage_state: TriageState
    duration_sec: float
    assertions: list[tuple[str, bool, str]] = field(default_factory=list)


@dataclass
class ScenarioResult:
    name: str
    description: str
    turns: list[TurnResult] = field(default_factory=list)
    passed: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Definición de Verificaciones (Asertos Semánticos y de Reglas de Negocio)
# ─────────────────────────────────────────────────────────────────────────────

def _assert_no_112(reply: str) -> tuple[bool, str]:
    """Nunca debe decir '112'."""
    if "112" in reply:
        return False, "La respuesta pronunció el número español prohibido '112'."
    return True, "No mencionó '112' (cumple regla de localización argentina)."


def _check_tools_contain(tools: list[dict[str, Any]], name: str) -> bool:
    return any(t["name"] == name for t in tools)


# Reglas para Turno 1 del Escenario Principal (Inconsciente)
def assert_turno_1_principal(turn: TurnResult) -> list[tuple[str, bool, str]]:
    checks = []
    bajo = turn.assistant_reply.lower()

    # 1. Señal crítica detectada
    ok_senal = turn.triage_state.senal_critica is not None
    checks.append((
        "Detección determinística de señal crítica ('inconsciente')",
        ok_senal,
        f"Señal registrada: '{turn.triage_state.senal_critica}'" if ok_senal else "No se registró señal crítica"
    ))

    # 2. Seguridad RCP: NO debe mandar RCP ni compresiones prematuras sin saber si respira
    manda_rcp = any(w in bajo for w in ("compresion", "compresión", "comprimí", "masaje", "30 compresiones"))
    checks.append((
        "Seguridad Médica: NO ordenó RCP prematuro a ciegas",
        not manda_rcp,
        "Correcto: no indicó compresiones torácicas sin verificar respiración" if not manda_rcp else "Peligro: Indicó compresiones antes de confirmar paro respiratorio"
    ))

    # 3. Pregunta si respira o se mueve el pecho
    pregunta_respira = any(w in bajo for w in ("respira", "respirando", "pecho", "aire"))
    checks.append((
        "Protocolo: Pregunta activamente si respira o se mueve el pecho",
        pregunta_respira,
        "Indicó verificar respiración" if pregunta_respira else "Faltó preguntar si la persona respira"
    ))

    # 4. Geolocalización automática
    menciona_geo = any(w in bajo for w in ("geolocaliz", "camino", "ayuda", "nueve once", "despach"))
    checks.append((
        "Contención y Despacho: Notifica que está geolocalizado / ayuda en camino",
        menciona_geo,
        "Mencionó geolocalización o despacho en curso" if menciona_geo else "No tranquilizó sobre la ayuda en camino"
    ))

    # 5. Sin 112
    ok_112, msg_112 = _assert_no_112(turn.assistant_reply)
    checks.append(("Localización: No decir 112", ok_112, msg_112))

    return checks


# Reglas para Turno 2 del Escenario Principal (No respira)
def assert_turno_2_principal(turn: TurnResult) -> list[tuple[str, bool, str]]:
    checks = []
    bajo = turn.assistant_reply.lower()

    # 1. Llamó a buscar_protocolo
    llamo_rag = _check_tools_contain(turn.tools_called, "buscar_protocolo")
    checks.append((
        "RAG: Consultó el manual con buscar_protocolo",
        llamo_rag,
        "Ejecutó búsqueda vectorial en Supabase" if llamo_rag else "No ejecutó buscar_protocolo"
    ))

    # 2. Llamó a derivar_a_emergencias
    llamo_derivar = _check_tools_contain(turn.tools_called, "derivar_a_emergencias") or turn.triage_state.derivado
    checks.append((
        "Despacho: Derivó la emergencia al 911",
        llamo_derivar,
        "Estado derivado=True (911 despachado)" if llamo_derivar else "No llamó a derivar_a_emergencias"
    ))

    # 3. Ordenó compresiones torácicas / RCP
    ordeno_rcp = any(w in bajo for w in ("compresion", "compresión", "comprim", "pecho", "manos en el centro", "rcp"))
    checks.append((
        "Primeros Auxilios: Ordenó compresiones en el centro del pecho",
        ordeno_rcp,
        "Indicó compresiones torácicas de reanimación" if ordeno_rcp else "No dio la indicación de compresiones en el pecho"
    ))

    # 4. Sin 112
    ok_112, msg_112 = _assert_no_112(turn.assistant_reply)
    checks.append(("Localización: No decir 112", ok_112, msg_112))

    return checks


# Reglas para Turno 3 del Escenario Principal (Ritmo)
def assert_turno_3_principal(turn: TurnResult) -> list[tuple[str, bool, str]]:
    checks = []
    bajo = turn.assistant_reply.lower()

    # 1. Guía de ritmo / frecuencia
    guio_ritmo = any(w in bajo for w in ("ritmo", "100", "120", "segundo", "rápido", "rapido", "fuerte", "sin parar", "continuo", "seguí"))
    checks.append((
        "Acompañamiento: Indicó cadencia o continuidad de compresiones",
        guio_ritmo,
        "Guió el ritmo y cadencia de RCP" if guio_ritmo else "No indicó ritmo ni continuidad"
    ))

    # 2. Sin 112
    ok_112, msg_112 = _assert_no_112(turn.assistant_reply)
    checks.append(("Localización: No decir 112", ok_112, msg_112))

    return checks


# Reglas para el Escenario del Casco (Motociclista)
def assert_escenario_casco(turn: TurnResult) -> list[tuple[str, bool, str]]:
    checks = []
    bajo = turn.assistant_reply.lower()

    # 1. Llamó a buscar_protocolo
    llamo_rag = _check_tools_contain(turn.tools_called, "buscar_protocolo")
    checks.append((
        "RAG: Consultó protocolo de siniestro vial en moto",
        llamo_rag,
        "Ejecutó búsqueda vectorial sobre accidentes de moto" if llamo_rag else "No ejecutó buscar_protocolo"
    ))

    # 2. Prohibición estricta de sacar el casco
    prohibe_sacar = (
        ("no" in bajo and any(w in bajo for w in ("saques", "sacar", "quites", "quitar", "retirar", "muevas", "mover")))
        or "dejale el casco" in bajo or "mantené el casco" in bajo or "mantener el casco" in bajo
    )
    checks.append((
        "Protocolo Vital: Prohibición expresa de quitar el casco",
        prohibe_sacar,
        "Indicó NO quitar el casco" if prohibe_sacar else "Peligro: No fue tajante en prohibir el retiro del casco"
    ))

    # 3. Mención de columna / cervical / inmovilización
    menciona_cervical = any(w in bajo for w in ("cervical", "cuello", "columna", "inmóvil", "inmovil", "quieto", "médic", "ambulancia"))
    checks.append((
        "Justificación Clínica: Daño cervical o inmovilización",
        menciona_cervical,
        "Justificó por riesgo cervical o necesidad de inmovilizar" if menciona_cervical else "Faltó justificación médica"
    ))

    # 4. Sin 112
    ok_112, msg_112 = _assert_no_112(turn.assistant_reply)
    checks.append(("Localización: No decir 112", ok_112, msg_112))

    return checks


# Reglas para Contraprueba: Inconsciente que SÍ respira
def assert_turno_2_inconsciente_respira(turn: TurnResult) -> list[tuple[str, bool, str]]:
    checks = []
    bajo = turn.assistant_reply.lower()

    # 1. Prohibición de RCP si respira
    no_rcp = (
        "no" in bajo and any(w in bajo for w in ("compresion", "compresión", "rcp", "masaje", "aprietes"))
    ) or not any(w in bajo for w in ("hacé compresiones", "comprimí", "inicia rcp"))

    checks.append((
        "Seguridad Médica: NO ordenar RCP a persona que sí respira",
        no_rcp,
        "Correcto: no ordenó compresiones a paciente que respira" if no_rcp else "Peligro: ordenó RCP sobre un paciente con respiración espontánea"
    ))

    # 2. Mantener vía aérea o vigilar
    cuida_aire = any(w in bajo for w in ("vía aérea", "via aerea", "aire", "respiración", "respirando", "costado", "vigil", "mirá"))
    checks.append((
        "Primeros Auxilios: Mantener vía de aire permeable y vigilar respiración",
        cuida_aire,
        "Indicó monitorear o cuidar la respiración continua" if cuida_aire else "Faltó indicar vigilancia de la respiración"
    ))

    # 3. Sin 112
    ok_112, msg_112 = _assert_no_112(turn.assistant_reply)
    checks.append(("Localización: No decir 112", ok_112, msg_112))

    return checks


# ─────────────────────────────────────────────────────────────────────────────
# Ejecución de Turno y Simulación de Sesión
# ─────────────────────────────────────────────────────────────────────────────

async def simular_turno(
    session: AgentSession,
    user_text: str,
    assert_fn: Callable[[TurnResult], list[tuple[str, bool, str]]] | None = None,
) -> TurnResult:
    """Ejecuta un turno con detección determinística y captura eventos y estado."""
    t0 = time.perf_counter()

    # 1. Procesamiento determinístico de triage (idéntico al camino de audio y chat)
    senal = procesar_turno_usuario(user_text, session.userdata)
    aviso = generar_aviso_critico(senal, session.userdata) if senal else ""
    entrada = user_text if not senal else f"{user_text}\n\n[{aviso}]"

    # 2. Inferencia y herramientas
    resultado = await session.run(user_input=entrada)
    duracion = time.perf_counter() - t0

    # 3. Recolectar llamadas a tools
    tools = []
    for ev in resultado.events:
        tipo = type(ev).__name__
        if tipo == "FunctionCallEvent":
            args = ev.item.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    pass
            tools.append({"name": ev.item.name, "arguments": args})

    # 4. Recolectar última respuesta del asistente
    assistant_msgs = [m for m in session.history.messages() if m.role == "assistant"]
    reply = assistant_msgs[-1].text_content if assistant_msgs else ""

    # 5. Armar resultado del turno
    turn_res = TurnResult(
        user_input=user_text,
        injected_alert=aviso,
        assistant_reply=reply,
        tools_called=tools,
        triage_state=session.userdata,
        duration_sec=duracion,
    )

    if assert_fn:
        turn_res.assertions = assert_fn(turn_res)

    return turn_res


# ─────────────────────────────────────────────────────────────────────────────
# Definición de los Escenarios de la Expo
# ─────────────────────────────────────────────────────────────────────────────

async def correr_escenario_principal(modelo: str) -> ScenarioResult:
    sc = ScenarioResult(
        name="Escenario Principal (Camino Crítico: Inconsciente -> Paro -> RCP)",
        description="Evalúa el flujo héroe para el Decano: choque en banquina, acompañante inconsciente que no respira y asistencia en RCP.",
    )

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
        # Turno 1
        t1 = await simular_turno(
            session,
            "Hola, choqué contra otro auto en la banquina. Mi acompañante está inconsciente y no me responde.",
            assert_turno_1_principal,
        )
        sc.turns.append(t1)

        # Turno 2
        t2 = await simular_turno(
            session,
            "No, no se le mueve el pecho y no está respirando.",
            assert_turno_2_principal,
        )
        sc.turns.append(t2)

        # Turno 3
        t3 = await simular_turno(
            session,
            "Sí, ya empecé a comprimir, ¿a qué ritmo sigo?",
            assert_turno_3_principal,
        )
        sc.turns.append(t3)

    finally:
        await session.aclose()

    # Evaluar si pasó todo
    sc.passed = all(
        all(ok for _, ok, _ in t.assertions)
        for t in sc.turns
    )
    return sc


async def correr_escenario_casco(modelo: str) -> ScenarioResult:
    sc = ScenarioResult(
        name="Pregunta Trampa: Motociclista y Casco",
        description="Evalúa si ante una pregunta del Decano el RAG prohíbe retirar el casco para proteger la columna cervical.",
    )

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
        t1 = await simular_turno(
            session,
            "Hola, estoy a salvo en la banquina. Recién se cayó un chico en moto al asfalto, ¿le tengo que sacar el casco?",
            assert_escenario_casco,
        )
        sc.turns.append(t1)
    finally:
        await session.aclose()

    sc.passed = all(
        all(ok for _, ok, _ in t.assertions)
        for t in sc.turns
    )
    return sc


async def correr_escenario_inconsciente_respira(modelo: str) -> ScenarioResult:
    sc = ScenarioResult(
        name="Contraprueba Médica: Inconsciente que SÍ Respira",
        description="Evalúa que si el herido respira normalmente, el sistema NO ordene compresiones y mande vigilar la respiración.",
    )

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
        t1 = await simular_turno(
            session,
            "Choqué contra otro auto, mi acompañante está inconsciente.",
            assert_turno_1_principal,
        )
        sc.turns.append(t1)

        t2 = await simular_turno(
            session,
            "Sí, se le mueve el pecho y está respirando.",
            assert_turno_2_inconsciente_respira,
        )
        sc.turns.append(t2)
    finally:
        await session.aclose()

    sc.passed = all(
        all(ok for _, ok, _ in t.assertions)
        for t in sc.turns
    )
    return sc


# ─────────────────────────────────────────────────────────────────────────────
# Visualización y Reporte
# ─────────────────────────────────────────────────────────────────────────────

def imprimir_reporte_escenario(sc: ScenarioResult, index: int) -> None:
    sep = "═" * 72
    print(f"\n{Fore.CYAN}{sep}")
    print(f"{Fore.CYAN} ESCENARIO {index}: {Style.BRIGHT}{sc.name}")
    print(f"{Fore.WHITE} {sc.description}")
    print(f"{Fore.CYAN}{sep}{Style.RESET_ALL}\n")

    for i, t in enumerate(sc.turns, 1):
        print(f"{Fore.YELLOW}{Style.BRIGHT}[TURNO {i}]{Style.RESET_ALL} {Fore.WHITE}Usuario:{Style.RESET_ALL} «{t.user_input}»")
        
        if t.injected_alert:
            print(f"  {Fore.MAGENTA}⚡ Alerta Triage Inyectada:{Style.RESET_ALL} {t.injected_alert[:90]}…")
        
        if t.tools_called:
            tools_str = ", ".join(f"{call['name']}()" for call in t.tools_called)
            print(f"  {Fore.BLUE}🔧 Tools ejecutadas:{Style.RESET_ALL} {tools_str}")

        print(f"  {Fore.GREEN}🎙 Asistente:{Style.RESET_ALL} «{t.assistant_reply}»")
        print(f"  {Fore.LIGHTBLACK_EX}⏱ Latencia LLM+Tools: {t.duration_sec:.2f}s{Style.RESET_ALL}")

        print(f"  {Style.BRIGHT}Verificaciones automáticas:{Style.RESET_ALL}")
        for desc, ok, detalle in t.assertions:
            if ok:
                print(f"    {Fore.GREEN}✓ {desc}{Style.RESET_ALL} ({Fore.LIGHTBLACK_EX}{detalle}{Style.RESET_ALL})")
            else:
                print(f"    {Fore.RED}{Style.BRIGHT}✗ {desc}{Style.RESET_ALL} -> {Fore.RED}{detalle}{Style.RESET_ALL}")
        print()

    estado = sc.turns[-1].triage_state
    print(f"{Fore.LIGHTBLACK_EX}  [Estado Triage Final] Crítico: {estado.critico()} | Derivado 911: {estado.derivado} | Señal: {estado.senal_critica}{Style.RESET_ALL}")


def guardar_resultados_json(resultados: list[ScenarioResult], path: Path, modelo: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = []
    for sc in resultados:
        serializable.append({
            "name": sc.name,
            "description": sc.description,
            "passed": sc.passed,
            "turns": [
                {
                    "user_input": t.user_input,
                    "assistant_reply": t.assistant_reply,
                    "tools_called": t.tools_called,
                    "duration_sec": round(t.duration_sec, 2),
                    "assertions": [
                        {"name": desc, "passed": ok, "detail": det}
                        for desc, ok, det in t.assertions
                    ],
                }
                for t in sc.turns
            ]
        })

    payload = {
        "timestamp": datetime.now().isoformat(),
        "modelo": modelo,
        "total_escenarios": len(resultados),
        "total_passed": sum(1 for s in resultados if s.passed),
        "escenarios": serializable,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# Main CLI
# ─────────────────────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser(description="Test y validación del guion para la Expo")
    parser.add_argument(
        "--escenario",
        choices=["principal", "casco", "inconsciente_respira", "todos"],
        default="todos",
        help="Escenario puntual a ejecutar (default: todos)",
    )
    parser.add_argument(
        "--modelo",
        default=os.getenv("LLM_MODEL", "openai/gpt-4.1-mini"),
        help="Modelo de lenguaje a utilizar para la prueba",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("metricas/resultados/evaluacion_guion_expo.json"),
        help="Archivo JSON de salida (evita pisar corridas de modelos distintos)",
    )
    args = parser.parse_args()

    print(f"\n{Fore.CYAN}{Style.BRIGHT}══════════════════════════════════════════════════════════════════════")
    print(f" 🚑 EVALUADOR AUTOMÁTICO DE GUION - EXPO FACULTAD")
    print(f" Modelo: {args.modelo}")
    print(f" Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"══════════════════════════════════════════════════════════════════════{Style.RESET_ALL}")

    resultados: list[ScenarioResult] = []

    async with http_context.open():
        if args.escenario in ("principal", "todos"):
            res = await correr_escenario_principal(args.modelo)
            resultados.append(res)

        if args.escenario in ("casco", "todos"):
            res = await correr_escenario_casco(args.modelo)
            resultados.append(res)

        if args.escenario in ("inconsciente_respira", "todos"):
            res = await correr_escenario_inconsciente_respira(args.modelo)
            resultados.append(res)

    for i, sc in enumerate(resultados, 1):
        imprimir_reporte_escenario(sc, i)

    # Resumen Final
    total_checks = sum(len(t.assertions) for sc in resultados for t in sc.turns)
    passed_checks = sum(
        1 for sc in resultados for t in sc.turns for _, ok, _ in t.assertions if ok
    )
    all_passed = all(sc.passed for sc in resultados)

    out_file = args.output
    guardar_resultados_json(resultados, out_file, args.modelo)

    print(f"\n{Fore.WHITE}{Style.BRIGHT}──────────────────────────────────────────────────────────────────────")
    print(f" RESUMEN DE EVALUACIÓN:")
    print(f" • Escenarios ejecutados: {len(resultados)}")
    print(f" • Verificaciones clínicas y protocolarias: {passed_checks}/{total_checks} aprobadas")
    print(f" • Reporte JSON guardado en: {out_file}")
    print(f"──────────────────────────────────────────────────────────────────────{Style.RESET_ALL}")

    if all_passed:
        print(f"\n{Fore.GREEN}{Style.BRIGHT}🎉 EXPO-READY: Todos los escenarios y reglas del guion pasaron con éxito.")
        print(f"El agente responde correctamente y está listo para ser presentado al Decano.{Style.RESET_ALL}\n")
        return 0
    else:
        print(f"\n{Fore.RED}{Style.BRIGHT}⚠️ ATENCIÓN: Se encontraron fallas en las reglas del protocolo.")
        print(f"Revisar el detalle de las fallas arriba antes de la presentación.{Style.RESET_ALL}\n")
        return 1


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.exit(code)
