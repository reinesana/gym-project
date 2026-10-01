import { useEffect, useRef, useState } from "react";
import "./App.css";

const EXERCISES = [
  { value: "squat", label: "Squat", tip: "Film from a 45° front-side angle" },
  { value: "lat_pulldown", label: "Lat Pulldown", tip: "Film from the front" },
];

const SPEAK_DEBOUNCE_MS = 4000;
const FRAME_INTERVAL_MS = 150;
const TARGET_REPS = 10;

const POSE_EDGES = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24], [23, 25], [25, 27],
  [24, 26], [26, 28], [15, 17], [15, 19], [16, 18], [16, 20],
];

const ISSUE_EDGES = {
  knee_cave: [[23, 25], [25, 27], [24, 26], [26, 28]],
  shallow_depth: [[23, 25], [24, 26]],
  hips_high: [[11, 23], [12, 24], [23, 24]],
  forward_lean: [[11, 23], [12, 24]],
  asymmetry: [[11, 13], [13, 15], [12, 14], [14, 16]],
  elbow_flare: [[11, 13], [12, 14]],
  shallow_pull: [[11, 13], [13, 15], [12, 14], [14, 16]],
  lean_back: [[11, 23], [12, 24]],
};

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
  });
}

function isActivePhase(phase) {
  return phase && !REST_PHASES.has(phase);
}

function edgeKey(a, b) {
  return a < b ? `${a}-${b}` : `${b}-${a}`;
}

function hotEdgesFromIssues(issues) {
  const hot = new Set();
  for (const issue of issues || []) {
    for (const [a, b] of ISSUE_EDGES[issue.type] || []) {
      hot.add(edgeKey(a, b));
    }
  }
  return hot;
}

function drawPose(ctx, landmarks, width, height, hotEdges, mirrored = true) {
  if (!landmarks?.length) return;

  const point = (lm) => {
    const x = mirrored ? (1 - lm.x) * width : lm.x * width;
    const y = lm.y * height;
    return [x, y];
  };

  const hotJoints = new Set();
  for (const key of hotEdges) {
    const [a, b] = key.split("-").map(Number);
    hotJoints.add(a);
    hotJoints.add(b);
  }

  for (const [a, b] of POSE_EDGES) {
    const la = landmarks[a];
    const lb = landmarks[b];
    if (!la || !lb || (la.visibility ?? 1) < 0.4 || (lb.visibility ?? 1) < 0.4) continue;
    const [x1, y1] = point(la);
    const [x2, y2] = point(lb);
    const hot = hotEdges.has(edgeKey(a, b));
    ctx.lineWidth = hot ? 5 : 3;
    ctx.strokeStyle = hot ? "#ff3b30" : "rgba(255,255,255,0.92)";
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.stroke();
  }

  landmarks.forEach((lm, index) => {
    if ((lm.visibility ?? 1) < 0.4) return;
    const [x, y] = point(lm);
    const hot = hotJoints.has(index);
    ctx.beginPath();
    ctx.arc(x, y, hot ? 6 : 4.5, 0, Math.PI * 2);
    ctx.fillStyle = hot ? "#ff3b30" : "#ffffff";
    ctx.fill();
  });
}

