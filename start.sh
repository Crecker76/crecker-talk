#!/usr/bin/env bash
# CreckerTalk — one-command start (macOS / Linux).
# Prereqs (one-time): Docker + Ollama must be installed.
#   Linux note: Ollama must listen on all interfaces so the container can reach it:
#   run  `OLLAMA_HOST=0.0.0.0 ollama serve`  (or set it as a service env var).
set -euo pipefail
cd "$(dirname "$0")"

# 1. .env from the prod preset if missing
if [ ! -f .env ]; then
  cp .env.prod.example .env
  echo "[CreckerTalk] created .env from .env.prod.example"
fi

# 2. pull the model named in .env
model="$(grep -E '^[[:space:]]*OLLAMA_MODEL[[:space:]]*=' .env | head -1 | sed -E 's/^[[:space:]]*OLLAMA_MODEL[[:space:]]*=//' | tr -d '[:space:]')"
model="${model:-dolphin3:8b}"
echo "[CreckerTalk] pulling model: $model  (first run can take a while)"
ollama pull "$model"

# 3. build & start
echo "[CreckerTalk] building and starting the container..."
docker compose up -d --build

echo "[CreckerTalk] running at http://localhost:8000  — hold Space to talk"
