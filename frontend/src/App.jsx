import { useEffect, useRef, useState } from "react";
import "./App.css";

const EXERCISES = [
  { value: "squat", label: "Squat" },
  { value: "lat_pulldown", label: "Lat Pulldown" },
];

const SPEAK_DEBOUNCE_MS = 4000;
const FRAME_INTERVAL_MS = 150;

function getWsBase() {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  // Prefer same-origin proxy in Vite; fall back to local FastAPI.
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

export default function App() {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const intervalRef = useRef(null);
  const lastSpeakAtRef = useRef(0);
  const sessionIssuesRef = useRef([]);
  const latestRepsRef = useRef(0);

  const [exercise, setExercise] = useState("squat");
  const [isActive, setIsActive] = useState(false);
  const [reps, setReps] = useState(0);
  const [phase, setPhase] = useState("—");
  const [status, setStatus] = useState("Camera ready");
  const [chatHistory, setChatHistory] = useState([]);
  const [workoutLog, setWorkoutLog] = useState([]);
  const [ending, setEnding] = useState(false);

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
        setStatus("Camera ready");
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

  function sendFrame() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
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
    if (data.phase) setPhase(data.phase);

    const issues = Array.isArray(data.issues) ? data.issues : [];
    if (issues.length === 0) return;

    sessionIssuesRef.current = [...sessionIssuesRef.current, ...issues];

    const now = Date.now();
    if (now - lastSpeakAtRef.current < SPEAK_DEBOUNCE_MS) return;

    const spoken = issues.map((i) => i.spoken_text).filter(Boolean).join(". ");
    if (!spoken) return;

    lastSpeakAtRef.current = now;
    speak(spoken);
  }

  function startSet() {
    if (isActive) return;
    stopStreaming();
    sessionIssuesRef.current = [];
    latestRepsRef.current = 0;
    setReps(0);
    setPhase("—");
    lastSpeakAtRef.current = 0;

    const url = `${getWsBase()}/ws/formcheck/${exercise}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsActive(true);
      setStatus(`Live coaching · ${exerciseLabel(exercise)}`);
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
    };
  }

  async function endSet() {
    if (ending) return;
    setEnding(true);
    stopStreaming();
    setIsActive(false);
    setStatus("Generating coach summary…");

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
        },
      ]);
      setStatus("Set logged");
    } catch (err) {
      console.error(err);
      setStatus("Could not reach coach summary API");
      setChatHistory(nextHistory);
    } finally {
      setEnding(false);
      sessionIssuesRef.current = [];
    }
  }

  return (
    <div className="app">
      <header className="hero">
        <p className="brand">FormForge</p>
        <h1>Live AI form coach</h1>
        <p className="lede">
          Record your set. Hear corrections the moment form breaks. Get a voice summary when you finish.
        </p>
      </header>

      <main className="stage">
        <div className="camera-wrap">
          <video ref={videoRef} className="camera" playsInline muted autoPlay />
          <canvas ref={canvasRef} className="hidden-canvas" aria-hidden="true" />
          <div className="hud">
            <span>{status}</span>
            <span>Reps {reps}</span>
            <span className="phase">{phase}</span>
          </div>
        </div>

        <div className="controls">
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

          <div className="actions">
            <button type="button" className="btn primary" onClick={startSet} disabled={isActive || ending}>
              Start Set
            </button>
            <button type="button" className="btn ghost" onClick={endSet} disabled={!isActive || ending}>
              {ending ? "Summarizing…" : "End Set"}
            </button>
          </div>
        </div>

        <section className="log" aria-label="Workout history">
          <h2>Workout history</h2>
          {workoutLog.length === 0 ? (
            <p className="empty">Completed sets will show up here with reps and AI feedback.</p>
          ) : (
            <ol className="log-list">
              {workoutLog.map((entry, index) => (
                <li key={`${entry.exercise}-${index}`}>
                  <div className="log-meta">
                    <strong>Set {index + 1}</strong>
                    <span>{exerciseLabel(entry.exercise)}</span>
                    <span>{entry.reps} reps</span>
                  </div>
                  <p>{entry.aiFeedback}</p>
                </li>
              ))}
            </ol>
          )}
        </section>
      </main>
    </div>
  );
}
