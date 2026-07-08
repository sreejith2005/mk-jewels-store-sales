from __future__ import annotations

import logging
import re
import sys
import time
import traceback

import torch
from flask import Flask, jsonify, request
from IndicTransToolkit.processor import IndicProcessor
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


MODEL_NAME = "ai4bharat/indictrans2-indic-en-dist-200M"
SRC_LANG = "hin_Deva"
TGT_LANG = "eng_Latn"
MAX_LENGTH = 256
NUM_BEAMS = 5
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def _load_model() -> tuple[AutoTokenizer, AutoModelForSeq2SeqLM, IndicProcessor, float]:
    load_start = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(
        MODEL_NAME,
        trust_remote_code=True,
    ).to("cpu")
    model.eval()
    processor = IndicProcessor(inference=True)
    load_ms = (time.perf_counter() - load_start) * 1000
    return tokenizer, model, processor, load_ms


try:
    TOKENIZER, MODEL, PROCESSOR, MODEL_LOAD_MS = _load_model()
except Exception:
    logger.exception("Failed to load translation model")
    sys.exit(1)

logger.info("Translation model loaded in %.2f ms", MODEL_LOAD_MS)


def _translate(text: str) -> str:
    batch = PROCESSOR.preprocess_batch([text], src_lang=SRC_LANG, tgt_lang=TGT_LANG)
    inputs = TOKENIZER(
        batch,
        truncation=True,
        padding="longest",
        max_length=MAX_LENGTH,
        return_tensors="pt",
    )
    with torch.no_grad():
        generated_tokens = MODEL.generate(
            **inputs,
            use_cache=True,
            min_length=0,
            max_length=MAX_LENGTH,
            num_beams=NUM_BEAMS,
            num_return_sequences=1,
        )

    decoded = TOKENIZER.batch_decode(
        generated_tokens,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=True,
    )
    return PROCESSOR.postprocess_batch(decoded, lang=TGT_LANG)[0]


@app.get("/health")
def health():
    return jsonify({"status": "ok", "model_loaded": True}), 200


@app.post("/translate")
def translate():
    start = time.perf_counter()
    try:
        payload = request.get_json(silent=True) or {}
        text = payload.get("text", "")
        if not isinstance(text, str):
            return jsonify({"error": "text must be a string"}), 400

        if not text or not DEVANAGARI_RE.search(text):
            elapsed_ms = (time.perf_counter() - start) * 1000
            return jsonify({"translated": text, "time_ms": elapsed_ms}), 200

        translated = _translate(text)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return jsonify({"translated": translated, "time_ms": elapsed_ms}), 200
    except Exception as error:
        logger.error("Translation request failed:\n%s", traceback.format_exc())
        return jsonify({"error": str(error)}), 500
