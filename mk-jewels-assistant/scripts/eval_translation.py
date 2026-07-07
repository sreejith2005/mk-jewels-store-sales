"""
ISOLATED EVAL SCRIPT - DO NOT RUN IN THE PRODUCTION VENV.

Setup (run once):
  cd mk-jewels-assistant
  python3 -m venv ../venv-eval
  source ../venv-eval/bin/activate
  pip install -r requirements-dev.txt

Run:
  source ../venv-eval/bin/activate
  python scripts/eval_translation.py

Never run this with the production venv (../venv or ./venv) active.
Installing these dependencies into the production venv previously
broke the live STT service by upgrading transformers.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import torch
from huggingface_hub import snapshot_download
from IndicTransToolkit.processor import IndicProcessor
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer


MODEL_NAME = "ai4bharat/indictrans2-indic-en-dist-200M"
SRC_LANG = "hin_Deva"
TGT_LANG = "eng_Latn"
MAX_LENGTH = 256
NUM_BEAMS = 5

SAMPLES = [
    "यस शर",
    "नंडंडंड",
    "चौ कडूड",
    "हलो यस ऑल राइट",
    "हेलो जी बोलिए यस य अमिंद स्टोर",
    "वॉट आर यू लुकिंग फॉर ओके यू आर लुकिंग फॉर डायमंड ओके सो डायमंड",
    "आपके लिए तो बहुत महंगा लग रहा है आई डोंट थिंक यू कैन बाय दिस आई डोंट थिंक यू ऑफ दी मनी",
    "तू बाई दिस डायमंड नेकस श्योर शो न प्रब्म",
    "य कन बा दट बक",
    "मिन मिनट",
    "दस यू कैन बायटस कस्ट आ",
    "अच्छ",
    "द न और ब",
]


def _require_isolated_eval_venv() -> None:
    venv_path = Path(sys.prefix).resolve()
    venv_name = venv_path.name.lower()
    if venv_name != "venv-eval":
        raise SystemExit(
            "Refusing to run outside the isolated eval venv. "
            f"Expected active venv named 'venv-eval', got: {venv_path}"
        )


def _directory_size_bytes(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for filename in files:
            file_path = Path(root) / filename
            try:
                total += file_path.stat().st_size
            except OSError:
                pass
    return total


def _format_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "K", "M", "G", "T"):
        if value < 1024 or unit == "T":
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}T"


def _translate(
    text: str,
    tokenizer: AutoTokenizer,
    model: AutoModelForSeq2SeqLM,
    processor: IndicProcessor,
) -> str:
    batch = processor.preprocess_batch([text], src_lang=SRC_LANG, tgt_lang=TGT_LANG)
    inputs = tokenizer(
        batch,
        truncation=True,
        padding="longest",
        max_length=MAX_LENGTH,
        return_tensors="pt",
    )
    with torch.no_grad():
        generated_tokens = model.generate(
            **inputs,
            use_cache=True,
            min_length=0,
            max_length=MAX_LENGTH,
            num_beams=NUM_BEAMS,
            num_return_sequences=1,
        )

    decoded = tokenizer.batch_decode(
        generated_tokens,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=True,
    )
    return processor.postprocess_batch(decoded, lang=TGT_LANG)[0]


def main() -> int:
    _require_isolated_eval_venv()

    print("IndicTrans2 isolated translation eval")
    print(f"Python: {sys.executable}")
    print(f"Venv: {Path(sys.prefix).resolve()}")
    print(f"Model: {MODEL_NAME}")
    print("Device: cpu")
    print()

    load_start = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(
        MODEL_NAME,
        trust_remote_code=True,
    ).to("cpu")
    model.eval()
    processor = IndicProcessor(inference=True)
    load_ms = (time.perf_counter() - load_start) * 1000

    inference_times = []
    for index, sample in enumerate(SAMPLES, start=1):
        sentence_start = time.perf_counter()
        translated = _translate(sample, tokenizer, model, processor)
        elapsed_ms = (time.perf_counter() - sentence_start) * 1000
        inference_times.append(elapsed_ms)

        print(f"Sample {index}")
        print(f"Original: {sample}")
        print(f"Translated: {translated}")
        print(f"Time ms: {elapsed_ms:.2f}")
        print()

    average_ms = sum(inference_times) / len(inference_times)
    snapshot_path = Path(snapshot_download(MODEL_NAME)).resolve()
    cache_root = Path.home() / ".cache" / "huggingface" / "hub"
    cache_root = cache_root.resolve()
    cache_status = (
        "yes"
        if snapshot_path.is_relative_to(cache_root)
        else "no"
    )
    model_size = _format_size(_directory_size_bytes(snapshot_path))

    print(f"Model load time ms: {load_ms:.2f}")
    print(f"Average inference time ms: {average_ms:.2f}")
    print(f"HF cache root: {cache_root}")
    print(f"Model snapshot path: {snapshot_path}")
    print(f"Downloaded under ~/.cache/huggingface/hub: {cache_status}")
    print(f"Model disk size: {model_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
