import os
import signal
import sys
import tempfile
import threading
import time
import uuid

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import numpy as np
import soundfile as sf
from kokoro import KPipeline

app = Flask(__name__)
CORS(app)

LANG_CODE = "a"
VOICE = "af_heart"
SPEED = 1.0
SAMPLE_RATE = 24000
IDLE_TIMEOUT_SEC = int(os.environ.get("KOKORO_IDLE_TIMEOUT", "600"))  # 10 minutes default

# Track last activity timestamp
last_activity_time = time.time()
activity_lock = threading.Lock()


def touch_activity():
    global last_activity_time
    with activity_lock:
        last_activity_time = time.time()


def idle_watchdog():
    """Background watchdog thread that terminates the process after 10 minutes of inactivity."""
    if IDLE_TIMEOUT_SEC <= 0:
        return
    print(
        f"[Kokoro Bridge] Inactivity watchdog running (auto-shutdown after {IDLE_TIMEOUT_SEC}s / {IDLE_TIMEOUT_SEC // 60}m)"
    )
    while True:
        time.sleep(10)
        with activity_lock:
            idle_duration = time.time() - last_activity_time
        if idle_duration >= IDLE_TIMEOUT_SEC:
            print(
                f"[Kokoro Bridge] Inactivity limit reached ({idle_duration:.1f}s >= {IDLE_TIMEOUT_SEC}s). Shutting down."
            )
            os._exit(0)


DEVICE = os.environ.get("KOKORO_DEVICE", "cpu")

print(f"[Kokoro Bridge] Initializing Kokoro Pipeline on {DEVICE}...")
pipeline = KPipeline(lang_code=LANG_CODE, device=DEVICE)


@app.route("/status", methods=["GET"])
@app.route("/health", methods=["GET"])
def status():
    with activity_lock:
        idle = time.time() - last_activity_time
    return jsonify({
        "status": "online",
        "idle_seconds": int(idle),
        "timeout_seconds": IDLE_TIMEOUT_SEC,
        "remaining_seconds": (
            max(0, int(IDLE_TIMEOUT_SEC - idle)) if IDLE_TIMEOUT_SEC > 0 else None
        ),
    })


@app.route("/shutdown", methods=["POST"])
def shutdown():
    def delayed_exit():
        time.sleep(0.5)
        os._exit(0)

    threading.Thread(target=delayed_exit, daemon=True).start()
    return jsonify({"status": "shutting down"})


@app.route("/speak", methods=["POST"])
def speak():
    touch_activity()
    text = request.json.get("text", "")
    voice = request.json.get("voice", VOICE)
    speed = float(request.json.get("speed", SPEED))

    if not text:
        return "No text", 400

    try:
        audio_chunks = []
        for _, _, audio in pipeline(text, voice=voice, speed=speed):
            if audio is not None:
                audio_chunks.append(audio)

        if not audio_chunks:
            return "No audio generated", 500

        combined = np.concatenate(audio_chunks)

        temp_id = str(uuid.uuid4())
        temp_path = f"/tmp/kokoro_{temp_id}.wav"
        sf.write(temp_path, combined, SAMPLE_RATE)

        return send_file(temp_path, mimetype="audio/wav")
    except Exception as e:
        print(f"Error: {e}")
        return str(e), 500


if __name__ == "__main__":
    watchdog = threading.Thread(target=idle_watchdog, daemon=True)
    watchdog.start()
    app.run(host="127.0.0.1", port=5001)
