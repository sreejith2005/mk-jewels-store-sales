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
        "Customer asked about necklace. Salesperson explained options.",
        "Asha",
    )

    assert len(calls) == 2
    assert calls[0]["timeout"] == (5, 90)
    assert calls[0]["json"]["think"] is False
    assert calls[0]["json"]["options"]["temperature"] == 0
    assert calls[0]["json"]["options"]["num_predict"] == 180
    assert calls[0]["json"]["options"]["stop"] == ["}"]
    assert result["greeting_score"] == 8
    assert result["customer_satisfaction"] == "Positive"


def test_score_session_returns_none_after_persistent_empty_response(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        return _FakeResponse("")

    monkeypatch.setattr(qwen3_triage.requests, "post", fake_post)
    monkeypatch.setattr(qwen3_triage.time, "sleep", lambda _seconds: None)

    result = qwen3_triage.score_session(
        "Customer asked about necklace. Salesperson explained options.",
        "Asha",
    )

    assert result is None
    assert len(calls) == 3
