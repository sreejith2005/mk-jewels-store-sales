from transcription import local_pipeline
from transcription import indic_conformer_stt


def test_indic_conformer_prefers_transcript_language_auto_then_english(monkeypatch):
    calls = []

    class FakeModel:
        def __call__(self, waveform, language, decoding):
            calls.append((language, decoding))
            if language == "auto":
                raise TypeError("auto unsupported")
            return "Hello diamond"

    monkeypatch.setattr(indic_conformer_stt.Config, "TRANSCRIPT_LANGUAGE", "auto")

    assert indic_conformer_stt._infer_transcript(FakeModel(), object()) == "Hello diamond"
    assert calls == [
        ("auto", indic_conformer_stt.DEFAULT_DECODING),
        ("en", indic_conformer_stt.DEFAULT_DECODING),
    ]


def test_romanize_hindi_skips_gemini_for_roman_transcript(monkeypatch):
    monkeypatch.setattr(local_pipeline.Config, "ROMANIZE_HINDI", True)
    monkeypatch.setattr(local_pipeline.Config, "GEMINI_API_KEY", "test-key")

    assert local_pipeline.romanize_hindi("Hello diamond") == "Hello diamond"


def test_romanize_hindi_falls_back_without_gemini_key(monkeypatch):
    raw_transcript = "मुझे डायमंड देखना है"
    monkeypatch.setattr(local_pipeline.Config, "ROMANIZE_HINDI", True)
    monkeypatch.setattr(local_pipeline.Config, "GEMINI_API_KEY", "")

    assert local_pipeline.romanize_hindi(raw_transcript) == raw_transcript


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
