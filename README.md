# stormhacks-gym-project

Gym Nerd 3000 — a real-time, AI-powered personal trainer.

## Architecture

- **Frontend:** React (Vite) — webcam capture, WebSocket frame streaming, browser TTS, workout history
- **Backend:** FastAPI + MediaPipe Pose — math detects form breaks; OpenAI phrases live cues + post-set summary
  - `app.py` — thin routes only (no classes)
  - `motion_tracker.py` — MediaPipe + WebSocket loop
  - `poses/` — squat / lat pulldown heuristics (visibility + set-started gating)
  - `ai/live_cue.py` — fresh mid-set coaching lines (debounced, not every frame)
  - `ai/coach.py` — post-set OpenAI summary

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
| WS | `/ws/motion_tracker/{exercise_type}` | Stream Base64 JPEG frames; receive reps + form issues |
| POST | `/api/live-cue` | Issue detail → fresh mid-set coaching line |
| POST | `/api/coach-summary` | `{ chat_history }` → GPT-4o-mini post-set summary |

Supported `exercise_type` values: `squat`, `lat_pulldown`, `bicep_curl`, `shoulder_press`.
