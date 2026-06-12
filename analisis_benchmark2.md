# Análisis en Profundidad — Benchmark LLM Local (2ª corrida, metodología mejorada)

Este documento analiza la corrida del benchmark con la metodología corregida sobre 10 modelos. Tres cambios respecto del análisis anterior (`analisis_benchmark.md`):

1. **Warmup por modelo**: el primer request a cada modelo pagaba la carga a VRAM, inflando el TTFT de la condición SIN CONTEXTO entre 5 y 12 segundos. Ahora se hace un request mínimo previo y los TTFT quedaron uniformes (173–722ms para todos los modelos en GPU), confirmando que aquellos números eran tiempo de carga, no del modelo.
2. **Mediana de 3 corridas** por condición: elimina el ruido de una corrida única en una laptop con thermal throttling.
3. **Detector de invenciones**: la columna `Inventa` cuenta frases típicas de primeros auxilios que NO están en el protocolo (911, 112, fotos, RCP, triángulos, etc.). Si aparecen en la respuesta CON CONTEXTO, el modelo está alucinando contenido.

La métrica de velocidad sigue siendo secundaria a la calidad: en un sistema de emergencias, una respuesta rápida con información incorrecta es más peligrosa que una respuesta lenta con información correcta.

---

## El protocolo de referencia

```
FASE 1 - TOMA DE CONOCIMIENTO: Registrar ubicación exacta del siniestro y cantidad de lesionados.
FASE 2 - ARRIBO AL LUGAR: Evaluar riesgos secundarios (derrames, incendios, tráfico).
FASE 3 - INTERVENCIÓN: Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.
```

Criterio de evaluación: ¿el modelo reproduce este protocolo fielmente, con sus tres fases y sus labels, sin agregar ni omitir instrucciones, y adaptándolo a la consulta concreta (2 heridos)?

**Sistema de puntuación (0–10):** fidelidad al protocolo (labels, completitud, verbatim) pesa 50%, ausencia de alucinaciones/alteraciones semánticas 30%, calidad del español y adaptación a la consulta 20%.

---

## Análisis por modelo

---

### 1. llama3.2:3b — Puntuación: 4.5/10
**CON CONTEXTO:** TTFT 231ms | 2.34s total | 75.3 tok/s

#### SIN CONTEXTO
Respuesta genérica razonable, pero repite los problemas de rol de la corrida anterior:

> *"Puedes ofrecerles agua, ropa cómoda y cualquier otro recurso que puedan necesitar."*

Dar agua a un herido es un error conceptual de primeros auxilios — contraindicado ante posible cirugía o lesión abdominal. También vuelve a pedir información forense (*"La velocidad a la que se movían los vehículos antes del accidente"*), que no es tarea del primer respondiente.

#### CON CONTEXTO
**El error estructural empeoró respecto de la corrida anterior.** El modelo tituló todo bajo FASE 1, listó las acciones de las tres fases como ítems de esa única fase, y cerró con esto:

> *"No hay indicación de qué hacer en FASE 2 - ARRIBO AL LUGAR ni en FASE 3 - INTERVENCIÓN, por lo que no puedo proporcionar una respuesta más detallada."*

Esto ya no es solo confusión de estructura — es una **alucinación sobre el propio contexto**: el modelo afirma que las fases 2 y 3 están vacías cuando están especificadas con precisión en el protocolo que tiene delante. Un operador leyendo esto concluiría que el protocolo está incompleto.

La métrica automática marca "Sigue protocolo: SI" porque las palabras clave aparecen — es un **falso positivo**. Este caso demuestra por qué la evaluación por keywords no reemplaza la lectura de las respuestas.

**Diagnóstico:** Descartado para producción. La velocidad (2º más rápido) no compensa que niegue la existencia de dos tercios del protocolo.

---

### 2. phi3.5 — Puntuación: 3.5/10
**CON CONTEXTO:** TTFT 173ms | 9.26s total | 27.9 tok/s | **Inventa: 2**

#### SIN CONTEXTO
El patrón de palabras inventadas persiste:

> *"Llame a emergenmediate: Contacte inmediatamente con los servicios médicos locales..."*

`emergenmediate` no existe en ningún idioma. Es el mismo defecto sistemático detectado en la corrida anterior (`atenzymedio`, `involucidos`, `segurthy`): el modelo genera tokens que se aproximan fonéticamente a palabras reales sin serlo.

