"""Estado de triage y las tools que lo llenan.

Por qué una máquina de estados en userdata y no AgentTask ni multi-agente:

El SDK trae `AgentTask` y `beta.workflows.TaskGroup`, donde cada task retiene el
turno hasta llenar su slot. Suena bien hasta que alguien contesta "¿dónde estás?"
con "¡se está desangrando!" y el flujo la trae de vuelta a la pregunta de la
dirección. Eso es peligroso acá, y en una demo en vivo es la falla que todos van
a notar. El handoff entre varios Agent tiene el mismo problema, más un turno
extra de LLM por transición y los bugs clásicos de arrastre de chat_ctx.

Con estado tipado en `session.userdata` el LLM puede intercalar libremente —dar
una indicación ahora, pedir el dato que falta en el turno siguiente— mientras el
estado queda auditable, que es justo lo que necesita el briefing al 911.

El truco que hace que funcione sin orquestación: el valor de retorno de la tool
dirige el flujo. Cada vez que el modelo guarda algo, se le dice qué falta, así
pregunta lo correcto sin código de coordinación y se recupera solo si se pierde
un turno.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolFlag

logger = logging.getLogger("triage")

# Señales de riesgo de vida, tal como las dice una persona común por teléfono.
# Se usan para detectar el caso crítico de forma DETERMINÍSTICA, sin depender de
# que el modelo se acuerde de llamar una tool. Medido: con el prompt solo, el
# modelo prioriza (bien) dar la indicación que salva la vida y nunca registra los
# datos, así que el estado quedaba vacío y critico() daba False justo cuando la
# persona acababa de decir "no respira".
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
    "corresponde, dala en un paso, y derivá con derivar_a_emergencias."
)


def procesar_turno_usuario(texto: str, st: TriageState) -> str | None:
    """Registra lo que dijo la persona y detecta riesgo de vida.

    Vive acá, y no dentro del hook del Agent, porque tiene que correr en los DOS
    caminos de entrada: el de audio (Agent.on_user_turn_completed, que lo llama
    el reconocimiento de voz) y el de texto (session.run(), que usan
    metricas/coverage/ y el back-channel de chat). El hook del Agent solo se
    dispara en el camino de audio, así que si la detección viviera solo ahí, la
    evaluación no ejercitaría nunca la señal de seguridad.

    Devuelve la señal detectada la primera vez que aparece, o None.
    """
    if not texto:
        return None

    st.dichos.append(texto)

    if st.senal_critica is not None:
        return None

    bajo = texto.lower()
    for senal in SENALES_CRITICAS:
        if senal in bajo:
            st.senal_critica = senal
            logger.warning("señal crítica en el habla: '%s' | dicho: %s", senal, texto)
            return senal
    return None


@dataclass
class TriageState:
    """Lo que se sabe de la escena. Es la fuente del briefing al 911."""

    ubicacion: str | None = None
    que_paso: str | None = None
    heridos: str | None = None
    riesgos: str | None = None
    consciente: bool | None = None
    respira: bool | None = None
    caller_seguro: bool | None = None

    derivado: bool = False
    operador_presente: bool = False
    # Lo levanta el detector determinístico de on_user_turn_completed, no el LLM.
    senal_critica: str | None = None
    # Lo que dijo la persona, textual. Es la red de seguridad del briefing al
    # 911: si el modelo no registró los datos, al menos el operador recibe las
    # palabras reales en lugar de una lista de NO CONFIRMADO.
    dichos: list[str] = field(default_factory=list)
    # Identidad SIP de quien llama, para logs y para saber a quién escuchar.
    caller_identity: str | None = None

    # -- consultas ---------------------------------------------------------

    def faltantes(self) -> list[str]:
        """Datos que todavía no están, en el orden en que hay que pedirlos."""
        pendientes = []
        if self.ubicacion is None:
            pendientes.append("dónde es")
        if self.que_paso is None:
            pendientes.append("qué pasó")
        if self.heridos is None:
            pendientes.append("cuántos lastimados")
        if self.riesgos is None:
            pendientes.append("riesgos (fuego, combustible, tránsito)")
        # Solo se pregunta por conciencia y respiración si hay alguien lastimado.
        # Sin esto el agente le preguntaba "¿está despierto?" a quien acababa de
        # decir "nadie está lastimado", que en una demo queda pésimo.
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
        return self.critico() or self.ubicacion is not None

    def brief(self) -> str:
        """Resumen para el operador humano.

        Se arma desde el estado, NO desde el transcript. El transcript de alguien
        en pánico hace que el modelo invente nombres de calles. Los datos que no
        están se dicen como no confirmados, en lugar de completarse.
        """
        def d(valor: str | None) -> str:
            return valor if valor else "NO CONFIRMADO"

        def sino(valor: bool | None) -> str:
            if valor is None:
                return "NO CONFIRMADO"
            return "sí" if valor else "no"

        brief = (
            f"Ubicación: {d(self.ubicacion)}. "
            f"Qué pasó: {d(self.que_paso)}. "
            f"Heridos: {d(self.heridos)}. "
            f"Riesgos: {d(self.riesgos)}. "
            f"Consciente: {sino(self.consciente)}. "
            f"Respira: {sino(self.respira)}."
        )
        if self.senal_critica:
            brief += f" SEÑAL CRÍTICA detectada: «{self.senal_critica}»."
        # Red de seguridad: si el modelo no llegó a registrar nada, el operador
        # igual recibe lo que la persona dijo, textual.
        if self.dichos and self.ubicacion is None:
            crudo = " | ".join(self.dichos[:4])
            brief += f" Sin datos registrados; la persona dijo: «{crudo}»."
        return brief


@function_tool(flags=ToolFlag.IGNORE_ON_ENTER)
async def registrar_datos_escena(
    context: RunContext[TriageState],
    ubicacion: str | None = None,
    que_paso: str | None = None,
    heridos: str | None = None,
    riesgos: str | None = None,
    consciente: bool | None = None,
    respira: bool | None = None,
    caller_seguro: bool | None = None,
) -> str:
    """Guarda datos de la escena a medida que la persona los va diciendo.

    Llamala en el mismo turno en que te dan un dato, con solo los campos que te
    dijeron. Sirve para armar el resumen que después se le pasa al operador del
    911, así que guardá las palabras de la persona, no tu interpretación.

    ubicacion: calle o ruta, kilómetro, localidad, punto de referencia.
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
        ("ubicacion", ubicacion),
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

    # El valor de retorno es lo que dirige el flujo: se le dice al modelo qué
    # falta para que pregunte lo correcto sin necesidad de orquestación.
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
