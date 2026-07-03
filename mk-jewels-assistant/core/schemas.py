from typing import Literal, NotRequired, TypedDict


AlertPriority = Literal["none", "low", "medium", "high"]


class EventDict(TypedDict):
    transcript: str
    raw_transcript: NotRequired[str]
    display_transcript: NotRequired[str]
    triage_status: NotRequired[str]
    objection_detected: bool
    price_concern: bool
    certification_question: bool
    upsell_miss: bool
    knowledge_gap: bool
    intent_signal: bool
    script_deviation: NotRequired[bool]
    factual_error: NotRequired[bool]
    missed_script_response: NotRequired[bool]
    knowledge_base_followed: NotRequired[bool]
    alert_priority: AlertPriority
    reasoning: str


class SessionSummary(TypedDict):
    session_id: str
    salesperson_name: str
    start_time: str
    total_events: int
    alerts_fired: int


REQUIRED_EVENT_KEYS = {
    "transcript",
    "objection_detected",
    "price_concern",
    "certification_question",
    "upsell_miss",
    "knowledge_gap",
    "intent_signal",
    "alert_priority",
    "reasoning",
}
VALID_ALERT_PRIORITIES = {"none", "low", "medium", "high"}
BOOL_EVENT_KEYS = {
    "objection_detected",
    "price_concern",
    "certification_question",
    "upsell_miss",
    "knowledge_gap",
    "intent_signal",
    "script_deviation",
    "factual_error",
    "missed_script_response",
    "knowledge_base_followed",
}


def _coerce_bool(value) -> bool:
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def validate_event(event: dict) -> EventDict:
    """
    Validates that a dict returned by any triage function
    matches the EventDict schema. Raises ValueError with a
    clear message if keys are missing or alert_priority is invalid.
    """
    missing_keys = REQUIRED_EVENT_KEYS - set(event.keys())
    if missing_keys:
        missing = ", ".join(sorted(missing_keys))
        raise ValueError(f"Event is missing required keys: {missing}")

    alert_priority = event["alert_priority"]
    if alert_priority not in VALID_ALERT_PRIORITIES:
        valid = ", ".join(sorted(VALID_ALERT_PRIORITIES))
        raise ValueError(
            f"Invalid alert_priority: {alert_priority!r}. Expected one of: {valid}"
        )

    raw_transcript = str(event.get("raw_transcript") or event.get("transcript") or "")
    display_transcript = str(event.get("display_transcript") or raw_transcript)
    transcript = display_transcript or raw_transcript

    validated = {
        "transcript": transcript,
        "raw_transcript": raw_transcript,
        "display_transcript": display_transcript,
        "objection_detected": _coerce_bool(event["objection_detected"]),
        "price_concern": _coerce_bool(event["price_concern"]),
        "certification_question": _coerce_bool(event["certification_question"]),
        "upsell_miss": _coerce_bool(event["upsell_miss"]),
        "knowledge_gap": _coerce_bool(event["knowledge_gap"]),
        "intent_signal": _coerce_bool(event["intent_signal"]),
        "alert_priority": alert_priority,
        "reasoning": event["reasoning"],
    }
    for key in BOOL_EVENT_KEYS - REQUIRED_EVENT_KEYS:
        if key in event:
            validated[key] = _coerce_bool(event[key])
    if "triage_status" in event:
        validated["triage_status"] = str(event["triage_status"])
    return validated
