"""Kokoro TTS Voice & Screen Reader Core Library.

Ported from opencode-voice and opencode-tts-voice with full sanitization,
bridge auto-spawning, sentence boundary chunking, and audio playback.
"""

import os
import re
import socket
import subprocess
import tempfile
import time
from typing import List, Optional

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(SCRIPTS_DIR)
BUNDLED_START_CMD = os.path.join(PLUGIN_ROOT, "server", "kokoro_server.sh")
USER_SCRIPTS_CMD = os.path.expanduser("~/scripts/kokoro_server.sh")

KOKORO_HOST = os.environ.get("KOKORO_HOST", "127.0.0.1")
KOKORO_PORT = int(os.environ.get("KOKORO_PORT", "5001"))
KOKORO_START_CMD = os.environ.get(
    "KOKORO_START_CMD",
    BUNDLED_START_CMD if os.path.exists(BUNDLED_START_CMD) else USER_SCRIPTS_CMD,
)
DEFAULT_VOICE = "af_heart"
DEFAULT_SPEED = 1.0

EXTENSION_NAMES = {
    "astro": "Astro",
    "cjs": "CommonJS",
    "css": "CSS",
    "csv": "CSV",
    "go": "Go",
    "html": "HTML",
    "js": "JavaScript",
    "json": "JSON",
    "jsx": "JSX",
    "md": "Markdown",
    "mjs": "JavaScript module",
    "py": "Python",
    "rs": "Rust",
    "sh": "shell script",
    "toml": "TOML",
    "ts": "TypeScript",
    "tsx": "TSX",
    "txt": "text",
    "xml": "XML",
    "yaml": "YAML",
    "yml": "YAML",
}

UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
HEX_HASH_PATTERN = re.compile(r"\b[0-9a-f]{32,}\b", re.IGNORECASE)
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MD_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")
MD_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
CONTROL_CHARS = re.compile(r"[\x00-\x09\x0b\x0c\x0e-\x1f]")


def sanitize_text_for_speech(text: str) -> str:
    """Sanitizes Markdown, code blocks, technical IDs, and noise for clean speech prosody."""
    if not text:
        return ""

    # Strip control characters (strand-proofing)
    text = CONTROL_CHARS.sub(" ", text)

    # 1. Replace multi-line code blocks
    def replace_code_block(match):
        lang = match.group(1).strip() if match.group(1) else ""
        lang_spoken = EXTENSION_NAMES.get(lang.lower(), lang.capitalize())
        if lang_spoken:
            return f"\nOmitted {lang_spoken} code block.\n"
        return "\nOmitted code block.\n"

    text = re.sub(r"```([a-zA-Z0-9_-]*)\n[\s\S]*?```", replace_code_block, text)

    # 2. Replace Markdown tables
    text = re.sub(r"(\n\|[^\n]+\|\n)(\|[-:\s|]+\|\n)(\|[^\n]+\|\n?)+", "\nOmitted table.\n", text)

    # 3. Replace images
    text = MD_IMAGE_PATTERN.sub(lambda m: f"Image: {m.group(1)}" if m.group(1) else "Image omitted.", text)

    # 4. Replace links: keep link text
    text = MD_LINK_PATTERN.sub(r"\1", text)

    # 5. Replace standalone URLs
    text = URL_PATTERN.sub("link", text)

    # 6. Replace UUIDs and long hex hashes
    text = UUID_PATTERN.sub("identifier omitted", text)
    text = HEX_HASH_PATTERN.sub("hash omitted", text)

    # 7. Convert common inline file extensions when wrapped in backticks or preceded by dot
    for ext, name in EXTENSION_NAMES.items():
        text = re.sub(rf"`([a-zA-Z0-9_\-]+)\.{ext}`", rf"\1 {name} file", text)
        text = re.sub(rf"(?<=\s)\.({ext})\b", rf"{name}", text)

    # 8. Clean up backticks from inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # 9. Clean up Markdown headings and list markers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)

    # 10. Clean up asterisks and bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)

    # 11. Normalize whitespace & blank lines
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def split_into_sentences(text: str, max_chunk_chars: int = 240) -> List[str]:
    """Splits sanitized text into spoken chunks based on sentence boundaries."""
    if not text:
        return []

    # Split paragraphs first
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []

    # Regex matching sentence boundaries: . ! ? followed by whitespace or end of line
    sentence_boundary = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“\"])")

    for p in paragraphs:
        sentences = sentence_boundary.split(p)
        current = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if not current:
                current = s
            elif len(current) + len(s) + 1 <= max_chunk_chars:
                current += " " + s
            else:
                chunks.append(current)
                current = s
        if current:
            chunks.append(current)

    return chunks


