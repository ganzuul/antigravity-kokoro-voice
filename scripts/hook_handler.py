#!/usr/bin/env python3
"""Antigravity Lifecycle Hook Handler for Kokoro TTS Voice Narration."""

import json
import os
import sys

# Add scripts directory to path
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

import subprocess
import voice_core

CONFIG_PATH = os.path.join(os.path.dirname(SCRIPTS_DIR), "voice_config.json")
SPEAK_ASYNC_PATH = os.path.join(SCRIPTS_DIR, "speak_async.py")


def spawn_speech_async(text: str, config: dict, interrupt: bool = True):
    if not text or not text.strip():
        return
    voice = config.get("voice", "af_heart")
    speed = str(config.get("speed", 1.0))
    intr = "1" if interrupt else "0"
    pause_ms = config.get("paragraph_pause_ms", 1000)
    pause_sec = str(float(pause_ms) / 1000.0)
    subprocess.Popen(
        [sys.executable, SPEAK_ASYNC_PATH, text, voice, speed, intr, pause_sec],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def load_config():
    defaults = {
        "enabled": True,
        "voice": "af_heart",
        "speed": 1.0,
        "player": "mpv",
        "narrate_tools": True,
        "narrate_responses": True,
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_conf = json.load(f)
                defaults.update(user_conf)
        except Exception:
            pass
    return defaults


def get_last_model_content(transcript_path: str) -> str:
    if not transcript_path or not os.path.exists(transcript_path):
        return ""

    try:
        # Read the last lines of transcript.jsonl
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
                        return content.strip()
            except Exception:
                continue
    except Exception as e:
        pass
    return ""


def handle_post_tool_use(payload: dict, config: dict):
    if not config.get("enabled") or not config.get("narrate_tools"):
        return

    tool_call = payload.get("toolCall", {})
    name = tool_call.get("name", "Tool")
    error = payload.get("error")

    # Clean display names for tools
    tool_descriptions = {
        "run_command": "Terminal command",
        "read_file": "Read file",
        "write_file": "Wrote file",
        "edit_file": "Edited file",
        "search_web": "Web search",
        "ask_question": "Question prompt",
    }
    desc = tool_descriptions.get(name, name.replace("_", " ").capitalize())

    if error:
        msg = f"{desc} failed."
    else:
        msg = f"{desc} complete."

    spawn_speech_async(msg, config, interrupt=False)


def handle_stop(payload: dict, config: dict):
    if not config.get("enabled") or not config.get("narrate_responses"):
        return

    transcript_path = payload.get("transcriptPath")
    conv_id = payload.get("conversationId", "default")
    last_content = get_last_model_content(transcript_path)

    if not last_content:
        return

    # Check state file to avoid re-speaking identical turn
    state_file = f"/tmp/kokoro_last_spoken_{conv_id}.txt"
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                last_spoken = f.read()
            if last_spoken.strip() == last_content.strip():
                return
        except Exception:
            pass

    # Record that we spoke this content
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            f.write(last_content)
    except Exception:
        pass

    spawn_speech_async(last_content, config, interrupt=True)


def main():
    try:
        input_data = sys.stdin.read()
        payload = json.loads(input_data) if input_data.strip() else {}
    except Exception:
        payload = {}

    config = load_config()

    event = sys.argv[1] if len(sys.argv) > 1 else ""

    try:
        if event == "PostToolUse":
            handle_post_tool_use(payload, config)
        elif event == "Stop":
            handle_stop(payload, config)
    except Exception as e:
        # Never break Antigravity loop on hook errors
        pass

    # Lifecycle hooks expect a valid JSON response on stdout
    print(json.dumps({}))


if __name__ == "__main__":
    main()
