from __future__ import annotations

import json

from triage import qwen3_triage


class _FakeResponse:
    status_code = 200

    def __init__(self, content: str):
        self._content = content
        self.text = json.dumps(
            {
                "done": True,
                "message": {"content": content},
            }
        )

    def json(self):
        return {
            "done": True,
            "message": {"content": self._content},
        }


def test_score_session_retries_empty_response(monkeypatch):
    responses = [
        _FakeResponse("   "),
        _FakeResponse(
            '{"greeting_score": 8, "product_knowledge_score": 7, '
            '"objection_handling_score": 6, "missed_oppurtuinity": 4, '
            '"upsell_score": 7, "closing_score": 8, '
            '"customer_satisfaction": "Positive", '
            '"score_reasoning": "Handled the customer well."'
        ),
    ]
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr(qwen3_triage.requests, "post", fake_post)
    monkeypatch.setattr(qwen3_triage.time, "sleep", lambda _seconds: None)

    result = qwen3_triage.score_session(
        "Customer: I need a necklace for my wedding and my budget is limited.\n"
        "Salesperson: Welcome, I can show bridal necklaces in your range and "
        "explain gold purity, making charges, certification, and exchange value.",
        "Asha",
    )

    assert len(calls) == 2
    assert calls[0]["timeout"] == (5, 90)
    assert calls[0]["json"]["think"] is False
    assert calls[0]["json"]["options"]["temperature"] == 0
    assert calls[0]["json"]["options"]["num_predict"] == 700
    assert result["greeting_score"] == 8
    assert result["customer_satisfaction"] == "Positive"


def test_score_session_parses_valid_json_response(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        return _FakeResponse(
            '{"score_status": "scored", "greeting_score": 9, '
            '"product_knowledge_score": 8, "objection_handling_score": 7, '
            '"missed_oppurtuinity": 2, "upsell_score": 8, "closing_score": 9, '
            '"customer_satisfaction": "Positive", '
            '"score_reasoning": "Clear greeting, good product explanation, and strong closing."}'
        )

    monkeypatch.setattr(qwen3_triage.requests, "post", fake_post)

    result = qwen3_triage.score_session(
        "Customer: I am shopping for a diamond ring but worry about certification.\n"
        "Salesperson: Welcome. This ring has IGI certification, BIS HUID details, "
        "and I can compare designs within your budget before we finalize.",
        "Asha",
    )

    assert len(calls) == 1
    assert result["score_status"] == "scored"
    assert result["greeting_score"] == 9
    assert result["missed_oppurtuinity"] == 2
    assert result["customer_satisfaction"] == "Positive"


def test_score_session_returns_none_after_persistent_empty_response(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        return _FakeResponse("")

    monkeypatch.setattr(qwen3_triage.requests, "post", fake_post)
    monkeypatch.setattr(qwen3_triage.time, "sleep", lambda _seconds: None)

    result = qwen3_triage.score_session(
        "Customer: I need a necklace for my wedding and my budget is limited.\n"
        "Salesperson: Welcome, I can show bridal necklaces in your range and "
        "explain gold purity, making charges, certification, and exchange value.",
        "Asha",
    )

    assert result is None
    assert len(calls) == 3


def test_score_session_retries_malformed_json_then_fails_gracefully(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        return _FakeResponse("not json")

    monkeypatch.setattr(qwen3_triage.requests, "post", fake_post)
    monkeypatch.setattr(qwen3_triage.time, "sleep", lambda _seconds: None)

    result = qwen3_triage.score_session(
        "Customer: I want bangles but this price is too high for me today.\n"
        "Salesperson: These are 22K gold bangles, making charges are explained, "
        "and I can show lighter options plus exchange value for old gold.",
        "Asha",
    )

    assert result is None
    assert len(calls) == 3


def test_score_session_insufficient_transcript_does_not_fake_fives(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        return _FakeResponse("{}")

    monkeypatch.setattr(qwen3_triage.requests, "post", fake_post)

    result = qwen3_triage.score_session("Customer: hello.\nSalesperson: hello.", "Asha")

    assert calls == []
    assert result == {
        "score_status": "insufficient_data",
        "reason": "Conversation too short / not enough transcript",
    }


def test_score_session_preserves_strong_and_poor_non_five_values(monkeypatch):
    responses = [
        _FakeResponse(
            '{"score_status": "scored", "greeting_score": 10, '
            '"product_knowledge_score": 9, "objection_handling_score": 8, '
            '"missed_oppurtuinity": 1, "upsell_score": 9, "closing_score": 10, '
            '"customer_satisfaction": "Positive", '
            '"score_reasoning": "Strong greeting, precise knowledge, and confident close."}'
        ),
        _FakeResponse(
            '{"score_status": "scored", "greeting_score": 2, '
            '"product_knowledge_score": 1, "objection_handling_score": 3, '
            '"missed_oppurtuinity": 9, "upsell_score": 2, "closing_score": 1, '
            '"customer_satisfaction": "Negative", '
            '"score_reasoning": "Weak greeting, wrong product facts, and no closing."}'
        ),
    ]

    monkeypatch.setattr(qwen3_triage.requests, "post", lambda *args, **kwargs: responses.pop(0))

    strong = qwen3_triage.score_session(
        "Customer: I want bridal jewellery and have questions about certification.\n"
        "Salesperson: Welcome. I will explain BIS HUID, IGI certificate, gold "
        "purity, budget options, matching earrings, and next steps clearly.",
        "Asha",
    )
    poor = qwen3_triage.score_session(
        "Customer: I want a certified diamond ring but this price feels high.\n"
        "Salesperson: No greeting. Certification does not matter, price cannot "
        "be explained, and there is no need to compare other designs.",
        "Asha",
    )

    assert strong["greeting_score"] == 10
    assert strong["missed_oppurtuinity"] == 1
    assert poor["greeting_score"] == 2
    assert poor["closing_score"] == 1