def is_port_open(host: str = KOKORO_HOST, port: int = KOKORO_PORT, timeout_sec: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except (OSError, socket.timeout):
        return False


def ensure_kokoro_server(host: str = KOKORO_HOST, port: int = KOKORO_PORT, max_wait_sec: int = 45) -> bool:
    if is_port_open(host, port):
        return True

    if not os.path.exists(KOKORO_START_CMD):
        return False

    # Spawn server detached and log to /tmp/kokoro_server.log
    try:
        log_file = open("/tmp/kokoro_server.log", "a")
    except Exception:
        log_file = subprocess.DEVNULL

    subprocess.Popen(
        ["bash", KOKORO_START_CMD],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setpgrp,
    )

    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        time.sleep(1.0)
        if is_port_open(host, port):
            return True
    return False


def shutdown_kokoro_server(host: str = KOKORO_HOST, port: int = KOKORO_PORT) -> bool:
    """Sends a clean shutdown request to the Kokoro server."""
    if not is_port_open(host, port):
        return True
    try:
        import urllib.request
        req = urllib.request.Request(f"http://{host}:{port}/shutdown", method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def synthesize_speech(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    host: str = KOKORO_HOST,
    port: int = KOKORO_PORT,
) -> Optional[str]:
    """Requests Kokoro bridge to synthesize speech and returns the path to the temporary wav file."""
    if not text:
        return None

    if not ensure_kokoro_server(host, port):
        return None

    import urllib.request
    import json

    payload = json.dumps({"text": text, "voice": voice, "speed": speed}).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}:{port}/speak",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                audio_data = resp.read()
                fd, path = tempfile.mkstemp(prefix="kokoro_tts_", suffix=".wav")
                with os.fdopen(fd, "wb") as f:
                    f.write(audio_data)
                return path
    except Exception as e:
        print(f"[Kokoro TTS] Synthesis error: {e}")
        return None
    return None


def play_audio(wav_path: str, player: Optional[str] = None) -> bool:
    """Plays the WAV audio file using the preferred installed player."""
    if not wav_path or not os.path.exists(wav_path):
        return False

    players = [player] if player else ["mpv", "paplay", "ffplay", "aplay"]
    for p in players:
        if not p:
            continue
        try:
            if p == "mpv":
                subprocess.run(
                    ["mpv", "--no-video", "--really-quiet", wav_path],
                    check=True,
                    timeout=60,
                )
                return True
            elif p == "paplay":
                subprocess.run(["paplay", wav_path], check=True, timeout=60)
                return True
            elif p == "ffplay":
                subprocess.run(
                    ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", wav_path],
                    check=True,
                    timeout=60,
                )
                return True
            elif p == "aplay":
                subprocess.run(["aplay", "-q", wav_path], check=True, timeout=60)
                return True
        except Exception:
            continue
    return False


def speak_text(
    text: str,
    voice: str = DEFAULT_VOICE,
    speed: float = DEFAULT_SPEED,
    pause_between_chunks_sec: float = 0.0,
):
    """Sanitizes, chunks, synthesizes, and plays text."""
    sanitized = sanitize_text_for_speech(text)
    if not sanitized:
        return

    chunks = split_into_sentences(sanitized)
    for i, chunk in enumerate(chunks):
        if i > 0 and pause_between_chunks_sec > 0:
            time.sleep(pause_between_chunks_sec)

        wav = synthesize_speech(chunk, voice=voice, speed=speed)
        if wav:
            try:
                play_audio(wav)
            finally:
                if os.path.exists(wav):
                    try:
                        os.remove(wav)
                    except OSError:
                        pass
