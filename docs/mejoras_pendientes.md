# Mejoras pendientes del asistente

Actualizado: 15/10/2026. Sale del análisis de la lógica de respuestas y de las
pruebas de ese día. Para retomarlo en otra máquina: `git pull` de `dev` y
seguir por el punto 1.

## Ya hecho (en `dev` y desplegado en LiveKit)

| Commit | Qué |
|---|---|
| `d3be908`, `f8740cf` | Negaciones: «No, no hay fuego ni humo» ya no deriva (`deteccion.py`). «Golpe en la cabeza» cuenta como herido. |
| `7a647e5` | Contexto separado: los protocolos quedan en el historial; el estado actual y los avisos van solo a la respuesta del turno (`Turno`, `estado_actual`, `TurnosConfirmados` en `agent.py`). Arreglo de la voz: la respuesta anticipada de LiveKit (preemptive) salía sin el contexto del sistema. |
| `c728d4b` | Respuestas fijas sin LLM en los momentos críticos (`respuestas_fijas.py`): RCP, «Fijate si se le mueve el pecho. ¿Respira?», casco y objeto clavado. Dos urgencias en el mismo turno se avisan las dos. «Se desmayó» cuenta como inconsciencia. |
| `c83aef5` | «Hay un accidentado en moto» deriva. «y si, el de la moto» confirma heridos. No repite «¿Hay alguien lastimado?». |

## Pendientes, en orden de prioridad

### 1. Quien llama es el herido (media)
- «Me duele mucho el cuello», «me sangra la pierna», «me golpeé la cabeza» y «no puedo mover las piernas» no derivan. Las reglas buscan «le duele», no «me duele» (`_HERIDO` en `triage.py`).
- Además el agente le habla en tercera persona. En una prueba dijo «¿Se está quedando quieto?».
- Qué hacer:
  - Detectar el herido en primera persona con `deteccion.buscar_regex`, para respetar las negaciones.
  - Agregar un campo de estado, por ejemplo `herido_es_quien_llama`, que derive al 911.
  - Sumar una línea en `estado_actual()` para que le hable de vos, no le pida revisar a otro y no le pida moverse.
  - Adaptar `respuestas_fijas.py`: «¿Me saco el casco?» → «No te saques el casco…».

### 2. Varios heridos (media)
- El estado guarda una sola víctima. Con «hay dos heridos: uno no respira y el otro sangra mucho» se mezcla todo.
- Sin rehacer `TriageState`:
  - detectar que hay más de uno y mostrarlo en el bloque de estado;
  - regla de prioridad: primero el que no respira;
  - si hay otra persona con quien llama, que esa persona apriete la herida del otro.
- Las respuestas fijas no se tienen que usar cuando hay varios heridos con urgencias distintas.

### 3. Errores del reconocimiento de voz (media)
- En pruebas por voz, «no se le mueve el pecho» llegó como «no se le **mare** el pecho» y como «no se le mueve el **techo**». En otro turno se perdió la palabra «fierro».
- Consecuencia: el modelo igual indicó compresiones, pero el sistema no registró el paro y el metrónomo no arrancó.
- Opciones:
  - sumar frases a `KEYTERMS_ES` en `prompts.py` («se le mueve el pecho», «fierro», «clavado», «convulsiona»);
  - aceptar variantes cercanas en las señales críticas;
  - confirmar en una línea cuando el turno es crítico y lo transcripto es dudoso.

### 4. Extracción en paralelo en lugar de `registrar_datos_escena` (media)
- El modelo registra cosas como «no» y la tool agrega una vuelta extra al LLM (~1 s).
- Reemplazarla por una extracción con un modelo chico (gpt-oss-20b devolviendo JSON) que corra en paralelo. Las reglas fijas quedan como red de seguridad.

### 5. Banco de casos con métricas (media)
- Llevar los escenarios a 40–50 casos: negaciones, errores de transcripción, varios heridos, quien llama como víctima y temas fuera del manual.
- Medir en cada caso:
  - violaciones de seguridad;
  - derivó cuando correspondía, y solo entonces;
  - respondió la pregunta;
  - preguntas dobles o repetidas;
  - largo de la respuesta;
  - voseo.
- Correr cada caso 3 veces por texto (Groq es barato). Por voz, 2 o 3 casos de control.

### 6. Temas fuera del manual (baja)
- Convulsiones, electrocución, RCP en niños, embarazadas, conductor descompensado y quemaduras químicas.
- Para cada uno, decidir una respuesta segura y explícita.
- Búsquedas fuera del caché: el piso de relevancia es bajo (0,10). «Convulsiones» trajo el fragmento de RCP (0,27).

### 7. Forma de la respuesta (baja)
- **Largo:** a veces pasa las 18 palabras. Medirlo y, si se pasa, quedarse con la primera indicación y el cierre.
- **Primer turno:** a veces inventa («poné el freno de mano», «esperá mi siguiente instrucción»). Se podría usar una plantilla según lo que contesten al saludo.
- **Objeto clavado:** a «Sí, sangra bastante alrededor» el modelo contestó solo con una pregunta, sin indicación.
- **Respiración:** a veces pide verificarla aunque el estado ya dice que el herido está despierto.

## Para validar con profesionales
- **Los textos de `respuestas_fijas.py`.** Están redactados a partir de los resúmenes del manual.
- **Frente-mentón.** El resumen del inconsciente que respira (`protocolos.py`) indica la maniobra frente-mentón, pero en un accidente de tránsito se lo trata como posible lesión de cuello.
- **«No respira y sale humo».** El modelo indica RCP y no menciona el fuego. ¿Hay que alejarlo primero?
- **Boca a boca.** El manual (de España) combina compresiones con boca a boca (30:2). El agente solo indica compresiones.

## Cómo trabajar

- **Tests sin red:** `python -m pytest tests/ -q` (al 15/10: 253 pasan, 9 skipped).
- **Texto con el modelo real** (solo Groq, barato):
  - `python ensayo.py --escenario <nombre>`
  - `python test_guion_expo.py` (guion de la Expo, 23/23)
- **Voz, de punta a punta:** gasta créditos de Cartesia. Hacer 1 a 3 pruebas como mucho, contra una copia local:
  - `$env:AGENT_NAME="asistente-emergencias-prueba"; python agent.py dev`
  - `python prueba_voz.py --agente asistente-emergencias-prueba "frase 1" "frase 2"`
- **Deploy:**
  - `lk agent deploy` (agente `CA_GMYJHNH2Tzwc`).
  - Antes de probar, esperar con `lk agent versions` a que la versión nueva figure como activa. La anterior sigue atendiendo un rato mientras se cierra.
- **Ramas:** el agente se trabaja en `dev` y el frontend en `main` (Vercel despliega `main`).
- **Commits:** en español, con el porqué.
- **Claves:** viven en `.env.local` (no está en git) y en los secretos de LiveKit Cloud.
