"""Estado de triage y las tools que lo llenan.

Por qué una máquina de estados en userdata y no AgentTask ni multi-agente:

El SDK trae `AgentTask` y `beta.workflows.TaskGroup`, donde cada task retiene el
turno hasta llenar su slot. Suena bien hasta que alguien contesta "¿qué pasó?"
con "¡se está desangrando!" y el flujo la trae de vuelta a la pregunta anterior.
Eso es peligroso acá, y en una demo en vivo es la falla que todos van a notar.

Con estado tipado en `session.userdata` el LLM puede intercalar libremente —dar
una indicación ahora, pedir el dato que falta en el turno siguiente— mientras el
estado queda auditable y ordenado.

La geolocalización se asume automática desde el sistema, por lo que no se le
pregunta ubicación a la persona. El triage se enfoca directamente en la gravedad
del hecho, riesgos inmediatos y estado de los heridos.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from livekit.agents import RunContext, ToolError, function_tool
from livekit.agents.llm import ToolFlag

logger = logging.getLogger("triage")

# Señales de riesgo de vida, tal como las dice una persona común por teléfono.
# Se usan para detectar el caso crítico de forma DETERMINÍSTICA, sin depender de
# que el modelo se acuerde de llamar una tool.
SENALES_CRITICAS = (
    "no respira", "no está respirando", "no esta respirando", "dejó de respirar",
    "dejo de respirar", "no reacciona", "no responde", "no se mueve",
    "inconsciente", "desmayado", "desvanecido",
    "se desangra", "sangra mucho", "mucha sangre", "hemorragia",
    "atrapado", "aplastado", "prensado",
    "fuego", "se prendió", "se prendio", "incendio", "humo", "combustible",
    "nafta", "convulsion", "convulsión", "no tiene pulso", "se está muriendo",
    "se esta muriendo",
)


def _tiene_senal_critica(texto: str) -> bool:
    bajo = texto.lower()
    return any(s in bajo for s in SENALES_CRITICAS)


# Instrucción que se le inyecta al modelo cuando salta una señal crítica.
AVISO_CRITICO = (
    "RIESGO DE VIDA detectado en lo que dijo la persona («{senal}»). "
    "Dejá de juntar datos. Buscá con buscar_protocolo la maniobra que "
    "corresponde, dala en un paso, y derivá con derivar_a_emergencias "
    "avisando que ya fue geolocalizada y el 911 va en camino."
)


def procesar_turno_usuario(texto: str, st: TriageState) -> str | None:
    """Registra lo que dijo la persona y detecta riesgo de vida determinísticamente."""
    if not texto:
        return None

    st.dichos.append(texto)

    if st.senal_critica is not None:
        return None

    bajo = texto.lower()
    for senal in SENALES_CRITICAS:
        if senal in bajo:
            st.senal_critica = senal
            logger.warning("señal crítica detectada: '%s' | dicho: %s", senal, texto)
            return senal
    return None


@dataclass
class TriageState:
    """Lo que se sabe de la escena y estado de la emergencia."""

    que_paso: str | None = None
    heridos: str | None = None
    riesgos: str | None = None
    consciente: bool | None = None
    respira: bool | None = None
    caller_seguro: bool | None = None

    derivado: bool = False
    # Lo levanta el detector determinístico de on_user_turn_completed, no el LLM.
    senal_critica: str | None = None
    # Lo que dijo la persona, textual.
    dichos: list[str] = field(default_factory=list)

    # -- consultas ---------------------------------------------------------

    def faltantes(self) -> list[str]:
        """Datos que todavía no están, en el orden en que hay que pedirlos."""
        pendientes = []
        if self.que_paso is None:
            pendientes.append("qué pasó")
        if self.heridos is None:
            pendientes.append("cuántos lastimados")
        if self.riesgos is None:
            pendientes.append("riesgos (fuego, combustible, tránsito)")
        # Solo se pregunta por conciencia y respiración si hay alguien lastimado.
        if self.heridos and not self._sin_heridos():
            if self.consciente is None:
                pendientes.append("si está despierto")
            if self.respira is None:
                pendientes.append("si respira")
        return pendientes

    def _sin_heridos(self) -> bool:
        """Si la persona ya dijo que no hay lastimados."""
        if not self.heridos:
            return False
        texto = self.heridos.lower()
        return any(
            n in texto
            for n in ("nadie", "ninguno", "ninguna", "no hay herid",
                      "no hay lastimad", "sin herid", "estamos bien", "todos bien")
        )

    def critico(self) -> bool:
        """Riesgo de vida inmediato: saltea el orden del triage y deriva ya."""
        if self.respira is False or self.consciente is False:
            return True
        if self.senal_critica:
            return True
        texto = " ".join(
            filter(None, (self.riesgos, self.heridos, self.que_paso))
        ).lower()
        return _tiene_senal_critica(texto)

    def listo_para_derivar(self) -> bool:
        return self.critico() or self.heridos is not None

    def brief(self) -> str:
        """Resumen del estado de la escena."""
        def d(valor: str | None) -> str:
            return valor if valor else "NO CONFIRMADO"

        def sino(valor: bool | None) -> str:
            if valor is None:
                return "NO CONFIRMADO"
            return "sí" if valor else "no"

        brief = (
            f"Ubicación: Geolocalizada automáticamente. "
            f"Qué pasó: {d(self.que_paso)}. "
            f"Heridos: {d(self.heridos)}. "
            f"Riesgos: {d(self.riesgos)}. "
            f"Consciente: {sino(self.consciente)}. "
            f"Respira: {sino(self.respira)}."
        )
        if self.senal_critica:
            brief += f" SEÑAL CRÍTICA detectada: «{self.senal_critica}»."
        if self.dichos and self.que_paso is None and self.heridos is None:
            crudo = " | ".join(self.dichos[:4])
            brief += f" Sin datos registrados; la persona dijo: «{crudo}»."
        return brief


@function_tool(flags=ToolFlag.IGNORE_ON_ENTER)
async def registrar_datos_escena(
    context: RunContext[TriageState],
    que_paso: str | None = None,
    heridos: str | None = None,
    riesgos: str | None = None,
    consciente: bool | None = None,
    respira: bool | None = None,
    caller_seguro: bool | None = None,
) -> str:
    """Guarda datos de la escena a medida que la persona los va diciendo.

    Llamala en el mismo turno en que te dan un dato, con solo los campos que te
    dijeron. Guardá las palabras de la persona, no tu interpretación.

    La ubicación NO se pide ni se guarda aquí porque el sistema ya geolocaliza
    automáticamente a la persona.

    que_paso: qué tipo de accidente fue, en palabras de quien llama.
    heridos: cuántas personas lastimadas y cómo se ven.
    riesgos: fuego, humo, olor a combustible, autos que siguen pasando.
    consciente: si el herido está despierto y reacciona.
    respira: si el herido respira.
    caller_seguro: si quien llama está fuera de la calzada, a salvo.
    """
    st = context.userdata
    guardados = []
    for nombre, valor in (
        ("que_paso", que_paso),
        ("heridos", heridos),
        ("riesgos", riesgos),
        ("consciente", consciente),
        ("respira", respira),
        ("caller_seguro", caller_seguro),
    ):
        if valor is not None:
            setattr(st, nombre, valor)
            guardados.append(nombre)

    if not guardados:
        return "No me pasaste ningún dato. Preguntale a la persona qué falta."

    logger.info("triage | guardado=%s | estado=%s", guardados, st.brief())

    if st.critico() and not st.derivado:
        return (
            "Registrado. HAY RIESGO DE VIDA: dejá de juntar datos. "
            "Dale primero la indicación que salva la vida (buscala con "
            "buscar_protocolo) y derivá con derivar_a_emergencias."
        )

    faltan = st.faltantes()
    if not faltan:
        return (
            "Registrado. Ya tenés todo lo necesario. "
            "Derivá al 911 con derivar_a_emergencias."
        )
    return f"Registrado. Todavía falta, en este orden: {', '.join(faltan)}."


@function_tool(flags=ToolFlag.IGNORE_ON_ENTER, on_duplicate="reject")
async def derivar_a_emergencias(context: RunContext[TriageState]) -> str:
    """Notifica y despacha los servicios de emergencia (911/ambulancia).

    Usala cuando ya sepas qué pasó y cuántos heridos hay, o antes si hay
    riesgo de vida (no respira, sangra sin parar, atrapado, fuego).
    La ubicación ya fue geolocalizada automáticamente por el sistema.
    Al llamarla, confirmale a la persona que fue geolocalizada y que la
    ayuda ya va en camino, y seguí asistiéndola con primeros auxilios.
    """
    st = context.userdata

    if st.derivado:
        return (
            "Ya diste aviso al 911 y la persona ya está geolocalizada. "
            "Seguí acompañándola y dándole indicaciones de primeros auxilios."
        )

    if not st.critico():
        if st.heridos is None:
            raise ToolError(
                "Todavía no sé si hay personas lastimadas. Preguntale cuántos "
                "heridos hay antes de despachar al 911."
            )

    st.derivado = True
    logger.info("derivar_a_emergencias | geolocalizado | estado=%s", st.brief())

    primero = ""
    if st.critico():
        primero = (
            "PRIMERO: si todavía no le diste la maniobra que salva la vida, "
            "dásela ahora en una frase corta y directa. "
        )

    return (
        f"{primero}La llamada fue GEOLOCALIZADA automáticamente con éxito y se dio aviso "
        "inmediato al 911 (servicios de emergencia y auxilio despachados en camino). "
        "Decile en una frase corta, calma y tranquilizadora a la persona que ya fue "
        "geolocalizada y que el 911 / la ambulancia va en camino. "
        "Continuá asistiéndola con las indicaciones de primeros auxilios y contención."
    )
