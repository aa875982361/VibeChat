# VibeChat

AI-driven anonymous emotion rooms built with FastAPI, SQLite, and Next.js.

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

For DeepSeek, set at least:

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

Open http://localhost:3000. The backend is exposed at http://localhost:8058, and SQLite data is stored in the `vibechat-data` Docker volume.

## Environment

Set AI credentials in `.env` or your shell to enable real AI emotion analysis. Without a key, the backend uses a local rule-based fallback so the MVP remains runnable.

DeepSeek example:

```bash
AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
NEXT_PUBLIC_API_URL=http://localhost:8058
```

OpenAI example:

```bash
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
NEXT_PUBLIC_API_URL=http://localhost:8058
```

## API

- `POST /api/sessions` creates an anonymous session.
- `POST /api/emotions/analyze` analyzes text and recommends an emotion room.
- `POST /api/rooms/join` joins a safe recommended room.
- `GET /api/rooms` lists rooms and online counts.
- `POST /api/messages/report` records a report.
- `WebSocket /ws/rooms/{room_id}?session_id=...` streams room messages.

The backend defaults to http://localhost:8058 in local development.
