#!/usr/bin/env python3
"""CLI utility to enable, disable, toggle, or check status of Kokoro Voice TTS."""

import json
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.path.dirname(SCRIPTS_DIR)
CONFIG_PATH = os.path.join(PLUGIN_ROOT, "voice_config.json")
sys.path.insert(0, SCRIPTS_DIR)

import voice_core


def load_config():
    defaults = {
        "enabled": False,
        "voice": "af_heart",
        "speed": 1.0,
        "player": "mpv",
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


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving config: {e}", file=sys.stderr)
        return False


def main():
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "status"
    cfg = load_config()

    if action in ["enable", "on", "start"]:
        cfg["enabled"] = True
        save_config(cfg)
        print("Kokoro Voice narration ENABLED.")
    elif action in ["disable", "off", "stop"]:
        cfg["enabled"] = False
        save_config(cfg)
        # Also shut down running bridge server to free VRAM/RAM immediately
        stopped = voice_core.shutdown_kokoro_server()
        status_msg = "Bridge stopped." if stopped else "Bridge was not running."
        print(f"Kokoro Voice narration DISABLED. {status_msg}")
    elif action in ["toggle"]:
        cfg["enabled"] = not cfg.get("enabled", False)
        save_config(cfg)
        if not cfg["enabled"]:
            voice_core.shutdown_kokoro_server()
        state = "ENABLED" if cfg["enabled"] else "DISABLED"
        print(f"Kokoro Voice narration is now {state}.")
    elif action in ["status"]:
        state = "ENABLED" if cfg.get("enabled") else "DISABLED"
        running = voice_core.is_port_open()
        server_state = "Running (Port 5001)" if running else "Offline"
        print(f"Plugin Status: {state}")
        print(f"Bridge Server: {server_state}")
        print(f"Config: voice={cfg.get('voice')}, speed={cfg.get('speed')}, narrate_responses={cfg.get('narrate_responses')}")
    else:
        print(f"Usage: {sys.argv[0]} [enable|disable|toggle|status]")
        sys.exit(1)


if __name__ == "__main__":
    main()
