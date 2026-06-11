# Análisis en Profundidad — Benchmark LLM Local

Este documento analiza la calidad de las respuestas de los 9 modelos evaluados para el RAG de emergencias viales. Se analizan tanto las respuestas **SIN CONTEXTO** (comportamiento base del modelo) como las respuestas **CON CONTEXTO** (comportamiento dentro del pipeline RAG). La métrica de velocidad es secundaria a la calidad: en un sistema de emergencias, una respuesta rápida con información incorrecta es más peligrosa que una respuesta lenta con información correcta.

---

## El protocolo de referencia

El prompt CON CONTEXTO inyecta este protocolo y exige usarlo **exclusivamente**:

```
FASE 1 - TOMA DE CONOCIMIENTO: Registrar ubicación exacta del siniestro y cantidad de lesionados.
FASE 2 - ARRIBO AL LUGAR: Evaluar riesgos secundarios (derrames, incendios, tráfico).
FASE 3 - INTERVENCIÓN: Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.
```

El criterio de evaluación es simple: ¿el modelo reproduce este protocolo fielmente, con sus tres fases y sus labels, sin agregar ni omitir instrucciones?

---

## Análisis por modelo

---

### 1. llama3.2:3b
**Velocidad CON CONTEXTO:** 1.7s | 73.7 tok/s

#### SIN CONTEXTO
La respuesta es genérica pero razonable. Cubre llamar a emergencias, no mover heridos, reunir información. El problema es que va más allá de un protocolo operativo:

> *"Reunir información: La velocidad a la que se movían los vehículos antes del accidente"*

Esto es información forense, no de respuesta temprana. Sin contexto el modelo mezcla roles — responde como si el operador fuera policía, médico y testigo al mismo tiempo. Esperado para un cold start sin grounding.

#### CON CONTEXTO
```
Según el protocolo, en esta situación, debes seguir las instrucciones de FASE 1 - TOMA DE CONOCIMIENTO:

1. Registrar ubicación exacta del siniestro y cantidad de lesionados.
2. Evaluar riesgos secundarios (derrames, incendios, tráfico).
3. Brindar auxilio médico primario.

No mover a lesionados salvo peligro inmediato.
```

**El error es estructural y peligroso.** El modelo tituló todo bajo `FASE 1 - TOMA DE CONOCIMIENTO` y luego listó las acciones de las tres fases como ítems numerados dentro de ella. Un operador que lea esto interpretará que evaluar riesgos secundarios y brindar auxilio médico son parte de la toma de conocimiento — no fases separadas con su propio momento de ejecución.

Además omitió `Estabilizar heridos graves` de FASE 3. El protocolo dice *"Brindar auxilio médico primario. Estabilizar heridos graves."* El modelo solo incluyó la primera instrucción, dejando caer la segunda.

**Diagnóstico:** El modelo siguió el contexto pero no entendió la estructura de fases. Tratable con prompt engineering que fuerce la separación explícita de cada fase.

---

### 2. phi3.5
**Velocidad CON CONTEXTO:** 11.1s | 25.8 tok/s

#### SIN CONTEXTO
Mezcla de instrucciones correctas con errores de español graves desde la primera oración:

> *"minimizar daños adicionales y asegurar una atenzymedio adecuada"*

`atenzymedio` es una palabra inventada. No existe en español. En la segunda corrida apareció `"involucidos"` y `"segurthy"`. Este patrón es consistente — el modelo genera tokens que fonéticamente se aproximan a palabras reales pero no lo son.

#### CON CONTEXTO
```
1. FASE 1 - TOMA DE CONOCIMIENTO: Ya has llegado a la escena del siniestro y descubierto que hay 2 heridos involucidos. Esta información registra el número de lesionados.
2. FASE 2 - ARRIBO AL LUGAR: Aunque no se especifica, según este paso, debes evaluar cualquier riesgo secundario...
3. FASE 3 - INTERVENCIÓN: ...excepto si hay una razón inmediata para hacerlo.
```

