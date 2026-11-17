# Changelog

Maintained by [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7).

## 0.1.0 — 2026-11-17

- One-time connection setup for existing Claude Desktop and Claude Code profiles, including migrated Windows Desktop storage.
- Backup, conflict refusal and preservation of other host settings; connection controls in the app and optional installer setup.
- Live Codex model discovery through the signed-in CLI app-server. Generation remains unavailable until response-only tool restrictions are verified.
- Existing provider settings survive the addition of new provider defaults.
- Clarified host/worker boundaries and Hermes configuration example.

## 0.0.0 â€” Version 0 â€” 2026-11-16

First public release of Local Agent Orchestrator, evolved from the private Local Agent Hub prototype.

- Windows desktop app, per-user installer and portable build.
- Local stdio MCP interface for compatible lead assistants.
- Ollama, LM Studio, Claude Code, Antigravity and configurable Gemini/OpenAI-compatible adapters with explicit capability limits.
- Text and vision inputs; service-dependent image generation.
- Scoped input snapshots, 8,000-character assembled prompts, cloud consent and evidence-based result review.
- Four active requests per profile with serialized local-model requests.
- MIT-licensed source, creator attribution, build instructions and Windows validation workflow.

Early preview: unsigned binaries, no automatic updates, no autonomous router or arbitrary worker shell/file tools. OpenCode worker execution is not enabled. See TEST-RESULTS.md for the exact validation scope.
