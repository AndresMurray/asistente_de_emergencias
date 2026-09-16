# Resumen Ejecutivo: Optimización, Desacoplamiento de Servicios y Estado del Asistente

Este documento detalla el trabajo de ingeniería realizado sobre el **Asistente de Emergencias Viales**, la transición al motor de inferencia de ultra-baja latencia **Groq**, el diagnóstico y resolución de cuotas de tokens y base de datos, y las pautas para la presentación en la Expo.

---

## 1. Problema Inicial: Rigidez y Falta de Humanización

### Diagnóstico
En las pruebas iniciales, ante la consulta del asistente (*"¿Estás en un lugar seguro, fuera de la calzada?"*), cuando el interlocutor preguntaba *"¿qué es la calzada?"*, el agente quedaba atrapado en un bucle rígido repitiendo la misma pregunta una y otra vez sin responder la duda.

### Solución Implementada
Se modificó el prompt del sistema en `prompts.py`:
* **Explicación empática:** Se instruyó al LLM a que, si el interlocutor no entiende un término o una pregunta, lo aclare brevemente en lenguaje cotidiano antes de continuar guiando la llamada.
* **Flexibilidad en límites:** Se relajó la regla de reencauce para que el asistente no ignore preguntas aclaratorias sobre sus propias indicaciones.

---

## 2. Diagnóstico del Error 429 de LiveKit Cloud y Desacoplamiento

Al ejecutar ensayos por consola, saltó el error:
```text
429 Too Many Requests: LLM token credit quota exceeded, category: MaxGatewayCredits, remaining_limit: 0
```

### Causa raíz
El código dependía del **Inference Gateway de LiveKit Cloud** (`agent-gateway.livekit.cloud`), el cual actúa como intermediario para llamar a los modelos de IA. En el plan gratuito **Build ($0/mo)**, LiveKit otorga una bolsa fija de créditos de cortesía para repartir entre STT, TTS y LLM que se agotó durante las pruebas.

### Desacoplamiento a Proveedores Directos
Para no pagar los $50 USD mensuales de LiveKit Cloud y tener control total sobre el sistema, se desacopló la inferencia del gateway y se conectó **cada servicio directamente a su proveedor oficial**.

---

## 3. Elección de Groq como Cerebro (LLM) y Gestión de Facturación

### ¿Por qué se eligió Groq?
1. **Velocidad de respuesta extrema (LPU):** Para un asistente de voz en tiempo real, el *Time to First Token* (TTFT) es crítico. Los chips LPU de Groq entregan el primer token en ~150–200 ms y alcanzan ~300 tokens/segundo, permitiendo que Cartesia TTS comience a hablar por streaming casi instantáneamente.
2. **Modelo seleccionado (`openai/gpt-oss-120b`):** 
   * Es el modelo abierto de **OpenAI de 120 mil millones de parámetros** optimizado sobre Groq.
   * Proporciona un razonamiento médico y de triage de primer nivel (respeta estrictamente no hacer RCP a quien respira, no retirar cascos a motociclistas y utiliza voseo rioplatense fluido).
   * Implementa *Tool Calling* / *Function Calling* nativo con máxima precisión para consultar Supabase (`buscar_protocolo`), derivar al 911 y registrar datos.

### Diagnóstico del Cuello de Botella en Groq Free Tier (8.000 TPM)
Durante las pruebas con `ensayo.py`, al 3.ᵉʳ turno saltó un error `429 Rate limit reached on tokens per minute (TPM): Limit 8000, Used 5412, Requested 3201`.
* **Causa:** El Free Tier de Groq impone un tope de 8.000 tokens por minuto. Nuestro system prompt + definiciones de herramientas JSON + historial consume ~2.700 tokens por turno, por lo que 3 intercambios en menos de 60 segundos superaban los 8.000 tokens acumulados.

### Gestión de Pagos y Blindaje de Costos en Groq (Developer Tier)
Para eliminar este límite sin riesgos económicos, se pasó la cuenta a **Developer Tier**:
* **Sin costo fijo mensual:** No es una suscripción ($0/mes de mantenimiento).
* **Cobro por umbrales progresivos (*Postpaid*):** Groq no cobra por adelantado; emite el primer cobro recién al acumular **$1.00 USD** de consumo real (o a fin de mes).
* **Blindaje estricto con Spend Limits:**
  * **Límite mensual fijado en:** **`$1.00 USD`** (`Current spend: $0.00 / $1.00`). Es imposible que se cobre más de un dólar.
  * **Alerta de consumo:** Configurada a los **`$0.50 USD`** con notificación directa al correo.
  * **Desbloqueo de cuota:** El límite de tokens saltó de 8.000 a **más de 300.000 TPM**, eliminando por completo cualquier error 429.

---

## 4. Arquitectura del Sistema Implementada

