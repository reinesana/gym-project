import { useEffect, useRef, useState } from "react";
import "./App.css";

const EXERCISES = [
  { value: "squat", label: "Squat", tip: "Film from a 45° front-side angle" },
  { value: "lat_pulldown", label: "Lat Pulldown", tip: "Film from the front" },
];

const SPEAK_DEBOUNCE_MS = 4000;
const FRAME_INTERVAL_MS = 150;

// MediaPipe Pose connections for skeleton drawing
const POSE_EDGES = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24], [23, 25], [25, 27],
  [24, 26], [26, 28], [15, 17], [15, 19], [16, 18], [16, 20],
];

const REST_PHASES = new Set(["standing", "arms_up", "—", "", null, undefined]);

function getWsBase() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  if (import.meta.env.DEV) {
    return `${proto}://${window.location.host}`;
  }
  return `${proto}://${window.location.hostname}:8000`;
}

function speak(text) {
  if (!text || !window.speechSynthesis) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.05;
  utterance.pitch = 1;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

function exerciseLabel(value) {
  return EXERCISES.find((e) => e.value === value)?.label ?? value;
}

function exerciseTip(value) {
  return EXERCISES.find((e) => e.value === value)?.tip ?? "";
}

function todayLabel() {
  return new Date().toLocaleDateString(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  }).toUpperCase();
}

function isActivePhase(phase) {
  return phase && !REST_PHASES.has(phase);
}

function drawPose(ctx, landmarks, width, height, mirrored = true) {
  if (!landmarks?.length) return;

  const point = (lm) => {
    const x = mirrored ? (1 - lm.x) * width : lm.x * width;
    const y = lm.y * height;
    return [x, y, lm.visibility ?? 1];
  };

  ctx.lineWidth = 3;
  ctx.strokeStyle = "rgba(178, 255, 89, 0.85)";
  ctx.fillStyle = "#ff4d6d";

  for (const [a, b] of POSE_EDGES) {
    const la = landmarks[a];
    const lb = landmarks[b];
    if (!la || !lb || (la.visibility ?? 1) < 0.4 || (lb.visibility ?? 1) < 0.4) continue;
    const [x1, y1] = point(la);
    const [x2, y2] = point(lb);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  }

  for (const lm of landmarks) {
    if ((lm.visibility ?? 1) < 0.4) continue;
    const [x, y] = point(lm);
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
  }
}

