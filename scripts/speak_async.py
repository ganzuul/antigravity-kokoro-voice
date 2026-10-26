#!/usr/bin/env python3
"""Asynchronous speech worker.

Runs detached from the Antigravity lifecycle hook so hooks return immediately ({})
while audio synthesizes and plays smoothly in the background.
"""

import os
import signal
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

import voice_core

PID_FILE = "/tmp/kokoro_voice_worker.pid"


def kill_previous_playback():
    """Kills any active previous speech worker so new turns interrupt stale audio."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            if old_pid != os.getpid():
                os.kill(old_pid, signal.SIGTERM)
        except Exception:
            pass


def main():
    if len(sys.argv) < 2:
        return

    text = sys.argv[1]
    voice = sys.argv[2] if len(sys.argv) > 2 else "af_heart"
    try:
        speed = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    except ValueError:
        speed = 1.0

    interrupt = sys.argv[4] == "1" if len(sys.argv) > 4 else True
    if interrupt:
        kill_previous_playback()

    # Save our PID
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass

    try:
        pause_sec = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
    except ValueError:
        pause_sec = 0.0

    try:
        voice_core.speak_text(
            text,
            voice=voice,
            speed=speed,
            pause_between_chunks_sec=pause_sec,
        )
    finally:
        if os.path.exists(PID_FILE):
            try:
                with open(PID_FILE, "r") as f:
                    if f.read().strip() == str(os.getpid()):
                        os.remove(PID_FILE)
            except Exception:
                pass


if __name__ == "__main__":
    main()