Tres problemas críticos:

**Primero,** `"involucidos"` — palabra inventada nuevamente. El modelo no puede generar texto en español de forma confiable.

**Segundo,** `"Aunque no se especifica"` es una alucinación directa. FASE 2 está especificada en el protocolo con precisión: *"Evaluar riesgos secundarios (derrames, incendios, tráfico)"*. El modelo afirmó que algo no está cuando sí está.

**Tercero,** el cambio más peligroso: el protocolo dice `"No mover a lesionados salvo peligro inmediato"`. El modelo lo reescribió como `"no mover a los lesionados, excepto si hay una razón inmediata para hacerlo"`. **"Razón inmediata" no es lo mismo que "peligro inmediato".** Una razón puede ser subjetiva. En un contexto de lesiones de columna, esta diferencia semántica puede derivar en una acción que paralice a un paciente.

**Diagnóstico:** Descartado definitivamente. Los errores de español son sistemáticos y la alteración semántica de instrucciones críticas lo hace inviable para cualquier sistema de seguridad.

---

### 3. qwen2.5:3b
**Velocidad CON CONTEXTO:** 3.8s | 73.4 tok/s

#### SIN CONTEXTO
Respuesta genérica y razonablemente correcta. Incluye llamar al 112, no mover heridos, seguridad primaria. Sin embargo, el modelo mezcla consistentemente respuesta inmediata con procedimientos post-accidente. En la segunda corrida (9 modelos):

> *"Documentación: Si es posible, documenta el accidente con fotos y nota cualquier información relevante como nombres de los involucrados, números de placas de identificación del vehículo, etc., para facilitar la investigación posterior."*

Documentar para la investigación policial no es tarea del operador de emergencias en el lugar del hecho — ese es el rol de la policía. En la primera corrida (ver `primera_corrida_bench.md`) el modelo fue más lejos:

> *"Contacta a un Asesor Legal: Si hay heridos graves, es importante tener asesoramiento legal profesional sobre tus derechos y opciones legales."*

Llamar a un abogado mientras hay heridos en la escena. El modelo no tiene claro a quién le está hablando ni cuál es el objetivo inmediato de la respuesta.

#### CON CONTEXTO
```
FASE 1 - TOMA DE CONOCIMIENTO: Registrar ubicación exacta del siniestro y cantidad de lesionados.
- Luego de llegar al lugar del accidente, registrar la ubicación precisa del accidente y confirmar que hay dos heridos.

FASE 2 - ARRIBO AL LUGAR: Evaluar riesgos secundarios (derrames, incendios, tráfico).
- Realizar una evaluación rápida para identificar si existen riesgos secundarios como derrames de vehículos, posibles incendios o problemas con el tráfico que puedan poner en peligro a los heridos o a los rescatistas.

FASE 3 - INTERVENCIÓN: Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.
- Brindar auxilio médico primario a los dos heridos en el lugar, aplicando técnicas de primeros auxilios si es necesario.
- Establecer la estabilidad de los heridos graves sin moverlos, a menos que sea necesario para evitar un peligro inminente.
```

Estructura correcta: las tres fases con sus labels, cada una citada verbatim y luego expandida. Las expansiones son mayormente seguras — `"confirmar que hay dos heridos"` es contextualmente apropiado (el número viene de la consulta). `"a los rescatistas"` agrega una palabra que no está en el protocolo pero no altera la instrucción.

El único problema de velocidad: 258 tokens para una respuesta que requería ~95. El modelo tiene el hábito de expandir cada fase con una oración de elaboración, lo que alarga el tiempo total a 3.8s — 2.5x más lento que gemma2:2b generando el mismo contenido útil.

**Diagnóstico:** Buena calidad de protocolo, sin alucinaciones peligrosas. Descartado por velocidad, no por calidad.

---

