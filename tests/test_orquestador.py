"""Tests del orquestador propio, sin red: el LLM, el STT y el TTS son simulados.

Qué cubren: que una llamada atendida sin LiveKit se comporta como se espera en
lo que antes resolvía AgentSession (fin de turno, borrador anticipado,
interrupciones, tools, frases fijas) y que el paquete no depende de LiveKit.
"""

from __future__ import annotations

import asyncio
import copy
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import nucleo
import respuestas_fijas as rf
from habla import FRASE_911
from orquestador import acceso
from orquestador.llm import LLM, LlamadaTool, LLMError, Proveedor, Texto, Tools, Uso
from orquestador.sesion import Config, Sesion
from orquestador.stt import EventoSTT
from orquestador.texto import parece_completa, por_oraciones
from orquestador.tts import SAMPLE_RATE, Audio, Palabras, TTSConRespaldo, TTSError
from prompts import SALUDO

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def sin_indice(monkeypatch):
    """Sin base ni red: el manual sale de los textos de respaldo."""
    monkeypatch.setattr(nucleo, "_retriever", None)
    monkeypatch.setattr(nucleo, "_iniciar_carga", lambda: None)


# --- dobles de prueba ---------------------------------------------------------


class LLMFalso:
    """Respuestas guionadas, una por llamada. Un número en el guion es una pausa."""

    modelo = "falso"
    cadena = "falso"

    def __init__(self, *guiones: list) -> None:
        self.guiones = list(guiones)
        self.llamadas: list[list[dict]] = []

    async def generar(self, mensajes, tools=None):
        self.llamadas.append(copy.deepcopy(mensajes))
        guion = self.guiones.pop(0) if self.guiones else ["Entendido."]
        for paso in guion:
            if isinstance(paso, (int, float)):
                await asyncio.sleep(paso)
            elif isinstance(paso, str):
                yield Texto(paso)
            elif isinstance(paso, Exception):
                raise paso
            else:
                yield paso
        yield Uso(proveedor="falso", modelo="falso", ttft=0.01, completion_tokens=5)

    async def precalentar(self) -> None:
        pass

    async def cerrar(self) -> None:
        pass


class TTSFalso:
    """Cada palabra dura `s_por_palabra` segundos de audio en silencio."""

    nombre = "falso"

    def __init__(self, s_por_palabra: float = 0.02, *, con_tiempos: bool = True, falla: bool = False) -> None:
        self.s_por_palabra = s_por_palabra
        self.con_tiempos = con_tiempos
        self.falla = falla
        self.oraciones: list[str] = []

    async def sintetizar(self, oraciones):
        t = 0.0
        async for oracion in oraciones:
            self.oraciones.append(oracion)
            if self.falla:
                raise TTSError("sin voz")
            for palabra in oracion.split():
                t += self.s_por_palabra
                yield Audio(bytes(int(SAMPLE_RATE * self.s_por_palabra) * 2))
                if self.con_tiempos:
                    yield Palabras([(palabra, t)])

    async def cerrar(self) -> None:
        pass


class STTFalso:
    def __init__(self) -> None:
        self._cola: asyncio.Queue[EventoSTT | None] = asyncio.Queue()

    async def iniciar(self) -> None:
        pass

    def enviar_audio(self, pcm: bytes) -> None:
        pass

    async def eventos(self):
        while (evento := await self._cola.get()) is not None:
            yield evento

    async def cerrar(self) -> None:
        self._cola.put_nowait(None)

    def oye(self, texto: str, *, final: bool = True, fin: bool = True) -> None:
        self._cola.put_nowait(
            EventoSTT("transcripcion", texto=texto, final=final, fin_de_habla=fin, fin_audio=time.monotonic())
        )


