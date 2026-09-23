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
import re
from dataclasses import dataclass, field

from livekit.agents import RunContext, function_tool
from livekit.agents.llm import ToolFlag

logger = logging.getLogger("triage")

# Señales de riesgo de vida, tal como las dice una persona común por teléfono.
# Se usan para detectar el caso crítico de forma DETERMINÍSTICA, sin depender de
# que el modelo se acuerde de llamar una tool.
SENALES_INCONSCIENCIA = (
    "inconsciente", "inconscientes",
    "desmayado", "desmayada", "desmayados", "desmayadas",
    "desvanecido", "desvanecida", "desvanecidos", "desvanecidas",
    "no reacciona", "no reaccionan",
    "no responde", "no responden",
    "no se mueve", "no se mueven",
)

SENALES_PARO_RESPIRATORIO = (
    "no respira", "no está respirando", "no esta respirando", "dejó de respirar",
    "dejo de respirar", "no tiene pulso", "se está muriendo", "se esta muriendo",
)

SENALES_ATRAPAMIENTO = (
    "atrapado", "atrapada", "atrapados", "atrapadas", "atrapad",
    "aplastado", "aplastada", "aplastados", "aplastadas", "aplastad",
    "prensado", "prensada", "prensados", "prensadas", "prensad",
    "aprisionado", "aprisionada", "aprisionados", "aprisionadas", "aprisionad",
    "encerrado", "encerrada", "encerrados", "encerradas", "encerrad",
    "no puede salir", "no pueden salir", "no logra salir",
    "trabado", "trabada", "trabados", "trabadas", "trabad",
)

SENALES_HEMORRAGIA = (
    "se desangra", "desangrando", "sangra mucho", "mucha sangre", "hemorragia",
    "no para de sangrar",
)

SENALES_FUEGO = (
    "fuego", "se prendió", "se prendio", "incendio", "humo", "llamas",
    "combustible", "nafta",
)

SENALES_CONVULSION = ("convulsion", "convulsión", "convulsiona", "convulsionando")

# Categoría -> señales. El orden es la prioridad cuando en una misma frase
# aparece más de una («no respira y sale humo» es primero un paro).
CATEGORIAS: dict[str, tuple[str, ...]] = {
    "paro": SENALES_PARO_RESPIRATORIO,
    "atrapamiento": SENALES_ATRAPAMIENTO,
    "inconsciencia": SENALES_INCONSCIENCIA,
    "hemorragia": SENALES_HEMORRAGIA,
    "fuego": SENALES_FUEGO,
    "convulsion": SENALES_CONVULSION,
}

SENALES_CRITICAS = tuple(s for senales in CATEGORIAS.values() for s in senales)

# Quien llama no puede ver ni llegar al herido: no hay que pedirle que revise
# nada del herido (en las pruebas, ante «no veo si reacciona», el agente
# preguntaba «¿está despierto?»).
SENALES_SIN_ACCESO = (
    "no lo veo", "no la veo", "no los veo", "no veo si", "no veo bien",
    "no llego", "no puedo llegar", "no alcanzo", "no me puedo acercar",
    "no puedo acercarme", "no puedo ver", "no se ve",
)


def _tiene_senal_critica(texto: str) -> bool:
    bajo = texto.lower()
    return any(s in bajo for s in SENALES_CRITICAS)


def _categoria_de(senal: str) -> str | None:
    for categoria, senales in CATEGORIAS.items():
        if senal in senales:
            return categoria
    return None


# Alguien lastimado, dicho como lo dice una persona común. No es riesgo de vida
# por sí solo, pero alcanza para derivar al 911. En producción, «está tirado en
# el piso con el casco» no disparaba nada y el agente terminaba diciendo
# «llamá ayuda».
_HERIDO = re.compile(
    r"\b(herid[oa]s?|lastimad[oa]s?|golpead[oa]s?|lesionad[oa]s?|atropellad[oa]s?|"
    r"tirad[oa]s? (en|sobre|al)|en el (piso|suelo|asfalto)|no se (puede )?levanta|"
    r"se cay[oó]|sangra|le duele|se queja)",
    re.IGNORECASE,
)
_SIN_HERIDOS = re.compile(
    r"\b(nadie|ning[uú]n[oa]?|no hay|sin|estamos bien|todos bien|ninguno)\b[^.?!]{0,25}"
    r"(herid|lastimad|lesionad|golpead)",
    re.IGNORECASE,
)


