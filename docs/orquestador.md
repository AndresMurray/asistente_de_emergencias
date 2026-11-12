# Orquestador propio: atender llamadas sin LiveKit

Agregado el 12/11/2026, en la rama `feature/orquestador-propio`. El agente de
LiveKit (`agent.py`) sigue funcionando igual; esto es un segundo camino que no
usa LiveKit en ningún punto: ni la sala, ni el worker, ni la librería.

## Qué reemplaza

| Antes (LiveKit) | Ahora (`orquestador/`) |
|---|---|
| Sala WebRTC de LiveKit Cloud | WebSocket propio (`servidor.py`) |
| `agent.py dev` / `lk agent deploy` | `python -m orquestador` |
| `AgentSession`: turnos, interrupciones, generación anticipada | `sesion.py` |
| Plugins de Deepgram, Cartesia, OpenAI/Google | `stt.py`, `tts.py`, `llm.py` (conexión directa a cada proveedor) |
| Token de sala (`/api/token`) | Pase firmado (`acceso.py`, `/api/orquestador` en el frontend) |
| `livekit-client` y sus componentes en la web | `app/lib/llamada-orquestador.ts`, `app/lib/chat.ts` |

Lo que NO cambió: el triage, los protocolos, las respuestas fijas, el prompt y
las tools. Viven en `nucleo.py` (antes estaban dentro de `agent.py`) y los usan
los dos caminos, así que una mejora del triage vale para ambos.

## Cómo correrlo

```bash
pip install -r requirements-orquestador.txt   # no instala LiveKit
python -m orquestador                         # servidor en ws://127.0.0.1:8787/ws
```

Con el servidor andando:

- **Web.** En `asistente-frontend/.env.local` agregar
  `ORQUESTADOR_URL=ws://127.0.0.1:8787/ws` y levantar la web (`npm run dev`).
  Al pie de la página dice «Orquestador propio». Sin esa variable, la web sigue
  usando LiveKit.
- **Texto en la terminal**, sin servidor ni voz (lo mismo que `ensayo.py`):
  `python -m orquestador.consola --interactivo` o `--escenario critico`.
- **Voz sin micrófono**, de punta a punta con audio sintetizado (lo mismo que
  `prueba_voz.py`): `python -m orquestador.prueba_voz`. Gasta créditos de voz.
- **Tests sin red:** `python -m pytest tests/test_orquestador.py -q`.

## Variables de entorno

Las claves son las mismas de siempre (`.env.local`); ninguna es de LiveKit.

| Variable | Para qué | Por defecto |
|---|---|---|
| `GROQ_API_KEY`, `GEMINI_API_KEY` | LLM principal y de respaldo | — |
| `LLM_MODEL`, `LLM_PROVIDER`, `LLM_FALLBACK` | Igual que en `agent.py` | `openai/gpt-oss-120b` |
| `LLM_BASE_URL`, `LLM_API_KEY` | Un LLM propio compatible con OpenAI (Ollama, vLLM); va primero | — |
| `DEEPGRAM_API_KEY` | Reconocimiento de voz (obligatoria para voz) y voz de respaldo | — |
| `CARTESIA_API_KEY`, `CARTESIA_VOICE_ID` | Voz del agente | — |
| `TTS_PROVIDER` | `cartesia` o `deepgram`: cuál va primero | `cartesia` |
| `DEEPGRAM_TTS_MODEL` | Voz de Deepgram | `aura-2-agustina-es` |
| `ORQUESTADOR_HOST`, `ORQUESTADOR_PUERTO` | Dónde escucha | `127.0.0.1`, `8787` |
| `ORQUESTADOR_ORIGENES` | Páginas web que pueden conectarse (separadas por coma, o `*`) | `http://localhost:3000` |
| `ORQUESTADOR_SECRETO` | Si está, cada conexión tiene que traer un pase firmado con este secreto | sin control |
| `ORQUESTADOR_MAX_SESIONES`, `ORQUESTADOR_MAX_MIN` | Llamadas simultáneas y duración máxima | `4`, `30` |
| `TURNO_SILENCIO_MIN_S`, `TURNO_SILENCIO_MAX_S` | Silencio que cierra el turno (frase completa / incompleta) | `0.5`, `1.2` |
| `INTERRUPCION_MIN_PALABRAS` | Palabras para callar al agente | `2` |
| `GENERACION_ANTICIPADA` | Empezar la respuesta antes de cerrar el turno | `on` |
| `LOG_DEBUG` | Loggers a detallar, p. ej. `orquestador.stt` | — |