class CanalFalso:
    def __init__(self) -> None:
        self.eventos: list[dict] = []
        self.bytes_de_audio = 0

    async def audio(self, pcm: bytes) -> None:
        self.bytes_de_audio += len(pcm)

    async def evento(self, datos: dict) -> None:
        self.eventos.append(datos)

    def de_tipo(self, tipo: str) -> list[dict]:
        return [e for e in self.eventos if e.get("type") == tipo]

    def dichos_por(self, rol: str) -> list[str]:
        return [e["texto"] for e in self.de_tipo("transcripcion") if e["rol"] == rol and e["final"]]


RAPIDO = Config(silencio_min_s=0.03, silencio_max_s=0.25, stt_endpointing_ms=0, ausencia_s=999.0)


async def hasta(condicion, segundos: float = 4.0) -> None:
    limite = time.monotonic() + segundos
    while not condicion():
        if time.monotonic() > limite:
            raise AssertionError("no se cumplió la condición a tiempo")
        await asyncio.sleep(0.01)


async def sesion_de_texto(llm: LLMFalso) -> tuple[Sesion, CanalFalso]:
    canal = CanalFalso()
    sesion = Sesion(canal, llm=llm, config=RAPIDO)
    await sesion.iniciar(saludar=False)
    sesion.saludo_de_texto()
    return sesion, canal


async def sesion_de_voz(llm: LLMFalso, tts: TTSFalso | None = None, config: Config = RAPIDO):
    canal, stt = CanalFalso(), STTFalso()
    sesion = Sesion(canal, llm=llm, stt=stt, tts=tts or TTSFalso(), config=config)
    await sesion.iniciar()
    # Como en la web: se habla recién cuando terminó el saludo.
    await hasta(lambda: sesion.ultima_respuesta() == SALUDO and sesion.estado_agente == "escuchando")
    return sesion, canal, stt


def roles(sesion: Sesion) -> list[str]:
    return [m["role"] for m in sesion.historial]


# --- turnos por texto ---------------------------------------------------------


def test_texto_los_protocolos_quedan_y_los_avisos_no():
    async def caso():
        llm = LLMFalso(["Apretá fuerte sobre la herida ", "con una tela limpia. ¿Sigue saliendo sangre?"])
        sesion, _ = await sesion_de_texto(llm)
        try:
            return await sesion.turno_de_texto("le sale mucha sangre de la pierna", debug=True), sesion, llm
        finally:
            await sesion.cerrar()

    respuesta, sesion, llm = asyncio.run(caso())
    assert respuesta["type"] == "chat_reply_debug"
    # Hay riesgo de vida: el sistema deriva y antepone el aviso, una sola vez.
    assert respuesta["message"].startswith(FRASE_911)
    assert respuesta["message"].endswith("¿Sigue saliendo sangre?")
    assert {tc["tool"] for tc in respuesta["tool_calls"]} >= {"derivar_a_emergencias", "prefetch_protocolo"}

    assert roles(sesion) == ["assistant", "user", "assistant"]
    guardado = sesion.historial[1]["content"]
    assert "PROTOCOLO DEL MANUAL (hemorragia)" in guardado
    assert "Estado de la llamada" not in guardado  # solo para la respuesta de este turno

    enviado = llm.llamadas[0]
    assert enviado[0]["role"] == "system"
    assert "Estado de la llamada" in enviado[-1]["content"]
    assert "PROTOCOLO DEL MANUAL (hemorragia)" in enviado[-1]["content"]


def test_respuesta_fija_no_llama_al_llm():
    async def caso():
        llm = LLMFalso()
        sesion, _ = await sesion_de_texto(llm)
        try:
            return await sesion.turno_de_texto("El acompañante está inconsciente, no reacciona"), llm
        finally:
            await sesion.cerrar()

    respuesta, llm = asyncio.run(caso())
    assert respuesta["message"] == f"{FRASE_911} {rf.FIJATE_SI_RESPIRA}"
    assert llm.llamadas == []


