from typing import Literal, TypedDict


AlertPriority = Literal["none", "low", "medium", "high"]


class EventDict(TypedDict):
    transcript: str
    objection_detected: bool
    price_concern: bool
    certification_question: bool
    upsell_miss: bool
    knowledge_gap: bool
    intent_signal: bool
    alert_priority: AlertPriority
    reasoning: str


class SessionSummary(TypedDict):
    session_id: str
    salesperson_name: str
    start_time: str
    total_events: int
    alerts_fired: int


REQUIRED_EVENT_KEYS = set(EventDict.__annotations__.keys())
VALID_ALERT_PRIORITIES = {"none", "low", "medium", "high"}
BOOL_EVENT_KEYS = {
    "objection_detected",
    "price_concern",
    "certification_question",
    "upsell_miss",
    "knowledge_gap",
    "intent_signal",
}


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

    return {
        "transcript": event["transcript"],
        "objection_detected": bool(event["objection_detected"]),
        "price_concern": bool(event["price_concern"]),
        "certification_question": bool(event["certification_question"]),
        "upsell_miss": bool(event["upsell_miss"]),
        "knowledge_gap": bool(event["knowledge_gap"]),
        "intent_signal": bool(event["intent_signal"]),
        "alert_priority": alert_priority,
        "reasoning": event["reasoning"],
    }
