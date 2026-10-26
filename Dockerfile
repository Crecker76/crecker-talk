# CPU-only app container: FastAPI + WebSocket + VAD/STT/TTS pipeline.
# The LLM (Ollama) runs natively on the host, NOT here. No GPU passthrough.
# Python 3.11 is chosen for the widest wheel availability
# (faster-whisper / ctranslate2 / onnxruntime / piper-phonemize).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libgomp1  -> OpenMP runtime for ctranslate2 / onnxruntime
# espeak-ng -> phonemizer fallback for Piper TTS
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
        espeak-ng \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY frontend ./frontend
COPY syllabus.yaml ./syllabus.yaml

# Volumes (mounted by compose): model weights and the SQLite DB.
# They are created here so the paths exist even before the first mount.
RUN mkdir -p /app/models/whisper /app/models/piper /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
