# 🎙️ Voice English Trainer

Локальный голосовой тренажёр английского. Ты разговариваешь голосом через микрофон с
анимированным персонажем в браузере; модель поправляет ошибки, ведёт программу обучения и
по запросу объясняет правила по-русски. Всё локально, в Docker. LLM крутится в **нативной**
Ollama (берёт GPU), STT/TTS/VAD — на CPU в одном app-контейнере.

```
Браузер (микрофон, Web Audio, персонаж)
   │  WebSocket (аудио ⇄ аудио)
   ▼
app-контейнер (CPU-only, FastAPI)
   VAD (Silero в faster-whisper) → STT (faster-whisper) → Оркестратор
      → LLM (Ollama, нативно, GPU)  http://host.docker.internal:11434
         → TTS (Piper, по клаузам) → аудио обратно в браузер
   Прогресс ⇄ SQLite (volume)   Программа ← syllabus.yaml (volume)
```

- **Язык ВВОДА** (что слышит Whisper): переключается в UI по `Tab` (EN/RU), шлётся с каждым аудио.
- **Язык ОТВЕТА**: задаётся режимом (system-prompt), от переключателя ввода не зависит.
- **Два режима**: *разговор* (партнёр на английском) и *объясни правило* (преподаватель, по-русски).

---

## Требования

- **Windows 10/11**
- **Docker Desktop** с бэкендом **WSL2** → https://www.docker.com/products/docker-desktop/
- **Ollama для Windows** (ставится нативно, НЕ в Docker) → https://ollama.com/download
- GPU желателен, но не обязателен: без подходящей видеокарты Ollama считает на CPU (медленнее).
  Целевой сценарий — GTX 1050 Ti (4 ГБ VRAM): на GPU идёт **только LLM**.

---

## Установка (Windows, с нуля)

### 1. Поставить Docker Desktop (WSL2)
Установи Docker Desktop, при первом запуске выбери **Use WSL 2 based engine**. Дождись
статуса *Docker Desktop is running*.

### 2. Поставить нативную Ollama и скачать модель
Установи Ollama для Windows (она сама поднимает сервис на `http://localhost:11434` и сама
подхватывает GPU). Затем скачай модель под свой пресет:

```bash
# dev (ноут, можно без GPU):
ollama pull llama3.2:3b

# прод (целевой ПК, 4 ГБ VRAM) — нецензурированная 7B:
ollama pull dolphin-mistral
```

Проверь, что Ollama отвечает:

```bash
ollama list
```

> Контейнер ходит в Ollama по адресу `host.docker.internal:11434`. Саму Ollama в Docker
> поднимать НЕ нужно.

### 3. Склонировать репозиторий

```bash
git clone https://github.com/Crecker76/voice-english-trainer.git
cd voice-english-trainer
```

### 4. Выбрать пресет окружения
Скопируй подходящий пример в `.env`:

```bash
# на ноуте:
copy .env.dev.example .env

# на целевом ПК:
copy .env.prod.example .env
```

При желании поправь `.env` (модель, размер Whisper, голоса — см. таблицу ниже).

### 5. Запустить

```bash
docker compose up --build
```

Первый запуск дольше: собирается образ и при первом обращении докачиваются веса STT
(faster-whisper) и голоса TTS (Piper) — они кэшируются в папке `models/` (volume) и в
репозиторий не коммитятся.

### 6. Открыть в браузере

```
http://localhost:8000
```

Разреши доступ к микрофону. Готово.

---

## Управление

| Клавиша / действие | Что делает |
|---|---|
| **Зажать `Space`** | говорить (push-to-talk): зажал — говоришь, отпустил — отправка |
| **`Tab`** | переключить язык **ввода** EN ⇄ RU (виден бейджем у персонажа) |
| Кнопка **mode** | переключить режим: *разговор* (англ.) ⇄ *объясни правило* (рус.) |
| Поле ввода внизу | отправить текст без микрофона (удобно тестировать логику) |

Персонаж показывает состояние пайплайна: **idle → listening → thinking → speaking**.

---

## Разработка на ноуте

Цель — чтобы пайплайн просто поднимался и тестировалась логика; скорость вторична.

- Используй `.env.dev.example` (лёгкая модель `llama3.2:3b` или `qwen2.5:3b`, `WHISPER_MODEL=base`).
- Ollama может считать на CPU — это нормально, просто медленнее.
- Правь `syllabus.yaml` на хосте — он примонтирован в контейнер, пересборка не нужна
  (достаточно переподключить вкладку/новую сессию).
- Фронтенд (`frontend/`) и `syllabus.yaml` монтируются/читаются на лету; код Python требует
  перезапуска контейнера: `docker compose up --build` (или `restart`).
- Быстрый тест без микрофона: печатай в поле ввода внизу — проходит весь путь, кроме STT.

## Перенос на целевой ПК (GTX 1050 Ti, 4 ГБ VRAM)

Перенос сводится к трём шагам:

```bash
git clone https://github.com/Crecker76/voice-english-trainer.git
cd voice-english-trainer
copy .env.prod.example .env
```

Затем:

```bash
ollama pull dolphin-mistral
docker compose up --build
```

Весь функционал тот же, что на ноуте — от железа зависят только скорость и выбор модели.
На GPU идёт только LLM; STT/TTS/VAD всегда на CPU (так и задумано под 4 ГБ VRAM).

---

## Настройки `.env`