def test_tool_actualiza_el_estado_y_la_respuesta_sigue():
    async def caso():
        pedido = Tools([LlamadaTool("c1", "registrar_datos_escena", '{"que_paso": "choque de dos autos"}')])
        llm = LLMFalso([pedido], ["¿Hay alguien lastimado?"])
        sesion, _ = await sesion_de_texto(llm)
        try:
            return await sesion.turno_de_texto("Chocaron dos autos acá adelante"), sesion, llm
        finally:
            await sesion.cerrar()

    respuesta, sesion, llm = asyncio.run(caso())
    assert respuesta["message"] == "¿Hay alguien lastimado?"
    assert sesion.estado.que_paso == "choque de dos autos"
    # El pedido y el resultado de la tool quedan en el historial, en orden.
    assert roles(sesion) == ["assistant", "user", "assistant", "tool", "assistant"]
    assert sesion.historial[2]["tool_calls"][0]["function"]["name"] == "registrar_datos_escena"
    assert llm.llamadas[1][-1]["role"] == "tool"


def test_si_el_llm_falla_se_dice_la_frase_de_respaldo():
    async def caso():
        sesion, _ = await sesion_de_texto(LLMFalso([LLMError("sin servicio")]))
        try:
            return await sesion.turno_de_texto("Tuve un roce con otro auto")
        finally:
            await sesion.cerrar()

    assert asyncio.run(caso())["message"] == nucleo.FRASE_FALLA_LLM


# --- turnos por voz -----------------------------------------------------------


def test_voz_cierra_el_turno_y_responde_con_audio():
    async def caso():
        llm = LLMFalso(["Quedate donde estás. ", "¿Hay alguien lastimado?"])
        sesion, canal, stt = await sesion_de_voz(llm)
        try:
            stt.oye("Choqué con otro auto.")
            await hasta(lambda: len(canal.dichos_por("asistente")) == 2)
            await hasta(lambda: sesion.estado_agente == "escuchando")
            return sesion, canal, llm
        finally:
            await sesion.cerrar()

    sesion, canal, llm = asyncio.run(caso())
    assert canal.dichos_por("usuario") == ["Choqué con otro auto."]
    assert canal.dichos_por("asistente") == [SALUDO, "Quedate donde estás. ¿Hay alguien lastimado?"]
    assert roles(sesion) == ["assistant", "user", "assistant"]
    assert canal.bytes_de_audio > 0
    assert [e["agente"] for e in canal.de_tipo("estado")][-3:] == ["pensando", "hablando", "escuchando"]
    # La frase terminaba en punto: se usó el borrador, sin generar dos veces.
    assert len(llm.llamadas) == 1
    assert sesion.estado.last_llm_metrics["e2e_latency_ms"] is not None


def test_interrupcion_guarda_solo_lo_que_se_llego_a_decir():
    larga = "Quedate donde estás y mirá bien alrededor antes de acercarte al auto, " * 3 + "¿hay humo?"

    async def caso():
        llm = LLMFalso([larga], ["Te escucho."])
        sesion, canal, stt = await sesion_de_voz(llm, TTSFalso(s_por_palabra=0.08))
        try:
            stt.oye("Choqué con otro auto.")
            await hasta(lambda: sesion.estado_agente == "hablando" and len(sesion.historial) == 2)
            await asyncio.sleep(0.5)
            stt.oye("pará, pará, escuchame", final=False, fin=False)
            await hasta(lambda: len(canal.de_tipo("limpiar")) == 1)
            cortada = sesion.ultima_respuesta()
            stt.oye("Pará, escuchame.")
            await hasta(lambda: sesion.ultima_respuesta() == "Te escucho.")
            return cortada, canal
        finally:
            await sesion.cerrar()

    cortada, canal = asyncio.run(caso())
    palabras = cortada.split()
    assert 2 <= len(palabras) < len(larga.split()) - 5
    assert larga.startswith(cortada)
    assert [e["interrumpida"] for e in canal.de_tipo("transcripcion") if e["rol"] == "asistente"][1] is True


