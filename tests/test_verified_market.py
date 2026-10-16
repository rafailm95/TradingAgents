"""Failure propagation, adversarial outputs and point-in-time data boundaries."""

import json
from unittest.mock import Mock

import pandas as pd
import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.output_quality import CompletionGuard, OutputQualityError
from tradingagents.agents.structured import invoke_structured_or_freetext
from tradingagents.dataflows.config import run_config
from tradingagents.verified_market import (
    LocalRanker,
    build_snapshot,
    parse_completion,
    run,
    validate_selection,
)


@pytest.fixture
def candles(tmp_path):
    # Synthetic TEST fixture, never used in the actual market experiment.
    close = [100.0 + i / 10 for i in range(220)]
    frame = pd.DataFrame({"Date": pd.date_range("2026-01-01", periods=220),
                          "Open": close, "High": [c + 1 for c in close],
                          "Low": [c - 1 for c in close], "Close": close, "Volume": 100.0})
    path = tmp_path / "candles.csv"
    frame.to_csv(path, index=False)
    return path, frame, frame.Date.iloc[-1].strftime("%Y-%m-%d")


@pytest.mark.parametrize("reason", ["length", "content_filter", None, "unexpected"])
def test_callback_blocks_downstream_before_consumption(reason):
    metadata = {"finish_reason": reason} if reason else {}
    model = FakeMessagesListChatModel(responses=[AIMessage(content="cut off", response_metadata=metadata)],
                                     callbacks=[CompletionGuard()])
    consumer = Mock()
    with pytest.raises(OutputQualityError):
        (model | RunnableLambda(consumer)).invoke("test")
    consumer.assert_not_called()


def test_successful_completion_reaches_consumer():
    model = FakeMessagesListChatModel(responses=[AIMessage(content="done", response_metadata={"finish_reason": "stop"})],
                                     callbacks=[CompletionGuard()])
    assert model.invoke("test").content == "done"


@pytest.mark.parametrize("failure", [OutputQualityError("truncated"), ValueError("bad schema")])
def test_strict_structured_failure_cannot_trigger_freetext_retry(failure):
    structured, plain = Mock(), Mock()
    structured.invoke.side_effect = failure
    with run_config({"strict_output_quality": True}), pytest.raises(OutputQualityError):
        invoke_structured_or_freetext(structured, plain, "prompt", str, "test")
    plain.invoke.assert_not_called()


def test_guard_exception_is_never_swallowed_even_outside_strict_context():
    structured, plain = Mock(), Mock()
    structured.invoke.side_effect = OutputQualityError("truncated")
    with run_config({"strict_output_quality": False}), pytest.raises(OutputQualityError):
        invoke_structured_or_freetext(structured, plain, "prompt", str, "test")
    plain.invoke.assert_not_called()


@pytest.mark.parametrize("kind", ["duplicate", "gap", "nan", "infinity", "bad_high", "negative_volume", "stale"])
def test_bad_data_rejected_before_any_ai_call(candles, tmp_path, kind):
    path, frame, cutoff = candles
    if kind == "duplicate":
        frame.loc[1, "Date"] = frame.loc[0, "Date"]
    elif kind == "gap":
        frame = frame.drop(10)
    elif kind == "nan":
        frame.loc[1, "Close"] = float("nan")
    elif kind == "infinity":
        frame.loc[1, "Close"] = float("inf")
    elif kind == "bad_high":
        frame.loc[1, "High"] = 1
    elif kind == "negative_volume":
        frame.loc[1, "Volume"] = -1
    else:
        frame = frame.iloc[:-1]
    frame.to_csv(path, index=False)
    ranker = Mock()
    with pytest.raises(ValueError):
        run(path, cutoff, tmp_path / "out", ranker)
    ranker.assert_not_called()
    assert not (tmp_path / "out/report.md").exists()


def test_future_price_cannot_leak_into_snapshot(candles):
    path, frame, cutoff = candles
    before = build_snapshot(path, cutoff)
    future = frame.iloc[-1:].copy()
    future["Date"] += pd.Timedelta(days=1)
    future[["Open", "High", "Low", "Close"]] = 10_000_000
    pd.concat([frame, future]).to_csv(path, index=False)
    after = build_snapshot(path, cutoff)
    assert after["excluded_future_rows"] == 1
    assert before["indicators"] == after["indicators"]
    assert before["facts"] == after["facts"]


@pytest.mark.parametrize("bad", [
    {"ranked_ids": ["invented_news"]}, {"ranked_ids": ["sma50", "sma50"]},
    {"ranked_ids": ["rsi"]}, {"ranked_ids": ["sma50"], "forecast": "guaranteed profit"},
    {"ranked_ids": []}, {"ranked_ids": [1]}, None,
])
def test_invalid_first_role_blocks_next_role_and_report(candles, tmp_path, bad):
    path, _, cutoff = candles
    ranker = Mock(return_value=bad)
    with pytest.raises(OutputQualityError):
        run(path, cutoff, tmp_path / "out", ranker)
    assert ranker.call_count == 1
    assert not (tmp_path / "out/report.md").exists()
    assert json.loads((tmp_path / "out/summary.json").read_text())["status"] == "REJECTED"


@pytest.mark.parametrize("content,reason", [
    ('{"ranked_ids": ["sma50"]}', "length"),
    ('{"ranked_ids":', "stop"),
    ('{"ranked_ids": [], "ranked_ids": ["sma50"]}', "stop"),
])
def test_parse_failure(content, reason):
    with pytest.raises(OutputQualityError):
        parse_completion({"choices": [{"finish_reason": reason, "message": {"content": content}}]})


@pytest.mark.parametrize("endpoint", ["https://api.openai.com/v1", "http://example.com/v1",
    "http://127.0.0.1:18080/v1?proxy=remote", "http://user:secret@127.0.0.1:18080/v1"])
def test_nonlocal_or_ambiguous_endpoint_rejected(endpoint):
    with pytest.raises(ValueError):
        LocalRanker(endpoint, "unused")


def test_report_keeps_all_facts_despite_narrow_model_selection(candles, tmp_path):
    path, _, cutoff = candles
    def ranker(snapshot, polarity, _output):
        ids = [fact["id"] for fact in snapshot["facts"] if fact["polarity"] == polarity]
        return {"ranked_ids": ids[:1]}
    output = tmp_path / "out"
    result = run(path, cutoff, output, ranker)
    assert result["status"] == "ACCEPTED_TECHNICAL_OUTPUT"
    report = (output / "report.md").read_text()
    for fact in build_snapshot(path, cutoff)["facts"]:
        assert fact["text"] in report
    assert "institutional" in report
    with pytest.raises(FileExistsError):
        run(path, cutoff, output, ranker)


def test_opposite_polarity_rejected():
    snapshot = {"facts": [{"id": "above", "polarity": "support"}, {"id": "below", "polarity": "risk"}]}
    with pytest.raises(OutputQualityError):
        validate_selection({"ranked_ids": ["below"]}, snapshot, "support")


def test_empty_perspective_does_not_call_model(candles, tmp_path):
    path, _, cutoff = candles
    calls = []

    def ranker(snapshot, polarity, _output):
        calls.append(polarity)
        ids = [fact["id"] for fact in snapshot["facts"] if fact["polarity"] == polarity]
        assert ids
        return {"ranked_ids": ids[:1]}

    run(path, cutoff, tmp_path / "out", ranker)
    assert calls == ["support"]  # Monotonically increasing fixture.