#### CON CONTEXTO
Estructura de tres fases correcta, pero con tres problemas:

**Primero, gramática rota:**

> *"Ya has llegado a la escena del siniestro y hay dos heridos, lo cual registres como cantidad de lesionados."*

*"lo cual registres"* es agramatical en español.

**Segundo, el único modelo con invenciones detectadas automáticamente.** El detector marcó `llamar a emergencia` y `seguro`:

> *"Recuerda siempre priorizar tu seguridad también mientras ayudes, puedes llamar a emergencias locales si es necesario o pedir asistencia adicional."*

Nada de esto está en el protocolo. El prompt exige usarlo **exclusivamente**.

**Tercero, reformulación semántica:** *"salvo en caso de peligro inminente para su vida"* — el protocolo dice *"peligro inmediato"*, sin restringirlo a riesgo de vida. La reformulación estrecha la condición.

**Diagnóstico:** Confirmado el descarte de la corrida anterior. Español no confiable + único modelo que el detector de alucinaciones atrapó.

---

### 3. qwen2.5:3b — Puntuación: 8/10
**CON CONTEXTO:** TTFT 210ms | 3.68s total | 74.9 tok/s

#### SIN CONTEXTO
Mantiene la mezcla de roles ya documentada:

> *"Anota las placas de los vehículos para reportar la situación posteriormente."*
> *"asegúrate de reportar el accidente al departamento de tránsito local"*

Tareas administrativas y forenses, no de respuesta temprana. También hay un desliz gramatical: *"como si se desmayen o si sufre un ataque cardíaco"* (concordancia rota).

#### CON CONTEXTO
La estructura es la correcta y consistente con la corrida anterior: cada fase citada verbatim con su label, seguida de una expansión aplicada al caso. Las expansiones son seguras — *"confirmar que hay dos heridos"* integra el dato de la consulta correctamente; *"atención médica especializada"* agrega vocabulario que no está en el protocolo pero no altera ninguna instrucción.

El costo sigue siendo la verbosidad: ~270 tokens para contenido que gemma2:2b resuelve en ~95. Eso explica los 3.68s frente a 1.56s.

**Diagnóstico:** Sin alucinaciones, fiel, bien estructurado. Pierde solo por velocidad. Tercer puesto sólido.

---

### 4. ministral-3:3b — Puntuación: 7/10
**CON CONTEXTO:** TTFT 294ms | 6.20s total | 27.3 tok/s

#### SIN CONTEXTO
La respuesta más detallada técnicamente, pero con un error de primeros auxilios concreto:

> *"Dale agua (si no hay riesgo de asfixia por vómitos)."*

Dar agua a un herido de accidente vial está contraindicado. Además instruye RCP y posición lateral de seguridad — correcto en sí, pero asume capacitación que el protocolo no presupone.

#### CON CONTEXTO
Limpia y bien estructurada, pero esta corrida introdujo una **contradicción interna sutil** que en la corrida anterior no estaba:

> *"Estabiliza a los heridos graves **antes de moverlos**."*
> *"No muevas a los lesionados salvo que haya un peligro inmediato."*

La primera frase presupone que los heridos VAN a ser movidos ("antes de moverlos"); la segunda dice que no se los mueve salvo peligro. El protocolo solo dice lo segundo. No es una alucinación grave, pero es exactamente el tipo de deriva semántica que en protocolos más largos puede escalar.

**Diagnóstico:** Calidad alta, pero 6.2s totales (4x gemma2:2b) y ahora con una incoherencia interna que antes no tenía. Sigue descartado por velocidad.

---

### 5. llama3:8b — Puntuación: 5/10
**CON CONTEXTO:** TTFT 310ms | 14.17s total | 11.5 tok/s

#### SIN CONTEXTO
Instrucción directamente peligrosa:

> *"Evacuar a las víctimas: Si es posible, intenta evacuar a las víctimas del lugar del accidente sin moverlas demasiado..."*

"Evacuar sin mover demasiado" es contradictorio en sí mismo, y evacuar heridos sin inmovilización contradice toda práctica de manejo de trauma.

#### CON CONTEXTO
A diferencia de la corrida anterior (donde omitió las fases 2 y 3 por completo), esta vez cubrió las tres fases. Pero:

**Omitió "Estabilizar heridos graves"** — de FASE 3 solo reprodujo *"debes brindar auxilio médico primario. No moverás a los lesionados salvo peligro inmediato"*. La instrucción de estabilización desapareció.

