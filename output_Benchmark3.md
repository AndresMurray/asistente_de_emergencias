python benchmark.py

════════════════════════════════════════════════════════════
  BENCHMARK LLM LOCAL — RAG Emergencias Viales
════════════════════════════════════════════════════════════
  Modelos: llama3.2:3b, phi3.5, qwen2.5:3b, ministral-3:3b, llama3:8b, gemma2:2b, gemma3:4b, qwen2.5:1.5b, phi4-mini, qwen3:8b
  Endpoint: http://localhost:11434/api/generate
  Repeticiones por condición: 3 (se reporta mediana)
  Warmup previo por modelo para excluir la carga a VRAM del TTFT.
════════════════════════════════════════════════════════════

  Cargando llama3.2:3b (warmup)...
  Probando llama3.2:3b [SIN CONTEXTO] corrida 1/3...
  Probando llama3.2:3b [SIN CONTEXTO] corrida 2/3...
  Probando llama3.2:3b [SIN CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [1] LLAMA3.2:3B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  256 ms
  Tiempo total:         6.62 s
  Velocidad:            75.0 tok/s

  Respuesta (primera corrida):

    En caso de un accidente vial con heridos, es importante actuar rápidamente y de manera adecuada para brindar atención médica y apoyar a las víctimas. Aquí te presento algunos de los primeros pasos que debes seguir:
    
    1. **Llamar a la emergencia**: Si no ya lo has hecho, llama a los servicios de emergencia (como el 911 en Estados Unidos o el 112 en Europa) y proporciona toda la información posible sobre el accidente.
    2. **Evaluar la situación**: Asegúrate de que estás en un lugar seguro y alejado del tráfico. Si es posible, intenta evaluar la gravedad de los heridos y determinar si alguien necesita atención médica inmediata.
    3. **Apoyar a las víctimas**: Si es posible, apoya a las víctimas sin poner en peligro tu propia seguridad. Puedes ofrecerles agua, ropa cómoda y cualquier otro recurso que puedan necesitar.
    4. **No mover a las víctimas**: A menos que sea absolutamente necesario para salvar una vida, no muevas a las víctimas desde su posición actual. Esto puede causar más daño y complicar la atención médica.
    5. **Reunir información**: Si es posible, recopila información sobre el accidente, como:
     * La ubicación exacta del accidente
     * El número de vehículos involucrados
     * Las características de los vehículos (marca, modelo, color)
     * La velocidad a la que se movían los vehículos antes del accidente
    6. **No dejar el lugar**: No te vayas del lugar del accidente hasta que la policía y los servicios de emergencia hayan llegado.
    7. **Brindar información a los servicios de emergencia**: Cuando llames a los servicios de emergencia, proporciona toda la información posible sobre el accidente y las víctimas.
    
    Recuerda que en caso de un accidente vial con heridos, es importante actuar rápidamente y de manera adecuada para brindar atención médica y apoyar a las víctimas.
  Probando llama3.2:3b [CON CONTEXTO] corrida 1/3...
  Probando llama3.2:3b [CON CONTEXTO] corrida 2/3...
  Probando llama3.2:3b [CON CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [2] LLAMA3.2:3B — CON CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  231 ms
  Tiempo total:         2.34 s
  Velocidad:            75.3 tok/s
  Sigue protocolo:      SI

  Respuesta (primera corrida):

    Según el protocolo, en esta situación, debes seguir las instrucciones de FASE 1 - TOMA DE CONOCIMIENTO:
    
    1. Registrar ubicación exacta del siniestro y cantidad de lesionados.
    
    2. Evaluar riesgos secundarios (derrames, incendios, tráfico).
    
    3. Brindar auxilio médico primario.
    
    4. Estabilizar heridos graves.
    
    5. No mover a lesionados salvo peligro inmediato.
    
    No hay indicación de qué hacer en FASE 2 - ARRIBO AL LUGAR ni en FASE 3 - INTERVENCIÓN, por lo que no puedo proporcionar una respuesta más detallada.

  Cargando phi3.5 (warmup)...
  Probando phi3.5 [SIN CONTEXTO] corrida 1/3...
  Probando phi3.5 [SIN CONTEXTO] corrida 2/3...
  Probando phi3.5 [SIN CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [3] PHI3.5 — SIN CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  188 ms
  Tiempo total:         18.62 s
  Velocidad:            27.8 tok/s

  Respuesta (primera corrida):

    En caso de encontrarse ante un accidente vehicular con lesionados, es crucial actuar rápidamente y responsablemente para garantizar la seguridad tanto del personal involucrado como a las víctimas. Aquí están los principales pasos que debe seguir:
    
    1. **Asegúrate de tu propia seguridad**: Antes de acercarse al lugar, confirme si es seguro hacerlo sin poner en riesgo su vida o la del personal médico llegando a él. Si el accidente está causando peligro para los conductores involucrados u otros usuarios de la vía pública (como peatones y ciclistas), espere que las autoridades intervengan antes de entrar en acción directa.
    
    2. **Llame a emergenmediate**: Contacte inmediatamente con los servicios médicos locales o llame al número de emergencia (como 911) para reportar el accidente y solicitar asistencia profesional lo antes posible, proporcionando una descripción precisa del lugar e indicando la gravedad.
    
    3. **Deje que los heridos permanezcan quietos**: Una vez en el sitio de un incidente con lesionados, es importante evitar causarles más estrés o movimiento innecesario hasta llegue ayuda profesional; esto puede ser crucial para su bienestar y tratamiento.
    
    4. **Proporciona asistencia básica**: Si está capacitado en primeros auxilios, pueda ofrecer atención inicial mientras esperan la respuesta médica (como aplicar presión directamente a una herida visible o mantener al lesionado caliente y cómodo). No intente reparaciones más complejas ni manipule objetos metálicos.
    
    5. **Apoya las labores de los socorristas**: Una vez que llegue la ayuda, colabore con ellos para facilitar su trabajo sin interferir en sus procedimientos médicos o operativos; esto puede incluir proporcionar información relevante sobre el accidente y cualquier conocimiento personal del estado físico de las víctimas.
    
    6. **Preserva los hechos**: Documentación como fotos
  Probando phi3.5 [CON CONTEXTO] corrida 1/3...
  Probando phi3.5 [CON CONTEXTO] corrida 2/3...
  Probando phi3.5 [CON CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [4] PHI3.5 — CON CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  173 ms
  Tiempo total:         9.26 s
  Velocidad:            27.9 tok/s
  Sigue protocolo:      SI
  Fuera de protocolo:   llamar a emergencia, seguro

  Respuesta (primera corrida):

    Según el protocolo proporcionado, estos son los pasos que debes seguir:
    
    1. FASE 1 - TOMA DE CONOCIMIENTO: Ya has llegado a la escena del siniestro y hay dos heridos, lo cual registres como cantidad de lesionados.
    
    2. FASE 2 - ARRIBO AL LUGAR: Ahora debes evaluar riesgos secundarios en la escena, tales como derrames, incendios o peligro por tráfico continuo.
    
    3. FASE 3 - INTERVENCIÓN: Una vez que hayas confirmado que no existen riesgos inmediatos, debes brindar auxilio médico primario y estabilizar a los heridos graves. Recuerda no mover a los lesionados salvo en caso de peligro inminente para su vida.
    
    Recuerda siempre priorizar tu seguridad también mientras ayudes, puedes llamar a emergencias locales si es necesario o pedir asistencia adicional.

  Cargando qwen2.5:3b (warmup)...
  Probando qwen2.5:3b [SIN CONTEXTO] corrida 1/3...
  Probando qwen2.5:3b [SIN CONTEXTO] corrida 2/3...
  Probando qwen2.5:3b [SIN CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [5] QWEN2.5:3B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  204 ms
  Tiempo total:         5.99 s
  Velocidad:            74.9 tok/s

  Respuesta (primera corrida):

    En caso de un accidente vial con heridos, es importante seguir estos pasos inmediatos:
    
    1. **Seguridad Primaria**: Asegúrate de que tú y cualquier persona más cerca del lugar estás a salvo antes de intentar ayudar a los heridos. Si el vehículo está en marcha, asegúrate de que todos los ocupantes abandonen el vehículo.
    
    2. **Llamada de Emergencia**: Llama al servicio de emergencias locales (como 911 en Estados Unidos) inmediatamente para solicitar ayuda médica y policíaca si es necesario. Explica la situación lo mejor posible, incluyendo cuántas personas están heridas y dónde se encuentran.
    
    3. **Evita el Manejo del Vehículo**: Si el vehículo está dañado o en peligro de derrapar, asegúrate de que nadie toque el volante o maniobre el vehículo hasta que lleguen los expertos en rescate y seguridad vial.
    
    4. **Mantén la Calma**: Trata de mantener a las personas heridas calmadas para evitar situaciones más peligrosas, como si se desmayen o si sufre un ataque cardíaco.
    
    5. **Identifica el Accidente**: Si es seguro hacerlo, intenta identificar el accidente y los vehículos involucrados. Anota las placas de los vehículos para reportar la situación posteriormente.
    
    6. **Ayuda Médica Inicial**: Si estás capacitado y tu experiencia médica lo permite, proporciona ayuda inicial a las personas heridas siguiendo instrucciones de primeros auxilios si es necesario. 
    
    7. **Reporte del Accidente**: Una vez que la emergencia se haya resuelto, asegúrate de reportar el accidente al departamento de tránsito local para registrar un informe y cualquier posible siniestro vial.
    
    Recuerda siempre que tu seguridad debe ser tu prioridad en situaciones como estas.
  Probando qwen2.5:3b [CON CONTEXTO] corrida 1/3...
  Probando qwen2.5:3b [CON CONTEXTO] corrida 2/3...
  Probando qwen2.5:3b [CON CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [6] QWEN2.5:3B — CON CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  210 ms
  Tiempo total:         3.68 s
  Velocidad:            74.9 tok/s
  Sigue protocolo:      SI

  Respuesta (primera corrida):

    Según el protocolo oficial proporcionado:
    
    FASE 1 - TOMA DE CONOCIMIENTO: Registrar ubicación exacta del siniestro y cantidad de lesionados.
    - Luego de llegar al lugar del accidente, registrar la ubicación precisa del accidente y confirmar que hay dos heridos.
    
    FASE 2 - ARRIBO AL LUGAR: Evaluar riesgos secundarios (derrames, incendios, tráfico).
    - Realizar una evaluación rápida para identificar si existen riesgos secundarios como derrames de combustible, incendios o problemas de tráfico que puedan afectar a los heridos.
    
    FASE 3 - INTERVENCIÓN: Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.
    - Brindar auxilio médico primario a los dos heridos.
    - Establecer si alguno de los heridos está en estado grave y necesita atención médica especializada, en cuyo caso proceder con la estabilización del mismo.
    - No mover a los heridos salvo que sea necesario para evitar un peligro inmediato.

  Cargando ministral-3:3b (warmup)...
  Probando ministral-3:3b [SIN CONTEXTO] corrida 1/3...
  Probando ministral-3:3b [SIN CONTEXTO] corrida 2/3...
  Probando ministral-3:3b [SIN CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [7] MINISTRAL-3:3B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  294 ms
  Tiempo total:         19.28 s
  Velocidad:            27.0 tok/s

  Respuesta (primera corrida):

    Si hay un accidente vial con heridos, es importante actuar de manera rápida y responsable para garantizar su seguridad y la del resto de personas involucradas. Aquí tienes los **primeros pasos clave** a seguir:
    
    ### **1. Mantener la calma y priorizar la seguridad**
       - **Evita correr hacia el lugar del accidente**: Si no hay riesgo inmediato (ej.: fuego, gas o tráfico en movimiento), aléjate para evitar más víctimas.
       - **Cierra la vía si es seguro hacerlo** (solo si hay peligro grave como un vehículo en llamas o una colisión con peatones).
    
    ### **2. Evaluar a las víctimas**
       - **Pregúntale a los heridos cómo se sienten** (dolor, pérdida de conciencia).
       - **No muevas a nadie sin necesidad**: Si hay riesgo de lesiones graves (ej.: fracturas), deja al herido en su lugar hasta que llegue ayuda profesional.
       - **Identifica si alguien está inconsciente o respirando con dificultad**.
    
    ### **3. Actuar según el estado del herido**
       - **Heridos conscientes pero con dolor**:
         - Ofrece consuelo y tranquilidad.
         - Dale agua (si no hay riesgo de asfixia por vómitos).
         - Aplica vendajes estériles en heridas abiertas (usa gasas o paños limpios si no hay material médico).
       - **Heridos inconscientes**:
         - **Verifica su respiración y pulso** (mínimo 10 segundos). Si no respiran, inicia **reanimación cardiopulmonar (RCP)** si es necesario.
         - Coloca al herido en posición lateral de seguridad si está inconsciente pero respirando (para evitar asfixia por vómitos).
       - **Heridos con quemaduras o fracturas**:
         - No apliques hielo ni rompas huesos. Usa mantas o ropa para aislar la zona.
    
    ### **4. Notificar a las autoridades**
       - **Llama al 112 (Emergencias Europeas)** o al número de emergencia local (ej.: 911 en EE.UU., 061 en México, 911 en España).
         - **Informa claramente**:
           - Ubicación exacta del accidente.
           - Número de heridos y su estado (conscientes/inconscientes).
           - Si hay
  Probando ministral-3:3b [CON CONTEXTO] corrida 1/3...
  Probando ministral-3:3b [CON CONTEXTO] corrida 2/3...
  Probando ministral-3:3b [CON CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [8] MINISTRAL-3:3B — CON CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  294 ms
  Tiempo total:         6.20 s
  Velocidad:            27.3 tok/s
  Sigue protocolo:      SI

  Respuesta (primera corrida):

    **Respuesta según el protocolo oficial:**
    
    1. **FASE 1 - TOMA DE CONOCIMIENTO:**
       Registra la ubicación exacta del siniestro y verifica que hay **dos lesionados**.
    
    2. **FASE 2 - ARRIBO AL LUGAR:**
       Evalúa riesgos secundarios (ej.: derrames de líquidos, incendios o tráfico en el área).
    
    3. **FASE 3 - INTERVENCIÓN:**
       Brinda auxilio médico primario según las necesidades de cada herido.
       Estabiliza a los heridos graves antes de moverlos.
       **No muevas a los lesionados salvo que haya un peligro inmediato** (ej.: riesgo de colisión o incendio).

  Cargando llama3:8b (warmup)...
  Probando llama3:8b [SIN CONTEXTO] corrida 1/3...
  Probando llama3:8b [SIN CONTEXTO] corrida 2/3...
  Probando llama3:8b [SIN CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [9] LLAMA3:8B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  347 ms
  Tiempo total:         46.19 s
  Velocidad:            11.2 tok/s

  Respuesta (primera corrida):

    En caso de un accidente vial con heridos, es fundamental actuar con rapidez y eficacia para minimizar el daño y garantizar la atención médica adecuada a las víctimas. A continuación, te presento los primeros pasos que debes seguir:
    
    1. **Llamar al 112 o número de emergencia**: Si se produce un accidente vial en España, llama al 112 (número de emergencia) y describe la situación con claridad. Indica el lugar exacto del accidente, el número de víctimas y la gravedad de los heridos.
    2. **Evacuar a las víctimas**: Si es posible, intenta evacuar a las víctimas del lugar del accidente sin moverlas demasiado, ya que esto puede empeorar su condición. Si no puedes evacuarlas, asegúrate de que estén en un lugar seguro y protegido.
    3. **Realizar primeros auxilios básicos**: Si tienes formación en primeros auxilios, intenta ayudar a las víctimas con los siguientes pasos:
    	* Controlar hemorragias: aplicar compresiones directas o usar vendajes para controlar la hemorragia.
    	* Estabilizar lesiones: utilizar materiales blandos (como toallas o trapos) para estabilizar lesiones en la cabeza, cuello o piernas.
    	* Respiración y circulación: si una víctima no respira, intenta realizar reanimación cardiopulmonar (RCP). Si no hay signo de vida, intenta mantener la circulación sanguínea mediante compresiones en el pecho.
    4. **Proteger a las víctimas del peligro**: Asegúrate de que las víctimas estén protegidas del peligro inmediato (como un incendio o una explosión) y no estén en riesgo de sufrir más lesiones.
    5. **Informar a los servicios de emergencia**: Si ya has llamado al 112, informa a los servicios de emergencia sobre la situación y el número de víctimas. Asegúrate de proporcionar información clara y precisa para que los profesionales médicos puedan prepararse adecuadamente.
    6. **Permanecer en el lugar**:
  Probando llama3:8b [CON CONTEXTO] corrida 1/3...
  Probando llama3:8b [CON CONTEXTO] corrida 2/3...
  Probando llama3:8b [CON CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [10] LLAMA3:8B — CON CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  310 ms
  Tiempo total:         14.17 s
  Velocidad:            11.5 tok/s
  Sigue protocolo:      SI

  Respuesta (primera corrida):

    Según el protocolo, la primera fase es "Toma de conocimiento", por lo que debes:
    
    * Registrar ubicación exacta del siniestro
    * Cantidad de lesionados (en este caso, 2)
    
    Luego, pasas a la segunda fase: "Arribo al lugar". Debes evaluar riesgos secundarios (derrames, incendios, tráfico).
    
    Finalmente, llegas a la tercera fase: "Intervención". Debido a que hay heridos, debes brindar auxilio médico primario. No moverás a los lesionados salvo peligro inmediato.
    
    No haces nada más hasta que no se complete esta tercera fase.

  Cargando gemma2:2b (warmup)...
  Probando gemma2:2b [SIN CONTEXTO] corrida 1/3...
  Probando gemma2:2b [SIN CONTEXTO] corrida 2/3...
  Probando gemma2:2b [SIN CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [11] GEMMA2:2B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  275 ms
  Tiempo total:         6.55 s
  Velocidad:            81.5 tok/s

  Respuesta (primera corrida):

    Un accidente vial con heridos es una situación extremadamente delicada que requiere actuar con rapidez y precaución. Aquí te presento los primeros pasos a seguir:
    
    **1. Seguridad Previa:**
    
    * **Evalúa la escena:** Asegúrate de que la zona sea segura para ti y otros antes de acercarse. Busca posibles peligros como cables sueltos, gas o fuego.
    * **Respeta las señales de tráfico:** Si hay señalización de emergencia, sigue las instrucciones. 
    * **Utiliza luces de emergencia:** Si tu vehículo tiene luces de emergencia, enciéndelas para alertar a otros conductores y peatones.
    
    **2. Ayuda a los lesionados:**
    
    * **Evalúa la gravedad de las lesiones:**  Si ves que alguien necesita atención médica inmediata, llama al 911 (o el número de emergencias local) sin dudarlo.
    * **Presta ayuda si es seguro:** Si puedes hacerlo sin poner en peligro tu seguridad o la de otros, ofrece asistencia a los heridos. Esto puede incluir:
        * **Mantenerlos tranquilos y seguros.**
        * **Verificar su respiración y pulso.**
        * **Limpia cualquier herida superficial con agua y jabón.**
        * **No les des líquidos ni alimentos sin saber si están conscientes.**
    * **Evita mover a los heridos:**  Mover a un herido puede empeorar sus lesiones. 
    
    **3. Llama al servicio de emergencia:**
    
    * **Llama al 911 (o el número de emergencias local) inmediatamente.**
    * **Proporciona la ubicación exacta del accidente y la cantidad de personas heridas.**
    * **Mantén la calma y proporciona información precisa a los operadores.**
    
    **4. Documenta el accidente:**
    
    * **Toma fotos o videos de la escena del accidente, incluyendo las marcas de vehículos, daños y heridos.**
    * **Recopila información sobre los involucrados, como nombres, direcciones y números de teléfono.**
    * **Guarda cualquier evidencia que pueda ser útil para la investigación, como documentos de seguro o testigos.**
    
    
    **5. Cooperación con las autoridades:**
    
    * **Mantente en contacto con las autoridades durante la investigación del accidente.**
    * **No te involucres en disputas o discusiones con otros conductores.**
    * **Sigue las instrucciones de los oficiales y coopera con la investigación.**
    
    
    Recuerda que tu seguridad y la de los demás es lo primero. Actúa con prudencia, calma y responsabilidad para ayudar a los heridos y asegurar una respuesta rápida a
  Probando gemma2:2b [CON CONTEXTO] corrida 1/3...
  Probando gemma2:2b [CON CONTEXTO] corrida 2/3...
  Probando gemma2:2b [CON CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [12] GEMMA2:2B — CON CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  274 ms
  Tiempo total:         1.56 s
  Velocidad:            82.7 tok/s
  Sigue protocolo:      SI

  Respuesta (primera corrida):

    1. **FASE 1 - TOMA DE CONOCIMIENTO:** Registrar la ubicación exacta del siniestro y la cantidad de lesionados (2). 
    2. **FASE 2 - ARRIBO AL LUGAR:** Evaluar riesgos secundarios (derrames, incendios, tráfico) antes de intervenir.
    3. **FASE 3 - INTERVENCIÓN:** Brindar auxilio médico primario a los heridos. Estabilizar a los heridos graves y no moverlos salvo peligro inmediato.

  Cargando gemma3:4b (warmup)...
  Probando gemma3:4b [SIN CONTEXTO] corrida 1/3...
  Probando gemma3:4b [SIN CONTEXTO] corrida 2/3...
  Probando gemma3:4b [SIN CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [13] GEMMA3:4B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  698 ms
  Tiempo total:         25.86 s
  Velocidad:            20.4 tok/s

  Respuesta (primera corrida):

    Un accidente vial con heridos es una situación de emergencia que requiere actuar con rapidez y calma. Aquí te detallo los primeros pasos a seguir, priorizando la seguridad y el bienestar de todos:
    
    **1. Asegurar la Seguridad del Lugar:**
    
    *   **Detenerse:** Lo primero es frenar inmediatamente y detenerte en un lugar seguro, lejos del tráfico.
    *   **Encender las luces de emergencia:** Esto alertará a otros conductores sobre el accidente.
    *   **Activar la luz intermitente:**  Indica que hay una situación de emergencia.
    *   **Posicionar el vehículo:** Si es posible y seguro, mueve tu vehículo a un lugar fuera del tráfico y donde no represente peligro para los heridos o para otros vehículos. Si no puedes moverlo, asegúrate de colocar triángulos de advertencia.
    *   **Evaluar la seguridad:** Observa si hay riesgos adicionales como cables eléctricos caídos, fugas de combustible, etc., y toma medidas para mitigarlos (si es seguro hacerlo).
    
    **2. Asistencia a los Heridos (Prioridad Máxima):**
    
    *   **No mover a los heridos (salvo que estén en peligro inmediato):**  A menos que haya un riesgo inminente (como fuego, derrumbe de vehículos, etc.), no muevas a las víctimas. Moverlos podría empeorar lesiones como la columna vertebral.
    *   **Evaluar el estado de conciencia:** Pregunta si están conscientes y responden.
    *   **Proporcionar primeros auxilios básicos:**
        *   **Control de hemorragias:** Aplica presión directa sobre las heridas con un paño limpio o tela para detener el sangrado.
        *   **Estabilizar la columna vertebral (si sospechas una lesión):** Si sospechas que alguien tiene una lesión en la columna, mantén su cabeza y cuello inamovibles.
        *   **Control de vías respiratorias:**  Si la persona no respira, intenta colocarla en posición lateral de seguridad (posición de recuperación) si es posible y seguro.
        *   **Mantener al paciente caliente:** Cubrirlo con una manta para prevenir hipotermia.
        *   **Tranquilizar al herido:** Hablarle suavemente y tranquilizarlo puede ayudar a reducir el estrés y el pánico.
    *   **No administrar alimentos ni bebidas:**  Esto no es apropiado en una situación de emergencia.
    
    **
  Probando gemma3:4b [CON CONTEXTO] corrida 1/3...
  Probando gemma3:4b [CON CONTEXTO] corrida 2/3...
  Probando gemma3:4b [CON CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [14] GEMMA3:4B — CON CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  722 ms
  Tiempo total:         4.61 s
  Velocidad:            21.0 tok/s
  Sigue protocolo:      SI

  Respuesta (primera corrida):

    FASE 1 - Toma de conocimiento: Registrar ubicación exacta del siniestro y cantidad de lesionados.
    FASE 2 - arribo al lugar: Evaluar riesgos secundarios (derrames, incendios, tráfico).
    FASE 3 - Intervención: Brindar auxilio médico primario. Estabilizar heridos graves. No mover a lesionados salvo peligro inmediato.

  Cargando qwen2.5:1.5b (warmup)...
  Probando qwen2.5:1.5b [SIN CONTEXTO] corrida 1/3...
  Probando qwen2.5:1.5b [SIN CONTEXTO] corrida 2/3...
  Probando qwen2.5:1.5b [SIN CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [15] QWEN2.5:1.5B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  204 ms
  Tiempo total:         7.13 s
  Velocidad:            59.6 tok/s

  Respuesta (primera corrida):

    En caso de un accidente vial con heridos, aquí están algunos pasos que puedes seguir:
    
    1. **Segura y seguro**: Primero asegúrate de que estés en una posición segura para ayudar a las personas afectadas.
    
    2. **Evita la confusión**: Mantén el lugar limpio y evita mover los cuerpos o objetos si no es necesario.
    
    3. **Identifica la situación**: Decide cuál es la prioridad: salvar vidas, proporcionar atención médica, etc.
    
    4. **Llamada al 911**: Si hay heridos graves, llama al 911 para informar sobre el accidente y solicitar ayuda médica inmediata.
    
    5. **Mantén comunicación con las autoridades**: Luego de que los servicios médicos lleguen, mantén la comunicación con ellos para proporcionar información precisa sobre el accidente.
    
    6. **Asegúrate de que todo esté bien protegido**: Si hay heridos graves o necesitan atención médica urgente, asegúrate de mantenerlos alejados del ambiente y en un lugar seguro.
    
    7. **Lleva a los heridos al hospital**: Si es posible, lleva a los heridos al hospital más cercano para recibir la atención médica adecuada.
    
    8. **Recuerda que el 911 no se usa para problemas de salud general o menores accidentes viales**.
    
    Es importante tener en cuenta que estos son solo recomendaciones generales y pueden variar dependiendo del contexto específico del accidente. Si tienes dudas, es mejor llamar al 911 directamente para obtener asesoramiento profesional.
  Probando qwen2.5:1.5b [CON CONTEXTO] corrida 1/3...
  Probando qwen2.5:1.5b [CON CONTEXTO] corrida 2/3...
  Probando qwen2.5:1.5b [CON CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [16] QWEN2.5:1.5B — CON CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  198 ms
  Tiempo total:         4.98 s
  Velocidad:            59.0 tok/s
  Sigue protocolo:      SI

  Respuesta (primera corrida):

    Según el protocolo oficial:
    
    1. **Toma de Conocimiento**: 
       - Registrar ubicación exacta del siniestro y cantidad de lesionados.
    
    2. **Arrivo al Lugar**:
       - Evaluar riesgos secundarios (derrames, incendios, tráfico).
    
    3. **Intervención**:
       - Brindar auxilio médico primario.
       - Estabilizar heridos graves.
       - No mover a lesionados salvo peligro inmediato.
    
    Entonces, para un accidente vial con 2 heridos:
    
    1. **Toma de Conocimiento**: 
       - Registrar la ubicación exacta del siniestro y contar con dos heridos.
    
    2. **Arrivo al Lugar**:
       - Evaluar riesgos secundarios (derrames, incendios, tráfico).
    
    3. **Intervención**:
       - Brindar auxilio médico primario.
       - Estabilizar los dos heridos graves.
       - No mover a los lesionados salvo peligro inmediato.
    
    Por lo tanto, la acción correcta sería:
    
    - **Brindar auxilio médico primario a los dos heridos** y asegurarse de que no se muevan hasta que sea necesario para evitar complicaciones.

  Cargando phi4-mini (warmup)...
  Probando phi4-mini [SIN CONTEXTO] corrida 1/3...
  Probando phi4-mini [SIN CONTEXTO] corrida 2/3...
  Probando phi4-mini [SIN CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [17] PHI4-MINI — SIN CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  284 ms
  Tiempo total:         7.89 s
  Velocidad:            39.3 tok/s

  Respuesta (primera corrida):

    Si se encuentra en una situación de emergencia, como un accidente vehicular con heridos, es crucial mantener la calma y tomar las siguientes acciones:
    
    1. **Llama a servicios de emergencia**: Alerta inmediatamente al 911 o al número local de emergencias para pedir asistencia médica.
    
    2. **Mantén el control del vehículo si está seguro hacerlo**: Si puede moverse sin poner en peligro su vida u otras personas, guíe suavemente su coche hacia una zona segura lejos del tráfico y deténgase allí.
    
    3. **Evita la escena**: No intente acercarse al lugar de los heridos o a las víctimas para no empeorar sus lesiones ni interrumpir el trabajo de los primeros respondientes.
    
    4. **Apoya a los heridos si es seguro hacerlo**: Si está cerca y puede ayudar sin poner en peligro su vida u otra persona, se le puede pedir que apueste al herido con cuidado hasta la llegada del personal médico o paramédico.
    
    5. **Proporciona información útil**: Una vez llegue el servicio de emergencia, proporcione toda la información posible sobre lo sucedido, incluyendo detalles como dónde ocurrió el accidente y si hay alguna víctima en peligro inmediato.
    
    6. **Mantén una distancia segura**: Manténgase alejado del lugar para permitir que los servicios de emergencia accedan al área sin obstáculos.
    
    Recuerde, su prioridad debe ser llamar a las autoridades antes de intentar hacer cualquier cosa más allá de mantener la seguridad personal y el control del vehículo si es posible hacerlo con seguridad. Los primeros respondientes son profesionales capacitados para manejar tales situaciones; sus esfuerzos deben tomarse como una prioridad sobre los intentos de asistencia no entrenados en el lugar.
  Probando phi4-mini [CON CONTEXTO] corrida 1/3...
  Probando phi4-mini [CON CONTEXTO] corrida 2/3...
  Probando phi4-mini [CON CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [18] PHI4-MINI — CON CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  272 ms
  Tiempo total:         3.25 s
  Velocidad:            39.4 tok/s
  Sigue protocolo:      SI

  Respuesta (primera corrida):

    Basado en el protocolo oficial proporcionado:
    
    FASE 1 - TOMA DE CONOCIMIENTO:
    - Registrar ubicación exacta del siniestro.
    - Contar y registrar cantidad de lesionados (en este caso, 2).
    
    FASE 2 - ARRIBO AL LUGAR:
    - Evaluar riesgos secundarios como derrames, incendios o tráfico.
    
    FASE 3 - INTERVENCIÓN:
    - Brindar auxilio médico primario a los heridos.
    - Estabilizar heridos graves sin moverlos salvo peligro inmediato.

  Cargando qwen3:8b (warmup)...
  Probando qwen3:8b [SIN CONTEXTO] corrida 1/3...
  Probando qwen3:8b [SIN CONTEXTO] corrida 2/3...
  Probando qwen3:8b [SIN CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [19] QWEN3:8B — SIN CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  0 ms
  Tiempo total:         58.24 s
  Velocidad:            8.8 tok/s

  Respuesta (primera corrida):

    
  Probando qwen3:8b [CON CONTEXTO] corrida 1/3...
  Probando qwen3:8b [CON CONTEXTO] corrida 2/3...
  Probando qwen3:8b [CON CONTEXTO] corrida 3/3...

────────────────────────────────────────────────────────────
  [20] QWEN3:8B — CON CONTEXTO
────────────────────────────────────────────────────────────
  Corridas:             3 (se reporta la mediana)
  TTFT (primer token):  41406 ms
  Tiempo total:         59.22 s
  Velocidad:            8.7 tok/s
  Sigue protocolo:      SI

  Respuesta (primera corrida):

    **FASE 2 - ARRIBO AL LUGAR:**  
    1. **Evaluar riesgos secundarios:** Verifique la presencia de derrames de combustible, incendios, cables eléctricos expuestos o tráfico que pueda poner en peligro a los heridos o a usted.  
    2. **Proteger la zona:** Si hay riesgos, actúe para minimizarlos (ej.: apagar motores, alejar vehículos, usar chalecos reflectantes).  
    
    **FASE 3 - INTERVENCIÓN:**  
    1. **Brindar auxilio médico primario:** Ofrezca primeros auxilios básicos (controlar hemorragias, inmovil


════════════════════════════════════════════════════════════════════════
  RESUMEN COMPARATIVO (medianas)
════════════════════════════════════════════════════════════════════════
  Modelo             Prompt              TTFT    Total    tok/s  Protocolo  Inventa
  ────────────────── ─────────────── ──────── ──────── ──────── ────────── ────────
  llama3.2:3b        SIN CONTEXTO        256ms     6.6s    75.0          —        —
  llama3.2:3b        CON CONTEXTO        231ms     2.3s    75.3         SI        —
  phi3.5             SIN CONTEXTO        188ms    18.6s    27.8          —        —
  phi3.5             CON CONTEXTO        173ms     9.3s    27.9         SI        2
  qwen2.5:3b         SIN CONTEXTO        204ms     6.0s    74.9          —        —
  qwen2.5:3b         CON CONTEXTO        210ms     3.7s    74.9         SI        —
  ministral-3:3b     SIN CONTEXTO        294ms    19.3s    27.0          —        —
  ministral-3:3b     CON CONTEXTO        294ms     6.2s    27.3         SI        —
  llama3:8b          SIN CONTEXTO        347ms    46.2s    11.2          —        —
  llama3:8b          CON CONTEXTO        310ms    14.2s    11.5         SI        —
  gemma2:2b          SIN CONTEXTO        275ms     6.5s    81.5          —        —
  gemma2:2b          CON CONTEXTO        274ms     1.6s    82.7         SI        —
  gemma3:4b          SIN CONTEXTO        698ms    25.9s    20.4          —        —
  gemma3:4b          CON CONTEXTO        722ms     4.6s    21.0         SI        —
  qwen2.5:1.5b       SIN CONTEXTO        204ms     7.1s    59.6          —        —
  qwen2.5:1.5b       CON CONTEXTO        198ms     5.0s    59.0         SI        —
  phi4-mini          SIN CONTEXTO        284ms     7.9s    39.3          —        —
  phi4-mini          CON CONTEXTO        272ms     3.2s    39.4         SI        —
  qwen3:8b           SIN CONTEXTO          0ms    58.2s     8.8          —        —
  qwen3:8b           CON CONTEXTO      41406ms    59.2s     8.7         SI        —
═════════════════════════════