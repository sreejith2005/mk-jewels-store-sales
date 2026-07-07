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


def test_validate_event_coerces_string_booleans():
    event = valid_event()
    event["objection_detected"] = "yes"
    event["price_concern"] = "false"
    event["certification_question"] = "FALSE"
    event["intent_signal"] = "1"
    event["script_deviation"] = "false"
    event["factual_error"] = "true"
    event["missed_script_response"] = "FALSE"
    event["knowledge_base_followed"] = "true"

    validated = validate_event(event)

    assert validated["objection_detected"] is True
    assert validated["price_concern"] is False
    assert validated["certification_question"] is False
    assert validated["intent_signal"] is True
    assert validated["script_deviation"] is False
    assert validated["factual_error"] is True
    assert validated["missed_script_response"] is False
    assert validated["knowledge_base_followed"] is True


def test_validate_event_accepts_display_transcript_and_raw_fallback():
    event = valid_event()
    event["transcript"] = "मुझे आपकी सर्विस बिल्कुल पसंद नहीं है"
    event["display_transcript"] = "Mujhe aapki service bilkul pasand nahi hai"

    validated = validate_event(event)

    assert validated["raw_transcript"] == "मुझे आपकी सर्विस बिल्कुल पसंद नहीं है"
    assert validated["display_transcript"] == "Mujhe aapki service bilkul pasand nahi hai"
    assert validated["transcript"] == "Mujhe aapki service bilkul pasand nahi hai"
