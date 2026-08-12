import pytest
import asyncio
from metricas.coverage.critical_information_coverage import (
    SIMULATED_CALLS,
    LIVEKIT_URL,
    LIVEKIT_API_KEY,
    LIVEKIT_API_SECRET,
    generar_room_name,
    obtener_checklist_de_supabase,
    ejecutar_agente_livekit_cloud,
    evaluar_cobertura_juez,
    guardar_resultado
)

# ── Pruebas con Pytest ────────────────────────────────────────────────────────
@pytest.mark.asyncio
@pytest.mark.parametrize("escenario", list(SIMULATED_CALLS.keys()))
async def test_critical_information_coverage(escenario):
    turns = SIMULATED_CALLS[escenario]
    
    # 1. Obtener Checklist
    checklist = await obtener_checklist_de_supabase(escenario, turns[0])
    assert len(checklist) > 0, "La checklist no puede estar vacía"
    
    # 2. Correr conversación multiturno
    if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        raise ValueError(
            "Faltan credenciales de LiveKit Cloud (LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) "
            "en .env.local para ejecutar la evaluación en la nube."
        )
        
    room_name = generar_room_name()
    conversation = await ejecutar_agente_livekit_cloud(turns, room_name)
    
    # Verificar que el agente haya respondido a todos los turnos
    for turn in conversation:
        if turn["assistant"] == "[Sin respuesta/Timeout]":
            raise RuntimeError(f"El agente en la nube no respondió o dio timeout en el turno: '{turn['user']}'")
        
    assert len(conversation) == len(turns), "La conversación no tiene el número esperado de turnos"
    
    # 3. Formatear la transcripción
    transcript_lines = []
    for turn in conversation:
        transcript_lines.append(f"Usuario: {turn['user']}")
        transcript_lines.append(f"Asistente: {turn['assistant']}")
    transcript = "\n".join(transcript_lines)
    
    # 4. Evaluar con el Juez local (con fallback heurístico)
    result = await evaluar_cobertura_juez(transcript, checklist)
    
    # Guardar en archivo
    ruta_relativa = guardar_resultado(escenario, transcript, checklist, result)
    
    score = result.get("score", 0.0)
    veredicto = "PASSED" if score >= 0.8 else "FAILED"
    
    print(f"\n========================================================")
    print(f" ESCENARIO: {escenario.upper()} ({veredicto})")
    print(f"========================================================")
    print(f"- Score obtenido: {score:.2f} (Umbral >= 0.80)")
    print(f"- Puntos cubiertos: {len(result.get('puntos_cubiertos', []))}/{len(checklist)}")
    print(f"- Reporte guardado en: {ruta_relativa}")
    print(f"========================================================\n")
    
    assert score >= 0.8, (
        f"El score de cobertura {score:.2f} es menor al umbral de 0.80.\n"
        f"Ver detalles en: {ruta_relativa}"
    )
