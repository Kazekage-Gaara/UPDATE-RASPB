# AGENTS.md — AI agent instructions

Purpose
- Short guide for AI coding agents working in this repository. Keep changes minimal, link to existing docs, and prefer actionable edits.

How to act
- Ask clarifying questions when goals are ambiguous.
- Run local tests or linting before proposing large changes when possible.
- Avoid guessing runtime secrets or credentials; instead describe what the user must provide.

Important project files
- [backend/config.py](backend/config.py) — update/config values.
- [backend/main.py](backend/main.py) — application entrypoint.
- [docker-compose.yml](docker-compose.yml) — local services.

Quick setup notes for agents
- Install Python deps: `pip install -r backend/requirements.txt` (if needed).
- Use `docker-compose up --build` to reproduce the app environment locally.

Ollama-specific guidance (argument: `ollama`)
- Purpose: When the user requests `ollama`, prefer instructions and prompt templates tailored for running models via Ollama locally.
- Typical Ollama commands:
  - Install: see https://ollama.ai
  - Pull a model: `ollama pull <model>`
  - Run a model interactively: `ollama run <model>`
  - Start local HTTP API (if available): `ollama serve` then query `http://localhost:11434`
- Prompt template (use system/user roles):
  - System: "You are a concise coding assistant. Focus only on repository edits and tests." 
  - User: Provide the task, affected files (list), and required constraints (format, tests).
- When producing code patches, return a unified diff or apply_patch-ready patch and explain why changes are minimal and safe.

Safety & conventions
- Never add secrets or credentials to repo files.
- Preserve existing code style; run formatting on changed files only.

If you need more project-specific policies (contrib rules, CI details), ask the user to add or link the relevant docs and we'll reference them rather than duplicating content.

Next steps you can request
- `create-skill agent` — add automated checks or more granular agent rules for backend/frontend.
- `update AGENTS.md` — expand with test commands or CI links after user confirms.
