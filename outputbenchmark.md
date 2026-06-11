python benchmark.py

════════════════════════════════════════════════════════════
  BENCHMARK LLM LOCAL — RAG Emergencias Viales
════════════════════════════════════════════════════════════
  Modelos: llama3.2:3b, phi3.5, qwen2.5:3b, ministral-3:3b, llama3:8b, gemma2:2b, gemma3:4b, qwen2.5:1.5b, phi4-mini
  Endpoint: http://localhost:11434/api/generate
  Cada modelo se prueba con y sin contexto de protocolo.
════════════════════════════════════════════════════════════

  Probando llama3.2:3b [SIN CONTEXTO]...


PROMPT_SIN_CONTEXTO = (
    "Hay un accidente vial con heridos. ¿Cuáles son los primeros pasos?"
)

PROTOCOLO_SIMULADO = """
FASE 1 - TOMA DE CONOCIMIENTO: Registrar ubicación exacta del siniestro y cantidad de lesionados.
FASE 2 - ARRIBO AL LUGAR: Evaluar riesgos secundarios (derrames, incendios, tráfico).
FASE 3 - INTERVENCIÓN: Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.
"""

PROMPT_CON_CONTEXTO = (
    f"Usando ÚNICAMENTE el siguiente protocolo oficial, respondé qué hacer ante un accidente vial con heridos. "
    f"No agregues información que no esté en el protocolo.\n\n"
    f"PROTOCOLO:\n{PROTOCOLO_SIMULADO}\n\n"
    f"CONSULTA: Llegué a la escena de un accidente vial, hay 2 heridos. ¿Qué hago?"
)