export default function App() {
  const videoRef = useRef(null);
  const captureRef = useRef(null);
  const overlayRef = useRef(null);
  const wsRef = useRef(null);
  const intervalRef = useRef(null);
  const timerRef = useRef(null);
  const lastSpeakAtRef = useRef(0);
  const sessionIssuesRef = useRef([]);
  const latestRepsRef = useRef(0);
  const workoutStartedRef = useRef(false);
  const phaseRef = useRef("—");
  const streamRef = useRef(null);

  const [page, setPage] = useState("start"); // start | app
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
  const [elapsed, setElapsed] = useState(0);
  const [liveCue, setLiveCue] = useState("");
  const [issueCount, setIssueCount] = useState(0);
  const [cameraReady, setCameraReady] = useState(false);

  const totalReps = workoutLog.reduce((sum, w) => sum + (w.reps || 0), 0);
  const totalSets = workoutLog.length;
  const ringPct = Math.min(100, (totalReps / 30) * 100);
  const setProgress = Math.min(100, (reps / TARGET_REPS) * 100);
  const formMeter = Math.max(12, 100 - issueCount * 8);

  useEffect(() => {
    return () => {
      stopStreaming();
      streamRef.current?.getTracks().forEach((t) => t.stop());
      if (timerRef.current) clearInterval(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (page !== "app") return;
    let cancelled = false;

    async function startCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play();
        }
        setCameraReady(true);
      } catch (err) {
        console.error(err);
        setStatus("Camera permission needed");
        setCameraReady(false);
      }
    }

    startCamera();
    return () => {
      cancelled = true;
    };
  }, [page]);

  function stopStreaming() {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
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

  function paintOverlay(landmarks, issues) {
    const video = videoRef.current;
    const overlay = overlayRef.current;
    if (!video || !overlay || !video.videoWidth) return;

    overlay.width = video.clientWidth || video.videoWidth;
    overlay.height = video.clientHeight || video.videoHeight;
    const ctx = overlay.getContext("2d");
    ctx.clearRect(0, 0, overlay.width, overlay.height);
    drawPose(ctx, landmarks, overlay.width, overlay.height, hotEdgesFromIssues(issues), true);
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

    const issues = Array.isArray(data.issues) ? data.issues : [];
    setPoseDetected(Boolean(data.pose_detected));
    paintOverlay(data.landmarks || [], issues);

    if (isActivePhase(nextPhase) && !workoutStartedRef.current) {
      workoutStartedRef.current = true;
      setCoachListening(true);
      setStatus("Coach is listening");
    }

    if (issues.length === 0) {
      if (workoutStartedRef.current) setLiveCue("");
      return;
    }

    sessionIssuesRef.current = [...sessionIssuesRef.current, ...issues];
    setIssueCount(sessionIssuesRef.current.length);
    const cue = issues[0]?.spoken_text || "";
    if (workoutStartedRef.current) setLiveCue(cue);

    if (!workoutStartedRef.current || !isActivePhase(phaseRef.current)) return;

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
    setElapsed(0);
    setPhase("—");
    setCoachListening(false);
    setPoseDetected(false);
    setLiveCue("");
    setIssueCount(0);
    lastSpeakAtRef.current = 0;
    clearOverlay();

    const url = `${getWsBase()}/ws/motion_tracker/${exercise}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsActive(true);
      setStatus("Quiet until you start moving");
      intervalRef.current = setInterval(sendFrame, FRAME_INTERVAL_MS);
      timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
    };
    ws.onmessage = handleWsMessage;
    ws.onerror = () => setStatus("WebSocket error — is the backend running?");
    ws.onclose = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
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
      setLiveCue("");
    }
  }

  if (page === "start") {
    return (
      <div className="webapp">
        <section className="start-page">
          <div className="start-copy">
            <p className="brand">FormForge</p>
            <p className="tagline">Your personal AI trainer</p>
            <h1>Train live. Fix form instantly.</h1>
            <p className="lede">
              Point your webcam at your set. MediaPipe tracks your body. The coach stays quiet until you move, then talks you through corrections.
            </p>
            <div className="start-actions">
              <button type="button" className="btn ghost" onClick={() => { setPage("app"); setTab("summary"); }}>
                View summary
              </button>
              <button type="button" className="btn primary" onClick={() => { setPage("app"); setTab("workout"); }}>
                Get started
              </button>
            </div>
          </div>

          <div className="start-panel">
            <article className="glass-card">
              <p className="eyebrow">Session preview</p>
              <h2>Live form coaching</h2>
              <ul>
                <li>Squat + lat pulldown tracking</li>
                <li>Pose skeleton on camera</li>
                <li>Voice cues only mid-set</li>
                <li>AI summary when you finish</li>
              </ul>
            </article>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="webapp">
      <header className="topbar">
        <button type="button" className="brand-btn" onClick={() => setPage("start")}>
          FormForge
        </button>
        <nav className="top-nav">
          <button type="button" className={tab === "summary" ? "active" : ""} onClick={() => setTab("summary")}>
            Summary
          </button>
          <button type="button" className={tab === "workout" ? "active" : ""} onClick={() => setTab("workout")}>
            Workout
          </button>
        </nav>
        <div className="top-meta">
          <span>{todayLabel()}</span>
          <span className={`pill ${coachListening ? "live" : "quiet"}`}>
            {isActive ? (coachListening ? "Coaching" : "Quiet") : "Idle"}
          </span>
        </div>
      </header>

      <main className={`main ${tab === "workout" ? "main-live" : ""}`}>
        <section className={`panel summary-panel ${tab === "summary" ? "visible" : "hidden"}`}>
          <div className="panel-head">
            <div>
              <p className="eyebrow">Today</p>
              <h1>Summary</h1>
            </div>
            <button type="button" className="btn primary" onClick={() => setTab("workout")}>
              Start workout
            </button>
          </div>

          <div className="summary-grid">
            <article className="tile activity-tile">
              <div>
                <p className="eyebrow">Activity</p>
                <p className="stat-line"><strong>{totalReps}</strong> <span>/ 30 reps</span></p>
                <p className="stat-sub">{totalSets} sets logged · {exerciseLabel(exercise)}</p>
              </div>
              <div
                className="ring"
                style={{ background: `conic-gradient(#2f6bff ${ringPct}%, #1a2338 0)` }}
              >
                <div className="ring-hole">
                  <span>{totalReps}</span>
                  <small>reps</small>
                </div>
              </div>
            </article>

            <article className="tile tip-tile">
              <p className="eyebrow">Camera setup</p>
              <h3>{exerciseLabel(exercise)}</h3>
              <p>{exerciseTip(exercise)}</p>
              <p>Keep head-to-feet in frame. Coach stays quiet until you start the movement.</p>
            </article>
          </div>

          <div className="panel-head tight">
            <h2>Workouts</h2>
          </div>

          {workoutLog.length === 0 ? (
            <article className="tile empty-tile">
              <p>No sets yet. Open Workout, press Start, and finish a set to build history here.</p>
            </article>
          ) : (
            <div className="history-grid">
              {[...workoutLog].reverse().map((entry, index) => (
                <article className="tile history-tile" key={`${entry.exercise}-${index}`}>
                  <div>
                    <strong>{exerciseLabel(entry.exercise)}</strong>
                    <p>{entry.aiFeedback}</p>
                  </div>
                  <div className="history-meta">
                    <span>{entry.reps} reps</span>
                    <span>{entry.at}</span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className={`panel live-panel ${tab === "workout" ? "visible" : "hidden"}`}>
          <div className="live-layout">
            <div className="live-camera">
              <video ref={videoRef} className="camera" playsInline muted autoPlay />
              <canvas ref={overlayRef} className="overlay-canvas" />
              <canvas ref={captureRef} className="hidden-canvas" aria-hidden="true" />

              <div className="live-top">
                <div className="guide-card">
                  <strong>{exerciseLabel(exercise)}</strong>
                  <p>{exerciseTip(exercise)}</p>
                </div>
                <span className={`pill ${coachListening ? "live" : "quiet"}`}>
                  {coachListening ? "Coaching" : "Quiet"}
                </span>
              </div>

              {liveCue ? <div className="cue-banner">{liveCue}</div> : null}

              <div className="live-bottom">
                <div className="rep-timer">
                  <div
                    className="rep-ring"
                    style={{ background: `conic-gradient(#fff ${setProgress}%, rgba(255,255,255,0.2) 0)` }}
                  >
                    <div className="rep-hole">
                      <span>{elapsed}s</span>
                    </div>
                  </div>
                  <p className="exercise-name">{exerciseLabel(exercise)}</p>
                  <p className="rep-sub">
                    {reps} reps · {poseDetected ? phase : cameraReady ? "finding you" : "camera off"}
                  </p>
                </div>
                <div className="form-meter" aria-label="Form meter">
                  <div className="form-fill" style={{ height: `${Math.min(100, formMeter)}%` }} />
                </div>
              </div>

              <div className="session-progress">
                <div style={{ width: `${setProgress}%` }} />
              </div>
            </div>

            <aside className="live-sidebar">
              <p className="eyebrow">Controls</p>
              <h2>Live set</h2>
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
              <p className="sidebar-tip">{exerciseTip(exercise)}</p>
              <div className="sidebar-actions">
                <button type="button" className="btn primary" onClick={startSet} disabled={isActive || ending}>
                  Start set
                </button>
                <button type="button" className="btn ghost" onClick={endSet} disabled={!isActive || ending}>
                  {ending ? "Summarizing…" : "End set"}
                </button>
              </div>
              <p className="sidebar-status">{status}</p>
            </aside>
          </div>
        </section>
      </main>
    </div>
  );
}
