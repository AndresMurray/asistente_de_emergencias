# Guion de Demostración para la Expo de la Facultad
## Asistente de Voz en Tiempo Real para Emergencias Viales (Tesina de Grado)

Este documento contiene la preparación completa, el guion paso a paso y las respuestas técnicas para presentar el proyecto ante el **Decano de la Facultad**, directores de carrera, profesores evaluadores y visitantes en el stand de la expo.

---

## 1. El "Elevator Pitch" (30 a 45 segundos)
*Decíselo al Decano apenas se acerque al stand, antes de iniciar la llamada o prueba de voz:*

> "Buenas tardes, Decano. Este proyecto es un **Asistente de Voz en Tiempo Real para Primeros Auxilios en Emergencias Viales**.
>
> En un siniestro vial, los primeros diez minutos —la llamada 'Hora de Oro'— definen la supervivencia de los heridos, y las personas en pánico a menudo no saben cómo actuar o cometen maniobras peligrosas. 
>
> Desarrollamos un sistema conversacional de bajísima latencia vía WebRTC que:
> 1. Asume **geolocalización automática** de la llamada.
> 2. Implementa un **triage determinístico de riesgo de vida** (que no depende únicamente de la creatividad del LLM).
> 3. Aplica **RAG con base de datos vectorial (Supabase pgvector)** sobre protocolos oficiales de primeros auxilios.
> 4. Coordina el despacho con el **911** mientras guía al testigo paso a paso con acento rioplatense y tono calmo.
>
> Les muestro una simulación en vivo de cómo responde ante un choque crítico."

---

## 2. Escenario Principal: "El Camino Crítico (Inconsciente y Paro)"
Este es el **escenario principal de demostración** porque exhibe el mayor rigor ético e ingenieril del sistema: **la prohibición de realizar RCP a ciegas sin verificar la respiración** (hacer RCP a alguien que respira es dañino y fractura costillas).

### Diálogo Turno a Turno

#### Inicio
* El sistema conecta a la sala y el asistente emite el saludo inicial de inmediato (pre-sintetizado sin delay de LLM):
> **Asistente:** *"Emergencias viales, te escucho. Estoy con vos. ¿Estás en un lugar seguro, fuera de la calzada?"*

---

#### Turno 1: Notificación del hecho e inconsciencia
* **Vos decís con voz clara:**
  > *"Hola, choqué contra otro auto en la banquina. Mi acompañante está inconsciente y no me responde."*
* **Qué hace el sistema por detrás (para explicarle al Decano):**
  * `triage.py` detecta la señal crítica `inconsciente`.
  * La máquina de estados frena las preguntas rutinarias de datos.
  * **Regla estricta:** NO ordena RCP directamente; fuerza la verificación de respiración y avisa la geolocalización.
* **Respuesta esperada del Asistente:**
  > *"Ya te geolocalizamos y la ayuda va en camino. Fijate si se le mueve el pecho o si sentís aire. ¿Respira?"*

---

#### Turno 2: Confirmación de paro respiratorio
* **Vos decís:**
  > *"No, no se le mueve el pecho y no está respirando."*
* **Qué hace el sistema por detrás:**
  * El asistente dispara la tool `buscar_protocolo("herido inconsciente que no respira reanimación cardiopulmonar")` contra Supabase pgvector.
  * Ejecuta `derivar_a_emergencias`, despachando el aviso al 911.
* **Respuesta esperada del Asistente:**
  > *"Colocá tus manos en el centro de su pecho y hacé compresiones fuertes y rápidas. ¿Lo pudiste hacer?"*

---

#### Turno 3: Acompañamiento activo y ritmo
* **Vos decís:**
  > *"Sí, ya empecé a comprimir, ¿a qué ritmo sigo?"*
* **Qué hace el sistema:**
  * Proporciona la cadencia recomendada (100-120 compresiones por minuto) sin abrumar.
* **Respuesta esperada del Asistente:**
  > *"Mantené un ritmo continuo, dos compresiones por segundo, sin parar. El nueve once ya va en camino."*

---

## 3. Escenarios Secundarios (Para que pruebe el Decano)

Si el Decano quiere tomar el micrófono o hacer preguntas, podés sugerirle estos dos casos emblemáticos:

### Caso A: El motociclista y el casco ("La pregunta trampa")
* **Consigna para el Decano:** *"Decile al asistente que viste a un motociclista tirado y preguntale si tenés que sacarle el casco."*
* **Frase del Decano:**
  > *"Hola, estoy a salvo en la banquina. Recién se cayó un chico en moto al asfalto, ¿le tengo que sacar el casco?"*
