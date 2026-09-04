from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import rag.retriever as retriever_module
from agent import _RagPrefetch, _prefetch_category, _query_category, _session_prefetch
from metricas.latencia import LatencyRecorder, _render_comparison_markdown, _stats, compare, summarize
from rag.errors import RetrievalError
from rag.retriever import Retriever


def _item(role: str, metrics: dict | None = None, text: str = "") -> SimpleNamespace:
    return SimpleNamespace(role=role, metrics=metrics or {}, text_content=text)


def test_recorder_correlates_user_assistant_and_rag(monkeypatch, tmp_path):
    monkeypatch.setenv("LATENCY_RUN_ID", "unit")
    monkeypatch.setenv("LATENCY_OUTPUT_DIR", str(tmp_path))
    recorder = LatencyRecorder(room="room", config={"llm_model": "test"})
    recorder.record_conversation_item(
        _item(
            "user",
            {
                "transcription_delay": 0.1,
                "end_of_turn_delay": 0.3,
                "on_user_turn_completed_delay": 0.02,
            },
            "no guardar",
        )
    )
    recorder.record_component(
        SimpleNamespace(
            type="eou_metrics", speech_id="speech-1", metadata=None,
            end_of_utterance_delay=0.3, transcription_delay=0.1,
        )
    )
    recorder.record_component(
        SimpleNamespace(
            type="llm_metrics", speech_id="speech-1", metadata=None,
            ttft=0.2, duration=0.6, prompt_tokens=10, completion_tokens=4,
            total_tokens=14, connection_reused=True, cancelled=False,
        )
    )
    recorder.record_rag(
        speech_id="speech-1",
        status="ok",
        timings_ms={"total": 500, "embedding": 200, "vector": 300, "rerank": None},
        prefetched=False,
        query_category="no_respira",
    )
    recorder.record_conversation_item(_item("assistant", {"e2e_latency": 1.1, "llm_node_ttft": 0.2, "tts_node_ttfb": 0.25}, "respuesta"))
    recorder.close()

    events = [json.loads(line) for line in (tmp_path / "unit.jsonl").read_text().splitlines()]
    turn = next(event for event in events if event["event"] == "turn")
    assert turn["turn"] == 1
    assert turn["end_of_turn_delay_ms"] == 300.0
    assert turn["e2e_latency_ms"] == 1100.0
    assert turn["llm_calls"] == 1
    assert "user_text" not in turn
    rag = next(event for event in events if event["event"] == "rag")
    assert rag["turn"] == 1
    assert summarize([str(tmp_path)])["groups"]["rag"]["e2e_latency_ms"]["n"] == 1


def test_recorder_marks_filler_and_multiple_segments(monkeypatch, tmp_path):
    monkeypatch.setenv("LATENCY_RUN_ID", "fillers")
    monkeypatch.setenv("LATENCY_OUTPUT_DIR", str(tmp_path))
    recorder = LatencyRecorder()
    recorder.record_conversation_item(_item("user", {"end_of_turn_delay": 0.2}))
    recorder.record_conversation_item(_item("assistant", {}, "Dame un segundo."))
    recorder.record_conversation_item(_item("assistant", {"e2e_latency": 1.0}, "Indicá presión directa."))
    recorder.close()
    events = [json.loads(line) for line in (tmp_path / "fillers.jsonl").read_text().splitlines()]
    turns = [event for event in events if event["event"] == "turn"]
    assert [turn["is_filler"] for turn in turns] == [True, False]
    assert turns[1]["segment"] == 2


def test_recorder_correlates_eou_emitted_before_user_item(monkeypatch, tmp_path):
    monkeypatch.setenv("LATENCY_RUN_ID", "late-user")
    monkeypatch.setenv("LATENCY_OUTPUT_DIR", str(tmp_path))
    recorder = LatencyRecorder()
    recorder.record_component(SimpleNamespace(type="llm_metrics", speech_id="late", metadata=None))
    recorder.record_component(SimpleNamespace(type="eou_metrics", speech_id="late", metadata=None))
    recorder.record_conversation_item(_item("user", {"end_of_turn_delay": 0.2}))
    recorder.record_conversation_item(_item("assistant", {"e2e_latency": 1.0}, "respuesta"))
    recorder.close()
    events = [json.loads(line) for line in (tmp_path / "late-user.jsonl").read_text().splitlines()]
    correlation = next(event for event in events if event["event"] == "correlation")
    turn = next(event for event in events if event["event"] == "turn")
    assert correlation["speech_id"] == "late" and correlation["turn"] == 1
    assert turn["llm_calls"] == 1


