# Speech & Screen Reader Accessibility Rules

The user operates with assistive voice synthesis / screen reader playback powered by local Kokoro TTS. To ensure clear, natural, and low-fatigue audio narration:

1. **Natural, Spoken Prose**:
   - Write in direct, conversational sentences.
   - Avoid visual-only clutter: no ASCII diagrams, decorative box drawings, emoji walls, or elaborate markdown borders.
   - Prefer simple, bulleted lists or sequential sentences over complex nested structures.

2. **Avoid Markdown Tables**:
   - Screen readers and TTS engines struggle with markdown table syntax (`|---|`).
   - Use concise key-value lines or short prose lists instead of markdown tables.

3. **Code & File Handling**:
   - Do NOT dump large code blocks (over 5-10 lines) in conversation text unless specifically requested. Use file-writing tools (`write_file`, `edit_file`) for code changes.
   - When referencing files or code symbols, introduce them naturally so spoken narration sounds fluent (e.g. "in the Python configuration script" or "in index dot ts").

4. **Action & Completion Summaries**:
   - After tool operations, clearly and concisely summarize what changed in 1-3 plain sentences.
   - When asking for input or clarification, formulate questions directly at the end of the response.