* **Respuesta esperada del Asistente:**
  > *"No, no le saques el casco bajo ningún concepto. Puede tener lesiones en la columna cervical. Mantenelo quieto. Ya dimos aviso al nueve once."*
* **Punto a destacar al Decano:** El RAG consulta el manual de siniestros viales y no se deja llevar por el sentido común popular de quitar el casco, protegiendo las vértebras del paciente.

### Caso B: Hemorragia severa
* **Consigna:** *"Avisale que hay alguien perdiendo mucha sangre en una pierna."*
* **Frase:**
  > *"Hay un choque y una persona se está desangrando de la pierna, sale mucha sangre."*
* **Respuesta esperada del Asistente:**
  > *"Hacé presión directa y firme sobre la herida con un paño limpio. No aflojes la presión. El nueve once va en camino."*

---

## 4. Preguntas Técnicas que puede hacer el Decano / Profesores

### 1. "¿Por qué un asistente de voz y no una app con botones o un chatbot de WhatsApp?"
> *"En un choque en ruta, la persona está en estado de shock, con las manos ocupadas, posiblemente herida o en la oscuridad de una banquina. No tiene tiempo ni serenidad para leer menús o escribir. La voz en tiempo real con manos libres es la única interfaz viable en ese momento."*

### 2. "¿Por qué no conectar la llamada directo a ChatGPT / GPT-4o?"
> *"Un LLM generalista sin guardarraíles alucina, responde con párrafos largos imposibles de escuchar en una urgencia, usa números extranjeros (como el 112) y puede indicar maniobras peligrosas. Nosotros construimos un pipeline especializado:*
> * *Triage determinístico:* reglas en código Python que mandan sobre el modelo si hay riesgo de vida.
> * *RAG sobre protocolos oficiales:* las indicaciones salen de manuales auditados guardados en Supabase.
> * *Optimización de latencia WebRTC:* Deepgram para STT, Cartesia para TTS en rioplatense, logrando respuestas en menos de 1 segundo."*

### 3. "¿Cómo manejan la geolocalización?"
> *"Asumimos geolocalización automática por infraestructura de telecomunicaciones / red celular. El agente tiene prohibido perder valiosos segundos preguntando '¿dónde estás?' o '¿en qué calle?'. Apenas atiende, le da la tranquilidad al usuario de que ya fue ubicado."*

### 4. "¿Cómo evaluaron que el sistema realmente funciona bien?"
> *"No lo evaluamos a ojo: armamos una suite de métricas automatizadas:*
> * **MRR (Mean Reciprocal Rank)** y **Recall@5** para medir la precisión de la recuperación RAG.
> * **Answer Relevancy** para medir la fidelidad de la respuesta al protocolo.
> * **Critical Information Coverage** para verificar que los datos vitales siempre se transmitan."*

---

## 5. Checklist Operativo para el Stand de la Expo

1. **Audio en vivo (Crítico):**
   * El salón de la expo va a tener mucho ruido de fondo.
   * **Usar headset o corbatero direccional:** no usar el micrófono integrado de la laptop, ya que captará los ruidos de los stands vecinos.
2. **Conectividad:**
   * La red Wi-Fi de la facultad suele colapsar durante las exposiciones.
   * Tené el teléfono configurado con zona Wi-Fi (4G/5G) vinculado a la laptop listo para switchar en 5 segundos si cae la red.
3. **Plan B (Demostración por texto si el salón es un caos acústico):**
   * Si hay parlantes o música al lado del stand, podés ejecutar en terminal:
     ```bash
     python ensayo.py --escenario critico
     ```
     o
     ```bash
     python ensayo.py --interactivo
     ```
     Esto corre exactamente el mismo agente, prompt, RAG y máquina de estados, pero por consola de texto, permitiendo mostrar la lógica sin problemas de audio.

---

## 6. Comandos para Practicar Antes de la Expo

* **Para ensayar los diálogos por consola (rápido y sin costo de audio):**
  ```bash
  python ensayo.py --escenario critico
  python ensayo.py --interactivo
  ```

* **Para correr el agente con voz y WebRTC en tu máquina:**
  ```bash
  python agent.py dev
  ```

* **Para mostrar los resultados de las métricas en la presentación:**
  ```bash
  python metricas/mrr.py
  python metricas/recall_at_5.py
  ```