### 4. ministral-3:3b
**Velocidad CON CONTEXTO:** 5.5s | 27.0 tok/s

#### SIN CONTEXTO
La respuesta más extensa del grupo en cold start. Bien estructurada con headers markdown, diferencia entre heridos graves y leves, menciona qué NO hacer. Sin errores de español. Pero incluye pasos que no corresponden a un primer respondiente:

> *"Protección personal: Usar chaleco reflectante o ropa brillante si no hay protección. Colocar triángulos de advertencia..."*

Esto asume que el operador tiene equipo de señalización y conoce la normativa vial local. Sobrepasa el protocolo de respuesta temprana.

#### CON CONTEXTO
```
**Según el protocolo oficial:**

1. **FASE 1 - TOMA DE CONOCIMIENTO:**
   Registra la ubicación exacta del siniestro y verifica que haya **dos lesionados**.

2. **FASE 2 - ARRIBO AL LUGAR:**
   Evalúa riesgos secundarios (ej.: derrames de líquidos, incendios o tráfico en el área).

3. **FASE 3 - INTERVENCIÓN:**
   Brinda auxilio médico primario y estabiliza a los heridos graves.
   **No muevas a los lesionados salvo que haya un peligro inmediato.**
```

Una de las respuestas más limpias del grupo en términos de estructura y fidelidad al protocolo. Las tres fases con sus labels en negrita, instrucciones verbatim. La única adición es `"de líquidos"` en FASE 2 — `"derrames de líquidos"` en lugar de solo `"derrames"`. No es una alucinación peligrosa, es una clarificación razonable.

La frase final en negrita enfatiza correctamente la restricción crítica de no mover lesionados.

**Por qué no ganó:** 5.5s total en una situación de emergencia es demasiado. El tiempo útil que agrega sobre gemma2:2b (4 segundos más) no se justifica con una mejora de calidad significativa.

---

### 5. llama3:8b
**Velocidad CON CONTEXTO:** 6.9s | 10.9 tok/s

#### SIN CONTEXTO
Respuesta genérica y correcta en líneas generales. Sin errores de español. Pero incluye:

> *"Protege a las víctimas: Mueve los vehículos involucrados lo más lejos posible de la carretera principal, si es necesario."*

Mover vehículos en una escena de accidente puede destruir evidencia y alterar la mecánica del hecho para peritajes. Esta instrucción contradice buenas prácticas de manejo de escena.

#### CON CONTEXTO
```
Según el protocolo, la respuesta correcta sería:

FASE 1 - TOMA DE CONOCIMIENTO: Registrar ubicación exacta del siniestro y cantidad de lesionados.

En este caso, registrar que hay un accidente vial con 2 heridos en una ubicación específica.
```

**Falla catastrófica.** El modelo listó solo FASE 1 y se detuvo. FASE 2 y FASE 3 — evaluar riesgos secundarios y brindar auxilio médico — fueron completamente omitidas. Un operador siguiendo esta respuesta jamás sabría que tiene que estabilizar heridos graves ni que no debe moverlos.

Solo generó 67 tokens. No fue un timeout ni un error de conexión — el modelo decidió que con FASE 1 era suficiente. Este comportamiento fue inconsistente entre corridas (en la corrida anterior listó las 3 fases), lo que lo hace aún más peligroso: no podés confiar en que siempre va a responder completo.

**Diagnóstico:** Descartado. Comportamiento inconsistente con omisión de fases críticas. El hardware limitante (modo mixto GPU+CPU, 6.9s) es secundario al problema de calidad.

---

### 6. gemma2:2b
**Velocidad CON CONTEXTO:** 1.5s | 80.4 tok/s

#### SIN CONTEXTO
Respuesta organizada, español impecable. Cubre seguridad personal, evaluación, llamado a emergencias. Sin errores. Aparece:

> *"Presta atención a las necesidades básicas: Si es posible, ofrece agua o comida a los heridos."*

