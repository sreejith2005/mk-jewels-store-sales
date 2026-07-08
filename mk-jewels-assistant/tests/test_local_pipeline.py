import importlib
import sys
import types

import requests


def test_local_pipeline_keeps_devanagari_raw_transcript(monkeypatch):
    raw_transcript = "\u092e\u0941\u091d\u0947 \u0906\u092a\u0915\u0940 \u0938\u0930\u094d\u0935\u093f\u0938 \u092c\u093f\u0932\u094d\u0915\u0941\u0932 \u092a\u0938\u0902\u0926 \u0928\u0939\u0940\u0902 \u0939\u0948"

    fake_stt = types.SimpleNamespace(
        transcribe=lambda audio_bytes, sample_rate: raw_transcript
    )
    monkeypatch.setitem(sys.modules, "transcription.indic_conformer_stt", fake_stt)
    sys.modules.pop("transcription.local_pipeline", None)
    local_pipeline = importlib.import_module("transcription.local_pipeline")
    triage_inputs = []

    monkeypatch.setattr(local_pipeline.Config, "PIPELINE_MODE", "production")
    monkeypatch.setattr(
        local_pipeline,
        "translate_to_english",
        lambda transcript: "I do not like your service at all",
    )

    monkeypatch.setattr(
        local_pipeline.qwen3_triage,
        "triage",
        lambda transcript, salesperson_name: triage_inputs.append(transcript) or {
            "transcript": "Mujhe aapki service bilkul pasand nahi hai",
            "raw_transcript": transcript,
            "display_transcript": "Mujhe aapki service bilkul pasand nahi hai",
            "objection_detected": True,
            "price_concern": False,
            "certification_question": False,
            "upsell_miss": False,
            "knowledge_gap": False,
            "intent_signal": False,
            "alert_priority": "medium",
            "reasoning": "Customer disliked service.",
        },
    )

    event = local_pipeline.transcribe_and_triage(b"\0\0" * 100, 16000, "Maya")

    assert triage_inputs == ["I do not like your service at all"]
    assert event["raw_transcript"] == raw_transcript
    assert event["display_transcript"] == "Mujhe aapki service bilkul pasand nahi hai"
    assert "prAijiMga" not in event["raw_transcript"]
    assert "kaiMDa" not in event["raw_transcript"]


def test_translate_to_english_returns_translated_text(monkeypatch):
    from transcription import local_pipeline

    def fake_post(url, json, timeout):
        assert url == "http://translate.local/translate"
        assert json == {"text": "नमस्ते"}
        assert timeout == (3, 15)

        class Response:
            status_code = 200

            def json(self):
                return {"translated": "Hello", "time_ms": 12.3}

        return Response()

    monkeypatch.setattr(local_pipeline.Config, "TRANSLATE_TO_ENGLISH", "true")
    monkeypatch.setattr(local_pipeline.Config, "TRANSLATE_SERVICE_URL", "http://translate.local")
    monkeypatch.setattr(local_pipeline.requests, "post", fake_post)

    assert local_pipeline.translate_to_english("नमस्ते") == "Hello"


def test_translate_to_english_falls_back_on_connection_error(monkeypatch):
    from transcription import local_pipeline

    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        raise requests.ConnectionError("service down")

    monkeypatch.setattr(local_pipeline.Config, "TRANSLATE_TO_ENGLISH", "true")
    monkeypatch.setattr(local_pipeline.Config, "TRANSLATE_SERVICE_URL", "http://translate.local")
    monkeypatch.setattr(local_pipeline.requests, "post", fake_post)
    monkeypatch.setattr(local_pipeline.time, "sleep", lambda seconds: None)

    assert local_pipeline.translate_to_english("मुझे अच्छा लगा") == "मुझे अच्छा लगा"
    assert len(calls) == 2


def test_translate_to_english_disabled_skips_http(monkeypatch):
    from transcription import local_pipeline

    def fake_post(url, json, timeout):
        raise AssertionError("HTTP call should not be attempted")

    monkeypatch.setattr(local_pipeline.Config, "TRANSLATE_TO_ENGLISH", "false")
    monkeypatch.setattr(local_pipeline.requests, "post", fake_post)

    assert local_pipeline.translate_to_english("नमस्ते") == "नमस्ते"


def test_translate_to_english_empty_input_skips_http(monkeypatch):
    from transcription import local_pipeline

    def fake_post(url, json, timeout):
        raise AssertionError("HTTP call should not be attempted")

    monkeypatch.setattr(local_pipeline.Config, "TRANSLATE_TO_ENGLISH", "true")
    monkeypatch.setattr(local_pipeline.requests, "post", fake_post)

    assert local_pipeline.translate_to_english("") == ""
    assert local_pipeline.translate_to_english("   ") == "   "