def hay_herido(texto: str) -> bool:
    """«Está tirado en el piso», «hay un herido». Descarta «nadie está herido»."""
    return bool(_HERIDO.search(texto)) and not _SIN_HERIDOS.search(texto)


def sin_acceso_al_herido(texto: str) -> bool:
    bajo = texto.lower()
    return any(s in bajo for s in SENALES_SIN_ACCESO)


_AVISO_911 = (
    "Ya se dio aviso al 911 y la llamada está geolocalizada (eso se lo dice el sistema "
    "a la persona automáticamente: vos no lo digas)."
)

# Instrucción genérica, para categorías sin aviso específico.
AVISO_CRITICO = (
    "RIESGO DE VIDA («{senal}»). " + _AVISO_911 + " Dejá de juntar datos y dale "
    "la indicación que salva la vida, con el protocolo del manual."
)


def generar_aviso_critico(senal: str, st: TriageState) -> str:
    """Instrucción específica según el tipo de riesgo de vida detectado.

    El aviso al 911 ya está hecho cuando esto se inyecta (lo hace
    procesar_turno_usuario), así que el modelo solo tiene que comunicarlo UNA
    vez, integrado con la maniobra."""
    categoria = _categoria_de(senal)

    if categoria == "atrapamiento":
        return (
            f"PERSONA ATRAPADA («{senal}»). {_AVISO_911} "
            "Decile con firmeza que NO la saque ni la mueva ni fuerce el auto: los bomberos tienen las "
            "herramientas. Que le hable desde afuera, sin meterse al auto."
        )
    if categoria == "paro" or st.respira is False:
        return (
            f"NO RESPIRA («{senal}»). {_AVISO_911} "
            "Indicá YA las compresiones en el centro del pecho, fuertes y rápidas, sin parar, "
            "según el protocolo del manual. En este turno no hagas preguntas de datos."
        )
    if categoria == "inconsciencia":
        if st.respira is True:
            return (
                f"INCONSCIENTE QUE RESPIRA («{senal}»). {_AVISO_911} "
                "NO indiques compresiones. Seguí el protocolo del manual para el herido "
                "inconsciente que respira y que vigile que siga respirando."
            )
        return (
            f"INCONSCIENTE («{senal}»). {_AVISO_911} "
            "Todavía NO se sabe si respira: PROHIBIDO indicar compresiones. "
            "Respondé exactamente con esta idea: «Fijate si se le mueve el pecho. ¿Respira?»."
        )
    if categoria == "hemorragia":
        return (
            f"SANGRADO GRAVE («{senal}»). {_AVISO_911} "
            "Indicá apretar fuerte y sin soltar sobre la herida, según el protocolo del manual."
        )
    if categoria == "fuego":
        return (
            f"RIESGO DE FUEGO («{senal}»). {_AVISO_911} "
            "Lo primero es que todos se alejen del vehículo y de la calzada. Dalo como "
            "indicación concreta en este turno, no solo el aviso."
        )
    if categoria == "convulsion":
        return (
            f"CONVULSIÓN («{senal}»). {_AVISO_911} "
            "El manual no tiene un protocolo de convulsiones: no inventes maniobras. "
            "Pedile que te avise si deja de respirar."
        )
    return AVISO_CRITICO.format(senal=senal)


def procesar_turno_usuario(texto: str, st: TriageState) -> str | None:
    """Registra lo que dijo la persona y detecta riesgo de vida determinísticamente.

    Devuelve la señal crítica de ESTE turno si es de una categoría que todavía
    no se avisó. Antes solo se detectaba la primera señal de la llamada: si
    alguien decía «inconsciente» y en el turno siguiente «no respira», el paro
    pasaba sin aviso.

    También actualiza el estado que no conviene dejar librado al modelo (que no
    respira, que hay alguien atrapado) y deriva al 911 sin esperar una tool.
    """
    if not texto:
        return None

    st.dichos.append(texto)
    bajo = texto.lower()

    for categoria, senales in CATEGORIAS.items():
        senal = next((s for s in senales if s in bajo), None)
        if senal is None:
            continue

        if categoria == "paro":
            st.respira = False
            st.consciente = False
        elif categoria == "inconsciencia":
            st.consciente = False
        elif categoria == "atrapamiento":
            st.atrapado = True

        if st.senal_critica is None:
            st.senal_critica = senal
        if categoria in st.alertas:
            return None
        st.alertas.add(categoria)
        logger.warning("señal crítica detectada: '%s' (%s) | dicho: %s", senal, categoria, texto)
        derivar_automatico(st, motivo=senal)
        return senal
    return None


