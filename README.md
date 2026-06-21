# VibeChat

AI-driven anonymous emotion rooms built with FastAPI, SQLite, and Next.js.

Users describe their current mood, the backend asks an LLM to analyze the emotion, and VibeChat matches them into anonymous rooms with similar emotional state.

## Quick Start

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env
uvicorn app.main:app --reload --port 8058
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

## Docker Compose

Create `.env` first:

```bash
cp .env.example .env
```

Set one LLM provider before starting. OpenAI and Anthropic are both supported; DeepSeek is available as an OpenAI-compatible option.

OpenAI:

```bash
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
OPENAI_MODERATION_MODEL=omni-moderation-latest
NEXT_PUBLIC_API_URL=http://localhost:8058
```

Anthropic:

```bash
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
NEXT_PUBLIC_API_URL=http://localhost:8058
```

DeepSeek:

```bash
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
NEXT_PUBLIC_API_URL=http://localhost:8058
```

Then start both services:

```bash
docker compose up --build
```

On Tencent Cloud, keep BuildKit enabled so Docker can reuse dependency caches:

```bash
DOCKER_BUILDKIT=1 COMPOSE_DOCKER_CLI_BUILD=1 docker compose build
docker compose up -d
```

The Docker build defaults to Tencent Cloud's PyPI mirror and npmmirror for npm.
Override them when needed:

```bash
PIP_INDEX_URL=https://pypi.org/simple NPM_CONFIG_REGISTRY=https://registry.npmjs.org docker compose build
```

Open http://localhost:3000. The backend is exposed at http://localhost:8058, and SQLite data is stored in the `vibechat-data` Docker volume.

## LLM Provider Configuration

Set AI credentials in `.env` or your shell to enable real AI emotion analysis. Without a key, the backend uses a local rule-based fallback so the MVP remains runnable.

OpenAI standard API:

```bash
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
OPENAI_BASE_URL=
OPENAI_MODERATION_MODEL=omni-moderation-latest
NEXT_PUBLIC_API_URL=http://localhost:8058
```

Anthropic standard API:

```bash
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
ANTHROPIC_BASE_URL=
NEXT_PUBLIC_API_URL=http://localhost:8058
```

DeepSeek example:

```bash
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
NEXT_PUBLIC_API_URL=http://localhost:8058
```

Provider notes:

- `AI_PROVIDER=openai` uses the OpenAI Responses API plus OpenAI moderation.
- `AI_PROVIDER=anthropic` uses the Anthropic Messages API and local safety keyword fallback.
- `AI_PROVIDER=deepseek` uses the OpenAI-compatible Chat Completions API.
- `OPENAI_BASE_URL`, `ANTHROPIC_BASE_URL`, and `DEEPSEEK_BASE_URL` are optional gateway/proxy overrides.

Start locally after configuring `.env`:

```bash
npm run dev
```

## API

- `POST /api/sessions` creates an anonymous session.
- `POST /api/emotions/analyze` analyzes text and recommends an emotion room.
- `POST /api/rooms/join` joins a safe recommended room.
- `GET /api/rooms` lists rooms and online counts.
- `POST /api/messages/report` records a report.
- `WebSocket /ws/rooms/{room_id}?session_id=...` streams room messages.

The backend defaults to http://localhost:8058 in local development.
