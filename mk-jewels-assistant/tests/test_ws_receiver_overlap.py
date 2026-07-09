from capture.ws_receiver import prepend_audio_overlap, strip_transcript_overlap


def test_strip_transcript_overlap_removes_duplicate_prefix_words():
    previous = "customer asked about diamond certification"
    current = "diamond certification and making charges"

    assert strip_transcript_overlap(previous, current) == "and making charges"


def test_strip_transcript_overlap_keeps_text_without_overlap():
    previous = "customer asked about diamond certification"
    current = "salesperson explained hallmark details"

    assert strip_transcript_overlap(previous, current) == current


def test_strip_transcript_overlap_handles_fully_duplicate_short_transcript():
    previous = "diamond certification"
    current = "diamond certification"

    assert strip_transcript_overlap(previous, current) == ""


def test_prepend_audio_overlap_resends_previous_tail_before_chunk_body():
    previous_tail = b"tail"
    chunk_body = b"chunk"

    assert prepend_audio_overlap(previous_tail, chunk_body) == b"tailchunk"
