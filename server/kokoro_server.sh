#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export KOKORO_DEVICE="${KOKORO_DEVICE:-cpu}"
export CUDA_VISIBLE_DEVICES=""
if [ -d "$HOME/scripts/kokoro-src" ]; then
  exec uv run --project "$HOME/scripts/kokoro-src" --python 3.12 python "$SCRIPT_DIR/kokoro_bridge.py" "$@"
else
  exec uv run --python 3.12 python "$SCRIPT_DIR/kokoro_bridge.py" "$@"
fi