def test_una_palabra_suelta_no_interrumpe_al_agente():
    larga = "Quedate donde estás y mirá bien alrededor antes de acercarte al auto. ¿Hay humo?"

    async def caso():
        llm = LLMFalso([larga])
        sesion, canal, stt = await sesion_de_voz(llm, TTSFalso(s_por_palabra=0.1))
        try:
            stt.oye("Choqué con otro auto.")
            await hasta(lambda: sesion.estado_agente == "hablando" and len(sesion.historial) == 2)
            stt.oye("Sí.")
            await hasta(lambda: sesion.ultima_respuesta() == larga)
            await asyncio.sleep(0.1)
            return canal, llm
        finally:
            await sesion.cerrar()

    canal, llm = asyncio.run(caso())
    assert canal.de_tipo("limpiar") == []
    assert len(llm.llamadas) == 1  # el «Sí.» de fondo no abrió otro turno


def test_el_borrador_no_toca_el_estado_y_se_descarta_si_sigue_hablando():
    async def caso():
        llm = LLMFalso([0.05, "¿Hay alguien lastimado?"], ["Ya estás acompañado. ", "¿Está despierto?"])
        sesion, canal, stt = await sesion_de_voz(llm)
        try:
            stt.oye("Choqué con otro auto")  # sin punto: espera más antes de cerrar
            await hasta(lambda: len(llm.llamadas) == 1)
            antes = (list(sesion.estado.dichos), roles(sesion))
            stt.oye("y hay un herido.")
            await hasta(lambda: len(canal.dichos_por("asistente")) == 2)
            return antes, sesion, canal, llm
        finally:
            await sesion.cerrar()

    antes, sesion, canal, llm = asyncio.run(caso())
    # Mientras el turno no se cerró, el borrador trabajó sobre una copia.
    assert antes == ([], ["assistant"])
    assert sesion.estado.dichos == ["Choqué con otro auto y hay un herido."]
    assert sesion.estado.derivado is True
    assert len(llm.llamadas) == 2
    assert canal.dichos_por("asistente")[1] == f"{FRASE_911} Ya estás acompañado. ¿Está despierto?"


def test_si_vuelve_a_haber_voz_el_turno_no_se_cierra():
    async def caso():
        llm = LLMFalso(["¿Hay alguien lastimado?"], ["¿Hay alguien lastimado?"])
        sesion, canal, stt = await sesion_de_voz(llm)
        try:
            stt.oye("Choqué con otro auto")
            await hasta(lambda: len(llm.llamadas) == 1)
            stt._cola.put_nowait(EventoSTT("habla"))  # Deepgram detecta voz otra vez
            await asyncio.sleep(0.5)
            abierto = roles(sesion)
            stt._cola.put_nowait(EventoSTT("fin_enunciado"))  # era un ruido: pasó el silencio largo
            await hasta(lambda: len(canal.dichos_por("asistente")) == 2)
            return abierto, roles(sesion)
        finally:
            await sesion.cerrar()

    abierto, cerrado = asyncio.run(caso())
    assert abierto == ["assistant"]  # medio segundo después el turno seguía abierto
    assert cerrado == ["assistant", "user", "assistant"]


def test_las_tools_no_corren_para_un_borrador():
    async def caso():
        pedido = Tools([LlamadaTool("c1", "registrar_datos_escena", '{"que_paso": "choque"}')])
        llm = LLMFalso([pedido], ["¿Hay alguien lastimado?"])
        sesion, canal, stt = await sesion_de_voz(llm)
        try:
            stt.oye("Chocaron dos autos acá adelante")  # sin punto: el cierre tarda
            await hasta(lambda: len(llm.llamadas) == 1)
            await asyncio.sleep(0.05)
            durante = sesion.estado.que_paso
            await hasta(lambda: len(canal.dichos_por("asistente")) == 2)
            return durante, sesion
        finally:
            await sesion.cerrar()

    durante, sesion = asyncio.run(caso())
    assert durante is None
    assert sesion.estado.que_paso == "choque"