**Inventó una instrucción de cierre:**

> *"No haces nada más hasta que no se complete esta tercera fase."*

Esa regla no existe en el protocolo. Es inofensiva en este caso, pero es invención.

La inconsistencia entre corridas (antes omitió 2 fases, ahora omite una instrucción) confirma el diagnóstico anterior: **no podés confiar en que responda completo**. Y a 11.5 tok/s con CPU offloading (5GB no entran en 4GB de VRAM), 14 segundos de respuesta es inviable.

**Diagnóstico:** Descartado por inconsistencia + hardware.

---

### 6. gemma2:2b — Puntuación: 10/10
**CON CONTEXTO:** TTFT 274ms | 1.56s total | 82.7 tok/s

#### SIN CONTEXTO
Español impecable, bien organizado. Persisten dos errores conceptuales menores de primeros auxilios:

> *"Limpia cualquier herida superficial con agua y jabón."*
> *"Toma fotos o videos de la escena del accidente..."*

Limpiar heridas no es prioridad del primer respondiente, y la documentación fotográfica es tarea forense. Errores de rol esperables en cold start sin grounding — irrelevantes para el caso de uso RAG.

#### CON CONTEXTO
```
1. **FASE 1 - TOMA DE CONOCIMIENTO:** Registrar la ubicación exacta del siniestro y la cantidad de lesionados (2).
2. **FASE 2 - ARRIBO AL LUGAR:** Evaluar riesgos secundarios (derrames, incendios, tráfico) antes de intervenir.
3. **FASE 3 - INTERVENCIÓN:** Brindar auxilio médico primario a los heridos. Estabilizar a los heridos graves y no moverlos salvo peligro inmediato.
```

Reproduce el resultado de la corrida anterior con consistencia total:

- **Fidelidad verbatim** de las tres fases, con labels y numeración.
- **El `(2)`** integra el dato de la consulta sin inventar nada.
- **La única adición es `"antes de intervenir"`** en FASE 2 — y es una adición correcta: explicita el orden de ejecución que el protocolo implica. Es el tipo de clarificación que ayuda al operador en vez de confundirlo.
- 1.56s de mediana sobre 3 corridas — el más rápido del grupo, otra vez.

**Diagnóstico:** Confirmado como modelo de producción con metodología sólida. Mismo resultado en ambas corridas del benchmark: la consistencia es en sí misma un dato de calidad.

---

### 7. gemma3:4b — Puntuación: 6/10
**CON CONTEXTO:** TTFT 722ms | 4.61s total | 21.0 tok/s

#### SIN CONTEXTO
Detallada y correcta en general, sin los regionalismos de la corrida anterior, aunque redundante (*"Encender las luces de emergencia"* y *"Activar la luz intermitente"* son la misma acción listada dos veces). Se truncó en los 512 tokens.

#### CON CONTEXTO
```
FASE 1 - Toma de conocimiento: Registrar ubicación exacta del siniestro y cantidad de lesionados.
FASE 2 - arribo al lugar: Evaluar riesgos secundarios (derrames, incendios, tráfico).
FASE 3 - Intervención: Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.
```

Mejoró respecto de la corrida anterior: esta vez **conservó los labels de fase** (antes los había eliminado). Pero el problema de fondo quedó expuesto con claridad: la respuesta es una **fotocopia del protocolo sin adaptación alguna**. No menciona los 2 heridos, no responde "¿Qué hago?", no integra ningún dato de la consulta. Hasta el casing es inconsistente (*"FASE 2 - arribo al lugar"* en minúsculas, copiando irregularmente).

Fidelidad sin utilidad: el operador recibe de vuelta el documento que el RAG ya tenía, no una respuesta. Sumado al TTFT más alto del grupo en GPU (722ms) y 21 tok/s.

**Diagnóstico:** Regurgita en vez de responder. Sigue por debajo de su predecesor gemma2:2b en velocidad y en utilidad de respuesta.

---

### 8. qwen2.5:1.5b — Puntuación: 4/10
**CON CONTEXTO:** TTFT 198ms | 4.98s total | 59.0 tok/s

#### SIN CONTEXTO
Vuelve a aconsejar el traslado por cuenta propia:

> *"Lleva a los heridos al hospital: Si es posible, lleva a los heridos al hospital más cercano para recibir la atención médica adecuada."*

