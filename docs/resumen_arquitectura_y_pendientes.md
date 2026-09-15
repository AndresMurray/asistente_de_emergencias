# Resumen Ejecutivo: Optimización, Desacoplamiento de Servicios y Estado del Asistente

Este documento detalla el trabajo realizado sobre el **Asistente de Emergencias Viales**, el diagnóstico de los errores de cuota en LiveKit Cloud, la arquitectura de proveedores directos implementada y los pasos pendientes para garantizar una presentación impecable en la Expo.

---

## 1. Problema Inicial: Rigidez y Falta de Humanización

### Diagnóstico
En las pruebas iniciales, ante una consulta del asistente (*"¿Estás en un lugar seguro, fuera de la calzada?"*), cuando el usuario preguntaba *"¿qué es la calzada?"*, el agente quedaba atrapado en un bucle rígido repitiendo la misma pregunta una y otra vez sin responder la duda.

### Solución Implementada
Se modificó el prompt del sistema en `prompts.py`:
* **Explicación empática:** Se instruyó al LLM a que, si el interlocutor no entiende un término o una pregunta (por ejemplo, qué significa *calzada*), lo aclare brevemente en lenguaje cotidiano antes de continuar guiando la llamada.
* **Flexibilidad en límites:** Se relajó la regla de reencauce para que el asistente no ignore preguntas aclaratorias sobre sus propias indicaciones.

---

## 2. Diagnóstico del Error 429 de LiveKit Cloud

Al intentar probar el agente por consola con `python ensayo.py --interactivo`, saltó el siguiente error:
```text
429 Too Many Requests: LLM token credit quota exceeded, category: MaxGatewayCredits, remaining_limit: 0
Hint: LLM token credit quota exhausted. Wait for the next billing cycle or upgrade your plan.
```

### La causa raíz:
* El código dependía del **Inference Gateway de LiveKit Cloud** (`agent-gateway.livekit.cloud`), el cual actúa como intermediario para llamar a los modelos de IA.
* En el plan gratuito **Build ($0/mo)**, LiveKit Cloud otorga una bolsa fija de créditos de cortesía ("Inference Credits") para repartir entre STT, TTS y LLM.
* En el panel de **Billing** se verificó que en el mes se habían consumido:
  * ~100.000 tokens de Gemma 4 31B.
  * ~200.000 tokens de GPT-4.1 mini.
  * Más de 600.000 tokens cacheados.
  * 35 minutos de Deepgram STT.
  * ~20.000 caracteres de Cartesia TTS.
* Al llegar al tope de la bolsa gratuita mensual de inferencia, LiveKit bloqueó las peticiones al gateway exigiendo pasar al plan pago **Ship ($50 USD/mes)**.
* **Aclaración importante sobre "los 1.000 minutos":** Los 1.000 minutos que incluye LiveKit son de *tiempo de conexión a la sala WebRTC (Agent session minutes)*, de los cuales solo se usaron 84 minutos (quedan 916 minutos libres). La inferencia de IA no se mide en minutos de sala, sino en tokens y créditos.

---

## 3. Arquitectura Desacoplada (Solución Implementada)

