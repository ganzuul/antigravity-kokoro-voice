#!/usr/bin/env python3
"""Streaming TTS Voice Daemon for Antigravity.

Continuously tails the active conversation transcript.jsonl, extracts new
sentences as they finish generating, and plays them through Kokoro TTS
with look-ahead synthesis (sentence-by-sentence streaming playback).
"""

import argparse
import glob
import json
import os
import queue
import sys
import threading
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

import voice_core

BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity/brain")


def get_latest_transcript() -> str:
    """Finds the most recently modified transcript.jsonl file."""
    pattern = os.path.join(BRAIN_DIR, "*", ".system_generated", "logs", "transcript.jsonl")
    candidates = glob.glob(pattern)
    if not candidates:
        return ""
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0]


class SpeechQueue:
    def __init__(self, voice="af_heart", speed=1.0):
        self.voice = voice
        self.speed = speed
        self.audio_queue = queue.Queue()
        self.running = True
        self.synth_thread = None
        self.play_thread = threading.Thread(target=self._play_loop, daemon=True)
        self.play_thread.start()

    def enqueue_text(self, text: str):
        if not text.strip():
            return
        threading.Thread(target=self._synth_worker, args=(text,), daemon=True).start()

    def _synth_worker(self, text: str):
        wav = voice_core.synthesize_speech(text, voice=self.voice, speed=self.speed)
        if wav:
            self.audio_queue.put(wav)

    def _play_loop(self):
        while self.running:
            try:
                wav = self.audio_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                voice_core.play_audio(wav)
            finally:
                if os.path.exists(wav):
                    try:
                        os.remove(wav)
                    except OSError:
                        pass
                self.audio_queue.task_done()


def tail_transcript(transcript_path: str, speech_queue: SpeechQueue):
    print(f"[*] Following transcript: {transcript_path}")
    print("[*] Streaming speech active (Ctrl+C to stop)...")

    spoken_step_indices = set()
    last_spoken_content = ""

    with open(transcript_path, "r", encoding="utf-8", errors="ignore") as f:
        # Seek to end so we don't replay past conversation history
        f.seek(0, os.SEEK_END)

        buffer = ""
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.3)
                continue

            buffer += line
            if not buffer.endswith("\n"):
                continue

            raw_line = buffer.strip()
            buffer = ""
            if not raw_line:
                continue

            try:
                entry = json.loads(raw_line)
            except Exception:
                continue

            step_idx = entry.get("step_index")
            source = entry.get("source")
            step_type = entry.get("type")

            if source == "MODEL" and step_type == "PLANNER_RESPONSE":
                content = entry.get("content", "")
                if content and step_idx not in spoken_step_indices:
                    # Sanitize and extract delta
                    sanitized = voice_core.sanitize_text_for_speech(content)
                    chunks = voice_core.split_into_sentences(sanitized)
                    for c in chunks:
                        speech_queue.enqueue_text(c)
                    spoken_step_indices.add(step_idx)


def main():
    parser = argparse.ArgumentParser(description="Antigravity Voice Streamer")
    parser.add_argument("--transcript", help="Explicit path to transcript.jsonl", default=None)
    parser.add_argument("--voice", default="af_heart", help="Kokoro voice name")
    parser.add_argument("--speed", type=float, default=1.0, help="Speech speed multiplier")
    args = parser.parse_args()

    transcript_path = args.transcript or get_latest_transcript()
    if not transcript_path or not os.path.exists(transcript_path):
        print("[!] No active transcript found. Start a conversation in Antigravity first.")
        sys.exit(1)

    print("[*] Ensuring Kokoro server is warm...")
    if not voice_core.ensure_kokoro_server():
        print("[!] Failed to connect to Kokoro bridge. Check /home/nos/scripts/kokoro_server.sh")
        sys.exit(1)

    speech_queue = SpeechQueue(voice=args.voice, speed=args.speed)
    try:
        tail_transcript(transcript_path, speech_queue)
    except KeyboardInterrupt:
        print("\n[*] Streaming stopped.")


if __name__ == "__main__":
    main()