Transportar heridos sin inmovilización es la instrucción más peligrosa que puede dar un sistema de emergencias. También inventa reglas inexistentes: *"Recuerda que el 911 no se usa para problemas de salud general o menores accidentes viales"*.

#### CON CONTEXTO
El detector no marcó invenciones esta vez (mejora respecto de la corrida anterior, donde inventó *"cerrar la avenida"* y el traslado en vehículo). Pero la respuesta tiene dos problemas:

**Primero, doble pasada redundante:** reproduce el protocolo completo, y después lo vuelve a reproducir "aplicado al caso". El contenido útil está duplicado — 4.98s para decir dos veces lo mismo.

**Segundo, inferencia inventada y debilitamiento semántico en la conclusión:**

> *"Estabilizar **los dos heridos graves**."*
> *"asegurarse de que no se muevan **hasta que sea necesario**"*

La consulta nunca dijo que los dos heridos fueran graves — el modelo lo asumió. Y *"hasta que sea necesario"* debilita *"salvo peligro inmediato"*: "necesario" es subjetivo, "peligro inmediato" es una condición concreta. Es la misma clase de deriva semántica que descalificó a phi3.5.

**Diagnóstico:** Mejoró (sin alucinaciones flagrantes esta corrida) pero la doble pasada es justamente donde introduce las distorsiones. Por debajo de 2B los modelos no sostienen la fidelidad. Descartado.

---

### 9. phi4-mini — Puntuación: 9/10
**CON CONTEXTO:** TTFT 272ms | 3.25s total | 39.4 tok/s

#### SIN CONTEXTO
Apareció un error léxico que en la corrida anterior no estaba:

> *"se le puede pedir que **apueste** al herido con cuidado hasta la llegada del personal médico"*

"Apueste" no tiene sentido en este contexto (¿"apoye"? ¿"asista"?). También hay una instrucción cuestionable: *"Evita la escena: No intente acercarse al lugar de los heridos"* — decirle al respondiente que no se acerque contradice el propósito de asistir.

#### CON CONTEXTO
```
FASE 1 - TOMA DE CONOCIMIENTO:
- Registrar ubicación exacta del siniestro.
- Contar y registrar cantidad de lesionados (en este caso, 2).

FASE 2 - ARRIBO AL LUGAR:
- Evaluar riesgos secundarios como derrames, incendios o tráfico.

FASE 3 - INTERVENCIÓN:
- Brindar auxilio médico primario a los heridos.
- Estabilizar heridos graves sin moverlos salvo peligro inmediato.
```

Idéntica en calidad a la corrida anterior: tres fases con labels, sin alucinaciones, sin invenciones, adaptación correcta (*"en este caso, 2"*), reformulaciones que no alteran significado (*"sin moverlos salvo peligro inmediato"*). La consistencia entre corridas lo confirma como el competidor real de gemma2:2b.

El único costo: 3.25s — 2.1x más lento que el líder, a 39 tok/s.

**Diagnóstico:** Plan B confirmado. Si gemma2:2b falla con protocolos largos del RAG real, este es el reemplazo.

---

### 10. qwen3:8b — Puntuación: 2/10
**CON CONTEXTO:** TTFT **41,406ms** | 59.22s total | 8.7 tok/s

#### SIN CONTEXTO
**Respuesta vacía en las 3 corridas.** El modelo tiene razonamiento (thinking) obligatorio: consume los 512 tokens de `num_predict` razonando internamente y nunca emite un token visible. TTFT de 0ms en la tabla significa "nunca llegó el primer token".

#### CON CONTEXTO
Cuando logra responder, la calidad del texto es buena — pero todo lo demás falla:

**Primero, omitió FASE 1 por completo.** La respuesta arranca directamente en *"**FASE 2 - ARRIBO AL LUGAR**"*. Registrar ubicación y cantidad de lesionados desapareció del protocolo.

**Segundo, inventa instrucciones:**

> *"Proteger la zona: Si hay riesgos, actúe para minimizarlos (ej.: apagar motores, alejar vehículos, **usar chalecos reflectantes**)."*

Ni apagar motores, ni alejar vehículos, ni chalecos reflectantes están en el protocolo.

**Tercero, se truncó a mitad de palabra** (*"controlar hemorragias, inmovil"*) — el thinking le consumió tanto presupuesto de tokens que no le alcanzó para cerrar la respuesta.