def test_sin_voz_el_texto_igual_llega_al_cliente():
    async def caso():
        canal, stt = CanalFalso(), STTFalso()
        sesion = Sesion(canal, llm=LLMFalso(), stt=stt, tts=TTSFalso(falla=True), config=RAPIDO)
        await sesion.iniciar()
        try:
            await hasta(lambda: sesion.ultima_respuesta() == SALUDO)
            return canal
        finally:
            await sesion.cerrar()

    canal = asyncio.run(caso())
    assert canal.dichos_por("asistente") == [SALUDO]
    assert canal.de_tipo("error")[0]["codigo"] == "tts"


def test_el_metronomo_arranca_con_la_rcp_y_se_apaga_si_vuelve_a_respirar():
    async def caso():
        llm = LLMFalso(["Dejá de comprimir y vigilá que siga respirando."])
        sesion, canal, stt = await sesion_de_voz(llm)
        try:
            stt.oye("Hay un hombre tirado que no respira.")
            await hasta(lambda: nucleo.FRASE_INICIO_METRONOMO in canal.dichos_por("asistente"))
            await hasta(lambda: sesion.estado_agente == "escuchando")
            prendido = sesion.estado.metronomo_activo
            stt.oye("Sí, respira.")
            await hasta(lambda: len(canal.de_tipo("metronomo")) == 2)
            return prendido, canal, llm, sesion
        finally:
            await sesion.cerrar()

    prendido, canal, llm, sesion = asyncio.run(caso())
    assert prendido is True
    # La primera indicación de RCP es fija: no pasó por el LLM.
    assert canal.dichos_por("asistente")[1] == f"{FRASE_911} {rf.RCP}"
    assert [e["activo"] for e in canal.de_tipo("metronomo")] == [True, False]
    assert canal.de_tipo("metronomo")[0]["bpm"] == 110
    assert sesion.estado.metronomo_activo is False


# --- piezas -------------------------------------------------------------------


def test_por_oraciones_junta_los_tramos_del_llm():
    async def caso(tramos):
        async def fuente():
            for tramo in tramos:
                yield tramo

        return [o async for o in por_oraciones(fuente())]

    assert asyncio.run(caso(["Apretá fuerte,", " sin soltar. ", "¿Sigue ", "saliendo sangre?"])) == [
        "Apretá fuerte, sin soltar.",
        "¿Sigue saliendo sangre?",
    ]
    # Una oración muy corta espera al resto en lugar de salir sola.
    assert asyncio.run(caso(["No. ", "No le saques el casco."])) == ["No. No le saques el casco."]
    assert parece_completa("Sí.") and parece_completa("¿Le saco el casco?")
    assert not parece_completa("Sí, pero")


def test_el_tts_de_respaldo_dice_la_frase_desde_el_principio():
    async def caso():
        roto, sano = TTSFalso(falla=True), TTSFalso()
        tts = TTSConRespaldo([roto, sano])

        async def fuente():
            yield "Primera oración."
            await asyncio.sleep(0.01)
            yield "Segunda oración."

        audio = [e async for e in tts.sintetizar(fuente()) if isinstance(e, Audio)]
        return roto, sano, tts, audio

    roto, sano, tts, audio = asyncio.run(caso())
    assert roto.oraciones == ["Primera oración."]
    assert sano.oraciones == ["Primera oración.", "Segunda oración."]
    assert len(audio) == 4
    assert tts.nombre == "falso -> falso"


