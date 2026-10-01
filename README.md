# stormhacks-gym-project

FormForge — a real-time, AI-powered personal trainer.

## Architecture

- **Frontend:** React (Vite) — webcam capture, WebSocket frame streaming, browser TTS, workout history
- **Backend:** FastAPI + MediaPipe Pose — functional math heuristics for live form cues; OpenAI only after the set ends

## Quick start

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — Vite proxies `/api` and `/ws` to the FastAPI server.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| WS | `/ws/formcheck/{exercise_type}` | Stream Base64 JPEG frames; receive reps + form issues |
| POST | `/api/coach-summary` | `{ chat_history }` → GPT-4o-mini post-set summary |

Supported `exercise_type` values: `squat`, `lat_pulldown`.