**Cuarto, 41 segundos de TTFT.** El modelo razona entre 36 y 50 segundos (CPU offloading: 5GB en una GPU de 4GB) antes de emitir la primera palabra. En una emergencia, el operador habría actuado sin el sistema mucho antes.

**Diagnóstico:** Inviable en todas las dimensiones que importan: latencia, completitud, fidelidad y hardware. Descartado definitivamente, junto con qwen3:4b (que en pruebas separadas consumió hasta 2048 tokens enteros razonando sin producir respuesta alguna).

---

## Tabla comparativa de calidad CON CONTEXTO

| Modelo | Puntuación | Labels de fase | Fidelidad | Alucinaciones / alteraciones | Español | Adaptación al caso |
|--------|-----------|----------------|-----------|------------------------------|---------|--------------------|
| gemma2:2b | **10** | ✅ | ✅ verbatim | ✅ ninguna | ✅ | ✅ integra "(2)" |
| phi4-mini | **9** | ✅ | ✅ verbatim + adiciones seguras | ✅ ninguna | ✅ | ✅ "en este caso, 2" |
| qwen2.5:3b | **8** | ✅ | ✅ verbatim + expansión | ✅ ninguna | ✅ | ✅ |
| ministral-3:3b | **7** | ✅ | ✅ verbatim | ⚠️ "antes de moverlos" contradice el protocolo | ✅ | ✅ |
| gemma3:4b | **6** | ✅ (casing inconsistente) | ✅ verbatim | ✅ ninguna | ✅ | ❌ copia sin adaptar |
| llama3:8b | **5** | ✅ | ⚠️ omite "Estabilizar heridos graves" | ⚠️ inventa regla de cierre | ✅ | ✅ |
| llama3.2:3b | **4.5** | ❌ todo bajo FASE 1 | ❌ niega que FASE 2 y 3 existan | ❌ alucina sobre el contexto | ✅ | ⚠️ |
| qwen2.5:1.5b | **4** | ✅ | ⚠️ doble pasada con deriva | ⚠️ asume "graves", debilita "peligro inmediato" | ✅ | ⚠️ |
| phi3.5 | **3.5** | ✅ | ⚠️ altera condiciones | ❌ 2 invenciones detectadas | ❌ "emergenmediate", gramática rota | ✅ |
| qwen3:8b | **2** | ⚠️ | ❌ omite FASE 1, se trunca | ❌ chalecos, apagar motores | ✅ | ✅ |

---

## Ranking por velocidad (CON CONTEXTO, medianas de 3 corridas)

### Por tiempo total de respuesta — la métrica que vive el operador

| # | Modelo | Total | tok/s | TTFT |
|---|--------|-------|-------|------|
| 1 | gemma2:2b | **1.56s** | 82.7 | 274ms |
| 2 | llama3.2:3b | 2.34s | 75.3 | 231ms |
| 3 | phi4-mini | 3.25s | 39.4 | 272ms |
| 4 | qwen2.5:3b | 3.68s | 74.9 | 210ms |
| 5 | gemma3:4b | 4.61s | 21.0 | 722ms |
| 6 | qwen2.5:1.5b | 4.98s | 59.0 | 198ms |
| 7 | ministral-3:3b | 6.20s | 27.3 | 294ms |
| 8 | phi3.5 | 9.26s | 27.9 | 173ms |
| 9 | llama3:8b | 14.17s | 11.5 | 310ms |
| 10 | qwen3:8b | 59.22s | 8.7 | 41,406ms |

### Por velocidad de generación (tok/s)

| # | Modelo | tok/s | Nota |
|---|--------|-------|------|
| 1 | gemma2:2b | 82.7 | 100% en GPU |
| 2 | llama3.2:3b | 75.3 | 100% en GPU |
| 3 | qwen2.5:3b | 74.9 | 100% en GPU |
| 4 | qwen2.5:1.5b | 59.0 | 100% en GPU |
| 5 | phi4-mini | 39.4 | 100% en GPU |
| 6 | phi3.5 | 27.9 | parcialmente en GPU |
| 7 | ministral-3:3b | 27.3 | parcialmente en GPU |
| 8 | gemma3:4b | 21.0 | parcialmente en GPU |
| 9 | llama3:8b | 11.5 | CPU offloading (4.7GB > 4GB VRAM) |
| 10 | qwen3:8b | 8.7 | CPU offloading (5GB > 4GB VRAM) |

Dos observaciones sobre estas tablas:

