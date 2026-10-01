# Gym Nerd 3000

A web app that watches your workout with your webcam, tracks your form with MediaPipe, and coaches you live with AI voice cues.

**Stack**
- Frontend: React (Vite)
- Backend: FastAPI + MediaPipe
- AI: OpenAI (`gpt-4o-mini`) for live cues + post-set summary

---

## What you need first

Install these if you don’t have them:

1. **Python 3.10+**  
   Check: `python3 --version`
2. **Node.js 18+ and npm**  
   Check: `node --version` and `npm --version`
3. **An OpenAI API key**  
   Get one from: https://platform.openai.com/api-keys  
   It usually looks like `sk-...` or `sk-proj-...`

You’ll also need a webcam and two terminal windows.

---

## 1. Download the project

```bash
git clone https://github.com/reinesana/stormhacks-gym-project.git
cd stormhacks-gym-project
git checkout main
git pull origin main
```

If you already cloned it:

```bash
cd stormhacks-gym-project
git checkout main
git pull origin main
```

---

## 2. Set your OpenAI API key (important)

The AI coach needs a key. We store it in a local file called `.env` so it is **not** uploaded to GitHub.

### Create the file

```bash
cd backend
cp .env.example .env
```

### Edit `backend/.env`

Open `backend/.env` in any editor and put your real key there:

```env
OPENAI_API_KEY=sk-your-real-key-here
```

Examples:

```env
OPENAI_API_KEY=sk-proj-xxxxxxxx
```

Rules:
- No quotes needed
- No spaces around `=`
- Do **not** commit `.env` (it is already in `.gitignore`)
- Keep `.env.example` as the template with a fake key

---

## 3. Start the backend

In terminal 1:

```bash
cd stormhacks-gym-project/backend

# create a virtual environment (first time only)
python3 -m venv .venv

# activate it
# Mac / Linux:
source .venv/bin/activate
# Windows (PowerShell):
# .venv\Scripts\Activate.ps1

# install packages (first time, or after requirements change)
pip install -r requirements.txt

# run the server
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

You should see something like:

```text
Uvicorn running on http://0.0.0.0:8000
```

Leave this terminal open.

### If you get `Address already in use`

Something else is using port 8000. Free it:

```bash
# Mac / Linux
kill -9 $(lsof -t -i :8000)
```

Then run `uvicorn` again.

---

## 4. Start the frontend

In terminal 2 (new window):

```bash
cd stormhacks-gym-project/frontend

# install packages (first time only)
npm install

# run the web app
npm run dev
```

You should see something like:

```text
Local: http://localhost:5173/
```

Open that link in your browser:

**http://localhost:5173**

Allow camera permission when the browser asks.

---

## 5. How to use the app

1. On the starter page, click **Get started**
2. Go to **Workout**
3. Pick an exercise:
   - Squat
   - Lat Pulldown
   - Bicep Curl
   - Shoulder Press
4. Click **Start set**
5. Do your reps — Gym Nerd stays quiet until you actually start moving
6. Click **End set** for an AI voice summary
7. Check **Summary** for workout history

### Camera tips

| Exercise | Best camera angle |
|----------|-------------------|
| Squat | 45° front-side |
| Lat Pulldown | Straight front |
| Bicep Curl | Front or slight side |
| Shoulder Press | Straight front, full arms in frame |

Keep the working joints visible. Good lighting helps MediaPipe a lot.

---

## Quick “is it working?” checks

Backend health:

```bash
curl http://127.0.0.1:8000/health
```

Expected:

```json
{"status":"ok","app":"Gym Nerd 3000"}
```

If End Set / live cues fail with a key error:
1. Make sure `backend/.env` exists
2. Make sure the key line is exactly `OPENAI_API_KEY=...`
3. Restart the backend after editing `.env`

---

## Project structure (simple view)

```text
stormhacks-gym-project/
├── backend/
│   ├── .env                 # your secret API key (you create this)
│   ├── .env.example         # template
│   ├── app.py               # API routes
│   ├── motion_tracker.py    # webcam / MediaPipe WebSocket
│   ├── poses/               # exercise form math
│   └── ai/                  # OpenAI live cue + summary
└── frontend/
    └── src/App.jsx          # web UI
```

---

## Common beginner problems

**Page loads but camera is black**  
- Allow camera permissions in the browser  
- Make sure no other app is using the webcam  

**AI never talks**  
- Backend must be running  
- `.env` must have a valid `OPENAI_API_KEY`  
- Start a set and actually begin the movement (it stays quiet on purpose until then)

**`git pull main` fails**  
Use:

```bash
git pull origin main
```

**You’re on an old branch**  
Use:

```bash
git checkout main
git pull origin main
```

---

## API overview (optional)

| Method | Path | Purpose |
|--------|------|---------|
| WS | `/ws/motion_tracker/{exercise_type}` | Stream frames, get reps + form issues |
| POST | `/api/live-cue` | Fresh mid-set coaching line |
| POST | `/api/coach-summary` | Post-set AI summary |

Supported exercises: `squat`, `lat_pulldown`, `bicep_curl`, `shoulder_press`.