def test_recorder_does_not_assign_next_eou_to_previous_turn(monkeypatch, tmp_path):
    monkeypatch.setenv("LATENCY_RUN_ID", "next-turn")
    monkeypatch.setenv("LATENCY_OUTPUT_DIR", str(tmp_path))
    recorder = LatencyRecorder()
    recorder.record_conversation_item(_item("user"))
    recorder.record_component(SimpleNamespace(type="eou_metrics", speech_id="first", metadata=None))
    recorder.record_conversation_item(_item("assistant", {}, "primera"))
    recorder.record_component(SimpleNamespace(type="eou_metrics", speech_id="second", metadata=None))
    recorder.record_component(SimpleNamespace(type="llm_metrics", speech_id="second", metadata=None))
    recorder.record_conversation_item(_item("user"))
    recorder.record_conversation_item(_item("assistant", {}, "segunda"))
    recorder.close()
    events = [json.loads(line) for line in (tmp_path / "next-turn.jsonl").read_text().splitlines()]
    correlations = [event for event in events if event["event"] == "correlation"]
    assert [(event["speech_id"], event["turn"]) for event in correlations] == [
        ("first", 1),
        ("second", 2),
    ]


def test_recorder_measures_first_agent_speaking(monkeypatch, tmp_path):
    monkeypatch.setenv("LATENCY_RUN_ID", "greeting")
    monkeypatch.setenv("LATENCY_OUTPUT_DIR", str(tmp_path))
    recorder = LatencyRecorder()
    recorder.record_startup(recorder.started_at)
    recorder.record_agent_state(SimpleNamespace(new_state="listening"))
    recorder.record_agent_state(SimpleNamespace(new_state="speaking"))
    recorder.record_agent_state(SimpleNamespace(new_state="speaking"))
    recorder.close()
    result = summarize([str(tmp_path / "greeting.jsonl")])
    assert result["startup"]["greeting_scheduled_ms"]["n"] == 1
    assert result["startup"]["first_agent_speaking_ms"]["n"] == 1


def test_compare_includes_per_stage_deltas(monkeypatch, tmp_path):
    monkeypatch.setenv("LATENCY_OUTPUT_DIR", str(tmp_path))
    for run_id, e2e in (("base", 1.0), ("candidate", 0.8)):
        monkeypatch.setenv("LATENCY_RUN_ID", run_id)
        recorder = LatencyRecorder(config={"llm_model": run_id})
        recorder.record_conversation_item(_item("user", {"end_of_turn_delay": 0.2}))
        recorder.record_conversation_item(_item("assistant", {"e2e_latency": e2e}))
        recorder.close()
    result = compare([str(tmp_path / "base.jsonl"), str(tmp_path / "candidate.jsonl")])
    candidate = result["candidates"][str(tmp_path / "candidate.jsonl")]
    assert candidate["p50_by_stage"]["all"]["e2e_latency_ms"]["delta_ms"] == -200.0
    assert "Etapas p50" in _render_comparison_markdown(result)


def test_stats_only_exposes_p95_with_enough_samples():
    assert _stats(range(19))["p95"] is None
    assert _stats(range(20))["p95"] is not None


def test_compare_accepts_generated_summary_json(monkeypatch, tmp_path):
    monkeypatch.setenv("LATENCY_RUN_ID", "summary-input")
    monkeypatch.setenv("LATENCY_OUTPUT_DIR", str(tmp_path))
    recorder = LatencyRecorder()
    recorder.record_conversation_item(_item("user", {"end_of_turn_delay": 0.2}))
    recorder.record_conversation_item(_item("assistant", {"e2e_latency": 1.0}, "respuesta"))
    recorder.close()

    raw_path = tmp_path / "summary-input.jsonl"
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summarize([str(raw_path)])), encoding="utf-8")

    result = compare([str(summary_path), str(raw_path)])
    candidate = result["candidates"][str(raw_path)]
    assert candidate["e2e_p50_delta_ms"] == 0.0