`METRONOMO*` funcionan igual que en el agente de LiveKit.

## Cómo se decide un turno

LiveKit usa un detector de voz local y un modelo de fin de turno. El
orquestador se apoya en Deepgram:

1. Deepgram avisa que hubo silencio (`speech_final`). En ese momento se empieza
   a generar la respuesta sobre una **copia** del estado (el borrador).
2. El turno se cierra cuando pasaron 0,5 s desde la última palabra si la frase
   terminó («Sí.») y 1,2 s si no («Sí, pero»). La pista es la puntuación que
   pone Deepgram.
3. Si la persona sigue hablando, el borrador se descarta y el estado no cambió.
   Si no, se actualiza el estado real y el borrador se usa solo si se generó
   con el mismo contexto (se compara; si difiere, se genera de nuevo).
4. Las tools no corren para un borrador, porque cambian el estado.
5. Si la persona dice dos palabras o más mientras el agente habla, el agente se
   calla y en el historial queda solo lo que llegó a decir. Con Cartesia se usan
   los tiempos por palabra que devuelve; con Deepgram se estima por duración.
   La interrupción se probó por voz con Deepgram; con Cartesia, solo en los
   tests simulados.

## Medido el 12/11/2026

Por voz, con `orquestador.prueba_voz`, Groq y Cartesia, desde esta máquina:

| Turno | Cierre del turno | Primer audio del agente |
|---|---|---|
| «Sí.» | 0,66 s | 1,49 s |
| «Tuve un choque con otro auto.» | 0,51 s | 1,18 s |
| «Hay un hombre tirado que no respira.» (respuesta fija, sin LLM) | 0,52 s | 0,86 s |

Los tiempos se cuentan desde la última palabra de quien llama. Con Deepgram
como voz (`TTS_PROVIDER=deepgram`) el primer audio tarda unos 0,3 s más.

## Diferencias con LiveKit que hay que conocer

- **Transporte.** WebSocket (TCP) en lugar de WebRTC (UDP). En una red mala,
  WebRTC degrada mejor; acá un corte congela el audio hasta que se recupera.
  No hay reconexión automática: si se cae, hay que volver a llamar.
- **Eco.** La cancelación de eco la hace el navegador. Si el agente se
  interrumpe solo al usar parlantes, usar auriculares o subir
  `INTERRUPCION_MIN_PALABRAS`. La pestaña Voz no se probó con un micrófono real,
  solo con audio simulado.
- **Ruido.** No está el filtro Krisp (es de LiveKit Cloud); queda la supresión
  de ruido del navegador.
- **Fin de turno.** Sin modelo propio de fin de turno: con mucho ruido de
  fondo, Deepgram puede tardar en avisar el silencio y el cierre pasa a
  depender de `UtteranceEnd` (alrededor de 1 s).
- **Metrónomo.** El servidor avisa y el clic lo genera el cliente. Un cliente
  que no sea la web (telefonía, por ejemplo) tendría que generarlo o habría que
  mezclarlo en el servidor.
- **Escala.** Un proceso atiende todas las llamadas (tope `ORQUESTADOR_MAX_SESIONES`).
  No hay reparto entre workers.

## Pendiente

- **Publicarlo.** Hoy corre en local. Para usarlo desde Vercel hace falta
  hospedar el servidor (un contenedor con `python -m orquestador`), ponerle
  `wss://` por delante, definir `ORQUESTADOR_SECRETO` en los dos lados y
  `ORQUESTADOR_ORIGENES` con el dominio de la web.
- **Probar con micrófono y parlantes reales**, sobre todo el eco.
- **Pasar `test_guion_expo.py` y las métricas** al orquestador (hoy usan
  `AgentSession` de LiveKit).
- **Elegir la voz de respaldo.** `aura-2-agustina-es` funciona, pero no se
  revisó qué acento tiene ni cómo pronuncia el voseo.
