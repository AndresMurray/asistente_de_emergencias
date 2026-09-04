"""Telemetría local de latencia para el agente de voz.

El módulo no depende de pandas ni de servicios externos: puede importarse desde
la imagen runtime. Sólo registra eventos cuando ``LATENCY_RUN_ID`` está definido.

Uso:
    LATENCY_RUN_ID=baseline LATENCY_VARIANT=actual \
      .venv/bin/python agent.py console --record
    .venv/bin/python -m metricas.latencia summarize metricas/resultados/latencia_raw/baseline.jsonl
    .venv/bin/python -m metricas.latencia compare baseline.jsonl candidata.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import statistics
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("metricas.latencia")

_WRITE_LOCK = threading.Lock()
_CORE_METRICS = (
    "transcription_delay_ms",
    "end_of_turn_delay_ms",
    "on_user_turn_completed_delay_ms",
    "e2e_latency_ms",
    "llm_node_ttft_ms",
    "tts_node_ttfb_ms",
    "playback_latency_ms",
)


def _ms(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value) * 1000, 3)
    except (TypeError, ValueError):
        return None


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _safe_text(item: Any) -> str:
    value = _field(item, "text_content", "")
    return value if isinstance(value, str) else str(value or "")


class LatencyRecorder:
    """Correlaciona métricas de ChatMessage y de los modelos por sesión.

    ``speech_id`` existe en las métricas por componente pero no en el reporte
    de ChatMessage de Agents 1.6.5. La métrica EOU permite asociarlo al último
    turno de usuario comprometido, y luego las métricas de LLM/TTS/RAG quedan
    correlacionadas con ese turno.
    """

    def __init__(
        self,
        *,
        room: str | None = None,
        job: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.run_id = os.getenv("LATENCY_RUN_ID", "").strip()
        self.enabled = bool(self.run_id)
        self.variant = os.getenv("LATENCY_VARIANT", "actual").strip() or "actual"
        self.scenario = os.getenv("LATENCY_SCENARIO", "manual").strip() or "manual"
        self.include_text = os.getenv("LATENCY_INCLUDE_TEXT", "0").lower() in {
            "1", "true", "yes"
        }
        self.room = room
        self.job = job
        self.config = config or {}
        self.started_at = time.time()
        self._turn = 0
        self._segment = 0
        self._pending_user: dict[str, Any] | None = None
        self._speech_turn: dict[str, int] = {}
        self._turn_components: dict[int, Counter[str]] = defaultdict(Counter)
        self._unmapped_components: dict[str, Counter[str]] = defaultdict(Counter)
        self._unmapped_eou: list[str] = []
        self._closed = False

        root = os.getenv("LATENCY_OUTPUT_DIR", "").strip()
        if not root and self.run_id:
            root = "metricas/resultados/latencia_raw"
        self.path: Path | None = None
        if root and self.run_id:
            directory = Path(root)
            directory.mkdir(parents=True, exist_ok=True)
            self.path = directory / f"{self.run_id}.jsonl"

        self._write("session_start", config=self.config)

    @property
    def current_turn(self) -> int | None:
        return self._pending_user["turn"] if self._pending_user else None

    def record_conversation_item(self, item: Any) -> None:
        role = _field(item, "role")
        if role == "user":
            self._turn += 1
            self._segment = 0
            metric = _field(item, "metrics", {}) or {}
            self._pending_user = {
                "turn": self._turn,
                "metrics": {
                    "transcription_delay_ms": _ms(_field(metric, "transcription_delay")),
                    "end_of_turn_delay_ms": _ms(_field(metric, "end_of_turn_delay")),
                    "on_user_turn_completed_delay_ms": _ms(
                        _field(metric, "on_user_turn_completed_delay")
                    ),
                },
                "text": _safe_text(item),
            }
            return

        if role != "assistant":
            return

        self._segment += 1
        metric = _field(item, "metrics", {}) or {}
        text = _safe_text(item)
        normalized = " ".join(text.lower().split())
        user = self._pending_user
        if user and self._unmapped_eou:
            # Agents 1.6.5 emite EOUMetrics antes de añadir el ChatMessage del
            # usuario. La respuesta siguiente es el primer punto donde ambos
            # lados están disponibles; allí cerramos la correlación sin asumir
            # que el saludo (que no tiene EOU) pertenece a un turno.
            speech_id = self._unmapped_eou.pop()
            self._speech_turn[speech_id] = user["turn"]
            self._turn_components[user["turn"]].update(
                self._unmapped_components.pop(speech_id, Counter())
            )
            self._write("correlation", speech_id=speech_id, turn=user["turn"])
        record: dict[str, Any] = {
            "turn": user["turn"] if user else None,
            "segment": self._segment,
            "is_filler": normalized == "dame un segundo.",
            "llm_node_ttft_ms": _ms(_field(metric, "llm_node_ttft")),
            "tts_node_ttfb_ms": _ms(_field(metric, "tts_node_ttfb")),
            "playback_latency_ms": _ms(_field(metric, "playback_latency")),
            "e2e_latency_ms": _ms(_field(metric, "e2e_latency")),
        }
        if user:
            record.update(user["metrics"])
            record["cold_turn"] = user["turn"] == 1
            counts = self._turn_components[user["turn"]]
            # Los eventos crudos mantienen el detalle; estos contadores hacen
            # visible en la fila del turno si hubo reintentos o tool loops.
            record["component_calls"] = dict(counts)
            record["stt_calls"] = counts["stt_metrics"]
            record["llm_calls"] = counts["llm_metrics"]
            record["tts_calls"] = counts["tts_metrics"]
        if self.include_text:
            record["user_text"] = user["text"] if user else None
            record["assistant_text"] = text
        self._write("turn", **record)

        # Sólo un assistant item con E2E representa la respuesta al turno. Se
        # conserva el pending user para poder registrar segmentos posteriores,
        # pero el siguiente usuario lo reemplaza de forma natural.

    def record_component(self, component: Any) -> None:
        kind = str(_field(component, "type", "unknown"))
        speech_id = _field(component, "speech_id")
        turn = self._speech_turn.get(speech_id) if speech_id else None
        if kind == "eou_metrics" and speech_id:
            # En Agents 1.6.5 el ChatMessage de usuario se añade después de
            # EOU. Siempre esperamos al assistant item correspondiente en vez
            # de reutilizar el usuario del turno anterior.
            self._unmapped_eou = [str(speech_id)]
        if turn:
            self._turn_components[turn][kind] += 1
        elif speech_id:
            self._unmapped_components[str(speech_id)][kind] += 1

        metadata = _field(component, "metadata")
        record = {
            "component_type": kind,
            "speech_id": speech_id,
            "turn": turn,
            "ttft_ms": _ms(_field(component, "ttft")),
            "ttfb_ms": _ms(_field(component, "ttfb")),
            "duration_ms": _ms(_field(component, "duration")),
            "audio_duration_ms": _ms(_field(component, "audio_duration")),
            "acquire_time_ms": _ms(_field(component, "acquire_time")),
            "connection_reused": _field(component, "connection_reused"),
            "cancelled": _field(component, "cancelled"),
            "prompt_tokens": _field(component, "prompt_tokens"),
            "completion_tokens": _field(component, "completion_tokens"),
            "total_tokens": _field(component, "total_tokens"),
            "characters_count": _field(component, "characters_count"),
            "model": _field(metadata, "model_name"),
            "provider": _field(metadata, "model_provider"),
        }
        self._write("component", **record)

    def record_rag(
        self,
        *,
        speech_id: str | None,
        status: str,
        timings_ms: dict[str, int | None],
        prefetched: bool,
        query_category: str | None,
    ) -> None:
        turn = self._speech_turn.get(speech_id) if speech_id else None
        if turn is None:
            turn = self.current_turn
        self._write(
            "rag",
            turn=turn,
            speech_id=speech_id,
            status=status,
            timings_ms=timings_ms,
            prefetched=prefetched,
            query_category=query_category,
        )

    def record_startup(self, greeting_scheduled_at: float) -> None:
        self._write(
            "startup",
            greeting_scheduled_ms=round((greeting_scheduled_at - self.started_at) * 1000, 3),
        )

    def record_agent_state(self, event: Any) -> None:
        """Registra el primer comienzo real de audio del saludo.

        Es una señal local de inicio de playback, no una medición del viaje
        WebRTC hasta el usuario; por eso se reporta por separado de E2E.
        """
        if _field(event, "new_state") != "speaking":
            return
        if getattr(self, "_first_agent_speaking", None) is not None:
            return
        self._first_agent_speaking = time.time()
        self._write(
            "startup",
            first_agent_speaking_ms=round(
                (self._first_agent_speaking - self.started_at) * 1000, 3
            ),
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._write("session_end", duration_ms=round((time.time() - self.started_at) * 1000, 3))

    def _write(self, event: str, **payload: Any) -> None:
        if not self.enabled:
            return
        record = {
            "event": event,
            "timestamp": time.time(),
            "run_id": self.run_id or None,
            "variant": self.variant,
            "scenario": self.scenario,
            "room": self.room,
            "job": self.job,
            **payload,
        }
        # El log queda disponible también en Cloud, donde el filesystem del
        # contenedor no persiste entre jobs.
        logger.info("latency_event=%s", json.dumps(record, ensure_ascii=False, default=str))
        if self.path is None:
            return
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with _WRITE_LOCK:
            with self.path.open("a", encoding="utf-8") as output:
                output.write(line)


def _percentile(values: list[float], percentile: float) -> float:
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * percentile
    low, high = math.floor(index), math.ceil(index)
    if low == high:
        return values[low]
    return values[low] + (values[high] - values[low]) * (index - low)


def _stats(values: Iterable[float | None]) -> dict[str, float | int | None]:
    clean = sorted(float(v) for v in values if v is not None)
    if not clean:
        return {"n": 0, "min": None, "p50": None, "p90": None, "p95": None, "max": None}
    return {
        "n": len(clean),
        "min": round(clean[0], 3),
        "p50": round(statistics.median(clean), 3),
        "p90": round(_percentile(clean, 0.9), 3),
        "p95": round(_percentile(clean, 0.95), 3) if len(clean) >= 20 else None,
        "max": round(clean[-1], 3),
    }


def _read_events(paths: Iterable[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path_string in paths:
        path = Path(path_string)
        if path.is_dir():
            children = sorted(path.glob("*.jsonl"))
        else:
            children = [path]
        for child in children:
            with child.open(encoding="utf-8") as source:
                for line in source:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("línea JSONL inválida ignorada: %s", child)
    return events


def summarize(paths: Iterable[str]) -> dict[str, Any]:
    events = _read_events(paths)
    correlations = {
        event.get("speech_id"): event.get("turn")
        for event in events
        if event.get("event") == "correlation" and event.get("speech_id")
    }
    rag_turns = {
        event.get("turn") or correlations.get(event.get("speech_id"))
        for event in events
        if event.get("event") == "rag"
        and (event.get("turn") is not None or correlations.get(event.get("speech_id")) is not None)
    }
    turns = [
        event
        for event in events
        if event.get("event") == "turn"
        and event.get("turn") is not None
        and not event.get("is_filler")
    ]
    groups: dict[str, list[dict[str, Any]]] = {
        "all": turns,
        "rag": [event for event in turns if event.get("turn") in rag_turns],
        "no_rag": [event for event in turns if event.get("turn") not in rag_turns],
        "cold": [event for event in turns if event.get("cold_turn")],
        "warm": [event for event in turns if not event.get("cold_turn")],
    }
    result: dict[str, Any] = {"events": len(events), "groups": {}}
    for name, group in groups.items():
        result["groups"][name] = {
            metric: _stats(event.get(metric) for event in group) for metric in _CORE_METRICS
        }
    result["rag"] = {
        metric: _stats(
            event.get("timings_ms", {}).get(metric)
            for event in events
            if event.get("event") == "rag"
        )
        for metric in ("total", "embedding", "vector", "rerank")
    }
    startup = [event for event in events if event.get("event") == "startup"]
    result["startup"] = {
        metric: _stats(event.get(metric) for event in startup)
        for metric in ("greeting_scheduled_ms", "first_agent_speaking_ms")
    }
    result["configs"] = [
        event.get("config", {})
        for event in events
        if event.get("event") == "session_start" and event.get("config")
    ]
    result["variants"] = sorted({event.get("variant") for event in events if event.get("variant")})
    result["scenarios"] = sorted({event.get("scenario") for event in events if event.get("scenario")})
    return result


def _render_markdown(summary: dict[str, Any], title: str) -> str:
    lines = [f"# {title}", "", f"Eventos: {summary['events']}", ""]
    for group, metrics in summary["groups"].items():
        lines.extend([f"## {group}", "", "| Métrica | n | p50 | p90 | p95 |", "| --- | ---: | ---: | ---: | ---: |"])
        for name, values in metrics.items():
            lines.append(
                f"| {name} | {values['n']} | {values['p50'] if values['p50'] is not None else '—'} | {values['p90'] if values['p90'] is not None else '—'} | {values['p95'] if values['p95'] is not None else '—'} |"
            )
        lines.append("")
    lines.extend(["## Saludo inicial", "", "| Métrica | n | p50 | p90 | p95 |", "| --- | ---: | ---: | ---: | ---: |"])
    for name, values in summary["startup"].items():
        lines.append(
            f"| {name} | {values['n']} | {values['p50'] if values['p50'] is not None else '—'} | {values['p90'] if values['p90'] is not None else '—'} | {values['p95'] if values['p95'] is not None else '—'} |"
        )
    lines.extend(["", "## Etapas RAG", "", "| Métrica | n | p50 | p90 | p95 |", "| --- | ---: | ---: | ---: | ---: |"])
    for name, values in summary["rag"].items():
        lines.append(
            f"| {name}_ms | {values['n']} | {values['p50'] if values['p50'] is not None else '—'} | {values['p90'] if values['p90'] is not None else '—'} | {values['p95'] if values['p95'] is not None else '—'} |"
        )
    return "\n".join(lines)


def compare(paths: Iterable[str]) -> dict[str, Any]:
    """Resume cada corrida y calcula deltas contra la primera (baseline)."""
    inputs = list(paths)
    if len(inputs) < 2:
        raise ValueError("compare requiere baseline y al menos una candidata")
    per_input = {path: _load_summary(path) for path in inputs}
    baseline = per_input[inputs[0]]
    baseline_e2e = baseline["groups"]["all"]["e2e_latency_ms"]["p50"]
    comparisons: dict[str, Any] = {}
    for path in inputs[1:]:
        candidate = per_input[path]
        candidate_e2e = candidate["groups"]["all"]["e2e_latency_ms"]["p50"]
        delta = None
        if baseline_e2e is not None and candidate_e2e is not None:
            delta = round(candidate_e2e - baseline_e2e, 3)
        stage_deltas: dict[str, dict[str, dict[str, float | None]]] = {}
        for group in ("all", "rag", "no_rag", "cold", "warm"):
            stage_deltas[group] = {}
            for metric in _CORE_METRICS:
                before = baseline["groups"][group][metric]["p50"]
                after = candidate["groups"][group][metric]["p50"]
                stage_deltas[group][metric] = {
                    "baseline_p50_ms": before,
                    "candidate_p50_ms": after,
                    "delta_ms": round(after - before, 3)
                    if before is not None and after is not None
                    else None,
                }
        for metric in ("total", "embedding", "vector", "rerank"):
            before = baseline["rag"][metric]["p50"]
            after = candidate["rag"][metric]["p50"]
            stage_deltas.setdefault("rag_stages", {})[metric] = {
                "baseline_p50_ms": before,
                "candidate_p50_ms": after,
                "delta_ms": round(after - before, 3)
                if before is not None and after is not None
                else None,
            }
        comparisons[path] = {
            "summary": candidate,
            "configuration": candidate["configs"],
            "p50_by_stage": stage_deltas,
            "e2e_p50_delta_ms": delta,
            "e2e_p50_improvement_pct": (
                round((-delta / baseline_e2e) * 100, 2)
                if delta is not None and baseline_e2e
                else None
            ),
        }
    return {"baseline": {"path": inputs[0], "summary": baseline}, "candidates": comparisons}


def _load_summary(path_string: str) -> dict[str, Any]:
    """Carga un reporte de ``summarize`` o resume uno o más JSONL crudos.

    Los reportes terminan en ``.json`` y los eventos crudos en ``.jsonl``.  La
    distinción evita que una comparación de los archivos entregables intente
    interpretar cada línea de JSON formateado como un evento independiente.
    """
    path = Path(path_string)
    if path.is_file() and path.suffix == ".json":
        with path.open(encoding="utf-8") as source:
            payload = json.load(source)
        if isinstance(payload, dict) and "groups" in payload and "rag" in payload:
            return payload
        raise ValueError(f"{path} no es un reporte de latencia válido")
    return summarize([path_string])


def _render_comparison_markdown(result: dict[str, Any]) -> str:
    lines = ["# Comparación de latencia", "", "| Corrida | p50 E2E (ms) | Δ vs baseline (ms) | Mejora |", "| --- | ---: | ---: | ---: |"]
    baseline = result["baseline"]
    baseline_p50 = baseline["summary"]["groups"]["all"]["e2e_latency_ms"]["p50"]
    lines.append(f"| baseline ({baseline['path']}) | {baseline_p50 if baseline_p50 is not None else '—'} | — | — |")
    for path, candidate in result["candidates"].items():
        p50 = candidate["summary"]["groups"]["all"]["e2e_latency_ms"]["p50"]
        improvement = candidate["e2e_p50_improvement_pct"]
        lines.append(
            f"| {path} | {p50 if p50 is not None else '—'} | {candidate['e2e_p50_delta_ms'] if candidate['e2e_p50_delta_ms'] is not None else '—'} | "
            f"{f'{improvement}%' if improvement is not None else '—'} |"
        )
        lines.extend(["", f"## Etapas p50: {path}", "", "| Grupo | Métrica | Baseline | Candidata | Δ ms |", "| --- | --- | ---: | ---: | ---: |"])
        for group, metrics in candidate["p50_by_stage"].items():
            for metric, values in metrics.items():
                lines.append(
                    f"| {group} | {metric} | {values['baseline_p50_ms'] if values['baseline_p50_ms'] is not None else '—'} | {values['candidate_p50_ms'] if values['candidate_p50_ms'] is not None else '—'} | {values['delta_ms'] if values['delta_ms'] is not None else '—'} |"
                )
        if candidate["configuration"]:
            lines.extend(["", "Configuración: `" + json.dumps(candidate["configuration"], ensure_ascii=False) + "`"])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resume corridas JSONL de latencia")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("summarize", "compare"):
        sub = subparsers.add_parser(name)
        sub.add_argument("inputs", nargs="+", help="archivo(s) JSONL o directorio(s)")
        sub.add_argument("--json-out", help="ruta opcional para el resumen JSON")
        sub.add_argument("--markdown-out", help="ruta opcional para el reporte Markdown")
    args = parser.parse_args()
    if args.command == "compare":
        summary = compare(args.inputs)
        rendered = _render_comparison_markdown(summary)
    else:
        summary = summarize(args.inputs)
        rendered = _render_markdown(summary, "Resumen de latencia")
    print(rendered)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.markdown_out:
        Path(args.markdown_out).write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