def test_stt_traduce_los_mensajes_de_deepgram(caplog):
    from orquestador.stt import STTDeepgram

    async def caso():
        stt = STTDeepgram("clave", keyterms=["RCP", "casco"])
        stt._enviado_s = 12.0
        antes = time.monotonic()
        # En estos dos, «channel» es una lista y no un objeto como en Results.
        stt._procesar({"type": "SpeechStarted", "channel": [0, 1], "timestamp": 10.9})
        stt._procesar({
            "type": "Results", "is_final": True, "speech_final": True,
            "channel": {"alternatives": [{"transcript": " No respira. ", "words": [{"word": "respira", "end": 11.4}]}]},
        })
        stt._procesar({"type": "Results", "is_final": False, "speech_final": False,
                       "channel": {"alternatives": [{"transcript": ""}]}})
        stt._procesar({"type": "UtteranceEnd", "channel": [0, 1], "last_word_end": 11.4})
        eventos = [stt._eventos.get_nowait() for _ in range(stt._eventos.qsize())]
        return stt, eventos, antes

    with caplog.at_level("DEBUG", logger="orquestador.stt"):
        stt, eventos, antes = asyncio.run(caso())
    assert [e.tipo for e in eventos] == ["habla", "transcripcion", "fin_enunciado"]
    hablado = eventos[1]
    assert (hablado.texto, hablado.final, hablado.fin_de_habla) == ("No respira.", True, True)
    # Se mandaron 12,0 s y la palabra terminó en 11,4: terminó hace 0,6 s.
    assert antes - 0.65 <= hablado.fin_audio <= antes - 0.55
    assert "keyterm=RCP&keyterm=casco" in stt._url and "endpointing=25" in stt._url


def _proveedor(nombre: str, crear) -> Proveedor:
    cliente = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=crear)))
    return Proveedor(nombre=nombre, modelo=f"modelo-{nombre}", base_url="http://x", api_key="k", _cliente=cliente)


def _chunk(texto=None, tool=None, usage=None):
    delta = SimpleNamespace(content=texto, tool_calls=[tool] if tool else None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)] if (texto or tool) else [], usage=usage)


def test_el_llm_pasa_al_proveedor_siguiente_si_el_primero_falla():
    async def falla(**_):
        raise RuntimeError("429 rate limit")

    async def responde(**kwargs):
        assert kwargs["tools"] and "parallel_tool_calls" in kwargs

        async def stream():
            yield _chunk("Hola ")
            yield _chunk(tool=SimpleNamespace(
                index=0, id="c1", function=SimpleNamespace(name="buscar_protocolo", arguments='{"query": ')
            ))
            yield _chunk(tool=SimpleNamespace(
                index=0, id=None, function=SimpleNamespace(name=None, arguments='"rcp"}')
            ))
            yield _chunk(usage=SimpleNamespace(prompt_tokens=10, completion_tokens=4, total_tokens=14))

        return stream()

    async def caso():
        llm = LLM([_proveedor("a", falla), _proveedor("b", responde)])
        return [e async for e in llm.generar([{"role": "user", "content": "hola"}], [{"type": "function"}])]

    texto, tools, uso = asyncio.run(caso())
    assert texto == Texto("Hola ")
    assert tools.llamadas[0].nombre == "buscar_protocolo"
    assert tools.llamadas[0].args() == {"query": "rcp"}
    assert (uso.proveedor, uso.total_tokens) == ("b", 14)


def test_el_llm_no_cambia_de_proveedor_a_mitad_de_la_respuesta():
    async def se_corta(**_):
        async def stream():
            yield _chunk("Apoyá el talón ")
            raise RuntimeError("conexión cortada")

        return stream()

    async def no_deberia(**_):
        raise AssertionError("no hay que empezar de nuevo con otro modelo")

    async def caso():
        llm = LLM([_proveedor("a", se_corta), _proveedor("b", no_deberia)])
        return [e async for e in llm.generar([{"role": "user", "content": "hola"}])]

    with pytest.raises(LLMError):
        asyncio.run(caso())


