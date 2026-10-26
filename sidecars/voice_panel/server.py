#!/usr/bin/env python3
"""Sidecar Web Server for Kokoro Voice Settings & Paragraph Playlist Player."""

import glob
import http.server
import json
import os
import socketserver
import sys
import urllib.parse
import urllib.request

SIDECAR_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(os.path.dirname(SIDECAR_DIR))
SCRIPTS_DIR = os.path.join(PLUGIN_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import voice_core

CONFIG_PATH = os.path.join(PLUGIN_DIR, "voice_config.json")
BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity/brain")


def load_config():
    defaults = {
        "enabled": True,
        "voice": "af_heart",
        "speed": 1.0,
        "player": "browser",
        "narrate_tools": True,
        "narrate_responses": True,
        "paragraph_pause_ms": 1000,
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                defaults.update(json.load(f))
        except Exception:
            pass
    return defaults


def save_config(new_conf):
    current = load_config()
    current.update(new_conf)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        return True, current
    except Exception as e:
        return False, str(e)


def list_recent_conversations():
    conversations = []
    pattern = os.path.join(BRAIN_DIR, "*", ".system_generated", "logs", "transcript.jsonl")
    candidates = glob.glob(pattern)
    if not candidates:
        return []
    candidates.sort(key=os.path.getmtime, reverse=True)
    for c_path in candidates[:10]:
        conv_id = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(c_path))))
        mtime = os.path.getmtime(c_path)
        snippet = ""
        try:
            with open(c_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    try:
                        e = json.loads(line)
                        if e.get("type") == "USER_INPUT":
                            snippet = e.get("content", "")[:70].replace("\n", " ").strip()
                            break
                    except Exception:
                        pass
        except Exception:
            pass
        conversations.append({
            "id": conv_id,
            "mtime": mtime,
            "title": snippet or f"Conversation {conv_id[:8]}",
            "is_latest": (c_path == candidates[0]),
        })
    return conversations


def get_latest_conversation_paragraphs(conv_id=None):
    """Retrieves paragraphs from the latest assistant response in the active conversation."""
    transcript_path = None
    resolved_conv_id = conv_id
    if conv_id:
        path = os.path.join(BRAIN_DIR, conv_id, ".system_generated", "logs", "transcript.jsonl")
        if os.path.exists(path):
            transcript_path = path

    if not transcript_path:
        pattern = os.path.join(BRAIN_DIR, "*", ".system_generated", "logs", "transcript.jsonl")
        candidates = glob.glob(pattern)
        if candidates:
            candidates.sort(key=os.path.getmtime, reverse=True)
            transcript_path = candidates[0]
            resolved_conv_id = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(transcript_path))))

    if not transcript_path or not os.path.exists(transcript_path):
        return [], resolved_conv_id

    latest_text = ""
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("source") == "MODEL" and entry.get("type") == "PLANNER_RESPONSE":
                    content = entry.get("content", "")
                    if content and content.strip():
                        latest_text = content.strip()
                        break
            except Exception:
                continue
    except Exception:
        pass

    if not latest_text:
        return [], resolved_conv_id

    # Sanitize and split into natural paragraphs
    sanitized = voice_core.sanitize_text_for_speech(latest_text)
    raw_paras = [p.strip() for p in sanitized.split("\n\n") if p.strip() and p.strip() != "---"]

    paragraphs = []
    for idx, p in enumerate(raw_paras):
        paragraphs.append({
            "id": idx + 1,
            "title": f"Paragraph {idx + 1}",
            "text": p,
            "preview": p[:80] + ("..." if len(p) > 80 else ""),
        })

    return paragraphs, resolved_conv_id


class VoiceSidecarHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Sidecar-Token")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ["/", "/ui.html"]:
            ui_path = os.path.join(SIDECAR_DIR, "ui.html")
            try:
                with open(ui_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_error(500, f"Error reading ui.html: {e}")
            return

        if path == "/api/config":
            cfg = load_config()
            cfg["available_voices"] = [
                {"id": "af_heart", "label": "Heart (US Female, Warm)"},
                {"id": "af_bella", "label": "Bella (US Female)"},
                {"id": "af_sky", "label": "Sky (US Female, Clear)"},
                {"id": "af_nicole", "label": "Nicole (US Female)"},
                {"id": "am_adam", "label": "Adam (US Male, Deep)"},
                {"id": "am_michael", "label": "Michael (US Male)"},
                {"id": "am_echo", "label": "Echo (US Male)"},
                {"id": "bf_alice", "label": "Alice (UK Female)"},
                {"id": "bf_emma", "label": "Emma (UK Female)"},
                {"id": "bf_isabella", "label": "Isabella (UK Female)"},
                {"id": "bm_george", "label": "George (UK Male)"},
                {"id": "bm_lewis", "label": "Lewis (UK Male)"},
            ]
            self.send_json(cfg)
            return

        if path == "/api/status":
            is_up = voice_core.is_port_open("127.0.0.1", 5001)
            info = {"server_running": is_up, "port": 5001}
            if is_up:
                try:
                    with urllib.request.urlopen("http://127.0.0.1:5001/status", timeout=1) as resp:
                        if resp.status == 200:
                            data = json.loads(resp.read().decode("utf-8"))
                            info.update(data)
                except Exception:
                    pass
            self.send_json(info)
            return

        if path == "/api/conversations":
            convs = list_recent_conversations()
            self.send_json({"conversations": convs})
            return

        if path == "/api/playlist":
            conv_id = query.get("conversationId", [None])[0]
            clear = query.get("clear", ["false"])[0].lower() in ["1", "true"]
            if clear:
                self.send_json({"paragraphs": [], "count": 0, "cleared": True})
                return

            paragraphs, resolved_id = get_latest_conversation_paragraphs(conv_id)
            self.send_json({
                "paragraphs": paragraphs,
                "count": len(paragraphs),
                "conversationId": resolved_id,
            })
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"

        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            data = {}

        if path == "/api/config":
            ok, res = save_config(data)
            if ok:
                self.send_json({"status": "saved", "config": res})
            else:
                self.send_json({"status": "error", "message": res}, code=500)
            return

        if path == "/api/start_bridge":
            started = voice_core.ensure_kokoro_server()
            self.send_json({"started": started, "port": 5001})
            return

        if path == "/api/stop_bridge":
            stopped = voice_core.shutdown_kokoro_server()
            self.send_json({"stopped": stopped, "port": 5001})
            return

        if path == "/api/speak":
            text = data.get("text", "")
            voice = data.get("voice", "af_heart")
            speed = float(data.get("speed", 1.0))

            if not text:
                self.send_json({"error": "No text provided"}, code=400)
                return

            wav_path = voice_core.synthesize_speech(text, voice=voice, speed=speed)
            if not wav_path or not os.path.exists(wav_path):
                self.send_json({"error": "Synthesis failed"}, code=500)
                return

            try:
                with open(wav_path, "rb") as f:
                    wav_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(wav_bytes)))
                self.end_headers()
                self.wfile.write(wav_bytes)
            finally:
                if os.path.exists(wav_path):
                    try:
                        os.remove(wav_path)
                    except OSError:
                        pass
            return

        if path == "/api/play_external":
            text = data.get("text", "")
            voice = data.get("voice", "af_heart")
            speed = float(data.get("speed", 1.0))
            player = data.get("player", "mpv")
            wav_path = voice_core.synthesize_speech(text, voice=voice, speed=speed)
            if wav_path:
                voice_core.play_audio(wav_path, player=player)
                self.send_json({"status": "played"})
            else:
                self.send_json({"error": "Playback failed"}, code=500)
            return

        self.send_error(404, "Not Found")

    def send_json(self, data, code=200):
        content = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main():
    port_env = os.environ.get("ANTIGRAVITY_SIDECAR_WEB_PORT")
    port = int(port_env) if port_env and port_env.isdigit() else 5002

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer(("127.0.0.1", port), VoiceSidecarHandler) as httpd:
        print(f"[*] Voice Sidecar server running on http://127.0.0.1:{port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
