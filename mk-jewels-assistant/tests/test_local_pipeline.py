from transcription import local_pipeline


def test_local_pipeline_keeps_devanagari_raw_transcript(monkeypatch):
    raw_transcript = "मुझे आपकी सर्विस बिल्कुल पसंद नहीं है"

    monkeypatch.setattr(
        local_pipeline.indic_conformer_stt,
        "transcribe",
        lambda audio_bytes, sample_rate: raw_transcript,
    )
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
