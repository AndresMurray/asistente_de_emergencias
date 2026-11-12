"""Núcleo del asistente: lo que pasa en cada turno ANTES de llamar al LLM.

Acá no se importa LiveKit ni ningún otro transporte. Lo usan igual agent.py
(el agente sobre LiveKit) y orquestador/ (el orquestador propio), así las dos
formas de atender una llamada comparten el mismo triage, los mismos protocolos
y las mismas respuestas fijas.

Qué hay:
- la carga del retriever (índice del manual) en segundo plano;
- consultar_manual(): lo que hace la tool buscar_protocolo;
- preparar_turno(): triage + protocolos + avisos de cada turno;
- las frases que dice el sistema sin pasar por el LLM.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
import random
import re
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

from metronomo import pide_apagar, pide_prender
from protocolos import TEMAS, detectar_temas, respira_positivo, tema_de_consulta
from rag import RetrievalResult, Retriever
from respuestas_fijas import respuesta_fija
from triage import (
    TriageState,
    categoria_de,
    confirma_despierto,
    confirma_heridos,
    derivar_automatico,
    esta_despierto,
    generar_aviso_critico,
    hay_herido,
    hay_objeto_clavado,
    llego_la_ayuda,
    niega_heridos,
    pregunto_por_heridos,
    procesar_turno_usuario,
    rcp_en_curso,
    recupera_acceso,
    sin_acceso_al_herido,
)

# Mismo nombre de logger que agent.py: los logs del turno salen igual por
# cualquiera de los dos caminos.
logger = logging.getLogger("emergency-agent")

# Un retriever por proceso: adentro tiene el pool de conexiones, el índice en
# memoria y el caché de consultas, y se comparte entre los jobs del proceso.
#
# Se carga en un hilo y NUNCA dentro de un turno: si Supabase está lento (se
# vio una carga del índice colgada más de 25 s), el proceso igual arranca y
# atiende con los textos de respaldo de protocolos.py hasta que el índice esté.
_retriever: Retriever | None = None
_carga: threading.Thread | None = None
_carga_lock = threading.Lock()
_PREWARM_ESPERA_S = 15.0


class RetrieverNoListo(RuntimeError):
    """El índice todavía se está cargando (o la base no respondió)."""


# Si la base no responde no se reintenta en cada turno: cada intento es un
# hilo, una conexión y un traceback en el log (con Supabase caído, uno por turno).
_REINTENTO_CARGA_S = 30.0
_ultimo_fallo: float | None = None


def _cargar_retriever() -> None:
    global _retriever, _ultimo_fallo
    try:
        r = Retriever()
        r.connect()
        _retriever = r  # se publica recién cuando está listo
    except Exception:
        _ultimo_fallo = time.monotonic()
        logger.exception(
            "no pude cargar el retriever; sigo con los textos de respaldo y reintento en %.0f s",
            _REINTENTO_CARGA_S,
        )


def _iniciar_carga() -> threading.Thread:
    global _carga
    with _carga_lock:
        en_curso = _carga is not None and _carga.is_alive()
        fallo_reciente = (
            _carga is not None
            and _ultimo_fallo is not None
            and time.monotonic() - _ultimo_fallo < _REINTENTO_CARGA_S
        )
        if not en_curso and not fallo_reciente:
            _carga = threading.Thread(target=_cargar_retriever, name="carga-retriever", daemon=True)
            _carga.start()
        assert _carga is not None
        return _carga


def _get_retriever() -> Retriever:
    """El retriever si ya está cargado. Si no, dispara la carga en segundo plano
    y levanta RetrieverNoListo: quien llama usa el texto de respaldo en lugar
    de dejar a la persona esperando."""
    if _retriever is not None:
        return _retriever
    _iniciar_carga()
    raise RetrieverNoListo("el índice del manual todavía se está cargando")


def prewarm(proc: object | None = None) -> None:
    """Carga base, índice y caché ANTES de que entre una llamada, con un tope de
    espera para no trabar el arranque del proceso (LiveKit lo corta a los 30 s)."""
    _iniciar_carga().join(timeout=_PREWARM_ESPERA_S)
    if _retriever is None:
        logger.warning("prewarm: el índice sigue cargando; mientras tanto, textos de respaldo")


def retriever_actual() -> Retriever | None:
    """El retriever si ya terminó de cargar; None mientras tanto. No dispara la carga."""
    return _retriever


# Frases de espera profesionales, serias y empáticas para emergencias viales.
# Transmiten control, acompañan y evitan sonar informales o repetitivas.
FRASES_ESPERA_EMERGENCIA = [
    "Dame un segundo, estoy con vos.",
    "Un momento, ya te confirmo el paso exacto.",
    "Un instante, estoy verificando el protocolo.",
    "Dame un segundo, ya te indico cómo seguir.",
    "Un momento, quedate conmigo.",
]


def _elegir_frase_espera(userdata: TriageState | None = None) -> str:
    """Elige una frase de espera profesional evitando repetir la última usada."""
    last_idx = getattr(userdata, "_last_filler_idx", -1) if userdata else -1
    candidatos = [i for i in range(len(FRASES_ESPERA_EMERGENCIA)) if i != last_idx]
    idx = random.choice(candidatos)
    if userdata:
        setattr(userdata, "_last_filler_idx", idx)
    return FRASES_ESPERA_EMERGENCIA[idx]


# --- consulta al manual (la tool buscar_protocolo) ------------------------------

# Lo que el LLM lee de la tool. Un solo texto para LiveKit (agent.py) y para el
# orquestador propio (orquestador/herramientas.py).
DESCRIPCION_BUSCAR_PROTOCOLO = """\
Busca en el manual de primeros auxilios los fragmentos relevantes.