Dar agua o comida a un herido puede ser contraproducente si hay lesiones abdominales o se necesita cirugía. Es un error conceptual de primeros auxilios, aunque no de español ni de estructura.

#### CON CONTEXTO
```
1. **FASE 1 - TOMA DE CONOCIMIENTO:** Registrar ubicación exacta del siniestro y cantidad de lesionados (2).
2. **FASE 2 - ARRIBO AL LUGAR:** Evaluar riesgos secundarios (derrames, incendios, tráfico).
3. **FASE 3 - INTERVENCIÓN:** Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.
```

La respuesta más económica y precisa del grupo. Tres características la distinguen:

**Primero, fidelidad total.** El texto de cada fase es verbatim del protocolo. No agrega, no quita, no reinterpreta.

**Segundo, labels correctos.** Cada fase tiene su número y nombre. Un operador puede ubicarse inmediatamente en el flujo del protocolo.

**Tercero, la única adición es contextualmente correcta.** El `(2)` al final de FASE 1 no es una alucinación — el número de heridos fue dado en la consulta. El modelo integró la información del contexto de forma apropiada sin inventar nada.

95 tokens. 1.5 segundos. Sin errores. Sin omisiones. Sin alucinaciones.

---

### 7. gemma3:4b
**Velocidad CON CONTEXTO:** 3.9s | 20.3 tok/s

#### SIN CONTEXTO
La respuesta más larga y detallada del grupo en cold start. Cubre seguridad vial, asistencia a heridos, comunicación con emergencias, primeros auxilios. Español sin errores. Incluye:

> *"Si hay mucho tráfico, considera poner la benzinera del vehículo en marcha."*

`benzinera` es un catalanismo / variante regional. En español rioplatense o estándar no se usa. No es un error grave pero revela que el modelo mezcla variedades del español.

#### CON CONTEXTO
```
1.  Registrar ubicación exacta del siniestro y cantidad de lesionados.
2.  Evaluar riesgos secundarios (derrames, incendios, tráfico).
3.  Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.
```

El contenido es correcto — las tres acciones están presentes y en orden. Pero **eliminó todos los labels de fase**. No aparece "FASE 1 - TOMA DE CONOCIMIENTO", ni "FASE 2 - ARRIBO AL LUGAR", ni "FASE 3 - INTERVENCIÓN".

Para un operador de emergencias, los labels no son decoración. Son el mapa del protocolo — le dicen en qué momento del procedimiento está y cuál es la lógica detrás de cada acción. Sin ellos, las tres instrucciones son una lista plana sin estructura de ejecución.

Además, es 2.6x más lento que gemma2:2b (3.9s vs 1.5s) y genera solo 20 tok/s — el segundo más lento del grupo después de llama3:8b.

**Diagnóstico:** Peor que su predecesor gemma2:2b en velocidad, calidad estructural y tamaño. Refuta la hipótesis de que más parámetros implica mejor resultado.

---

### 8. qwen2.5:1.5b
**Velocidad CON CONTEXTO:** 6.3s | 59.2 tok/s

#### SIN CONTEXTO
Respuesta razonable con algunos problemas:

> *"Lleva a los heridos al hospital: Si es posible, lleva a las personas más graves al hospital lo antes posible para recibir atención médica."*

Mover heridos sin inmovilización previa es peligroso. El modelo aconseja esto sin ninguna advertencia sobre lesiones de columna.

#### CON CONTEXTO
```
1. **Toma de Conocimiento**: 
   - Registrar ubicación exacta del siniestro y cantidad de lesionados.
   - Si hay peligro inmediato o riesgo significativo, tomar medidas para minimizar el daño.

2. **Arrivo al Lugar**:
   ...
   - Si se detectan riesgos significativos, tomar medidas para minimizarlos (por ejemplo, cerrar la avenida afectada).

3. **Intervención**: 
   ...
   - Estabilizar heridos graves: asegurarse de que los lesionados sean transportados en un vehículo seguro para su traslado al hospital.
```