────────────────────────────────────────────────────────────
  [1] LLAMA3.2:3B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  6160 ms
  Tiempo total:         13.07 s
  Tokens generados:     505
  Velocidad:            73.1 tok/s

  Respuesta:

    En caso de un accidente vial con heridos, es importante actuar rápidamente y de manera adecuada para brindar atención médica y apoyar a las víctimas. Aquí te presento algunos de los primeros pasos que debes seguir:
    
    1. **Llamar a la emergencia**: Si no has llamado ya, llama a los servicios de emergencia (como el 911 en Estados Unidos o el 112 en Europa) y proporciona toda la información posible sobre el accidente.
    2. **Evaluar la situación**: Asegúrate de que estás en un lugar seguro y alejado del tráfico. Si es posible, intenta evaluar la gravedad de los heridos y determinar cuántas personas están involucradas.
    3. **Apoyar a las víctimas**: Si es posible, apoya a las víctimas sin poner en peligro tu propia seguridad. Intenta mantenerlas calmadas y tranquilas hasta que lleguen los servicios de emergencia.
    4. **Reunir información**: Recopila toda la información posible sobre el accidente, como:
     * La ubicación exacta del accidente
     * El número de vehículos involucrados
     * Las características de los vehículos (marca, modelo, color)
     * La velocidad a la que se movían los vehículos antes del accidente
     * Si hubo testigos o personas que puedan proporcionar información adicional
    5. **No mover a las víctimas**: A menos que sea absolutamente necesario para evitar un mayor daño, no muevas a las víctimas desde su posición actual. Esto puede causar más daño y complicar la atención médica.
    6. **Brindar información al personal de emergencia**: Cuando lleguen los servicios de emergencia, proporciona toda la información que hayas recopilado sobre el accidente y las víctimas.
    7. **Mantener a las víctimas calmas y tranquilas**: Intenta mantener a las víctimas calmadas y tranquilas hasta que lleguen los servicios de emergencia. Esto puede ayudar a reducir su estrés y ansiedad.
    
    Recuerda que la seguridad es lo más importante en un accidente vial. Si no estás seguro de qué hacer, siempre es mejor errar en el lado de la precaución y buscar ayuda profesional.

  Probando llama3.2:3b [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [2] LLAMA3.2:3B — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  337 ms
  Tiempo total:         1.65 s
  Tokens generados:     97
  Velocidad:            73.7 tok/s
  Sigue protocolo:      SI

  Respuesta:

    Según el protocolo, en esta situación, debes seguir las instrucciones de FASE 1 - TOMA DE CONOCIMIENTO:
    
    1. Registrar ubicación exacta del siniestro y cantidad de lesionados.
    2. Evaluar riesgos secundarios (derrames, incendios, tráfico).
    3. Brindar auxilio médico primario.
    
    No mover a lesionados salvo peligro inmediato.

  Probando phi3.5 [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [3] PHI3.5 — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  4955 ms
  Tiempo total:         23.40 s
  Tokens generados:     512
  Velocidad:            27.8 tok/s

  Respuesta:

    En caso de encontrarse ante un accidente vial con lesionados, es crucial actuar rápidamente y responsablemente para minimizar daños adicionales y asegurar una atenzymedio adecuada. Aquí están los primeros pasos que se pueden seguir:
    
    1. **Apoya al Herido**: Si estás seguro, ayuda al herido manteniéndolo lo más quieto posible para evitar lesiones adicionales y reduce el riesgo de shock. Usa tu cuerpo o cualquier objeto disponible como una barrera protectora entre ellos y la superficie dura si están expuestos a ella.
    
    2. **Ponte los Guantes**: Si tienes guantes, póntelos para evitar posibles infecciones cruzadas por sangre u otros fluidos corporales.
    
    3. **Evalúa la Situación de Seguridad**: Asegúrate que el lugar sea seguro tanto para ti como los heridos antes de intentar moverlos o hacer más contacto físico, ya que esto podría causarte daño si hay peligro inmediato presente.
    
    4. **Llama a la Cruz Roja**: Contacta con las autoridades médicas locales llamando al número nacional de emergencias (como 911 en los Estados Unidos) para pedir ayuda lo antes posible, proporcionándoles información precisa sobre el lugar y la situación.
    
    5. **Proporciona Información**: Cuando lleguen las autoridades o mientras esperan su arribo, infórmales de cualquier detalles relevantes como los síntomas del herido (dolor en el pecho, sangrado severo), posibles lesiones visibles y si conoces la historia médica pasada del individuo.
    
    6. **No Intentes Reposicionar o Mover al Herido**: A menos que sea necesario para evitar un peligro inmediato (como una llama encendida, agua entrando en el lugar), no intentes mover a los heridos ya que esto podría causarte lesiones y empeorar su condición.
    
    7. **Proporciona Comfort Emocional**: Mantén al individuo calmado mientras esperan la

  Probando phi3.5 [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [4] PHI3.5 — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  383 ms
  Tiempo total:         11.10 s
  Tokens generados:     276
  Velocidad:            25.8 tok/s
  Sigue protocolo:      SI

  Respuesta:

    Según el protocolo proporcionado, estos son los pasos que debes seguir:
    
    1. FASE 1 - TOMA DE CONOCIMIENTO: Ya has llegado a la escena del siniestro y descubierto que hay 2 heridos involucidos. Esta información registra el número de lesionados.
    
    2. FASE 2 - ARRIBO AL LUGAR: Aunque no se especifica, según este paso, debes evaluar cualquier riesgo secundario como derrames, incendios o peligro en tráfico antes de proceder más.
    
    3. FASE 3 - INTERVENCIÓN: Comienza a brindar auxilio médico primario y estabilizar los heridos graves. Recuerda no mover a los lesionados, excepto si hay un peligro inmediato que justifique dicha acción.
    
    Por lo tanto, basándote en el protocolo dado, deberías comenzar la intervención médica directamente en la escena mientras evalúas cualquier riesgo secundario potencial y solo mueves a los lesionados si hay una razón inmediata para hacerlo.

  Probando qwen2.5:3b [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [5] QWEN2.5:3B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  5454 ms
  Tiempo total:         11.03 s
  Tokens generados:     403
  Velocidad:            72.3 tok/s

  Respuesta:

    En situaciones de emergencia como este, es importante mantener la calma y actuar rápidamente para ayudar a las personas involucradas. Aquí hay algunos pasos que se pueden seguir:
    
    1. **Seguridad Primaria**: Asegúrate de tu propia seguridad antes de intervenir en una situación de accidente. Si el accidente está causando peligro, como un incendio o explosión, evita la zona y llama a las autoridades.
    
    2. **Llama al 112 (o similar):** Llama inmediatamente a los servicios de emergencia locales para solicitar ayuda médica y policía si es necesario.
    
    3. **Evita el Accidente**: Si no hay peligro inminente, intenta evitar que la situación se vuelva peor mientras esperas a las autoridades. Por ejemplo, si un vehículo está atrapado en otro vehículo, asegúrate de que nadie entre o salga del vehículo para evitar más daños.
    
    4. **Ayuda Médica**: Si los servicios de emergencia no llegan de inmediato y hay personas heridas, proporciona ayuda básica mientras esperas a la ambulancia. Esto puede incluir controlar hemorragias, mantener a las personas en posición segura o ayudar a que se sienten cómodos.
    
    5. **Documentación**: Si es posible, documenta el accidente con fotos y nota cualquier información relevante como nombres de los involucrados, números de placas de identificación del vehículo, etc., para facilitar la investigación posterior.
    
    6. **Cooperación con las Autoridades**: Cuando lleguen los servicios de emergencia, asegúrate de cooperar completamente con ellos. Proporciona toda la información que puedas sobre el accidente y cualquier detalle relevante.
    
    Recuerda siempre mantener tu seguridad como prioridad en situaciones de emergencia.

  Probando qwen2.5:3b [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [6] QWEN2.5:3B — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  286 ms
  Tiempo total:         3.80 s
  Tokens generados:     258
  Velocidad:            73.4 tok/s
  Sigue protocolo:      SI

  Respuesta:

    Según el protocolo oficial proporcionado:
    
    FASE 1 - TOMA DE CONOCIMIENTO: Registrar ubicación exacta del siniestro y cantidad de lesionados.
    - Luego de llegar al lugar del accidente, registrar la ubicación precisa del accidente y confirmar que hay dos heridos.
    
    FASE 2 - ARRIBO AL LUGAR: Evaluar riesgos secundarios (derrames, incendios, tráfico).
    - Realizar una evaluación rápida para identificar si existen riesgos secundarios como derrames de vehículos, posibles incendios o problemas con el tráfico que puedan poner en peligro a los heridos o a los rescatistas.
    
    FASE 3 - INTERVENCIÓN: Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.
    - Brindar auxilio médico primario a los dos heridos en el lugar, aplicando técnicas de primeros auxilios si es necesario. 
    - Establecer la estabilidad de los heridos graves sin moverlos, a menos que sea necesario para evitar un peligro inminente.

  Probando ministral-3:3b [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [7] MINISTRAL-3:3B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  9026 ms
  Tiempo total:         28.07 s
  Tokens generados:     512
  Velocidad:            26.9 tok/s

  Respuesta:

    Si hay un accidente vial con heridos, es importante actuar rápidamente y seguir estos pasos básicos para garantizar su seguridad y atención médica adecuada:
    
    ### **1. Mantener la calma y evaluar el escenario**
    - **No se acerque a los heridos** si no está seguro de que sea seguro hacerlo (por ejemplo, por riesgo de más accidentes o explosiones).
    - Si hay fuego, humo o gases tóxicos, aléjese del área.
    
    ### **2. Evitar riesgos adicionales**
    - **Apagar el vehículo** si es posible y activar las luces de emergencia.
    - **No mover a los heridos** a menos que haya un peligro inmediato (ej.: riesgo de incendio, colapso de estructura).
    - Si hay niños o personas con movilidad reducida, priorice su seguridad.
    
    ### **3. Actuar según el nivel de gravedad**
    #### **Si hay heridos graves (con pérdida de conciencia, hemorragias severas, fracturas expuestas):**
    ✅ **Llamar a emergencias** (112 en España, 911 en EE.UU., 061 en México, etc.).
    ✅ **Comunicar el número de heridos y su estado** al servicio médico.
    ✅ **No moverlos sin ayuda profesional**, pero si es necesario para evitar más daño (ej.: bloquear un paso de tráfico), hazlo con cuidado.
    
    #### **Si hay heridos leves o no críticos:**
    - **Dar primeros auxilios básicos**:
      - **Hemorragias**: Presionar firmemente con una gasa estéril y elevar la extremidad si es posible.
      - **Traumatismos**: Inmovilizar la zona afectada (ej.: fracturas de muñeca o tobillo).
      - **Conciencia alterada**: Mantener al herido en posición lateral segura (si está inconsciente pero respirando).
    
    ### **4. Ayudar a los servicios de emergencia**
    - **Indicar el lugar exacto** del accidente (coordenadas GPS si es posible).
    - **Describir el número y estado de heridos** (ej.: "1 persona con fractura en brazo, otra con hemorragia").
    - **No mover objetos peligrosos** (gasolina, químicos) sin supervisión.
    
    ### **5. Después del accidente**
    - Si los servicios médicos llegan, **deja que ellos tomen las decisiones**.
    - Si hay

  Probando ministral-3:3b [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [8] MINISTRAL-3:3B — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  473 ms
  Tiempo total:         5.47 s
  Tokens generados:     135
  Velocidad:            27.0 tok/s
  Sigue protocolo:      SI

  Respuesta:

    **Según el protocolo oficial:**
    
    1. **FASE 1 - TOMA DE CONOCIMIENTO:**
       Registra la ubicación exacta del siniestro y verifica que haya **dos lesionados**.
    
    2. **FASE 2 - ARRIBO AL LUGAR:**
       Evalúa riesgos secundarios (ej.: derrames de líquidos, incendios o tráfico en el área).
    
    3. **FASE 3 - INTERVENCIÓN:**
       Brinda auxilio médico primario y estabiliza a los heridos graves.
       **No muevas a los lesionados salvo que haya un peligro inmediato.**

  Probando llama3:8b [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [9] LLAMA3:8B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  9951 ms
  Tiempo total:         57.77 s
  Tokens generados:     512
  Velocidad:            10.7 tok/s

  Respuesta:

    En caso de un accidente vial con heridos, es fundamental actuar con rapidez y eficiencia para minimizar el daño y garantizar la atención médica adecuada a las víctimas. A continuación, te presento los primeros pasos que debes seguir:
    
    1. **Llamar al 911 o número de emergencia**: Si se produce un accidente vial en Estados Unidos, llama al 911 (o al número de emergencia correspondiente en tu país). Informa a la centralita sobre el lugar y la gravedad del accidente.
    2. **Evalúa la situación**: Antes de intervenir, evalúa la situación para determinar si hay peligro inminente o si las víctimas necesitan atención médica urgente.
    3. **Protege a las víctimas**: Si es seguro hacerlo, intenta proteger a las víctimas del tráfico y de posibles daños adicionales. Mueve los vehículos involucrados lo más lejos posible de la carretera principal, si es necesario.
    4. **Aplica primeros auxilios básicos**: Si tienes formación en primeros auxilios, intenta ayudar a las víctimas que no estén gravemente heridas. Aplica los siguientes pasos:
    	* Controla la hemorragia (si es posible).
    	* Alivia el dolor y la ansiedad.
    	* Mantiene a las víctimas calientes y cómodas.
    5. **No muevas a las víctimas**: A menos que sea absolutamente necesario, no te acerques a las víctimas heridas ni les desplaces. Puedes hacer más daño si no tienes la formación adecuada o si no estás equipado para manejar una situación de emergencia.
    6. **Espera a los servicios médicos**: Una vez que hayas aplicado primeros auxilios básicos, espera a que lleguen los servicios médicos (ambulancias, bomberos, etc.). No intentes mover a las víctimas ni tratar de curarlas tú mismo.
    7. **Coopera con los servicios médicos**: Cuando los servicios médicos lleguen, coopera con ellos y proporciona información sobre la situación y el estado de las víctimas.
    
    Recuerda que, en caso de un accidente vial, la seguridad es

  Probando llama3:8b [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [10] LLAMA3:8B — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  704 ms
  Tiempo total:         6.86 s
  Tokens generados:     67
  Velocidad:            10.9 tok/s
  Sigue protocolo:      SI

  Respuesta:

    Según el protocolo, la respuesta correcta sería:
    
    FASE 1 - TOMA DE CONOCIMIENTO: Registrar ubicación exacta del siniestro y cantidad de lesionados.
    
    En este caso, registrar que hay un accidente vial con 2 heridos en una ubicación específica.

  Probando gemma2:2b [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [11] GEMMA2:2B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  5865 ms
  Tiempo total:         11.97 s
  Tokens generados:     482
  Velocidad:            79.0 tok/s

  Respuesta:

    Un accidente vial con heridos es una situación extremadamente seria que requiere actuar con rapidez y precaución. Aquí te presento algunos pasos a seguir:
    
    **1. Seguridad:**
    
    * **Evalúa la escena:** Asegúrate de que la zona sea segura para ti y otros antes de proceder. 
    * **Respeta las señales de tráfico:** Si hay señalización de emergencia, sigue sus instrucciones.
    * **Utiliza luces de emergencia:** Si es posible, enciende las luces de emergencia en tu vehículo para alertar a otros conductores.
    
    **2. Ayuda a los heridos:**
    
    * **Verifica la seguridad de todos:** Asegúrate de que nadie esté herido gravemente antes de intentar ayudar a los demás.
    * **Evalúa las lesiones:**  Si es posible, examina las lesiones de los involucrados y proporciona ayuda básica si es necesario (por ejemplo, colocar una persona en posición cómoda o cubrirla con un paño). 
    * **Llama al servicio de emergencia:** Llama al número de emergencias local (como el 911 en Estados Unidos) para reportar el accidente.  
    
    **3. Mantén la calma y actúa con responsabilidad:**
    
    * **No te involucres en disputas:** Evita confrontar a los involucrados o discutir responsabilidades hasta que llegue la policía.
    * **Mantente seguro:** No te arriesgues a tu propia seguridad al intentar ayudar a otros. 
    * **Documenta el accidente:** Si es posible, toma fotos de la escena del accidente para documentarlo.
    
    **4. Informa a las autoridades:**
    
    * **Denuncia el accidente:** Una vez que los servicios de emergencia lleguen, informa a las autoridades sobre el accidente y cualquier información relevante (por ejemplo, nombres de los involucrados).
    * **Cooperación con la policía:**  Sigue las instrucciones de la policía y proporciona toda la información necesaria para la investigación.
    
    
    **Recuerda:**
    
    * **Tu seguridad es lo primero.** No te arriesgues a tu propia seguridad al intentar ayudar a otros. 
    * **Mantén la calma y actúa con responsabilidad.** 
    * **Llama al servicio de emergencia inmediatamente.**  
    * **Documenta el accidente.** 
    
    
    Es importante destacar que estos son solo pasos generales, y las acciones específicas pueden variar según la situación del accidente. Siempre es mejor buscar ayuda profesional en caso de duda o emergencia.

  Probando gemma2:2b [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [12] GEMMA2:2B — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  325 ms
  Tiempo total:         1.51 s
  Tokens generados:     95
  Velocidad:            80.4 tok/s
  Sigue protocolo:      SI

  Respuesta:

    1. **FASE 1 - TOMA DE CONOCIMIENTO:** Registrar ubicación exacta del siniestro y cantidad de lesionados (2).
    2. **FASE 2 - ARRIBO AL LUGAR:** Evaluar riesgos secundarios (derrames, incendios, tráfico).
    3. **FASE 3 - INTERVENCIÓN:** Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.

  Probando gemma3:4b [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [13] GEMMA3:4B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  11371 ms
  Tiempo total:         37.77 s
  Tokens generados:     512
  Velocidad:            19.4 tok/s

  Respuesta:

    Un accidente vial con heridos es una situación de emergencia que requiere actuar con rapidez y calma. Aquí te detallo los primeros pasos a seguir, priorizando la seguridad y el bienestar de todos:
    
    **1. Asegurar la Seguridad del Lugar:**
    
    *   **Detenerse:** Lo primero es frenar inmediatamente y detenerte en un lugar seguro, lejos del tráfico.
    *   **Encender las luces de emergencia (intermitentes):** Esto alerta a otros conductores sobre el accidente.
    *   **Posicionar el vehículo:** Si es posible y seguro hacerlo, mueve tu vehículo a un lugar fuera del flujo del tráfico, preferiblemente en una zona segura y nivelada.  Si no puedes moverlo, activa las luces de emergencia y mantén la distancia máxima posible del otro tráfico.
    *   **Advertir al Tráfico:** Coloca señales reflectantes (triángulos de advertencia) a una distancia adecuada para alertar a otros conductores sobre el peligro. La distancia recomendada suele ser de 30-50 metros, dependiendo de las condiciones de visibilidad. Si hay mucho tráfico, considera poner la benzinera del vehículo en marcha.
    *   **Evaluar el riesgo:** Observa si hay peligros adicionales como cables eléctricos caídos, fugas de combustible o materiales peligrosos.
    
    **2. Asistencia a los Heridos (Prioridad Máxima):**
    
    *   **Verificar el estado de conciencia:** Pregunta a las personas atrapadas si están bien y si pueden moverse.
    *   **Llamar al 112 (o número de emergencias local):**  Es crucial informar inmediatamente sobre el accidente, indicando la ubicación exacta, el tipo de incidente, el número de heridos y cualquier otra información relevante.  No cuelgues hasta que te indiquen lo contrario.
    *   **Primeros Auxilios (si estás capacitado):** Si tienes conocimientos en primeros auxilios, puedes intentar ayudar a los heridos mientras esperas la llegada de los servicios de emergencia.  Sin embargo, **no muevas a las personas heridas a menos que sea absolutamente necesario para evitar un peligro inminente.**
        *   **Controla hemorragias:** Aplica presión directa sobre las heridas con un paño limpio o gasa.
        *   **Mantén la calma y consuela a los heridos:**  Trata de tranquilizarlos y mantenerlos cómodos hasta que llegue ayuda profesional.
        *   **No

  Probando gemma3:4b [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [14] GEMMA3:4B — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  814 ms
  Tiempo total:         3.92 s
  Tokens generados:     63
  Velocidad:            20.3 tok/s
  Sigue protocolo:      SI

  Respuesta:

    1.  Registrar ubicación exacta del siniestro y cantidad de lesionados.
    2.  Evaluar riesgos secundarios (derrames, incendios, tráfico).
    3.  Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.

  Probando qwen2.5:1.5b [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [15] QWEN2.5:1.5B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  2968 ms
  Tiempo total:         10.31 s
  Tokens generados:     434
  Velocidad:            59.1 tok/s

  Respuesta:

    En caso de un accidente vial con heridos, aquí están algunos pasos importantes que debes seguir:
    
    1. **Seguridad para ti mismo y otros**: Si estás en la escena del accidente, asegúrate de mantener tu seguridad al evitar cualquier riesgo adicional.
    
    2. **Alertar a los demás**: Llama a emergencias (911 o 0) si es necesario. Explica el problema y avísalo que hay heridos.
    
    3. **Evitar la confusión**: Mantén la calma para poder ayudar eficazmente a las personas afectadas por el accidente.
    
    4. **Identificar los heridos**: Asegúrate de identificar cuáles son las personas más graves y necesitan atención médica inmediata.
    
    5. **Evitar movimientos bruscos**: Evita mover a las personas si no es necesario para su seguridad o la de otros.
    
    6. **Asegurarte de que los heridos están seguros antes de moverlos**: Si hay heridos, asegúrate de mantenerlos en posición cómoda y sin riesgo.
    
    7. **Lleva a los heridos al hospital**: Si es posible, lleva a las personas más graves al hospital lo antes posible para recibir atención médica.
    
    8. **Reporta el accidente**: Luego del incidente, reporta el accidente a la policía o a la autoridad local si se trata de un accidente grave o mortal.
    
    9. **Lleva una descripción detallada del accidente**: Si es posible, recopila información sobre el lugar del accidente y las circunstancias que podrían ser útiles para la investigación policial.
    
    10. **Contacta a los familiares de los heridos**: Luego del incidente, comunica con los familiares de las personas afectadas por el accidente para informarles lo sucedido.
    
    Recuerda siempre mantener tu seguridad y la de otros en primer lugar, pero también es importante ayudar a las personas que han sido impactadas.

  Probando qwen2.5:1.5b [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [16] QWEN2.5:1.5B — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  269 ms
  Tiempo total:         6.27 s
  Tokens generados:     355
  Velocidad:            59.2 tok/s
  Sigue protocolo:      SI

  Respuesta:

    Según el protocolo oficial:
    
    1. **Toma de Conocimiento**: 
       - Registrar ubicación exacta del siniestro y cantidad de lesionados.
       
    2. **Arrivo al Lugar**:
       - Evaluar riesgos secundarios (derrames, incendios, tráfico).
       - Si hay peligro inmediato o riesgo significativo, tomar medidas para minimizar el daño.
    
    3. **Intervención**: 
       - Brindar auxilio médico primario.
       - Estabilizar heridos graves.
       - No mover a lesionados salvo peligro inmediato.
    
    Basándome en estos pasos y teniendo en cuenta que hay 2 heridos, aquí es cómo procedería:
    
    1. **Toma de Conocimiento**: 
       - Registrar la ubicación exacta del accidente vial.
       - Establecer el número total de lesionados: 2.
    
    2. **Arrivo al Lugar**:
       - Evaluar si hay riesgos secundarios, como derrames o incendios potenciales.
       - Si se detectan riesgos significativos, tomar medidas para minimizarlos (por ejemplo, cerrar la avenida afectada).
    
    3. **Intervención**: 
       - Brindar auxilio médico primario: atención básica y primeros auxilios.
       - Estabilizar heridos graves: asegurarse de que los lesionados sean transportados en un vehículo seguro para su traslado al hospital.
    
    Es importante recordar siempre la seguridad del personal y evitar mover a las personas afectadas, especialmente si se sospecha una lesión grave.

  Probando phi4-mini [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [17] PHI4-MINI — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  20909 ms
  Tiempo total:         30.23 s
  Tokens generados:     350
  Velocidad:            37.5 tok/s

  Respuesta:

    Si se encuentra en una situación de emergencia, como un accidente vial con heridos, es crucial mantener la calma y tomar las siguientes acciones:
    
    1. **Llama a servicios médicos de emergencia**: Hazlo inmediatamente llamando al número de emergencia local (como 911 en Estados Unidos o el equivalente correspondiente en tu país). Proporciona toda la información posible sobre la ubicación del accidente.
    
    2. **Mantén la seguridad**: Si es seguro, dirígete hacia donde se encuentran los heridos para proporcionar asistencia hasta que lleguen las autoridades y los servicios médicos de emergencia. Sin embargo, no te arriesques a más lesiones si el camino está peligroso o hay riesgo de otro accidente.
    
    3. **Evita cruzar la carretera**: Si es posible, evita cruzar la vía del tráfico en caso de estar cerca del lugar del accidente para evitar causar otra colisión con vehículos que puedan llegar al área.
    
    4. **Apoya a los heridos si puedes hacerlo sin peligro**: Una vez lleguen las autoridades y los servicios médicos de emergencia, haz lo mejor posible para ayudar según tus habilidades (por ejemplo, proporcionar primeros auxilios básicos como presión en el punto de sangrado o mantenerlos calientes) hasta que llegue la ayuda profesional.
    
    5. **No interrumpas a los profesionales de emergencias**: Si llegan los bomberos, paramédicos u oficiales de policía, deja que ellos tomen control del área y sigan sus instrucciones sin interferir con su trabajo.
    
    Recuerda, tu prioridad debe ser llamar al número de emergencia lo antes posible para recibir asistencia profesional. No intentes manejar las lesiones tú mismo si no tienes formación en primeros auxilios; es mejor dejarlo a los profesionales capacitados.

  Probando phi4-mini [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [18] PHI4-MINI — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  384 ms
  Tiempo total:         3.43 s
  Tokens generados:     115
  Velocidad:            37.8 tok/s
  Sigue protocolo:      SI

  Respuesta:

    Basado en el protocolo oficial proporcionado:
    
    FASE 1 - TOMA DE CONOCIMIENTO:
    - Registrar ubicación exacta del siniestro.
    - Contar y registrar cantidad de lesionados (en este caso, 2).
    
    FASE 2 - ARRIBO AL LUGAR: 
    - Evaluar riesgos secundarios como derrames, incendios o tráfico.
    
    FASE 3 - INTERVENCIÓN:
    - Brindar auxilio médico primario a los heridos.
    - Estabilizar heridos graves sin moverlos salvo peligro inmediato.


════════════════════════════════════════════════════════════
  RESUMEN COMPARATIVO
════════════════════════════════════════════════════════════
  Modelo             Prompt              TTFT    Total    tok/s  Protocolo
  ────────────────── ─────────────── ──────── ──────── ──────── ──────────
  llama3.2:3b        SIN CONTEXTO       6160ms    13.1s    73.1          —
  llama3.2:3b        CON CONTEXTO        337ms     1.7s    73.7         SI
  phi3.5             SIN CONTEXTO       4955ms    23.4s    27.8          —
  phi3.5             CON CONTEXTO        383ms    11.1s    25.8         SI
  qwen2.5:3b         SIN CONTEXTO       5454ms    11.0s    72.3          —
  qwen2.5:3b         CON CONTEXTO        286ms     3.8s    73.4         SI
  ministral-3:3b     SIN CONTEXTO       9026ms    28.1s    26.9          —
  ministral-3:3b     CON CONTEXTO        473ms     5.5s    27.0         SI
  llama3:8b          SIN CONTEXTO       9951ms    57.8s    10.7          —
  llama3:8b          CON CONTEXTO        704ms     6.9s    10.9         SI
  gemma2:2b          SIN CONTEXTO       5865ms    12.0s    79.0          —
  gemma2:2b          CON CONTEXTO        325ms     1.5s    80.4         SI
  gemma3:4b          SIN CONTEXTO      11371ms    37.8s    19.4          —
  gemma3:4b          CON CONTEXTO        814ms     3.9s    20.3         SI
  qwen2.5:1.5b       SIN CONTEXTO       2968ms    10.3s    59.1          —
  qwen2.5:1.5b       CON CONTEXTO        269ms     6.3s    59.2         SI
  phi4-mini          SIN CONTEXTO      20909ms    30.2s    37.5          —
  phi4-mini          CON CONTEXTO        384ms     3.4s    37.8         SI
════════════════════════════════════════════════════════════