```
                              ┌──────────────────────────────────────────────┐
                              │          LiveKit Cloud (WebRTC)              │
                              │   Salas de audio y streaming en tiempo real   │
                              │       (916 minutos libres disponibles)        │
                              └──────────────────────┬───────────────────────┘
                                                     │
                                       ┌─────────────┴─────────────┐
                                       │   Asistente (agent.py)    │
                                       └─────────────┬─────────────┘
                                                     │
         ┌───────────────────────────┬───────────────┴───────────────┬───────────────────────────┐
         ▼                           ▼                               ▼                           ▼
┌──────────────────┐       ┌──────────────────┐            ┌──────────────────┐        ┌──────────────────┐
│ STT: Deepgram    │       │  LLM: Groq (LPU) │            │  TTS: Cartesia   │        │ RAG: Supabase    │
│ Modelo: nova-3   │       │  openai/         │            │  Modelo: sonic-3 │        │ pgvector (HNSW)  │
│ Clave: Propia    │       │  gpt-oss-120b    │            │  Clave: Propia   │        │ Puerto: 6543     │
│ ($200 saldo)     │       │  Clave: Propia   │            │  (20.000 chars)  │        │ Embeddings:      │
│                  │       │  ($1 spend limit)│            │                  │        │ gemini-embed-001 │
└──────────────────┘       └──────────────────┘            └──────────────────┘        └──────────────────┘
```

---

## 5. Otras Correcciones y Mejoras Técnicas Clave

### A. Conexión a Supabase: Puerto 5432 a 6543
* **Problema:** Durante una búsqueda de protocolo surgió `psycopg2.OperationalError: connection to ... port 5432 failed: timeout expired`.
* **Causa:** El puerto estándar de Postgres (5432) suele ser bloqueado por firewalls de red o sufrir latencias en conexiones directas.
* **Solución:** Se configuró en `DATABASE_URL` el puerto **`6543`** (modo *Connection Pooler* transaccional de Supabase), garantizando alta disponibilidad y superando restricciones de red.

### B. Saludo Inicial en el Simulador (`ensayo.py`)
* En el agente real de voz (`agent.py`), el saludo (*"Emergencias viales, te escucho. Estoy con vos. ¿Estás en un lugar seguro, fuera de la calzada?"*) se reproduce por TTS mediante `session.say(SALUDO)` a 0 ms de latencia sin consultar al LLM.
* Se adaptó `ensayo.py` para imprimir automáticamente este `SALUDO` al inicio de la sesión interactiva, haciendo que la prueba por consola sea idéntica a la llamada telefónica real.

### C. Confirmación Explícita de Geolocalización al Derivar
* **Regla Condicional:** Se refinó `prompts.py` y `triage.py` para que, **únicamente cuando corresponda derivar** (heridos o riesgo de vida), el asistente confirme en ese mismo turno:
  > *«Ya estás geolocalizado y la ayuda va en camino. [Maniobra médica inmediata]»*
* Si no hay heridos (ej: choque leve sin lesiones), el sistema no deriva ni menciona ambulancias en camino, brindando pautas de seguridad vial.

### D. Unificación de Scripts con `create_llm()`
* Se actualizaron `agent.py`, `ensayo.py`, `test_guion_expo.py` y `ask_livekit.py` para que todos consuman `create_llm()`, respetando el proveedor activo (Groq con fallback a Gemini) y evitando consumir créditos de LiveKit.

---

## 6. Estado y Blindaje de Cuotas

| Proveedor | Rol en el Asistente | Configuración / Cuota Actual | ¿Suficiente para la Expo? |
| :--- | :--- | :--- | :---: |
| **Groq** | Cerebro / LLM (`openai/gpt-oss-120b`) | Developer Tier activo. Límite estricto de gasto de **$1.00 USD** con alerta en **$0.50 USD**. Más de 300K TPM libres. | **Sí (100% blindado)** |
| **Deepgram** | STT (Escucha) | Clave propia con $200 USD de saldo de bienvenida (~700 horas de audio). | **Sí (100% blindado)** |
| **Cartesia** | TTS (Voz rioplatense) | 20.000 créditos/caracteres intactos (~250 respuestas habladas). | **Sí (100% blindado)** |
| **LiveKit Cloud** | WebRTC (Conexión de audio) | 916 minutos de agente restantes y 49 GB de ancho de banda libres. | **Sí (~15 horas continuas)** |
| **Supabase** | RAG (Base vectorial) | PostgreSQL + pgvector con Connection Pooler activo en puerto **6543**. | **Sí (100% blindado)** |
| **Google AI Studio** | Embeddings RAG | Pico histórico 79/100 RPM. Consume 1 llamada por consulta de protocolo. | **Sí** |

---

## 7. Pasos de Validación y Despliegue

### 1. Ensayo Interactivo por Consola
```bash
python ensayo.py --interactivo
```
Verifica el flujo completo: saludo inicial, aclaración de términos cotidianos, triage, consulta al RAG en Supabase y derivación condicional.

### 2. Validación de Escenarios Guionados
```bash
python test_guion_expo.py --escenario principal
python test_guion_expo.py --escenario casco
python test_guion_expo.py --escenario inconsciente_respira
```
Ejecuta la batería de pruebas automatizadas que certifica las reglas médicas y de seguridad.

### 3. Ejecución Local con Voz Real
```bash
python agent.py dev
```
Inicia el agente conectado a LiveKit Cloud para probar la interacción real de voz mediante el frontend web.

### 4. Despliegue en la Nube (Producción)
Cuando se desee actualizar el agente desplegado en LiveKit Cloud:
```bash
lk agent deploy
```
*Asegurarse de que en el Dashboard de LiveKit Cloud (Settings > Environment Variables) estén cargadas: `GROQ_API_KEY`, `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, `DATABASE_URL` (con puerto 6543) y `GEMINI_API_KEY`.*