def test_concurrent_recorders_do_not_corrupt_jsonl(monkeypatch, tmp_path):
    monkeypatch.setenv("LATENCY_RUN_ID", "concurrent")
    monkeypatch.setenv("LATENCY_OUTPUT_DIR", str(tmp_path))
    recorders = [LatencyRecorder() for _ in range(4)]
    async def write_all():
        await asyncio.gather(
            *(asyncio.to_thread(recorder.record_startup, recorder.started_at) for recorder in recorders)
        )

    asyncio.run(write_all())
    for recorder in recorders:
        recorder.close()
    lines = (tmp_path / "concurrent.jsonl").read_text().splitlines()
    assert all(json.loads(line)["event"] for line in lines)


@pytest.mark.asyncio
async def test_retriever_records_stage_timings(monkeypatch):
    async def fake_embed(query, settings):
        return [0.1, 0.2]

    class Store:
        async def search(self, vector, limit):
            return []

    retriever = Retriever.__new__(Retriever)
    retriever._settings = SimpleNamespace(
        timeout_s=1.0, k_vector=3, rerank_enabled=False, min_score=0.5,
        min_rerank_score=0.08, top_k=3,
    )
    retriever._store = Store()
    monkeypatch.setattr(retriever_module, "embed_query", fake_embed)
    result = await retriever.search("consulta")
    assert result.status == "no_match"
    assert result.timings_ms["total"] is not None
    assert result.timings_ms["embedding"] is not None
    assert result.timings_ms["vector"] is not None


@pytest.mark.asyncio
async def test_retriever_keeps_partial_timing_on_error(monkeypatch):
    async def failing_embed(query, settings):
        raise RetrievalError("sin embedding")

    retriever = Retriever.__new__(Retriever)
    retriever._settings = SimpleNamespace(timeout_s=1.0)
    monkeypatch.setattr(retriever_module, "embed_query", failing_embed)
    result = await retriever.search("consulta")
    assert result.status == "error"
    assert result.timings_ms["embedding"] is not None
    assert result.timings_ms["total"] is not None


@pytest.mark.asyncio
async def test_retriever_keeps_partial_timing_on_timeout(monkeypatch):
    async def slow_embed(query, settings):
        await asyncio.sleep(0.05)
        return [0.1]

    retriever = Retriever.__new__(Retriever)
    retriever._settings = SimpleNamespace(timeout_s=0.001)
    monkeypatch.setattr(retriever_module, "embed_query", slow_embed)
    result = await retriever.search("consulta")
    assert result.status == "error"
    assert result.timings_ms["embedding"] is not None
    assert result.timings_ms["total"] is not None


def test_prefetch_categories_do_not_treat_unconscious_as_rcp():
    assert _prefetch_category("Está inconsciente y no responde") is None
    assert _prefetch_category("No respira y no se mueve") == "no_respira"
    assert _prefetch_category("Hay mucha sangre") == "hemorragia"
    assert _query_category("herido inconsciente que no respira RCP") == "no_respira"


@pytest.mark.asyncio
async def test_prefetch_is_consumed_only_by_matching_query():
    task = asyncio.create_task(asyncio.sleep(0, result="resultado"))
    state = SimpleNamespace(_rag_prefetch=_RagPrefetch("no_respira", task))
    context = SimpleNamespace(userdata=state)
    matched, used, category = _session_prefetch(context, "no respira RCP")
    assert used and category == "no_respira" and await matched == "resultado"
    assert state._rag_prefetch is None

    other_task = asyncio.create_task(asyncio.sleep(0, result="resultado"))
    state._rag_prefetch = _RagPrefetch("hemorragia", other_task)
    matched, used, _ = _session_prefetch(context, "no respira RCP")
    assert matched is None and not used
    assert state._rag_prefetch is None
    with pytest.raises(asyncio.CancelledError):
        await other_task