Llamala cuando necesites una maniobra que NO esté ya en el contexto (si ya
tenés el protocolo adjunto en el mensaje de la persona, no la llames).
Reformulá lo que dijo la persona con palabras del manual: "no respira" se
busca como "herido inconsciente que no respira reanimación cardiopulmonar";
"se está desangrando" como "control de hemorragias externas".
NUNCA la llames más de una vez en el mismo turno ni repitas la misma consulta."""


class ManualNoDisponible(RuntimeError):
    """La búsqueda falló por un problema técnico y el tema no tiene texto de respaldo."""


async def consultar_manual(query: str, st: TriageState) -> str:
    """Lo que hace la tool buscar_protocolo, sin depender de quién la llama.

    Devuelve el texto para el LLM. Levanta ManualNoDisponible si la búsqueda
    falló por un problema técnico y el tema no tiene texto de respaldo."""
    q_norm = query.strip().lower()
    if st.ultima_consulta == q_norm:
        logger.warning("buscar_protocolo: consulta duplicada en el mismo turno: '%s'", query)
        return (
            f"Ya consultaste el manual para «{query}» en este turno y los fragmentos están arriba. "
            "Formulá tu respuesta ahora."
        )
    st.ultima_consulta = q_norm

    # Si la consulta es claramente de un tema crítico, se usa la consulta
    # canónica: su resultado está precalculado y sale en 0 ms.
    tema = tema_de_consulta(query)
    consulta = tema.consulta if tema else query

    t0 = time.monotonic()
    try:
        result = await _get_retriever().search(consulta)
    except RetrieverNoListo as exc:
        result = RetrievalResult(status="error", error=str(exc))
    elapsed = int((time.monotonic() - t0) * 1000)

    usa_respaldo = result.status != "ok" and tema is not None
    st.tool_calls.append({
        "tool": "buscar_protocolo",
        "args": {"query": query, "consulta_usada": consulta},
        "origen": "respaldo" if usa_respaldo else result.modo,
        "total_latency_ms": elapsed,
        "chunks_found": len(result.fragments),
        "context_for_llm": (
            result.para_llm() if result.status == "ok" else tema.respaldo if usa_respaldo else None
        ),
        **result.to_debug_dict(),
    })

    if result.status == "ok":
        return result.para_llm()

    # Para los temas críticos nunca se contesta "no está en el manual" ni
    # "perdí el acceso": hay texto de respaldo redactado del mismo manual.
    if usa_respaldo:
        logger.warning("buscar_protocolo: %s (%s), uso respaldo de «%s»", result.status, result.error, tema.clave)
        return tema.respaldo

    if result.status == "error":
        raise ManualNoDisponible(
            "La búsqueda en el manual falló por un problema técnico. "
            f"Motivo: {result.error}"
        )
    return (
        "El manual no tiene nada relevante para esa consulta. "
        "No inventes un procedimiento: decí que no está en tu manual y seguí acompañando."
    )


# --- contexto determinístico de cada turno -----------------------------------

_MAX_TEMAS_POR_TURNO = 2

# «¿le saco el casco?», «tengo que mover el auto». Deepgram puntúa, pero por
# las dudas también se miran las formas típicas de pedir una indicación.
_PREGUNTA = re.compile(
    r"\?|\b(tengo que|debo|hago|le saco|lo saco|la saco|lo muevo|la muevo|"
    r"qué hago|que hago|cómo|como hago|está bien|esta bien)\b",
    re.IGNORECASE,
)


_ENCABEZADO = "[Contexto del sistema, no lo leas en voz alta]"


@dataclass
class Turno:
    """Lo que el sistema le agrega a un turno, separado por cuánto tiene que durar.

    Antes todo iba pegado al mensaje de la persona y quedaba en el historial:
    los avisos de turnos viejos seguían visibles aunque ya no valieran («pedí
    que se fije si respira» seguía ahí con la RCP en marcha) y el contexto
    crecía unos 2.000 caracteres por tema."""

    # Quedan en el historial: el manual ya consultado sirve en los turnos
    # siguientes y no se vuelve a mandar.
    protocolos: list[str] = field(default_factory=list)
    # Solo para la respuesta de este turno: el estado actual de la llamada y
    # los avisos (los agrega Assistant.llm_node, no quedan en el historial).
    directivas: list[str] = field(default_factory=list)
    # Momento crítico con respuesta fija (respuestas_fijas.py): se dice esto y
    # el LLM no se llama.
    respuesta_fija: str | None = None

    def texto_protocolos(self) -> str | None:
        return f"{_ENCABEZADO}\n" + "\n\n".join(self.protocolos) if self.protocolos else None

    def texto_directivas(self) -> str | None:
        return f"{_ENCABEZADO}\n" + "\n\n".join(self.directivas) if self.directivas else None

    def con_protocolos(self, texto: str) -> str:
        """El mensaje de la persona tal como queda en el historial."""
        protocolos = self.texto_protocolos()
        return f"{texto}\n\n{protocolos}" if protocolos else texto

    def completo(self) -> str | None:
        partes = [t for t in (self.texto_protocolos(), self.texto_directivas()) if t]
        return "\n\n".join(partes) or None


def _corto(texto: str, n: int = 90) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= n else texto[: n - 1] + "…"


def estado_actual(st: TriageState) -> str:
    """Lo que ya se sabe de la llamada, regenerado en cada turno.

    Reemplaza a los avisos que antes sobrevivían en el historial: el modelo
    tiene el estado de AHORA en un solo lugar."""

    def sino(valor: bool | None) -> str:
        return "no se sabe" if valor is None else ("sí" if valor else "no")

    hay_heridos = bool(st.heridos) and not st._sin_heridos()
    lineas = ["911: ya avisado, la ayuda va en camino." if st.derivado else "911: todavía no hizo falta avisar."]
    if st.que_paso:
        lineas.append(f"Qué pasó: {_corto(st.que_paso)}.")
    if st.heridos is None:
        lineas.append("Heridos: todavía no se sabe.")
    elif hay_heridos:
        lineas.append(f"Heridos: sí («{_corto(st.heridos)}»).")
    else:
        lineas.append("Heridos: no hay.")
    if st.consciente is False or st.respira is not None:
        lineas.append(f"Herido despierto: {sino(st.consciente)}. Respira: {sino(st.respira)}.")
    elif st.consciente:
        # Si está despierto respira: que no se pregunte lo obvio.
        lineas.append("Herido despierto: sí (entonces respira).")
    elif hay_heridos:
        # Sin «Respira: no se sabe»: el modelo lo tomaba como pie para
        # preguntar por la respiración antes de saber si está despierto.
        lineas.append("Herido despierto: no se sabe.")
    if st.consciente is False and st.respira is None:
        lineas.append(
            "Todavía no se sabe si respira: PROHIBIDO indicar compresiones hasta que se fije "
            "si se le mueve el pecho."
        )
    if st.atrapado:
        lineas.append("Hay alguien atrapado en el vehículo.")
    if hay_objeto_clavado(st):
        lineas.append("El herido tiene un objeto clavado.")
    if "fuego" in st.alertas:
        lineas.append("Hubo aviso de fuego, humo o combustible.")
    if st.riesgos:
        lineas.append(f"Riesgos que contó: {_corto(st.riesgos)}.")
    if rcp_en_curso(st):
        lineas.append(
            "RCP en curso, con un sonido que marca el ritmo." if st.metronomo_activo else "RCP en curso."
        )
    if st.metronomo_silenciado:
        lineas.append("El sonido del ritmo está apagado porque lo pidió la persona.")
    if st.ayuda_llego:
        lineas.append("Ya llegó la ayuda: que los profesionales se hagan cargo.")
    if st.sin_acceso:
        lineas.append("Quien llama NO puede ver ni llegar al herido: no le pidas que revise nada del herido.")
    if st.temas_inyectados:
        lineas.append(
            "Protocolos del manual ya dados en esta llamada (están más arriba): "
            + ", ".join(sorted(st.temas_inyectados)) + "."
        )
    return "Estado de la llamada:\n" + "\n".join(f"- {linea}" for linea in lineas)


async def preparar_turno(
    texto: str, st: TriageState, ultima_respuesta: str | None = None
) -> Turno:
    """Lo que el sistema le agrega al turno ANTES de llamar al LLM.

    Es el mismo para voz, chat y los scripts de prueba. Hace tres cosas sin
    depender de que el modelo llame una tool:
    1. detecta riesgo de vida y deriva al 911 (triage.procesar_turno_usuario);
    2. adjunta el protocolo del manual de los temas mencionados (precalculado:
       0 ms), así el modelo responde en UNA pasada en vez de llamar a
       buscar_protocolo y esperar otra vuelta;
    3. marca situaciones que el modelo manejaba mal (no ve al herido, pide RCP
       sin saber si respira).

    Actualiza el estado que recibe: para una respuesta anticipada se le pasa
    una copia (ver TurnosConfirmados).
    """
    st.ultima_consulta = None
    if ultima_respuesta is not None:
        st.ultima_respuesta = ultima_respuesta
    st.pregunta_pendiente = bool(_PREGUNTA.search(texto))
    directivas: list[str] = []
    protocolos: list[str] = []

    senal = procesar_turno_usuario(texto, st)
    herido_nuevo = False
    if not senal and not st.derivado and hay_herido(texto):
        # Herido sin riesgo de vida explícito: igual se deriva (y el sistema le
        # dice a la persona que la ayuda va en camino).
        if st.heridos is None:
            st.heridos = texto
        derivar_automatico(st, motivo="herido")
        herido_nuevo = True
    elif not senal and not st.derivado and confirma_heridos(texto, st.ultima_respuesta):
        # «sí, una persona» a «¿Hay alguien herido?»: no dice «herido», pero lo
        # confirma. Antes dependía de que el modelo llamara a la tool, y en
        # producción no la llamó: no derivaba y preguntaba «¿cuántos heridos?».
        st.heridos = texto
        derivar_automatico(st, motivo="heridos confirmados")
        herido_nuevo = True
    elif st.heridos is None and niega_heridos(texto):
        st.heridos = texto
    if herido_nuevo:
        directivas.append(
            f"Ya está confirmado que hay un herido («{texto}»): no vuelvas a preguntar si hay "
            "heridos ni cuántos. Lo próximo es saber si el herido está despierto y responde "
            "(salvo que la persona te haya preguntado algo: eso primero)."
        )
    categorias_nuevas = [categoria_de(s) for s in st.senales_del_turno]
    if st.respira is not False and "inconsciencia" not in categorias_nuevas and (
        esta_despierto(texto) or confirma_despierto(texto, st.ultima_respuesta)
    ):
        st.consciente = True
    for nueva in st.senales_del_turno:
        # Con el paro, el aviso de inconsciencia sobra (y dice lo contrario:
        # «todavía no se sabe si respira»).
        if categoria_de(nueva) == "inconsciencia" and "paro" in categorias_nuevas:
            continue
        directivas.append(generar_aviso_critico(nueva, st))
    if senal:
        # Lo esencial (no respira, inconsciente, atrapado) ya quedó registrado y
        # el 911 ya fue avisado: registrar_datos_escena acá solo agrega otra
        # vuelta al LLM (~1 s) en el turno donde más importa la velocidad.
        directivas.append("Esto ya quedó registrado: respondé directo, SIN llamar herramientas en este turno.")

    if not st.ayuda_llego and llego_la_ayuda(texto):
        st.ayuda_llego = True
        # En los ensayos, con un «hagan cargo» a secas, el modelo decía
        # «detené las compresiones» apenas llegaba la ambulancia: no se frena
        # hasta que alguien toma el lugar.
        aviso_ayuda = "LLEGÓ LA AYUDA: que deje que los profesionales se hagan cargo y les cuente lo que pasó."
        if st.respira is False:
            aviso_ayuda += (
                " NO le digas que deje de comprimir: que siga hasta que un profesional le pida el lugar."
            )
        directivas.append(aviso_ayuda)

    if pide_apagar(texto) and not st.metronomo_silenciado:
        st.metronomo_silenciado = True
        directivas.append(
            "La persona pidió sacar el sonido del ritmo: ya se apagó. Confirmáselo en pocas "
            "palabras y, si está comprimiendo, que siga al mismo ritmo."
        )
    elif pide_prender(texto) and st.metronomo_silenciado:
        st.metronomo_silenciado = False
        directivas.append("La persona pidió volver a escuchar el ritmo: ya vuelve a sonar. Decile que lo siga.")

    inconsciente = st.consciente is False or "inconsciencia" in st.alertas
    en_rcp = rcp_en_curso(st)
    if respira_positivo(texto) and (st.respira is False or (inconsciente and st.respira is None)):
        # También cubre «¡volvió a respirar!» en plena RCP: se dejan las
        # compresiones y pasa al protocolo del inconsciente que respira.
        if st.respira is False:
            directivas.append("VOLVIÓ A RESPIRAR: que deje de comprimir y vigile que siga respirando.")
        st.respira = True
        en_rcp = False
    elif en_rcp:
        # En las pruebas, ante «ya hice las compresiones, ¿ahora qué?», el
        # modelo pedía revisar si respiraba: eso frena la RCP.
        # El ejemplo de cierre rota: con uno fijo, el modelo terminaba cada
        # turno de RCP con la misma frase.
        cierre_rcp = _CIERRES_RCP[st.seguimientos_usados.get("rcp", 0) % len(_CIERRES_RCP)]
        st.seguimientos_usados["rcp"] = st.seguimientos_usados.get("rcp", 0) + 1
        aviso_rcp = (
            "Está haciendo RCP: que siga comprimiendo sin parar, dos veces por segundo, hasta que "
            "llegue la ayuda o la persona empiece a respirar. No le pidas que frene ni que revise nada. "
            f"No le hagas preguntas: cerrá invitándola a avisarte, por ejemplo «{cierre_rcp}»."
        )
        if st.metronomo_activo:
            aviso_rcp += " Ya suena un sonido que marca el ritmo: decile que siga ese sonido."
        directivas.append(aviso_rcp)

    temas = detectar_temas(texto)
    mencionados = list(temas)
    repetidos = [t for t in temas if t in st.temas_inyectados]
    if repetidos:
        # «le scao el casco» (con error de tipeo, sin signo de pregunta) después
        # de haber hablado del casco: es una pregunta aunque no lo parezca, y el
        # agente respondía repitiendo su pregunta anterior.
        st.pregunta_pendiente = True
        directivas.append(
            f"La persona vuelve a preguntar por {', '.join(repetidos)}: respondé eso directo, "
            "con el protocolo que ya tenés, antes que cualquier otra cosa."
        )
    if st.respira is False:
        temas.insert(0, "rcp")
    elif "rcp" in temas:
        # Pregunta por RCP sin paro confirmado: nunca adjuntar el protocolo de
        # compresiones a ciegas (si respira, comprimir le hace daño).
        temas.remove("rcp")
        directivas.append(
            "Todavía no está confirmado que el herido NO respire: antes de cualquier "
            "compresión, pedí que se fije si se le mueve el pecho."
        )
    if inconsciente and st.respira is True:
        temas.insert(0, "inconsciente_respira")
    if "hemorragia" in temas and ("objeto_clavado" in temas or "objeto_clavado" in st.temas_inyectados):
        # El protocolo de hemorragia dice «apretar directo sobre el punto que
        # sangra»: con un objeto clavado eso lo empuja. El de objeto clavado ya
        # dice cómo tapar el sangrado.
        temas.remove("hemorragia")

    if st.pregunta_pendiente:
        # En las pruebas el modelo ignoraba «¿le saco el casco?» para seguir con
        # sus preguntas de triage, aun con el protocolo adjunto.
        directivas.append(
            "La persona te hizo una pregunta: respondela en ESTE turno, con el protocolo "
            "si lo hay, antes de preguntar cualquier otra cosa."
        )

    if sin_acceso_al_herido(texto):
        st.sin_acceso = True
        directivas.append(
            "La persona NO puede ver ni llegar al herido: no le pidas que revise nada del "
            "herido. Que se quede a resguardo, fuera de la calzada, y te avise si ve algún cambio."
        )
    elif st.sin_acceso and recupera_acceso(texto):
        st.sin_acceso = False

    nuevos = [t for t in dict.fromkeys(temas) if t not in st.temas_inyectados]
    st.indicacion_pendiente = bool(nuevos)
    if nuevos:
        st.tema_activo = nuevos[0]
    for clave in nuevos[:_MAX_TEMAS_POR_TURNO]:
        tema = TEMAS[clave]
        # Primero el resumen verificado (redactado del manual para este caso) y
        # después los fragmentos como respaldo. Solo con los fragmentos, el
        # modelo tomaba el primero al pie de la letra: ante un inconsciente
        # que respira indicaba la posición lateral, cuando el manual dice que en
        # un accidente de tránsito no hay que moverlo salvo que vomite.
        fragmentos = ""
        res = None
        t0 = time.monotonic()
        try:
            res = await _get_retriever().search(tema.consulta)
            if res.status == "ok":
                fragmentos = res.para_llm()
        except RetrieverNoListo:
            logger.warning("prefetch de «%s»: índice cargando, uso solo el resumen", clave)
        except Exception:
            logger.exception("prefetch de «%s» falló, uso solo el resumen", clave)
        elapsed = int((time.monotonic() - t0) * 1000)
        st.temas_inyectados.add(clave)
        bloque = (
            f"PROTOCOLO DEL MANUAL ({clave}), ya consultado, no llames buscar_protocolo para esto.\n"
            f"Qué indicar: {tema.respaldo}"
        )
        if fragmentos:
            bloque += f"\nFragmentos del manual:\n{fragmentos}"
        protocolos.append(bloque)

        # Mismo formato que buscar_protocolo, para que el panel de debug del
        # frontend muestre fragmentos, scores y el contexto que recibió el LLM.
        debug = res.to_debug_dict() if res else {"status": "error", "error": "retriever no disponible", "fragments": []}
        st.tool_calls.append({
            "tool": "prefetch_protocolo",
            "args": {"tema": clave, "query": tema.consulta},
            "origen": debug.get("modo") if fragmentos else "respaldo",
            "total_latency_ms": elapsed,
            "chunks_found": len(debug["fragments"]),
            "context_for_llm": bloque,
            **debug,
        })

    if not directivas and not protocolos and st.heridos is None and not st.derivado:
        if pregunto_por_heridos(st.ultima_respuesta):
            # Ya lo preguntó y la respuesta no fue clara: repetir la misma
            # pregunta es un bucle (visto en la web: «¿Hay alguien lastimado?»
            # dos veces seguidas, con un motociclista accidentado).
            directivas.append(
                "Ya preguntaste si hay heridos y la respuesta no fue clara: NO repitas "
                "«¿Hay alguien lastimado?». Preguntalo de otra forma, directo por la persona "
                "que mencionó (por ejemplo «¿Está lastimado?» o «¿Te responde?»)."
            )
        else:
            # Al principio de la llamada el modelo juntaba dos preguntas («¿Qué
            # pasó y cuántas personas resultaron heridas?»). Lo que importa
            # primero es si hay heridos: una sola pregunta.
            directivas.append(
                "Todavía no se sabe si hay heridos: preguntá solo eso, con una sola pregunta "
                "corta («¿Hay alguien lastimado?»)."
            )
    cierre = _guia_de_cierre(temas, nuevos, st, en_rcp)
    if directivas or protocolos:
        # Con el protocolo completo a mano el modelo tendía a recitarlo entero
        # (50+ palabras): por teléfono eso no se retiene.
        directivas.append(
            "Respondé con UNA indicación corta (máximo dieciocho palabras) y la pregunta de "
            "cierre si corresponde; lo demás, en los turnos siguientes."
        )
    fija = respuesta_fija(texto, categorias_nuevas, mencionados, nuevos, st)
    if fija is not None:
        st.fijas_dadas[fija[0]] = st.fijas_dadas.get(fija[0], 0) + 1
        st.tool_calls.append({"tool": "respuesta_fija", "args": {"momento": fija[0]}, "respuesta": fija[1]})
    return Turno(
        protocolos=protocolos,
        directivas=[estado_actual(st), *directivas, *cierre],
        respuesta_fija=fija[1] if fija else None,
    )


async def contexto_del_turno(
    texto: str, st: TriageState, ultima_respuesta: str | None = None
) -> str | None:
    """Todo el contexto del turno en un solo texto (para tests y diagnóstico)."""
    return (await preparar_turno(texto, st, ultima_respuesta)).completo()


_CIERRES_RCP = (
    "Avisame si se mueve o empieza a respirar.",
    "Si ves que respira, decímelo enseguida.",
    "Vas bien, avisame si notás algún cambio.",
)

_ULTIMA_PREGUNTA = re.compile(r"¿[^¿?]+\?")


def _ultima_pregunta(texto: str) -> str | None:
    preguntas = _ULTIMA_PREGUNTA.findall(texto or "")
    return preguntas[-1] if preguntas else None


def _pregunta_de_seguimiento(temas: list[str], nuevos: list[str], st: TriageState) -> str | None:
    """La próxima pregunta de seguimiento sin usar del tema más relevante.

    Primero los temas recién adjuntados, después los mencionados en el turno y
    por último el último tema tratado (la persona dice «listo, ya aprieto» sin
    nombrar el tema). Cada pregunta se sugiere una sola vez por llamada: después
    el modelo cierra con sus palabras en lugar de repetir siempre la misma."""
    for clave in dict.fromkeys([*nuevos, *temas, st.tema_activo]):
        if clave is None:
            continue
        preguntas = TEMAS[clave].seguimiento
        usadas = st.seguimientos_usados.get(clave, 0)
        if usadas < len(preguntas):
            st.seguimientos_usados[clave] = usadas + 1
            return preguntas[usadas]
    return None


def _guia_de_cierre(temas: list[str], nuevos: list[str], st: TriageState, en_rcp: bool) -> list[str]:
    """Cómo cerrar el turno para que la conversación siga.

    Librado al prompt, el modelo cerraba casi todo con «¿Lo pudiste hacer?»,
    que no le sirve para decidir el paso siguiente. Acá se le sugiere la
    observación que importa para el tema en curso («¿Sigue saliendo sangre?»)
    y se le recuerda su última pregunta para que no la repita igual."""
    if st.respira is False and not st.ayuda_llego:
        if en_rcp:
            return []  # el aviso de RCP ya dice cómo cerrar sin preguntar
        return [
            "No cierres con una pregunta: que empiece a comprimir ya y te avise si se mueve "
            "o empieza a respirar."
        ]

    cierre: list[str] = []
    if not st.sin_acceso:
        if sugerida := _pregunta_de_seguimiento(temas, nuevos, st):
            cierre.append(
                f"Cerrá con UNA pregunta que te diga si la indicación funcionó, por ejemplo "
                f"«{sugerida}». No uses «¿Pudiste?» si hay algo más útil para observar."
            )
    if previa := _ultima_pregunta(st.ultima_respuesta):
        cierre.append(f"Tu última pregunta fue «{previa}»: no la repitas igual.")
    return cierre


# Mientras se calcula el contexto de una respuesta anticipada (sobre una copia
# del estado) no se loguea: los avisos del turno salen una vez, al confirmarlo.
_ANTICIPADA: contextvars.ContextVar[bool] = contextvars.ContextVar("respuesta_anticipada", default=False)


class _SinLogsAnticipados(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _ANTICIPADA.get()


for _nombre in ("triage", "emergency-agent"):
    logging.getLogger(_nombre).addFilter(_SinLogsAnticipados())


@contextlib.contextmanager
def turno_anticipado() -> Iterator[None]:
    """Mientras dura, los avisos del turno no se loguean: el contexto se está
    calculando sobre una copia del estado, para una respuesta que todavía se
    puede descartar."""
    marca = _ANTICIPADA.set(True)
    try:
        yield
    finally:
        _ANTICIPADA.reset(marca)


# --- frases que dice el sistema sin pasar por el LLM ---------------------------

FRASE_FALLA_LLM = "Perdón, se me cortó un momento. Seguí con lo que estabas haciendo y repetime lo último."

FRASE_INICIO_METRONOMO = "Comprimí al ritmo de este sonido, sin parar."
FRASE_FIN_METRONOMO = (
    "Voy a sacar el sonido. Si seguís comprimiendo, mantené el mismo ritmo. "
    "Si querés que vuelva, pedime que ponga el sonido."
)

FRASES_ALIENTO_RCP = [
    "Vas muy bien, seguí al ritmo del sonido.",
    "No pares, la ayuda ya viene en camino.",
    "Fuerte y parejo, seguí el sonido.",
]