export default function App() {
  const videoRef = useRef(null);
  const captureRef = useRef(null);
  const overlayRef = useRef(null);
  const wsRef = useRef(null);
  const intervalRef = useRef(null);
  const lastSpeakAtRef = useRef(0);
  const sessionIssuesRef = useRef([]);
  const latestRepsRef = useRef(0);
  const workoutStartedRef = useRef(false);
  const phaseRef = useRef("—");

  const [tab, setTab] = useState("summary");
  const [exercise, setExercise] = useState("squat");
  const [isActive, setIsActive] = useState(false);
  const [reps, setReps] = useState(0);
  const [phase, setPhase] = useState("—");
  const [status, setStatus] = useState("Ready when you are");
  const [coachListening, setCoachListening] = useState(false);
  const [chatHistory, setChatHistory] = useState([]);
  const [workoutLog, setWorkoutLog] = useState([]);
  const [ending, setEnding] = useState(false);
  const [poseDetected, setPoseDetected] = useState(false);

  const totalReps = workoutLog.reduce((sum, w) => sum + (w.reps || 0), 0);
  const totalSets = workoutLog.length;
  const ringPct = Math.min(100, (totalReps / 30) * 100);

  useEffect(() => {
    let stream;
    async function startCamera() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
      } catch (err) {
        console.error(err);
        setStatus("Camera permission needed");
      }
    }
    startCamera();
    return () => {
      stream?.getTracks().forEach((t) => t.stop());
      stopStreaming();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function stopStreaming() {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
    }
  }

  function clearOverlay() {
    const overlay = overlayRef.current;
    if (!overlay) return;
    const ctx = overlay.getContext("2d");
    ctx.clearRect(0, 0, overlay.width, overlay.height);
  }

  function paintOverlay(landmarks) {
    const video = videoRef.current;
    const overlay = overlayRef.current;
    if (!video || !overlay || !video.videoWidth) return;

    overlay.width = video.clientWidth || video.videoWidth;
    overlay.height = video.clientHeight || video.videoHeight;
    const ctx = overlay.getContext("2d");
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    drawPose(ctx, landmarks, overlay.width, overlay.height, true);
  }

  function sendFrame() {
    const video = videoRef.current;
    const canvas = captureRef.current;
    const ws = wsRef.current;
    if (!video || !canvas || !ws || ws.readyState !== WebSocket.OPEN) return;
    if (!video.videoWidth) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    canvas.toBlob(
      async (blob) => {
        if (!blob || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        const buffer = await blob.arrayBuffer();
        const bytes = new Uint8Array(buffer);
        let binary = "";
        for (let i = 0; i < bytes.length; i += 1) {
          binary += String.fromCharCode(bytes[i]);
        }
        const b64 = btoa(binary);
        wsRef.current.send(JSON.stringify({ frame: `data:image/jpeg;base64,${b64}` }));
      },
      "image/jpeg",
      0.7
    );
  }

  function handleWsMessage(event) {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }

    if (typeof data.reps === "number") {
      setReps(data.reps);
      latestRepsRef.current = data.reps;
    }

    const nextPhase = data.phase || "—";
    if (data.phase) {
      setPhase(nextPhase);
      phaseRef.current = nextPhase;
    }

    setPoseDetected(Boolean(data.pose_detected));
    paintOverlay(data.landmarks || []);

    // Coach stays quiet until the athlete actually starts moving
    if (isActivePhase(nextPhase) && !workoutStartedRef.current) {
      workoutStartedRef.current = true;
      setCoachListening(true);
      setStatus("Coach is listening — keep going");
    }

    const issues = Array.isArray(data.issues) ? data.issues : [];
    if (issues.length === 0) return;

    sessionIssuesRef.current = [...sessionIssuesRef.current, ...issues];

    if (!workoutStartedRef.current || !isActivePhase(phaseRef.current)) {
      return;
    }

    const now = Date.now();
    if (now - lastSpeakAtRef.current < SPEAK_DEBOUNCE_MS) return;

    const spoken = issues.map((i) => i.spoken_text).filter(Boolean).join(". ");
    if (!spoken) return;

    lastSpeakAtRef.current = now;
    speak(spoken);
  }

  function startSet() {
    if (isActive) return;
    setTab("workout");
    stopStreaming();
    sessionIssuesRef.current = [];
    latestRepsRef.current = 0;
    workoutStartedRef.current = false;
    phaseRef.current = "—";
    setReps(0);
    setPhase("—");
    setCoachListening(false);
    setPoseDetected(false);
    lastSpeakAtRef.current = 0;
    clearOverlay();

    const url = `${getWsBase()}/ws/motion_tracker/${exercise}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsActive(true);
      setStatus("Tracking pose — AI is quiet until you start the set");
      intervalRef.current = setInterval(sendFrame, FRAME_INTERVAL_MS);
    };
    ws.onmessage = handleWsMessage;
    ws.onerror = () => setStatus("WebSocket error — is the backend running?");
    ws.onclose = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      setIsActive(false);
      setCoachListening(false);
    };
  }

  async function endSet() {
    if (ending) return;
    setEnding(true);
    stopStreaming();
    setIsActive(false);
    setCoachListening(false);
    setStatus("Generating coach summary…");
    clearOverlay();

    const finalReps = latestRepsRef.current;
    const issueLog = sessionIssuesRef.current;
    const issueText =
      issueLog.length === 0
        ? "No form issues detected."
        : issueLog.map((i) => i.spoken_text || i.type).join("; ");

    const userMessage = {
      role: "user",
      content:
        `I just finished a set of ${exerciseLabel(exercise)}. ` +
        `Reps completed: ${finalReps}. Form issues during the set: ${issueText}. ` +
        `Give me a short spoken post-set summary.`,
    };

    const nextHistory = [...chatHistory, userMessage];

    try {
      const res = await fetch("/api/coach-summary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_history: nextHistory }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = await res.json();
      const summary = body.summary || "Solid work finishing that set.";

      speak(summary);
      setChatHistory([
        ...nextHistory,
        { role: "assistant", content: summary },
      ]);
      setWorkoutLog((prev) => [
        ...prev,
        {
          exercise,
          reps: finalReps,
          aiFeedback: summary,
          at: new Date().toLocaleDateString(),
        },
      ]);
      setStatus("Set logged");
      setTab("summary");
    } catch (err) {
      console.error(err);
      setStatus("Could not reach coach summary API");
      setChatHistory(nextHistory);
    } finally {
      setEnding(false);
      sessionIssuesRef.current = [];
      workoutStartedRef.current = false;
    }
  }

  return (
    <div className="app-shell">
      <div className="phone">
        <section className={`screen summary-screen ${tab === "summary" ? "visible" : "hidden"}`}>
          <header className="summary-header">
            <div>
              <p className="date">{todayLabel()}</p>
              <h1>Summary</h1>
            </div>
            <div className="avatar" aria-hidden="true">FF</div>
          </header>

          <div className="section-head">
            <h2>Activity</h2>
          </div>
          <article className="card activity-card">
            <div className="activity-stats">
              <p><span className="label move">Reps</span> <strong className="move">{totalReps}</strong><span className="muted">/30</span></p>
              <p><span className="label">Sets</span> <strong>{totalSets}</strong></p>
              <p><span className="label">Exercise</span> <strong>{exerciseLabel(exercise)}</strong></p>
            </div>
            <div
              className="ring"
              style={{ background: `conic-gradient(#ff4d6d ${ringPct}%, #3a151c 0)` }}
              aria-label={`${totalReps} of 30 reps`}
            >
              <div className="ring-hole">
                <span>{totalReps}</span>
                <small>reps</small>
              </div>
            </div>
          </article>

          <div className="section-head">
            <h2>Workouts</h2>
            <button type="button" className="linkish" onClick={() => setTab("workout")}>
              Start
            </button>
          </div>

          {workoutLog.length === 0 ? (
            <article className="card empty-card">
              <p>No sets yet. Start a workout and your history will show up here.</p>
            </article>
          ) : (
            <div className="workout-list">
              {[...workoutLog].reverse().map((entry, index) => (
                <article className="card workout-row" key={`${entry.exercise}-${index}`}>
                  <div className="workout-icon" aria-hidden="true">F</div>
                  <div className="workout-copy">
                    <strong>{exerciseLabel(entry.exercise)}</strong>
                    <p>{entry.aiFeedback}</p>
                  </div>
                  <div className="workout-meta">
                    <span className="duration">{entry.reps} reps</span>
                    <span className="when">{entry.at}</span>
                  </div>
                </article>
              ))}
            </div>
          )}

          <div className="section-head">
            <h2>Camera tip</h2>
          </div>
          <article className="card tip-card">
            <p><strong>Squat:</strong> 45° front-side so we can see knee cave and depth.</p>
            <p><strong>Lat pulldown:</strong> straight-on front view for both arms.</p>
            <p>Keep your full body in frame from head to feet.</p>
          </article>
        </section>

        <section className={`screen workout-screen ${tab === "workout" ? "visible" : "hidden"}`}>
          <header className="workout-header">
            <button type="button" className="back" onClick={() => !isActive && setTab("summary")}>
              Summary
            </button>
            <h1>Live Set</h1>
            <span className={`pill ${coachListening ? "live" : "quiet"}`}>
              {coachListening ? "Coaching" : "Quiet"}
            </span>
          </header>

          <div className="camera-wrap">
            <video ref={videoRef} className="camera" playsInline muted autoPlay />
            <canvas ref={overlayRef} className="overlay-canvas" />
            <canvas ref={captureRef} className="hidden-canvas" aria-hidden="true" />
            <div className="hud">
              <span>{status}</span>
              <span>Reps {reps}</span>
              <span>{poseDetected ? phase : "no pose"}</span>
            </div>
          </div>

          <div className="controls card">
            <label className="field">
              <span>Exercise</span>
              <select
                value={exercise}
                disabled={isActive}
                onChange={(e) => setExercise(e.target.value)}
              >
                {EXERCISES.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
            <p className="tip-line">{exerciseTip(exercise)}</p>
            <div className="actions">
              <button type="button" className="btn primary" onClick={startSet} disabled={isActive || ending}>
                Start Set
              </button>
              <button type="button" className="btn ghost" onClick={endSet} disabled={!isActive || ending}>
                {ending ? "Summarizing…" : "End Set"}
              </button>
            </div>
          </div>
        </section>

        <nav className="tabbar" aria-label="Primary">
          <button
            type="button"
            className={tab === "summary" ? "active" : ""}
            onClick={() => setTab("summary")}
          >
            <span className="tab-icon ringlet" />
            Summary
          </button>
          <button
            type="button"
            className={tab === "workout" ? "active" : ""}
            onClick={() => setTab("workout")}
          >
            <span className="tab-icon person" />
            Workout
          </button>
        </nav>
      </div>
    </div>
  );
}
