import { useEffect, useRef, useState } from "react";
import { streamSocketUrl, type Alert, type Detection } from "../api/client";
import { AlertFeed } from "../components/AlertFeed";

// ~5 fps: fast enough to feel live, slow enough to keep CPU-only inference
// viable on a laptop demo. Documented, not hidden.
const CAPTURE_INTERVAL_MS = 200;

type ConnectionState = "idle" | "connecting" | "connected" | "error" | "closed";

interface StreamMessage {
  image_b64?: string;
  detections?: Detection[];
  alerts?: Alert[];
  error?: string;
}

// Web Audio emergency siren generator
let webAudioCtx: AudioContext | null = null;
let lastWebAlarmTime = 0;

export function playLoudWebAlarm() {
  const nowMs = Date.now();
  if (nowMs - lastWebAlarmTime < 1500) return;
  lastWebAlarmTime = nowMs;

  try {
    const AudioContextClass =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) return;
    if (!webAudioCtx) {
      webAudioCtx = new AudioContextClass();
    }
    if (webAudioCtx.state === "suspended") {
      webAudioCtx.resume();
    }

    const t = webAudioCtx.currentTime;
    const osc = webAudioCtx.createOscillator();
    const gain = webAudioCtx.createGain();

    osc.type = "sawtooth";
    // Rapid European police siren sweep (1200Hz to 2400Hz)
    osc.frequency.setValueAtTime(1400, t);
    osc.frequency.linearRampToValueAtTime(2400, t + 0.12);
    osc.frequency.linearRampToValueAtTime(1400, t + 0.24);
    osc.frequency.linearRampToValueAtTime(2400, t + 0.36);
    osc.frequency.linearRampToValueAtTime(1400, t + 0.48);
    osc.frequency.linearRampToValueAtTime(2400, t + 0.60);
    osc.frequency.linearRampToValueAtTime(1400, t + 0.72);

    // Full volume output through browser soundcard
    gain.gain.setValueAtTime(1.0, t);
    gain.gain.linearRampToValueAtTime(1.0, t + 0.70);
    gain.gain.linearRampToValueAtTime(0.01, t + 0.78);

    osc.connect(gain);
    gain.connect(webAudioCtx.destination);

    osc.start(t);
    osc.stop(t + 0.78);
  } catch (err) {
    console.warn("Web audio playback error:", err);
  }
}

export function LivePage() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const captureCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intervalRef = useRef<number | null>(null);
  const sendingRef = useRef(false);

  const [connection, setConnection] = useState<ConnectionState>("idle");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [detectionCount, setDetectionCount] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => stop, []);

  function stopCapture() {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }

  function stop() {
    stopCapture();
    socketRef.current?.close();
    socketRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setConnection("idle");
  }

  function drawFrame(imageB64: string) {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const img = new Image();
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);
    };
    img.src = `data:image/jpeg;base64,${imageB64}`;
  }

  function captureAndSend() {
    const video = videoRef.current;
    const socket = socketRef.current;
    if (!video || !socket || socket.readyState !== WebSocket.OPEN) return;
    if (sendingRef.current) return; // backpressure: skip a tick rather than pile up frames

    if (!captureCanvasRef.current) {
      captureCanvasRef.current = document.createElement("canvas");
    }
    const canvas = captureCanvasRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx || canvas.width === 0 || canvas.height === 0) return;

    ctx.drawImage(video, 0, 0);
    sendingRef.current = true;
    canvas.toBlob(
      (blob) => {
        sendingRef.current = false;
        if (blob && socket.readyState === WebSocket.OPEN) {
          blob.arrayBuffer().then((buf) => socket.send(buf));
        }
      },
      "image/jpeg",
      0.7,
    );
  }

  async function start() {
    setErrorMessage(null);
    setAlerts([]);
    setConnection("connecting");

    try {
      if (!webAudioCtx) {
        const AudioContextClass =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        if (AudioContextClass) webAudioCtx = new AudioContextClass();
      }
      if (webAudioCtx && webAudioCtx.state === "suspended") {
        webAudioCtx.resume();
      }
    } catch {
      // Audio unlock non-fatal
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
    } catch (err) {
      setConnection("error");
      setErrorMessage(
        "Could not access the camera: " + (err instanceof Error ? err.message : String(err)),
      );
      return;
    }

    const socket = new WebSocket(streamSocketUrl());
    socketRef.current = socket;

    socket.onopen = () => {
      setConnection("connected");
      intervalRef.current = window.setInterval(captureAndSend, CAPTURE_INTERVAL_MS);
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data as string) as StreamMessage;

      if (data.error) {
        setErrorMessage(data.error);
        return;
      }
      if (data.image_b64) {
        drawFrame(data.image_b64);
      }
      setDetectionCount(data.detections?.length ?? 0);
      if (data.alerts && data.alerts.length > 0) {
        setAlerts((prev) => [...prev, ...data.alerts!].slice(-300));
        const isWeaponThreat = data.alerts.some(
          (a) => a.type === "weapon_detected" && a.event === "started"
        );
        if (isWeaponThreat) {
          playLoudWebAlarm();
        }
      }
    };

    socket.onerror = () => {
      setConnection("error");
      setErrorMessage("Live connection failed. Is the backend running?");
    };

    socket.onclose = () => {
      setConnection((current) => (current === "error" ? current : "closed"));
      stopCapture();
    };
  }

  const canStart = connection === "idle" || connection === "closed" || connection === "error";

  return (
    <section className="page">
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <h1>Live Camera Detection</h1>
        <span style={{ backgroundColor: "#ef4444", color: "#ffffff", padding: "4px 10px", borderRadius: "6px", fontSize: "0.85rem", fontWeight: "bold" }}>
          WEAPON DETECTION DEMO
        </span>
      </div>
      <p className="muted">
        Real-time AI weapon surveillance stream. The dedicated computer vision model scans webcam
        frames for weapons (pistols, knives, firearms), highlighting armed threats with instant bounding boxes,
        critical telemetry, and audio alarms.
      </p>

      <div className="live-controls">
        <span className={`status-pill status-${connection}`}>{connection}</span>
        {canStart ? (
          <button onClick={start}>Start Camera</button>
        ) : (
          <button onClick={stop}>Stop Camera</button>
        )}
        <button
          type="button"
          onClick={() => playLoudWebAlarm()}
          style={{
            backgroundColor: "#dc2626",
            color: "#ffffff",
            fontWeight: 600,
            cursor: "pointer",
          }}
          title="Play test alarm sound through speakers"
        >
          🔊 Test Siren
        </button>
        <span className="muted">{detectionCount} threat(s) tracked</span>
        <span style={{ marginLeft: "auto", fontSize: "0.85rem", color: "#ef4444", fontWeight: 600 }}>
          Target Classes: Pistols, Knives, Firearms
        </span>
      </div>

      {errorMessage && <p className="error-text">{errorMessage}</p>}

      <div className="live-layout">
        {/* Hidden source element feeding the capture canvas; the visible feed is the annotated canvas below. */}
        <video ref={videoRef} muted playsInline className="hidden-video" />
        <canvas ref={canvasRef} className="live-canvas" />
        <div className="live-alerts">
          <h2>Alerts</h2>
          <AlertFeed alerts={alerts} />
        </div>
      </div>
    </section>
  );
}
