"""Conversaciones guionadas para probar el agente por texto.

Las usan ensayo.py (sobre LiveKit) y orquestador/consola.py (orquestador
propio), así los dos caminos se prueban con los mismos casos.
"""

from __future__ import annotations

# Escenarios pensados para ejercitar los caminos que importan, incluidos los que
# tienen que fallar de forma segura.
ESCENARIOS: dict[str, list[str]] = {
    "inconsciente_respira": [
        "Choqué contra otro auto, estoy en la banquina",
        "El acompañante quedó inconsciente, no me responde",
        "Sí, se le mueve el pecho, está respirando",
    ],
    "inconsciente_no_respira": [
        "Choqué contra otro auto, estoy en la banquina",
        "El acompañante está inconsciente y no responde",
        "No, no se mueve el pecho y no respira",
    ],
    "critico": [
        "Choqué con la moto, estoy en la banquina",
        "Hay un señor tirado en el asfalto, no se mueve y no respira",
        "Ya le hice las compresiones, ¿ahora qué?",
    ],
    "hemorragia": [
        "Hola, hubo un choque múltiple",
        "Una chica se está desangrando de la pierna, sale mucha sangre",
        "Le puse una remera apretando, ¿está bien?",
    ],
    "leve": [
        "Tuve un roce con otro auto",
        "Nadie está lastimado, solo estamos asustados",
        "¿Tengo que mover el auto o lo dejo?",
    ],
    "fuera_de_alcance": [
        "Hola, quería saber cuánto sale la VTV",
        "¿Y el seguro me cubre el granizo?",
    ],
    "con_riesgo": [
        "Chocamos contra un poste",
        "No hay nadie herido pero sale humo y olor a combustible del motor",
        "¿Qué hacemos?",
    ],
    "atrapado": [
        "hola, si estoy fuera de la calzada chocaron dos autos",
        "hay una persona atrapada en auto las demas estan bien",
        "no veo si reacciona",
    ],
    "casco": [
        "Hola, estoy a salvo en la banquina. Se cayó un chico en moto, ¿le saco el casco?",
        "Está despierto y se queja del cuello",
    ],
    # Conversación real de la pestaña Test en producción (con el error de tipeo).
    "moto_produccion": [
        "choco una moto",
        "si esta tirado en el piso con el casco",
        "le scao el casco",
        "le saco el casco?",
    ],
    # Segunda conversación real de producción: «sí, una persona» no derivaba.
    "herido_confirmado": [
        "choco una moto",
        "si, una persona",
        "una",
        "si, me pide que le saque el casco",
        "le sangra una pierna mucho",
    ],
    "pregunta_directa": [
        "Choqué de atrás a otro auto en la avenida",
        "No, nadie lastimado. ¿Tengo que mover el auto o lo dejo?",
    ],
    # RCP sostenida: mientras comprime no se le pregunta nada, y al llegar la
    # ayuda se corta.
    "rcp_continua": [
        "Choqué, hay un hombre tirado en la ruta que no respira",
        "Ya empecé a comprimir, ¿a qué ritmo sigo?",
        "Sigo, sigo, estoy cansado",
        "Llegó la ambulancia",
    ],
    # El caso de la prueba por consola: «Sí, respira» en plena RCP tiene que
    # cortar las compresiones (y el metrónomo).
    "rcp_vuelve_a_respirar": [
        "Hay un hombre tirado en la ruta que no respira",
        "Ya estoy comprimiendo",
        "Sí, respira",
    ],
    # Seguimiento de una indicación: el cierre tiene que preguntar por el
    # resultado («¿sigue saliendo sangre?»), no «¿lo pudiste hacer?».
    "seguimiento_hemorragia": [
        "Hubo un choque, un muchacho tiene un tajo en el brazo y sangra",
        "Listo, ya le estoy apretando con una remera",
        "Bajó bastante",
        "Ahora está tranquilo, me habla",
    ],
}