Para no pagar los $50 USD mensuales de LiveKit Cloud y tener control total sobre el sistema, se desacopló la inferencia del gateway de LiveKit y se conectó **cada servicio directamente a su proveedor oficial**:

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
│ STT: Deepgram    │       │  LLM: Google     │            │  TTS: Cartesia   │        │ RAG: Supabase    │
│ Modelo: nova-3   │       │  gemini-3.6-flash│            │  Modelo: sonic-3 │        │ pgvector (HNSW)  │
│ Clave: Propia    │       │  Clave: Propia   │            │  Clave: Propia   │        │ Embeddings:      │
│ ($200 saldo)     │       │  (Google Studio) │            │  (20.000 chars)  │        │ gemini-embed-001 │
└──────────────────┘       └──────────────────┘            └──────────────────┘        └──────────────────┘
```

### Cambios en Código:
1. **`agent.py`:**
   * Imports consolidados al inicio del archivo según estándar PEP 8 (`cartesia`, `deepgram`, `google`).
   * Función `create_llm()`: Conecta con `livekit.plugins.google.LLM` usando `GEMINI_API_KEY` (modelo `gemini-3.6-flash`).
   * Función `create_stt()`: Conecta con `livekit.plugins.deepgram.STT` usando `DEEPGRAM_API_KEY` propia.
   * Función `create_tts()`: Conecta con `livekit.plugins.cartesia.TTS` usando `CARTESIA_API_KEY` propia con voz rioplatense.
2. **`ensayo.py`:**
   * Actualizado para usar `create_llm()` directamente, permitiendo ensayos de texto sin consumir créditos de LiveKit.
3. **`.env.local`:**
   * Incorporada la clave directa de Deepgram (`DEEPGRAM_API_KEY`).
   * Configurado `LLM_MODEL=gemini-3.6-flash`.
   * Limpiada clave duplicada para evitar advertencias de SDK.

---

## 4. Estado y Cuotas de Cada Proveedor

| Proveedor | Rol en el Asistente | Estado Actual de Cuota | ¿Suficiente para la Expo? |
| :--- | :--- | :--- | :---: |
| **Deepgram** | STT (Escucha) | Clave nueva propia vinculada con saldo de bienvenida ($200 USD ≈ 700 horas de audio). | **Sí (100% blindado)** |
| **Cartesia** | TTS (Voz rioplatense) | 20.000 créditos/caracteres intactos (0% consumido, renueva 30 de septiembre). Permite ~250 respuestas habladas. | **Sí (100% blindado)** |
| **LiveKit Cloud** | WebRTC (Conexión de audio) | 916 minutos de agente restantes (de 1.000) y 49 GB de ancho de banda libres. | **Sí (~15 horas continuas)** |
| **Supabase** | RAG (Base vectorial) | PostgreSQL + pgvector activo en capa gratuita permanente. | **Sí** |
| **Google Gemini (Embeddings)** | Búsqueda semántica | Pico histórico 79/100 RPM durante ingesta. En runtime gasta 1 llamada por búsqueda. | **Sí** |
| **Google Gemini (LLM)** | Cerebro y Triage | Cuenta Free Tier: 5 RPM (pedidos por minuto) para 3.6 Flash / 1.500 al día. | **Atención (ver pendientes)** |

---

## 5. Tareas Pendientes y Recomendaciones para la Expo

### A. Para el LLM (Google AI Studio)
En la prueba por consola comprobamos que el pipeline completo funcionó a la perfección:
* Identificó el siniestro.
* Registró el triage (`registrar_datos_escena`).
* Consultó el RAG en Supabase (`buscar_protocolo`).
* Disparó el despacho al 911 (`derivar_a_emergencias`).
* Formuló la respuesta médica exacta en rioplatense.

Sin embargo, en la capa gratuita el límite es de **5 pedidos por minuto (5 RPM)**. Como el agente encadena llamadas a herramientas en un mismo turno, puede rozar ese límite si se le habla muy rápido.

* **Recomendación para la Expo:** En la pantalla de [Google AI Studio (Límites de frecuencia)](https://ai.dev/rate-limit), hacer clic en **`Configurar la facturación`** y asociar una tarjeta al proyecto de Google Cloud (Pay-as-you-go).
  * El límite sube instantáneamente a **1.000+ RPM**.
  * El costo de los modelos Flash es de **$0.10 USD por millón de tokens** (toda la expo costará menos de $0.50 USD).
  * Si es la primera cuenta de Google Cloud, Google acredita $300 USD gratis por 90 días.

### B. Pruebas Pendientes a Realizar
1. **Ensayo interactivo por texto:**
   ```bash
   python ensayo.py --interactivo
   ```
   Probar el caso de *"¿Qué es la calzada?"* para validar la respuesta humanizada.
2. **Ejecución local del agente completo (con voz y frontend):**
   ```bash
   python agent.py dev
   ```
   Abrir la interfaz web de pruebas y validar el flujo con voz real de Cartesia y STT de Deepgram.
3. **Validación de escenarios guionados:**
   ```bash
   python test_guion_expo.py --escenario principal
   ```
   Verificar que las pruebas automáticas del guion de la facultad pasen en verde.

### C. Despliegue en Producción (LiveKit Cloud)
Cuando se desee actualizar el agente desplegado en la nube de LiveKit:
* Recordar que `livekit.toml` y `agent.py` se despliegan con:
  ```bash
  lk agent deploy
  ```
* Las variables de entorno de producción (`DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, `GEMINI_API_KEY`, `DATABASE_URL`) deben quedar cargadas en el **LiveKit Cloud Dashboard > Settings > Environment Variables** del agente para que el contenedor en la nube también use las claves directas.
