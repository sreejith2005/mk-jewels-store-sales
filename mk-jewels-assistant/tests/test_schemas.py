import pytest

from core.schemas import validate_event


def valid_event():
    return {
        "transcript": "Customer asked about a diamond ring.",
        "objection_detected": False,
        "price_concern": False,
        "certification_question": True,
        "upsell_miss": False,
        "knowledge_gap": False,
        "intent_signal": True,
        "alert_priority": "medium",
        "reasoning": "Customer asked for certification details.",
    }


def test_validate_event_accepts_valid_event():
    validate_event(valid_event())


def test_validate_event_rejects_missing_transcript():
    event = valid_event()
    del event["transcript"]

    with pytest.raises(ValueError):
        validate_event(event)


def test_validate_event_rejects_invalid_alert_priority():
    event = valid_event()
    event["alert_priority"] = "critical"

    with pytest.raises(ValueError):
        validate_event(event)


def test_validate_event_coerces_objection_detected_to_true():
    event = valid_event()
    event["objection_detected"] = 1

    validated = validate_event(event)

    assert validated["objection_detected"] is True


def test_validate_event_coerces_price_concern_to_false():
    event = valid_event()
    event["price_concern"] = 0

    validated = validate_event(event)

    assert validated["price_concern"] is False