| Переменная | Назначение | dev | prod |
|---|---|---|---|
| `OLLAMA_HOST` | адрес нативной Ollama | `http://host.docker.internal:11434` | то же |
| `OLLAMA_MODEL` | модель LLM (на GPU) | `llama3.2:3b` | `dolphin-mistral` |
| `OLLAMA_NUM_CTX` | размер контекста | `4096` | `2048` |
| `OLLAMA_NUM_GPU` | лимит слоёв на GPU (пусто = авто) | — | опц. при VRAM OOM |
| `WHISPER_MODEL` | размер STT-модели | `base` | `small` |
| `STT_DEVICE` | устройство STT | `cpu` | `cpu` |
| `STT_COMPUTE_TYPE` | квантование STT | `int8` | `int8` |
| `TTS_BACKEND` | движок TTS | `piper` | `piper` |
| `TTS_VOICE` | голос для английских ответов | `en_US-lessac-medium` | то же |
| `TTS_VOICE_RU` | голос для русских ответов (режим «объясни») | `ru_RU-irina-medium` | то же |
| `DEFAULT_INPUT_LANG` | язык ввода по умолчанию | `en` | `en` |
| `DEFAULT_MODE` | режим по умолчанию | `conversation` | `conversation` |

Полный список — в [app/config.py](app/config.py). Ничего железозависимого в коде не захардкожено.

---

## Программа обучения и прогресс

- **Программа** — в [syllabus.yaml](syllabus.yaml): уровни (A2/B1/B2) → темы → правило с примерами.
  Редактируется на хосте без пересборки.
- **Прогресс** — в SQLite (`data/progress.db`, volume): сессии, реплики, текущая позиция в
  программе, сводка. В начале сессии краткая сводка прошлого прогресса подмешивается в контекст
  LLM; в конце сессии модель формирует новую сводку (частые ошибки + уровень), и программа
  продвигается к следующей теме.

---

## Troubleshooting

**Микрофон не работает / нет запроса доступа.**
`getUserMedia` требует secure context. На `http://localhost:8000` это выполняется — работает.
Если открываешь по IP (`http://192.168...`), браузер мик не даст. Используй `localhost`.

**`host.docker.internal` не резолвится / LLM недоступен.**
Открой `http://localhost:8000/api/ollama` — покажет `reachable`. Если `false`:
- Ollama запущена на хосте? (`ollama list`)
- Модель скачана? (`ollama pull <OLLAMA_MODEL>`)
- На Docker Desktop `host.docker.internal` работает из коробки; в compose уже прописан
  `extra_hosts: host-gateway` на случай Linux.

**`LLM call failed` в UI / Ollama отдаёт 500 `unable to allocate ... buffer`.**
Модель не влезла в память. На ноуте без мощной GPU Ollama грузит модель в ОЗУ: 7B
(`dolphin-mistral`) хочет ~4 ГБ непрерывно, и под Docker + браузером их может не быть.
Это ровно тот случай, под который сделан dev-пресет. Решения:
- На ноуте бери лёгкую модель: `ollama pull llama3.2:3b` + `copy .env.dev.example .env` (3B, ~2 ГБ).
- Или освободи ОЗУ (закрой вкладки/приложения) и оставь текущую модель.
- Проверь, что модель из `.env` реально скачана: `ollama list` (имя должно совпадать с `OLLAMA_MODEL`).

**Не хватает VRAM (4 ГБ, целевой ПК) / модель уходит в CPU.**
- Понизь `OLLAMA_NUM_CTX` (например, `2048`).
- Ограничь слои на GPU: раскомментируй `OLLAMA_NUM_GPU` в `.env` (напр. `24`).
- Откатись на 3B: `OLLAMA_MODEL=llama3.2:3b` (как в dev).

**Первый запуск долгий.**
Качаются веса STT и голоса TTS (один раз, в `models/`). Дальше берутся из кэша.

**Долгая первая фраза.**
Модели STT/TTS прогреваются в фоне при старте; первый ответ Ollama тоже грузит модель в VRAM.
Дальше быстрее (`OLLAMA_KEEP_ALIVE` держит модель в памяти).

**TTS молчит.**
Проверь логи контейнера: при первом обращении Piper качает голос из rhasspy/piper-voices.
Нужен доступ в интернет на первый раз. Для русского режима используется `TTS_VOICE_RU`.

---

## Структура проекта

```
voice-english-trainer/
├── app/
│   ├── main.py            FastAPI + WebSocket + статика + lifespan
│   ├── config.py          все настройки из .env
│   ├── orchestrator.py    сессия: STT→LLM→TTS, режимы, прогресс
│   ├── prompts.py         system-prompt'ы режимов
│   ├── syllabus.py        загрузка syllabus.yaml
│   ├── progress.py        прогресс в SQLite
│   ├── ws_protocol.py     схемы WebSocket-сообщений
│   └── pipeline/
│       ├── vad.py         Silero VAD (через faster-whisper)
│       ├── stt.py         faster-whisper (CPU)
│       ├── llm.py         Ollama-стриминг + склейка по клаузам
│       └── tts/           base.py, piper_tts.py, kokoro_tts.py (заготовка)
├── frontend/              index.html, style.css, character.js, audio.js, main.js
├── models/  data/         volumes (веса и SQLite; в git не коммитятся)
├── syllabus.yaml          программа обучения
├── Dockerfile  docker-compose.yml  requirements.txt
└── .env.dev.example  .env.prod.example
```

---

## Как это работает (кратко)

1. Браузер пишет микрофон (`MediaRecorder`), по `Space`-отпусканию шлёт аудио + язык ввода по WebSocket.
2. Контейнер: Silero VAD → faster-whisper (STT, язык из UI) → текст.
3. Оркестратор строит контекст (system-prompt режима + сводка прогресса + фокус-тема) и
   стримит ответ из Ollama.
4. Ответ режется на клаузы; каждая озвучивается Piper и сразу летит в браузер как WAV —
   первый звук идёт, пока модель ещё договаривает.
5. Персонаж отражает состояния; прогресс пишется в SQLite.