def derivar_automatico(st: TriageState, motivo: str) -> None:
    """Despacho al 911. Lo hace el sistema, no el modelo: antes existía la tool
    derivar_a_emergencias y el modelo la seguía llamando aunque ya fuera
    automática, lo que costaba una vuelta extra al LLM por turno."""
    if st.derivado:
        return
    st.derivado = True
    st.tool_calls.append({
        "tool": "derivar_a_emergencias",
        "args": {"auto": True, "motivo": motivo},
        "was_critical": True,
        "triage_brief": st.brief(),
    })
    logger.info("derivar_a_emergencias (auto) | geolocalizado | estado=%s", st.brief())


@dataclass
class TriageState:
    """Lo que se sabe de la escena y estado de la emergencia."""

    que_paso: str | None = None
    heridos: str | None = None
    riesgos: str | None = None
    consciente: bool | None = None
    respira: bool | None = None
    caller_seguro: bool | None = None
    atrapado: bool | None = None

    derivado: bool = False
    # El sistema ya le dijo «Ya estás geolocalizado y la ayuda va en camino.»
    # (lo agrega habla.aplicar_aviso_911, una vez por llamada).
    aviso_911_dicho: bool = False
    # Lo levanta el detector determinístico de on_user_turn_completed, no el LLM.
    senal_critica: str | None = None
    # Categorías de riesgo ya avisadas al modelo (para no repetir el aviso).
    alertas: set[str] = field(default_factory=set)
    # Temas del manual ya inyectados en el contexto (para no repetirlos).
    temas_inyectados: set[str] = field(default_factory=set)
    # Lo que dijo la persona, textual.
    dichos: list[str] = field(default_factory=list)
    # Última consulta a buscar_protocolo en este turno (evita repetirla).
    ultima_consulta: str | None = None
    # La persona hizo una pregunta en este turno (la marca contexto_del_turno).
    pregunta_pendiente: bool = False
    # En este turno se adjuntó un protocolo: la indicación va antes que los datos.
    indicacion_pendiente: bool = False

    # Debug: tool calls en el turno actual
    tool_calls: list[dict] = field(default_factory=list)
    # Debug: métricas del último response del LLM
    last_llm_metrics: dict | None = None
    # Debug: uso de tokens del LLM
    last_llm_tokens: dict | None = None

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
            # Si está consciente, respira seguro — no preguntar lo obvio.
            # Solo preguntar respiración si está inconsciente o no se sabe.
            if self.respira is None and self.consciente is not True:
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
        if self.respira is False or self.consciente is False or self.atrapado is True:
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
        if self.atrapado:
            brief += " Persona atrapada: sí."
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
    atrapado: bool | None = None,
) -> str:
    """Guarda datos de la escena a medida que la persona los va diciendo.

    Llamala en el mismo turno en que te dan un dato NUEVO, con solo los campos
    que te dijeron. Si en el turno no hay datos nuevos de la escena, no la llames.
    Guardá las palabras de la persona, no tu interpretación.

    La ubicación NO se pide ni se guarda aquí porque el sistema ya geolocaliza
    automáticamente a la persona.

    que_paso: qué tipo de accidente fue, en palabras de quien llama.
    heridos: cuántas personas lastimadas y cómo se ven.
    riesgos: fuego, humo, olor a combustible, autos que siguen pasando.
    consciente: si el herido está despierto y reacciona.
    respira: si el herido respira.
    caller_seguro: si quien llama está fuera de la calzada, a salvo.
    atrapado: si hay alguna persona atrapada, aprisionada o encerrada en un vehículo.
    """
    st = context.userdata

    if atrapado is None:
        texto_in = f"{heridos or ''} {que_paso or ''}".lower()
        if any(s in texto_in for s in SENALES_ATRAPAMIENTO):
            atrapado = True

    guardados = []
    for nombre, valor in (
        ("que_paso", que_paso),
        ("heridos", heridos),
        ("riesgos", riesgos),
        ("consciente", consciente),
        ("respira", respira),
        ("caller_seguro", caller_seguro),
        ("atrapado", atrapado),
    ):
        if valor is not None:
            setattr(st, nombre, valor)
            guardados.append(nombre)

    # Si está consciente, respira seguro — inferirlo evita una pregunta
    # mecánica e innecesaria que suena robótica.
    if st.consciente is True and st.respira is None:
        st.respira = True
        if "respira" not in guardados:
            guardados.append("respira")

    if not guardados:
        if st.critico() and not st.derivado:
            derivar_automatico(st, motivo="riesgo de vida")
            return (
                "No hay nuevos datos. Hay riesgo de vida: ya se dio aviso al 911 y está "
                "geolocalizado. Seguí asistiendo con indicaciones seguras."
            )
        return "No se registraron datos nuevos. Seguí asistiendo a la persona."

    context.userdata.tool_calls.append({
        "tool": "registrar_datos_escena",
        "args": {
            k: v for k, v in (
                ("que_paso", que_paso), ("heridos", heridos), ("riesgos", riesgos),
                ("consciente", consciente), ("respira", respira), ("caller_seguro", caller_seguro),
                ("atrapado", atrapado),
            ) if v is not None
        },
        "saved_fields": guardados,
    })

    logger.info("triage | guardado=%s | estado=%s", guardados, st.brief())

    # En las pruebas, con «¿le saco el casco?» o «se queja del cuello», el
    # modelo registraba datos en paralelo y la respuesta de esta tool («faltan
    # datos») lo llevaba a preguntar en vez de indicar. Si hay una pregunta o
    # un protocolo recién adjuntado, eso va primero.
    if st.pregunta_pendiente or st.indicacion_pendiente:
        if st.critico() or (st.heridos and not st._sin_heridos()):
            derivar_automatico(st, motivo="riesgo de vida" if st.critico() else "heridos")
        que = "respondé la pregunta de la persona" if st.pregunta_pendiente else "dale la indicación"
        return (
            f"Registrado. Ahora {que} con el protocolo del contexto. "
            "No hagas ninguna pregunta en este turno."
        )

    # Auto-derivación: con heridos confirmados o riesgo crítico el sistema
    # despacha al 911 sin otra vuelta al LLM.
    if st.critico() or (st.heridos and not st._sin_heridos()):
        derivar_automatico(st, motivo="riesgo de vida" if st.critico() else "heridos")

    if st.critico():
        es_atrapado = (
            st.atrapado is True
            or any(s in (st.heridos or "").lower() for s in SENALES_ATRAPAMIENTO)
            or any(s in (st.que_paso or "").lower() for s in SENALES_ATRAPAMIENTO)
            or any(s in (st.senal_critica or "").lower() for s in SENALES_ATRAPAMIENTO)
        )
        if st.respira is False:
            return (
                "Registrado. NO RESPIRA: ya se dio aviso al 911 y está geolocalizado. "
                "Indicá compresiones en el centro del pecho, fuertes y rápidas. "
                "Si ya está comprimiendo, que siga sin parar hasta que llegue la ayuda."
            )
        if es_atrapado:
            return (
                "Registrado. PERSONA ATRAPADA: ya se dio aviso al 911 y está geolocalizado. "
                "Que NO la mueva ni fuerce el vehículo (riesgo de dañar la columna). "
                "Si puede verla, que le hable desde afuera; si no la ve, que no insista y se quede a resguardo."
            )
        if st.consciente is False and st.respira is None:
            return (
                "Registrado. INCONSCIENTE: ya se dio aviso al 911 y está geolocalizado. "
                "No indiques compresiones sin saber si respira: pedile que se fije si se le mueve el pecho."
            )
        if st.consciente is False and st.respira is True:
            return (
                "Registrado. Inconsciente pero RESPIRA: ya se dio aviso al 911 y está geolocalizado. "
                "NO indiques compresiones. Que no lo mueva, mantenga libre el paso del aire y vigile "
                "que siga respirando."
            )
        return (
            "Registrado. HAY RIESGO DE VIDA: ya se dio aviso al 911 y está geolocalizado. "
            "Dale la indicación que salva la vida con la información del manual."
        )

    faltan = st.faltantes()
    if not faltan:
        if st._sin_heridos():
            return (
                "Registrado. NO HAY HERIDOS ni riesgo de vida: no menciones ambulancia ni 911. "
                "Respondé lo que haya preguntado y guiala con pautas de seguridad vial."
            )
        return (
            "Registrado. Ya se dio aviso al 911 y la llamada está geolocalizada. "
            "Seguí asistiendo paso a paso."
        )
    return (
        "Registrado. Si la persona hizo una pregunta, respondela primero. "
        f"Datos que faltan (pedí uno solo, y solo si no hay algo más urgente): {', '.join(faltan)}."
    )