**Dos alucinaciones críticas que hacen a este modelo inaceptable para producción:**

**Primera:** `"cerrar la avenida afectada"` — esta instrucción no existe en el protocolo. El modelo la inventó. Un operador de emergencias no tiene autoridad ni medios para cerrar una avenida. Seguir esta instrucción significaría actuar fuera del protocolo oficial.

**Segunda y más grave:** `"asegurarse de que los lesionados sean transportados en un vehículo seguro para su traslado al hospital"`. El protocolo dice literalmente lo contrario: `"No mover a lesionados salvo peligro inmediato"`. El modelo no solo inventó una instrucción — inventó una instrucción que contradice directamente el protocolo. Transportar un herido con posible lesión de columna sin inmovilización puede causar parálisis permanente.

Además generó 355 tokens — el modelo pasó al protocolo de referencia, luego volvió a repetirlo con interpretaciones propias en una segunda pasada. Esta doble pasada es donde se introdujeron las alucinaciones.

**Diagnóstico:** Descartado por riesgo de seguridad. No importa la velocidad del TTFT (269ms, el más rápido del grupo) cuando el contenido puede inducir a un operador a dañar a un paciente.

---

### 9. phi4-mini
**Velocidad CON CONTEXTO:** 3.4s | 37.8 tok/s

#### SIN CONTEXTO
Una de las mejores respuestas sin contexto del grupo. Sin errores de español, sin instrucciones contraproducentes. Concisa y prioriza lo correcto:

> *"No intentes manejar las lesiones tú mismo si no tienes formación en primeros auxilios; es mejor dejarlo a los profesionales capacitados."*

Esta instrucción es apropiada y responsable. El modelo reconoce los límites del rol del operador.

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

Respuesta limpia y bien estructurada. Tres fases con labels. Sin alucinaciones. El modelo hizo dos adiciones menores pero correctas:

`"Contar y"` antes de registrar lesionados — el conteo está implícito en el protocolo, explicitar el verbo es razonable y útil.

`"sin moverlos"` en FASE 3 — el protocolo dice `"No mover a lesionados salvo peligro inmediato"`. El modelo lo reformuló como `"sin moverlos salvo peligro inmediato"`. No altera el significado, lo hace más directo.

El problema es exclusivamente la velocidad: 3.4s total. Es 2.3x más lento que gemma2:2b sin ofrecer una mejora de calidad que justifique esa diferencia.

**Diagnóstico:** El mejor competidor de gemma2:2b en calidad de respuesta. Si la latencia no fuera un criterio, estarían empatados. Queda como reserva de calidad en caso de que el prompt engineering del Integrante 4 encuentre casos donde gemma2:2b falla.

---

## Tabla comparativa de calidad CON CONTEXTO

| Modelo | Labels de fase | Fidelidad al protocolo | Alucinaciones | Español | Velocidad |
|--------|---------------|----------------------|---------------|---------|-----------|
| gemma2:2b | ✅ | ✅ verbatim | ✅ ninguna | ✅ | ✅ 1.5s |
| phi4-mini | ✅ | ✅ verbatim + adiciones seguras | ✅ ninguna | ✅ | ⚠️ 3.4s |
| ministral-3:3b | ✅ | ✅ verbatim | ✅ ninguna | ✅ | ⚠️ 5.5s |
| qwen2.5:3b | ✅ | ✅ verbatim + expansión | ✅ ninguna | ✅ | ⚠️ 3.8s |
| llama3.2:3b | ⚠️ solo FASE 1 | ⚠️ incompleto | ✅ ninguna | ✅ | ✅ 1.7s |
| gemma3:4b | ❌ sin labels | ✅ verbatim | ✅ ninguna | ✅ | ⚠️ 3.9s |
| llama3:8b | ⚠️ solo FASE 1 | ❌ omite FASE 2 y 3 | ✅ ninguna | ✅ | ❌ 6.9s |
| qwen2.5:1.5b | ⚠️ sin "FASE N -" | ❌ inventa instrucciones | ❌ críticas | ✅ | ❌ 6.3s |
| phi3.5 | ✅ | ⚠️ altera significado | ⚠️ semántica | ❌ palabras inventadas | ❌ 11.1s |