def test_pase_de_entrada():
    pase = acceso.nuevo_pase("secreto", dura_s=60)
    assert acceso.verificar("secreto", pase)
    assert not acceso.verificar("otro", pase)
    assert not acceso.verificar("secreto", pase, ahora=time.time() + 120)  # vencido
    vence, _, firma = pase.partition(".")
    assert not acceso.verificar("secreto", f"{int(vence) + 999}.{firma}")  # fecha cambiada
    assert not acceso.verificar("secreto", None)


def test_servidor_atiende_un_chat_de_texto_por_websocket():
    from aiohttp.test_utils import TestClient, TestServer

    from orquestador.servidor import crear_app

    async def caso():
        app = crear_app(LLMFalso(["¿Hay alguien lastimado?"]), cargar_indice=False)
        async with TestClient(TestServer(app)) as cliente:
            salud = await (await cliente.get("/salud")).json()
            async with cliente.ws_connect("/ws") as ws:
                await ws.send_json({"type": "inicio", "modo": "texto"})
                recibidos = []
                while not any(m["type"] == "chat_reply" for m in recibidos):
                    recibidos.append(await ws.receive_json(timeout=3))
                await ws.send_json({"type": "chat_request", "message": "Tuve un roce con otro auto", "debug": True})
                while recibidos[-1]["type"] != "chat_reply_debug":
                    recibidos.append(await ws.receive_json(timeout=3))
                await ws.send_json({"type": "fin"})
            return salud, recibidos

    salud, recibidos = asyncio.run(caso())
    assert salud["ok"] is True and salud["llm"] == "falso"
    tipos = [m["type"] for m in recibidos]
    assert tipos[0] == "listo"
    assert next(m for m in recibidos if m["type"] == "chat_reply")["message"] == SALUDO
    assert "chat_status" in tipos
    assert recibidos[-1]["message"] == "¿Hay alguien lastimado?"
    assert recibidos[-1]["config"]["llm_model"] == "falso"


def test_servidor_rechaza_un_navegador_de_otro_origen_y_un_pase_invalido(monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer

    from orquestador.servidor import crear_app

    monkeypatch.setenv("ORQUESTADOR_SECRETO", "secreto")
    monkeypatch.delenv("ORQUESTADOR_ORIGENES", raising=False)

    async def caso():
        app = crear_app(LLMFalso(), cargar_indice=False)
        async with TestClient(TestServer(app)) as cliente:
            ajeno = await cliente.get("/ws", headers={"Origin": "https://otra-pagina.example"})
            async with cliente.ws_connect("/ws", headers={"Origin": "http://localhost:3000"}) as ws:
                await ws.send_json({"type": "inicio", "modo": "texto", "pase": "123.abc"})
                sin_pase = await ws.receive_json(timeout=3)
            async with cliente.ws_connect("/ws") as ws:
                await ws.send_json({"type": "inicio", "modo": "texto", "pase": acceso.nuevo_pase("secreto")})
                con_pase = await ws.receive_json(timeout=3)
            return ajeno.status, sin_pase, con_pase

    estado, sin_pase, con_pase = asyncio.run(caso())
    assert estado == 403
    assert (sin_pase["type"], sin_pase["codigo"]) == ("error", "pase")
    assert con_pase["type"] == "listo"


def test_el_orquestador_no_importa_livekit():
    """Con LiveKit bloqueado, el servidor y la consola se importan igual."""
    codigo = (
        "import sys\n"
        "class Bloqueo:\n"
        "    def find_spec(self, nombre, path=None, target=None):\n"
        "        if nombre == 'livekit' or nombre.startswith('livekit.'):\n"
        "            raise ImportError(nombre + ' bloqueado')\n"
        "sys.meta_path.insert(0, Bloqueo())\n"
        "import orquestador.servidor, orquestador.consola\n"
        "assert not any(m == 'livekit' or m.startswith('livekit.') for m in sys.modules)\n"
    )
    resultado = subprocess.run(
        [sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=120
    )
    assert resultado.returncode == 0, resultado.stderr
