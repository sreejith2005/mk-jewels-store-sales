from collections import defaultdict
import datetime
import time
from typing import Any

from google import genai
from google.genai import errors
from google.genai import types

from config import Config
from storage.db import Database


SYSTEM_PROMPT = (
    "You are a sales coaching expert for a jewelry store in India called MK Jewels. You will receive a summary of a salesperson's conversations from today and must generate a structured end-of-day coaching report."
)

USER_PROMPT_TEMPLATE = (
    f"Today's date: {datetime.date.today().strftime('%d %B %Y')}\n\n"
    "Here is today's conversation data for salesperson {name}:\n\n{context}\n\nGenerate a coaching report with these exact sections:\n1. PERFORMANCE SUMMARY (2-3 sentences overall assessment)\n2. STRENGTHS OBSERVED (bullet points of what they did well)\n3. AREAS FOR IMPROVEMENT (specific gaps with examples from transcripts)\n4. RECURRING PATTERNS (objections or concerns that came up multiple times)\n5. COACHING FOCUS FOR TOMORROW (1-2 specific things to practice)\n\nBe specific, reference actual transcript content where relevant, and keep the tone constructive."
)

SIGNAL_TYPES = (
    "objection_detected",
    "price_concern",
    "certification_question",
    "upsell_miss",
    "knowledge_gap",
    "intent_signal",
)


def generate_daily_report(salesperson_name: str = None):
    if not Config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to your environment or .env file.")

    db = Database()
    events = db.get_today_events(salesperson_name)
    if not events:
        if salesperson_name:
            print(f"No events found for {salesperson_name} today.")
        else:
            print("No events found for today.")
        return

    grouped_events = _group_events_by_salesperson(events)
    client = genai.Client(api_key=Config.GEMINI_API_KEY)

    for name in sorted(grouped_events):
        context = _build_context(grouped_events[name])
        try:
            response = _generate_report_with_retry(client, name, context)
        except Exception as exc:
            print(f"Failed to generate report for {name}: {exc}")
            continue

        report_text = response.text or ""

        print(f"\n===== Daily Coaching Report: {name} =====\n")
        print(report_text)

        db.save_report(name, report_text)


def _generate_report_with_retry(client: genai.Client, name: str, context: str, attempts: int = 3):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return client.models.generate_content(
                model="gemini-2.5-flash",
                contents=USER_PROMPT_TEMPLATE.format(name=name, context=context),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.2,
                ),
            )
        except errors.ServerError as exc:
            last_error = exc
            if attempt == attempts:
                break

            wait_seconds = attempt * 10
            print(
                f"Gemini is temporarily unavailable for {name}. "
                f"Retrying in {wait_seconds} seconds ({attempt}/{attempts})..."
            )
            time.sleep(wait_seconds)

    raise last_error


def _group_events_by_salesperson(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        name = event.get("salesperson_name")
        if name:
            grouped_events[name].append(event)
    return grouped_events


def _build_context(events: list[dict[str, Any]]) -> str:
    signal_counts = {
        signal_type: sum(1 for event in events if bool(event.get(signal_type)))
        for signal_type in SIGNAL_TYPES
    }
    transcripts = [
        str(event.get("transcript", "")).strip()
        for event in events
        if str(event.get("transcript", "")).strip()
    ]

    lines = [
        f"Total events: {len(events)}",
        "Signal counts:",
    ]
    lines.extend(f"- {signal_type}: {count}" for signal_type, count in signal_counts.items())
    lines.extend(
        [
            "",
            "Transcripts in order:",
            "\n\n".join(transcripts) if transcripts else "No transcript text available.",
        ]
    )

    return "\n".join(lines)
