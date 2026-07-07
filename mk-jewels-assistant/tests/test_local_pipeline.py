import importlib
import sys
import types


def test_local_pipeline_keeps_devanagari_raw_transcript(monkeypatch):
    raw_transcript = "\u092e\u0941\u091d\u0947 \u0906\u092a\u0915\u0940 \u0938\u0930\u094d\u0935\u093f\u0938 \u092c\u093f\u0932\u094d\u0915\u0941\u0932 \u092a\u0938\u0902\u0926 \u0928\u0939\u0940\u0902 \u0939\u0948"

    fake_stt = types.SimpleNamespace(
        transcribe=lambda audio_bytes, sample_rate: raw_transcript
    )
    monkeypatch.setitem(sys.modules, "transcription.indic_conformer_stt", fake_stt)
    sys.modules.pop("transcription.local_pipeline", None)
    local_pipeline = importlib.import_module("transcription.local_pipeline")

    monkeypatch.setattr(
        local_pipeline.qwen3_triage,
        "triage",
        lambda transcript, salesperson_name: {
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

    assert event["raw_transcript"] == raw_transcript
    assert event["display_transcript"] == "Mujhe aapki service bilkul pasand nahi hai"
    assert "prAijiMga" not in event["raw_transcript"]
    assert "kaiMDa" not in event["raw_transcript"]
