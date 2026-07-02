# Evaluación del RAG de emergencias — Métricas

Suite de métricas para evaluar el asistente de primeros auxilios (RAG sobre el
PDF *COMPORTAMIENTO EN CASO DE ACCIDENTE - PRIMEROS AUXILIOS*).

El set de test (`DataSetTest.xlsx`) tiene 25 preguntas realistas de emergencia con
su respuesta esperada. Ese set se materializa en `dataset_evaluacion.json`, que es
la **única fuente de verdad** que consumen todos los scripts de esta carpeta.

## Por qué evaluamos en dos planos

Un RAG puede fallar en dos lugares distintos, y conviene medirlos por separado:

1. **Retrieval** — ¿el buscador trae el fragmento (*chunk*) correcto del manual, y
   lo trae arriba en el ranking? Si acá falla, la generación parte de contexto
   equivocado por más bueno que sea el modelo.
2. **Generación** — dado el contexto recuperado, ¿la respuesta es pertinente,
   completa, fiel a la fuente y segura? Acá es donde el LLM puede divagar, omitir
   un dato que salva vidas o alucinar.

En un dominio médico de urgencia esta distinción no es cosmética: una respuesta
"linda" construida sobre el protocolo equivocado es peligrosa.

## Decisión de diseño: la evaluación de retrieval es a nivel *chunk*

Todo el corpus proviene de **un solo PDF**. Si evaluáramos relevancia a nivel
*documento* (comparando `metadata["source"]` esperado vs. recuperado), la respuesta
siempre es "sí, salió de ese PDF" → **toda métrica de retrieval daría 1.0 trivial**
(lo verificamos: el Recall@5 original daba 1.0 en las 25 preguntas). No mide nada.

Por eso la relevancia se evalúa **a nivel de chunk**, comparando ids reales de
chunk. Dos problemas prácticos y cómo se resuelven:

- Los ids de chunk son **UUID aleatorios** que cambian al re-ingestar → no se pueden
  hardcodear en el dataset.
- Los chunks **no guardan número de página** (la limpieza del texto borra los
  marcadores) → no hay identificador humano estable.

**Solución:** el conjunto de chunks relevantes ("gold") se resuelve *en tiempo de
evaluación*. Cada script recorre el corpus y marca como gold los chunks cuyo texto
contiene las **palabras-clave distintivas de la respuesta correcta**
(campo `mrr_relevant_keywords`; si falta, usa `critical_facts`). El match es por
substring, insensible a mayúsculas y acentos. Así obtenemos `expected_chunk_ids`
reales por consulta, robustos ante re-ingesta y sin tocar la ingesta compartida.

> Nota: son etiquetas *silver* (heurísticas por keyword), no anotadas a mano. Es un
> compromiso consciente entre rigor y esfuerzo, adecuado para una PoC.

### Estructura de cada entrada del dataset

```json
{
  "query": "Una persona está sangrando mucho por el brazo ¿Que Hago?",
  "expected_relevant_docs": ["COMPORTAMIENTO-...-PRIMEROS-AUXILIOS.pdf"],
  "critical_facts": ["presión directa", "elevar", "presión arterial", "torniquete"],
  "mrr_relevant_keywords": ["arteria humeral", "torniquete", "presión directa"]
}
```

- `critical_facts` → hechos que la **respuesta** debe contener (métrica de generación).
- `mrr_relevant_keywords` → términos distintivos que identifican el **chunk fuente**
  (métricas de retrieval). Se separan porque cumplen roles distintos.

---

## Métricas de Retrieval

### MRR — Mean Reciprocal Rank · `mrr.py` · *(Salva)*

- **Qué mide:** la posición del **primer** chunk relevante dentro del ranking
  recuperado. `RR = 1/rank` (1.0 si está primero, 0.5 si segundo, …; 0 si no aparece
  en el top-K). El MRR es el promedio sobre las 25 consultas. Se evalúa `MRR@10`.
- **Por qué la elegimos / qué información da:** en emergencias, el modelo suele usar
  solo los 1-2 chunks de más arriba para responder. El MRR responde justamente a
  *"¿el protocolo correcto aparece en lo más alto del ranking?"*. Premia colocar la
  respuesta correcta en el primer lugar, no solo "en algún lado". Es la métrica que
  mejor refleja lo que el generador realmente va a leer.
- **Cómo se calcula acá:** para cada consulta se resuelve el gold set de ids sobre el
  corpus, se recuperan los top-10 chunks y se busca el primer id recuperado que esté
  en el gold set. `RR = 1/(esa posición)`.

### Recall@5 · `recall_at_5.py` · *(Andy)*

- **Qué mide:** qué **proporción** de los chunks relevantes del corpus fueron
  recuperados dentro del top-5. `Recall@5 = |top5 ∩ gold| / |gold|`.