---

## Conclusión — Por qué elegimos gemma2:2b

La elección de `gemma2:2b` no es una preferencia — es el resultado de un proceso de eliminación riguroso sobre nueve modelos evaluados en las dos dimensiones que importan: **velocidad** y **seguridad del contenido**.

### Los modelos más rápidos fallaron en calidad

`llama3.2:3b` (1.7s) y `gemma2:2b` (1.5s) son los únicos modelos bajo los 2 segundos. De esos dos, llama3.2:3b tiene un problema estructural consistente — agrupó las tres fases bajo el label de FASE 1 en todas las corridas. Esta no es una falla ocasional: es el comportamiento por defecto del modelo con este prompt. Para un operador que ejecuta el protocolo en tiempo real, leer `"FASE 1: [pasos de tres fases]"` genera confusión sobre el flujo de ejecución. gemma2:2b produjo la estructura correcta en todas las corridas sin instrucción explícita.

### Los modelos con mejor calidad fueron demasiado lentos

`phi4-mini` (3.4s) y `ministral-3:3b` (5.5s) produjeron respuestas comparables o superiores en estructura y fidelidad al protocolo. Pero en una emergencia vial, 3.4 segundos es el doble del tiempo de respuesta del líder. Cada segundo que el operador espera la respuesta del sistema es un segundo que no está actuando. La diferencia de calidad entre phi4-mini y gemma2:2b no justifica 1.9 segundos adicionales de espera.

### Los modelos más pequeños alucinaron

`qwen2.5:1.5b` demostró que reducir el tamaño del modelo por debajo de 2B parámetros tiene un costo concreto en este dominio. No fue un problema de velocidad (269ms de TTFT es el mejor del grupo) sino de comportamiento: el modelo generó instrucciones inexistentes en el protocolo y, lo más grave, una instrucción que directamente contradice el protocolo oficial (`"transportados en un vehículo seguro para traslado al hospital"` vs `"No mover a lesionados"`). En un sistema de emergencias, una alucinación no es un bug de software — es una instrucción que alguien podría seguir.

### La hipótesis de gemma3:4b fue refutada

Se esperaba que el sucesor directo de gemma2 lo superara. El resultado fue el opuesto: gemma3:4b fue 2.6x más lento (3.9s vs 1.5s), generó solo 20 tok/s contra 80 de gemma2:2b, y perdió los labels de fase en la respuesta. Esto confirma que en tareas específicas de seguimiento estricto de instrucciones, la generación anterior de un modelo más pequeño puede superar a la generación siguiente con más parámetros.

### gemma2:2b reúne todas las condiciones simultáneamente

- **Velocidad:** 1.5s total, 80 tok/s — el más rápido del grupo
- **Estructura:** tres fases con labels correctos en todas las corridas
- **Fidelidad:** texto verbatim del protocolo, sin omisiones ni reinterpretaciones
- **Seguridad:** ninguna alucinación en ninguna corrida
- **Español:** limpio, sin errores gramaticales
- **Hardware:** 1.6GB — el modelo más pequeño, corre en cualquier equipo del equipo

Ningún otro modelo alcanzó estos cinco criterios simultáneamente. Algunos son más rápidos en TTFT pero más lentos en total. Algunos tienen mejor calidad de expansión pero son más lentos. Ninguno tiene la combinación de velocidad total + fidelidad de protocolo + ausencia de alucinaciones que tiene gemma2:2b.

El modelo seleccionado para producción es `gemma2:2b`.
