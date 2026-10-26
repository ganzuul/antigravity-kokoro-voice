# Antigravity Kokoro Voice

High-quality local text-to-speech voice output and screen-reader accessibility for Google Antigravity, powered by [Kokoro TTS](https://github.com/hexgrad/kokoro).

Includes an interactive paragraph audio playlist with full playback controls, native Electron sidecar configuration, non-blocking lifecycle hooks, and spoken-friendly assistant prompt rules.

---

## Features

- **Local Neural Speech Synthesis**: Powered by Kokoro-82M with multiple natural voices (US/UK English, male and female).
- **Auto-Wake & 10-Minute Inactivity Unload**: Automatically boots the synthesis server on demand when an utterance is requested, and cleanly shuts it down after 10 minutes of inactivity to release memory.
- **Interactive Message Paragraph Playlist**: Breaks assistant responses into paragraphs and displays them in a playlist with Play, Pause, Next, Previous, seeking scrubber, and track jump.
- **Configurable Paragraph Pause**: Set custom pause intervals (0s to 5s) between paragraphs for comfortable listening cadence during auto-advance.
- **Spoken-Friendly System Prompt (`rules/AGENTS.md`)**: Instructs the agent to produce conversational prose and avoids visual clutter (tables, ASCII art, raw diffs) that degrades screen-reader prosody.
- **Markdown & Syntax Sanitizer**: Strips code blocks, raw hex hashes, UUIDs, and converts file extensions (e.g. `.ts` to "TypeScript file") into natural spoken text.
- **Non-Blocking Lifecycle Hooks (`hooks.json`)**: Runs audio synthesis in detached worker processes so Antigravity execution loops return in ~50ms.
- **Electron GUI Sidecar Panel**: Openable in Antigravity's auxiliary side pane (`sidecar://kokoro-tts-voice/voice_panel/ui.html`).

---

## Directory Structure

```text
antigravity-kokoro-voice/
├── plugin.json                 # Antigravity plugin manifest
├── voice_config.json           # User configuration (voice, speed, pauses)
├── hooks.json                  # Lifecycle hooks (PostToolUse, Stop)
├── rules/
│   └── AGENTS.md               # Spoken-friendly prose rules
├── scripts/
│   ├── voice_core.py           # Core sanitizer, chunker, and player
│   ├── hook_handler.py         # Fast non-blocking hook dispatcher
│   ├── speak_async.py          # Detached background audio player
│   └── voice_streamer.py       # Live streaming daemon
├── server/
│   ├── kokoro_bridge.py        # Flask bridge with 10-minute idle watchdog
│   └── kokoro_server.sh        # Server runner
└── sidecars/
    └── voice_panel/
        ├── sidecar.json        # Sidecar manifest
        ├── server.py           # Sidecar web & API server
        └── ui.html             # Playlist & audio player GUI
```

---

## Quick Install

Clone directly into your Antigravity global plugin directory:

```bash
git clone https://github.com/ganzuul/antigravity-kokoro-voice.git ~/.gemini/config/plugins/kokoro-tts-voice
```

Antigravity will automatically discover the plugin on next launch.

---

## Configuration

Adjust settings in `voice_config.json` or directly in the Electron sidecar panel:

```json
{
  "enabled": true,
  "voice": "af_heart",
  "speed": 1.0,
  "player": "mpv",
  "narrate_tools": true,
  "narrate_responses": true,
  "paragraph_pause_ms": 1000
}
```

---

## Credits

- Derived in part from `@semirhuduti/opencode-tts-voice` and `opencode-voice`.
- Speech model: [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) by hexgrad.

## License

[MIT](LICENSE)
