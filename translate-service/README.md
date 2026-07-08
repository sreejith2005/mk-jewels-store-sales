# Standalone Translation Service

This service runs IndicTrans2 Hindi/Devanagari to English translation in a separate Python environment and process. It is intentionally isolated because `ai4bharat/indictrans2-indic-en-dist-200M` requires `transformers==4.44.2`, while the production IndicConformer STT stack requires `transformers==4.57.6`. Running both in one venv has caused production dependency collisions, so the backend will later call this service over local HTTP only.

The service binds only to `127.0.0.1:8811`. It must not be exposed publicly.

## Setup

```bash
cd translate-service
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

If the model is not already cached, authenticate Hugging Face access in this isolated venv before startup:

```bash
huggingface-cli login
```

Alternatively, provide an access token to the service process with `HF_TOKEN`.

## Run

Manual run for testing:

```bash
source venv/bin/activate
gunicorn --bind 127.0.0.1:8811 --workers 1 --timeout 60 app:app
```

`--workers 1` is intentional. The model is loaded once per worker process, so multiple workers would multiply memory usage without benefit for this low-throughput service.

## Test

```bash
curl http://127.0.0.1:8811/health
curl -X POST http://127.0.0.1:8811/translate \
  -H "Content-Type: application/json" \
  -d '{"text": "हेलो जी बोलिए यस य अमिंद स्टोर"}'
```
