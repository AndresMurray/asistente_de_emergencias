python benchmark.py

════════════════════════════════════════════════════════════
  BENCHMARK LLM LOCAL — RAG Emergencias Viales
════════════════════════════════════════════════════════════
  Modelos: llama3.2:3b, phi3.5, qwen2.5:3b, ministral-3:3b, llama3:8b, gemma2:2b
  Endpoint: http://localhost:11434/api/generate
  Cada modelo se prueba con y sin contexto de protocolo.
════════════════════════════════════════════════════════════

  Probando llama3.2:3b [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [1] LLAMA3.2:3B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  5948 ms
  Tiempo total:         12.85 s
  Tokens generados:     512
  Velocidad:            74.2 tok/s

  Respuesta:

    En caso de un accidente vial con heridos, es importante actuar rápidamente y de manera adecuada para brindar atención médica y apoyar a las víctimas. Aquí te presento algunos de los primeros pasos que debes seguir:
    
    1. **Llamar a la emergencia**: Si no has llamado ya, llama a los servicios de emergencia (como el 911 en Estados Unidos o el 112 en Europa) para informar sobre el accidente y pedir ayuda.
    2. **Evaluar la situación**: Asegúrate de que estás en un lugar seguro y alejado del tráfico. Evalúa la gravedad de los heridos y busca ayuda si es necesario.
    3. **Aplicar primeros auxilios**: Si no hay nadie capacitado para aplicar primeros auxilios, puedes aprender a hacerlo básicamente. Esto incluye:
     * Aplicar presión en heridas abiertas para detener la hemorragia.
     * Comprobar el pulso y la respiración de las víctimas.
     * Buscar signos de vida (como movimientos, respuestas o sonidos).
    4. **Mantener a las víctimas calmadas**: A veces, las víctimas pueden entrar en shock o perder la conciencia. Manténlas calmas y tranquilas para ayudarles a recuperarse.
    5. **No moverse a menos que sea necesario**: Si no hay riesgo de que las víctimas se hagan daño más grave, es mejor no moverlas hasta que llegue el equipo médico.
    6. **Proteger la cabeza y el cuello**: Si una víctima tiene lesiones en la cabeza o el cuello, es importante protegerla para evitar que se haga daño más grave.
    7. **Mantener a las víctimas informadas**: Asegúrate de que las víctimas estén informadas sobre lo que está sucediendo y qué pasará a continuación.
    8. **No dejar a las víctimas solas**: Mantén a las víctimas con ti hasta que llegue el equipo médico o alguien más pueda ayudarlas.
    
    Recuerda que, en caso de un accidente vial, es importante actuar rápidamente y de manera adecuada para brindar atención médica y apoyar a las ví

  Probando llama3.2:3b [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [2] LLAMA3.2:3B — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  314 ms
  Tiempo total:         1.60 s
  Tokens generados:     97
  Velocidad:            75.4 tok/s
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
  TTFT (primer token):  5501 ms
  Tiempo total:         23.85 s
  Tokens generados:     512
  Velocidad:            27.9 tok/s

  Respuesta:

    En caso de encontrarse ante un accidente vial con lesionados, es crucial actuar rápidamente y responsablemente para minimizar daños adicionales e intentar proporcionar la ayuda necesaria. Aquí están los principales pasos a seguir:
    
    1. **Asegúrate de que sea seguro**: Antes de acercarse, verifica si el lugar es seguro tanto para ti como para las víctimas; evita entrar en una situación peligrosa por tu cuenta. Si hay riesgo inminente (por ejemplo, vehículos aún moviéndose), espera la llegada de los servicios adecuados o busca refugio seguro cerca donde puedas observar sin interferir con el lugar del accidente.
    
    2. **Llame al 911**: Contactar inmediatamente a las autoridades es fundamental, ya que ellos pueden enviar ayuda especializada y establecer la escena de manera segura para todos los involucrados. Informa con precisión sobre el número exacto de heridos, posibles lesiones graves o accidentes mortales e indica si hay riesgo inmediato (como fuego u otra emergencia).
    
    3. **Proporcionar asistencia**: Una vez que sea seguro y las autoridades estén en camino, puedes ofrecer ayuda directamente a los heridos siempre y cuando no te pongas en riesgo personal ni interfieras con el trabajo de profesionales médicos. Esto puede incluir proporcionar ropa o mantas para cubrir lesiones abiertas (siempre que sea seguro hacerlo sin tocar directamente a las víctimas), ofrecer palabras reconfortantes y ayudarles hasta la llegada del personal de emergencia.
    
    4. **Crea una barrera física**: Si es necesario, establece un área protegida para mantener el orden en la escena e impedir que más vehículos o personas entren al lugar sin autorización y pongan aún más lesionados en peligro.
    
    5. **Proporciona información relevante**: Si conoces detalles sobre los involucrados, como sus nombres u otra identificación

  Probando phi3.5 [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [4] PHI3.5 — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  377 ms
  Tiempo total:         8.89 s
  Tokens generados:     233
  Velocidad:            27.4 tok/s
  Sigue protocolo:      SI

  Respuesta:

    Según el protocolo oficial:
    
    1. FASE 1 - TOMA DE CONOCIMIENTO: Ya has llegado a la escena del siniestro y ha notado que hay 2 lesionados, lo cual cumple con esta fase.
    2. FASE 2 - ARRIBO AL LUGAR: Ahora, debe evaluar los riesgos secundarios como derrames, incendios o tráfico en la escena del accidente.
    3. FASE 3 - INTERVENCIÓN: Después de asegurarse que no hay riesgos adicionales, proceder con brindar auxilio médico primario y estabilización de los heridos graves. Solo mover a lesionados si hay peligro inmediato.
    
    Por lo tanto, su próximo paso es evaluar cualquier posible riesgo secundario en la escena del accidente antes de intervenir directamente con el cuidado médico primario y estabilización de los heridos graves.

  Probando qwen2.5:3b [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [5] QWEN2.5:3B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  5261 ms
  Tiempo total:         11.68 s
  Tokens generados:     477
  Velocidad:            74.3 tok/s

  Respuesta:

    En caso de un accidente vial con heridos, es importante seguir estos pasos inmediatos:
    
    1. **Seguridad Primaria**: Asegúrate de que tú y cualquier persona más cerca del lugar estás seguros antes de ayudar a otros. Si el vehículo está en marcha o si hay riesgo de colisión, asegúrate de que todos los ocupantes salgan del vehículo.
    
    2. **Llamada de Emergencia**: Llama al servicio de emergencias locales (como 911 en Estados Unidos) inmediatamente para solicitar ayuda médica y policíaca. Explica la situación lo mejor posible, incluyendo el número de tu llamada si es necesario para rastrearla.
    
    3. **Evita Moverte**: Si no hay riesgo de colisión o accidente adicional, intenta mantener el vehículo en su lugar hasta que lleguen los servicios de emergencia. Esto puede ayudar a los médicos y policías a determinar la naturaleza del incidente más fácilmente.
    
    4. **Identifica a las Partes Involved**: Si es seguro hacerlo, identifica a todas las personas involucradas en el accidente, incluyendo conductores de otros vehículos si hay varios. También busca cualquier testigo que pueda ayudar a describir lo que ocurrió.
    
    5. **No Hacer Conjeturas o Juzgados**: No hagas suposiciones sobre quién es culpable del accidente. Esto puede ser confuso para las autoridades y puede afectar la investigación posterior.
    
    6. **Documenta el Accidente**: Si es seguro hacerlo, toma fotos de los vehículos involucrados, cualquier daño a terrenos o estructuras cercanas, y cualquier persona que pueda estar relacionada con el accidente. Esto puede ser útil para las autoridades y en caso de reclamaciones futuras.
    
    7. **Contacta a un Asesor Legal**: Si hay heridos graves, es importante tener asesoramiento legal profesional sobre tus derechos y opciones legales.
    
    Recuerda siempre mantener tu seguridad y la de los demás en situaciones de emergencia.

  Probando qwen2.5:3b [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [6] QWEN2.5:3B — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  372 ms
  Tiempo total:         8.70 s
  Tokens generados:     235
  Velocidad:            39.9 tok/s
  Sigue protocolo:      SI

  Respuesta:

    Según el protocolo oficial proporcionado:
    
    FASE 1 - TOMA DE CONOCIMIENTO: Registrar ubicación exacta del siniestro y cantidad de lesionados.
    - Luego de llegar al lugar del accidente, registrar la ubicación precisa del accidente y confirmar que hay dos heridos.
    
    FASE 2 - ARRIBO AL LUGAR: Evaluar riesgos secundarios (derrames, incendios, tráfico).
    - Realizar un análisis rápido para identificar si existen riesgos secundarios como derrames de combustible, incendios o problemas de tráfico que puedan afectar a los heridos.
    
    FASE 3 - INTERVENCIÓN: Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.
    - Brindar auxilio médico primario a los dos heridos. Tratar lesiones externas y posibles fracturas. Establecer la estabilidad de los heridos graves si es necesario, pero no moverlos hasta que no sea seguro hacerlo.

  Probando ministral-3:3b [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [7] MINISTRAL-3:3B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  8887 ms
  Tiempo total:         28.13 s
  Tokens generados:     512
  Velocidad:            16.5 tok/s

  Respuesta:

    En caso de un accidente vial con heridos, es crucial actuar rápido y seguir estos pasos básicos para garantizar su seguridad y atención médica inmediata:
    
    ### **1. Mantener la calma y evaluar el escenario**
       - **No se muevan a menos que sea necesario**: Evitar movimientos bruscos puede empeorar lesiones.
       - **Verificar si hay víctimas con riesgo vital** (ej.: heridas en cabeza, cuello o columna, quemaduras graves, pérdida de conciencia).
    
    ### **2. Actuar según el nivel de gravedad**
    #### **Si hay heridos graves (con riesgo de muerte):**
       - **Llamar a emergencias** (112 en España, 911 en muchos países hispanohablantes).
         - Proporcionar detalles exactos: ubicación, número de víctimas, tipo de lesiones.
       - **Proteger al accidentado**:
         - Colocar un objeto duro bajo la cabeza si está inconsciente o con traumatismo craneoencefálico.
         - Evitar moverlo sin ayuda médica (riesgo de lesiones adicionales).
       - **Controlar sangrado**: Presionar firmemente con gasas estériles o paños limpios en zonas heridas.
    
    #### **Si hay heridos leves (heridas menores, fracturas no graves):**
       - **Dar primeros auxilios básicos**:
         - Lavar heridas con agua y jabón si es posible.
         - Aplicar vendaje limpio para evitar infecciones.
       - **Evitar mover a la persona** si hay sospecha de lesiones en columna (ej.: dolor al moverse).
    
    ### **3. Protección personal**
       - Usar chaleco reflectante o ropa brillante si no hay protección.
       - Colocar triángulos de advertencia (si es legal en tu zona) para alertar a otros conductores.
    
    ### **4. Coordinación con autoridades**
       - Si hay vehículos involucrados, **no se deben mover** hasta que llegue la policía o bomberos (puede haber riesgos eléctricos o químicos).
       - Registrar datos clave: placas de los coches, testigos, descripción del accidente.
    
    ---
    ### **¿Qué NO hacer?**
    ❌ **Mover a una víctima sin necesidad** (riesgo de lesiones adicionales).
    ❌ **Dar comida/agua** si está inconsciente o con traumatismo.
    ❌ **Ignorar heridas graves

  Probando ministral-3:3b [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [8] MINISTRAL-3:3B — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  664 ms
  Tiempo total:         11.20 s
  Tokens generados:     144
  Velocidad:            16.5 tok/s
  Sigue protocolo:      SI

  Respuesta:

    **Según el protocolo oficial:**
    
    1. **FASE 1 - TOMA DE CONOCIMIENTO:**
       Registra la ubicación exacta del siniestro y verifica que hay **dos lesionados**.
    
    2. **FASE 2 - ARRIBO AL LUGAR:**
       Evalúa riesgos secundarios (ej.: derrames de líquidos, incendios o tráfico en el área).
    
    3. **FASE 3 - INTERVENCIÓN:**
       Brinda auxilio médico primario y estabiliza a los heridos graves.
       **No muevas a las víctimas salvo que haya un peligro inmediato** (ej.: riesgo de colisión, incendio).

  Probando llama3:8b [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [9] LLAMA3:8B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  11854 ms
  Tiempo total:         53.12 s
  Tokens generados:     482
  Velocidad:            10.0 tok/s

  Respuesta:

    En caso de un accidente vial con heridos, es fundamental actuar con rapidez y eficiencia para minimizar el daño y proteger la vida de las personas involucradas. A continuación, te presento los primeros pasos a seguir:
    
    1. **Llamar al 911 o número de emergencia**: Si se encuentra en Estados Unidos, llama al 911. En otros países, llama al número de emergencia correspondiente (por ejemplo, 112 en Europa).
    2. **Evaluar la situación**: Antes de intervenir, evalúa la situación para determinar si hay personas heridas o peligro inminente.
    3. **Proteger el área**: Si es seguro hacerlo, intenta proteger el área del accidente vial para evitar que más personas se lesionen al acercarse.
    4. **Proporcionar primeros auxilios básicos**: Si tienes formación en primeros auxilios, proporciona ayuda básica a las personas heridas, como:
        * Controlar hemorragias con vendas o toallas limpias.
        * Aliviar el dolor y la ansiedad.
        * Mantener a los heridos cómodos y seguros.
    5. **No mover a los heridos**: A menos que sea absolutamente necesario, no te acerques a los heridos ni intentes moverlos. Pueden tener lesiones internas graves o ser peligroso para ti mismo.
    6. **Informar al personal de emergencia**: Cuando lleguen los servicios de emergencia, proporciona información clara y concisa sobre la situación:
        * Número de personas heridas.
        * Gravedad de las lesiones.
        * Ubicación exacta del accidente vial.
    7. **Permanecer en el lugar**: No te alejes del área del accidente vial hasta que los servicios de emergencia hayan llegado y evaluado la situación.
    
    Recuerda que, si no tienes formación en primeros auxilios o sientes que no estás capacitado para ayudar, es mejor esperar a que los profesionales de emergencia lleguen al lugar. La seguridad de las personas involucradas es lo más importante.

  Probando llama3:8b [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [10] LLAMA3:8B — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  712 ms
  Tiempo total:         18.48 s
  Tokens generados:     196
  Velocidad:            11.0 tok/s
  Sigue protocolo:      SI

  Respuesta:

    Según el protocolo, la primera fase es la Toma de Conocimiento, por lo que registra la ubicación exacta del siniestro y la cantidad de lesionados.
    
    Luego, pasa a la Fase 2 - Aribbo al Lugar, donde evalúas riesgos secundarios (derrames, incendios, tráfico).
    
    Finalmente, llegas a la Fase 3 - Intervención, donde brindas auxilio médico primario y estabilizas a los heridos graves. No mueves a los lesionados salvo peligro inmediato.
    
    En resumen:
    
    1. Registra ubicación exacta del siniestro y cantidad de lesionados.
    2. Evalúa riesgos secundarios (derrames, incendios, tráfico).
    3. Brinda auxilio médico primario y estabilizas a los heridos graves.

  Probando gemma2:2b [SIN CONTEXTO]...

────────────────────────────────────────────────────────────
  [11] GEMMA2:2B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  24090 ms
  Tiempo total:         30.28 s
  Tokens generados:     499
  Velocidad:            80.7 tok/s

  Respuesta:

    Un accidente vial con heridos es una situación extremadamente seria que requiere actuar con rapidez y cuidado. Aquí te presento los primeros pasos a seguir:
    
    **1. Seguridad:**
    
    * **Evalúa la escena:** Asegúrate de que la zona sea segura para ti y otros antes de intentar ayudar. 
    * **Activa las luces de emergencia:** Si es posible, enciende las luces de emergencia en tu vehículo para alertar a otros conductores.
    * **Presta atención a tu seguridad:** No te arriesgues a entrar en contacto con los vehículos o personas lesionadas si no estás seguro de la situación.
    
    **2. Ayuda a los heridos:**
    
    * **Evalúa la gravedad de las lesiones:** Si ves que alguien necesita ayuda inmediata, llama al 911 (o el número de emergencia local) y trata de mantener a la persona tranquila y segura.
    * **Si puedes, ofrece asistencia básica:**  
        * **Mantén la calma:** Habla con los heridos y trata de calmarlos.
        * **Revisa si hay heridas graves:** Busca signos de sangrado, dificultad para respirar o pérdida de conocimiento. 
        * **Presta atención a las necesidades básicas:** Si es posible, ofrece agua o comida a los heridos.
        * **No intentes mover a los heridos sin la ayuda de profesionales:**  Mover a un herido puede empeorar sus lesiones.
    
    **3. Llama al servicio de emergencia:**
    
    * **Llama al 911 (o el número de emergencia local) inmediatamente.**  
    * **Proporciona la ubicación exacta del accidente y la cantidad de personas heridas.**
    * **Mantén la calma y proporciona información precisa a los operadores.**
    
    **4. Mantente en la escena:**
    
    * **No te desvíes de la escena del accidente.** 
    * **Mantente en la zona hasta que llegue la policía y los servicios de emergencia.**
    * **Si es posible, ofrece información sobre las personas heridas a los agentes.**
    
    
    **Recuerda:**
    
    * **Tu seguridad y la de los demás es lo primero.**
    * **No intentes solucionar el problema por tu cuenta.** 
    * **Mantente calmado y actúa con prudencia.**
    * **Llama al servicio de emergencia inmediatamente.**
    
    
    Es importante que sepas que no estás solo. Hay personas capacitadas para ayudarte en situaciones como esta.  ¡Recuerda que la seguridad es lo primero!

  Probando gemma2:2b [CON CONTEXTO]...

────────────────────────────────────────────────────────────
  [12] GEMMA2:2B — CON CONTEXTO
────────────────────────────────────────────────────────────
  TTFT (primer token):  299 ms
  Tiempo total:         1.46 s
  Tokens generados:     95
  Velocidad:            81.7 tok/s
  Sigue protocolo:      SI

  Respuesta:

    1. **FASE 1 - TOMA DE CONOCIMIENTO:** Registrar ubicación exacta del siniestro y cantidad de lesionados (2).
    2. **FASE 2 - ARRIBO AL LUGAR:** Evaluar riesgos secundarios (derrames, incendios, tráfico).
    3. **FASE 3 - INTERVENCIÓN:** Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.


════════════════════════════════════════════════════════════
  RESUMEN COMPARATIVO
════════════════════════════════════════════════════════════
  Modelo             Prompt              TTFT    Total    tok/s  Protocolo
  ────────────────── ─────────────── ──────── ──────── ──────── ──────────
  llama3.2:3b        SIN CONTEXTO       5948ms    12.8s    74.2          —
  llama3.2:3b        CON CONTEXTO        314ms     1.6s    75.4         SI
  phi3.5             SIN CONTEXTO       5501ms    23.9s    27.9          —
  phi3.5             CON CONTEXTO        377ms     8.9s    27.4         SI
  qwen2.5:3b         SIN CONTEXTO       5261ms    11.7s    74.3          —
  qwen2.5:3b         CON CONTEXTO        372ms     8.7s    39.9         SI
  ministral-3:3b     SIN CONTEXTO       8887ms    28.1s    16.5          —
  ministral-3:3b     CON CONTEXTO        664ms    11.2s    16.5         SI
  llama3:8b          SIN CONTEXTO      11854ms    53.1s    10.0          —
  llama3:8b          CON CONTEXTO        712ms    18.5s    11.0         SI
  gemma2:2b          SIN CONTEXTO      24090ms    30.3s    80.7          —
  gemma2:2b          CON CONTEXTO        299ms     1.5s    81.7         SI
════════════════════════════════════════════════════════════