- **El tiempo total importa más que el tok/s aislado.** qwen2.5:1.5b genera a 59 tok/s pero tarda 5s porque escribe el doble de lo necesario. La economía de tokens de gemma2:2b (~95 tokens útiles) es parte de su velocidad real.
- **El corte de los ~30 tok/s coincide con el límite de los 4GB de VRAM.** Todo modelo que no entra completo en la GPU cae a la mitad o menos de velocidad. Es el techo físico de este hardware y explica por qué los 8B no son opción, independientemente de su calidad.

---

## Ranking general (calidad + velocidad, ponderado para el caso de uso RAG)

| # | Modelo | Puntuación calidad | Total CON CONTEXTO | Veredicto |
|---|--------|--------------------|--------------------|-----------|
| 🥇 1 | **gemma2:2b** | 10/10 | 1.56s | **Producción.** Único modelo perfecto en calidad Y el más rápido. |
| 🥈 2 | **phi4-mini** | 9/10 | 3.25s | **Plan B.** Calidad equivalente, 2.1x más lento. |
| 🥉 3 | **qwen2.5:3b** | 8/10 | 3.68s | Fiel y seguro, descartado solo por verbosidad/velocidad. |
| 4 | ministral-3:3b | 7/10 | 6.20s | Buena calidad con deriva semántica menor; demasiado lento. |
| 5 | gemma3:4b | 6/10 | 4.61s | Fiel pero regurgita sin adaptar; más lento que su predecesor. |
| 6 | llama3:8b | 5/10 | 14.17s | Inconsistente entre corridas + CPU offloading. |
| 7 | llama3.2:3b | 4.5/10 | 2.34s | Rápido pero alucina sobre la estructura del contexto. |
| 8 | qwen2.5:1.5b | 4/10 | 4.98s | Deriva semántica en instrucciones críticas. |
| 9 | phi3.5 | 3.5/10 | 9.26s | Palabras inventadas + únicas invenciones detectadas. |
| 10 | qwen3:8b | 2/10 | 59.22s | TTFT de 41s, omite fases, inviable en este hardware. |

---

## Conclusión

La segunda corrida, con metodología corregida, **confirma y refuerza** la decisión de la primera:

### gemma2:2b revalidó el título con datos más sólidos

Con warmup (sin el sesgo de carga a VRAM) y mediana de 3 corridas, gemma2:2b repitió exactamente el mismo comportamiento: fidelidad verbatim, labels correctos, integración del dato contextual `(2)`, cero alucinaciones, y el menor tiempo total del grupo (1.56s). **La consistencia entre corridas independientes es en sí misma evidencia de calidad** — no fue suerte de una corrida.

### El detector de invenciones funcionó

phi3.5 fue el único modelo atrapado automáticamente (2 invenciones), validando su descarte. Pero el detector también mostró sus límites: las invenciones de qwen3:8b ("chalecos reflectantes", "apagar motores") y la inferencia de qwen2.5:1.5b ("los dos heridos graves") pasaron sin marcar. **La revisión manual de respuestas sigue siendo obligatoria** — las métricas automáticas filtran, no deciden.

### El falso positivo de llama3.2:3b es la lección del benchmark

"Sigue protocolo: SI" con una respuesta que niega la existencia de las fases 2 y 3. Si la selección de modelo se hubiera hecho solo con la tabla resumen, llama3.2:3b habría parecido un candidato viable (2.34s, 75 tok/s, "SI"). Leyendo la respuesta, es de los peores del grupo.

### Los 8B quedaron formalmente cerrados

llama3:8b y qwen3:8b confirmaron en 3 corridas con mediana lo que ya se sabía: con 4GB de VRAM, los modelos que no entran completos en GPU (≥4.5GB en Q4) caen a 8–11 tok/s y 14–59s de respuesta. No hay configuración que arregle un límite físico. La familia qwen3 suma además el problema del razonamiento obligatorio, que consume el presupuesto de tokens pensando (qwen3:4b llegó a gastar 2048 tokens sin emitir una palabra visible).

### Próximo paso

El test pendiente que decidirá si phi4-mini alguna vez reemplaza a gemma2:2b: repetir este benchmark con **protocolos largos reales** (2–3 páginas de contexto recuperado por el retrieval). Ahí es donde un modelo de 2B puede empezar a perder fidelidad y uno de 3.8B justificar sus 1.7 segundos extra.

El modelo seleccionado para producción sigue siendo **`gemma2:2b`**.