- **Por qué la elegimos / qué información da:** complementa al MRR. El MRR mira *dónde*
  cayó el primer acierto; el Recall mira *cuánta* de la información relevante logramos
  traer. Importa cuando la respuesta correcta está repartida en varios chunks (p. ej.
  "qué llevar en el botiquín" toca varios fragmentos): un buen MRR con bajo Recall
  avisa que estamos dejando afuera parte del protocolo.
- **Cómo se calcula acá:** versión refactorizada a nivel chunk. Requiere leer el
  corpus completo para conocer el denominador (cuántos chunks gold existen); si una
  consulta no tiene chunks gold, se marca `N/A` y no promedia.

---

## Métricas de Generación

### Answer Relevancy — Relevancia de la respuesta · `answer_relevancy.py` · *(Alex)*

- **Qué mide:** qué tan **pertinente y enfocada** es la respuesta respecto a la
  pregunta. Es *reference-free*: no usa la respuesta esperada, solo pregunta +
  respuesta generada.
- **Por qué la elegimos / qué información da:** detecta respuestas que "se van por las
  ramas", incompletas o con relleno irrelevante — algo típico cuando el contexto
  recuperado es flojo. Un valor bajo indica que el asistente no está respondiendo *lo
  que se le preguntó*, aunque diga cosas correctas. Al no depender de una respuesta de
  referencia, evalúa la coherencia pregunta↔respuesta de forma barata y automática.
- **Cómo se calcula acá (estilo RAGAS):** (1) se genera la respuesta real del RAG;
  (2) un LLM produce 3 "preguntas inversas" que esa respuesta estaría contestando;
  (3) se mide la similitud coseno (embeddings) entre cada pregunta inversa y la
  original; (4) el score es el promedio. Si la respuesta es **evasiva** (no compromete
  información: "no tengo ese dato", derivación al 911, etc.) se asigna **0**, porque
  una respuesta que no responde no puede ser relevante. Reutiliza el LLM y los
  embeddings de Ollama ya cableados en el pipeline.

### Critical Information Coverage · `critical_information_coverage.py` · *(Andy)*

- **Qué mide:** qué fracción de los **hechos críticos** esperados aparece en la
  respuesta. `cobertura = hechos_presentes / hechos_esperados` (campo `critical_facts`).
- **Por qué la elegimos / qué información da:** es la métrica de **seguridad clínica**.
  Que la respuesta sea relevante y fluida no garantiza que incluya el dato que importa
  ("llamá al 112", "no muevas al herido", "no retires el objeto clavado"). Esta métrica
  mide directamente si esos datos accionables están o no. En este dominio, omitir un
  hecho crítico es el peor error posible, y acá se hace visible.
- **Cómo se calcula acá:** genera la respuesta real y verifica por substring la
  presencia de cada hecho crítico.

### Pendientes de otras personas (parte de la suite)

- **STS — Semantic Text Similarity** *(Lalo)*: similitud semántica entre la respuesta
  generada y la respuesta esperada (Excel col. B). *Qué info da:* cuán parecida es la
  respuesta al "gold" de referencia, más allá de coincidencias literales. Requiere
  incorporar la respuesta esperada al dataset.
- **Faithfulness — Fidelidad** *(Lauti)*: qué proporción de las afirmaciones de la
  respuesta está **respaldada por el contexto recuperado**. *Qué info da:* mide
  alucinaciones — respuestas que "inventan" fuera de la fuente.
- **Safety Compliance** *(Lauti)*: cumplimiento de reglas de seguridad (no dar
  medicación, no mover heridos, derivar a emergencias). *Qué info da:* riesgo de que el
  asistente dé una indicación peligrosa.

---

## Cómo correr las métricas

**Requisitos:** el stack levantado (ver `../LEVANTAR_RAG.md`): Docker + PostgreSQL/
pgvector en `:5433` con el corpus ya ingestado + Ollama con los modelos
(`gemma2:2b` para generación, `paraphrase-multilingual` para embeddings).

```bash
# desde la raíz del repo
python metricas/mrr.py
python metricas/recall_at_5.py
python metricas/answer_relevancy.py
python metricas/critical_information_coverage.py
```

Cada script imprime el detalle por consulta, el promedio global y guarda un JSON con
timestamp en `metricas/resultados/`, con la traza completa (chunks recuperados, ids
gold, keywords que matchearon, preguntas inversas, etc.) para poder auditar el número.

## Notas y limitaciones

- **Etiquetas gold silver:** la relevancia de chunks se define por keywords, no por
  anotación manual. Buenas keywords distintivas la hacen fiable, pero es una heurística.
- **MRR y Recall dependen del corpus:** leen la tabla `protocol_chunks` para resolver
  el gold set. Sin BD, el MRR degrada a un fallback (RR equivalente) y el Recall avisa
  que su denominador no es fiable.
- **Modelo local chico:** `gemma2:2b` genera respuestas y preguntas inversas modestas;
  los números absolutos hay que leerlos en términos comparativos (entre configuraciones
  del RAG), no como una nota final.
- **`temperature=0.1`:** la generación es casi determinista, pero puede haber pequeñas
  variaciones entre corridas.
