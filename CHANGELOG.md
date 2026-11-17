# Changelog

Maintained by [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7).

## 0.2.1 — 2026-11-17

- Run CLI model discovery in a fresh temporary directory rather than the Desktop host's application directory. This prevents protected host directories and their project context from affecting discovery.
- Allow up to 20 seconds for CLI model startup within a 25-second discovery deadline; history and status remain independent. The earlier eight-second CLI deadline was insufficient on the tested Desktop launch route.
- Added a regression check for independent discovery working directories and cleanup on failure. Worker permissions and model restrictions are unchanged.

## 0.2.0 — 2026-11-17

- Restricted Codex workers use the existing ChatGPT CLI sign-in, a temporary capability-narrowed model catalog, disabled external-tool inventory and ephemeral sessions. Execution is limited to the verified CLI version; no credential copying or API fallback.
- Antigravity workers use documented print mode, constant-output pre-tool deny hooks and session-only sensitive-action denies. Hooks work in the Windows executable without Python installed. Rejected tool attempts cannot be treated as successful responses.
- Both adapters preserve selected versus provider-observed model identity and bound process cleanup. Existing host lifecycle behavior remains subject to host policy; this is not OS isolation.
- Status includes the active server version and executable path. Regression checks cover status and history responding while model discovery is blocked.
- An opt-in interoperability harness tests each of the six lead-to-worker directions with explicit cloud authorization, synthetic inputs, artifact retrieval and separate lead review.

## 0.1.1 — 2026-11-17

- Model discovery runs independently of history, with concurrent probes, a shared 12-second deadline, 30-second cache and no duplicate in-flight probes.
- CLI probes no longer inherit MCP stdin. Child cleanup waits are bounded.
- Claude workers use strict empty MCP configuration, no built-in tools, disabled optional hooks/skills/connectors and deny-on-prompt behavior. Runtime tool lists, terminal status and reported model are checked.
- Child recursion markers block MCP and direct submit/review operations. This is defense in depth, not same-user authentication.
- Existing owner authorization covers scoped cloud subtasks without repeated permission questions.
- Antigravity profile registration, including its empty initial MCP file, with original-byte backup.
- Live Antigravity→Claude delegation succeeded. Claude lead discovery/history reads succeeded; Codex submission stopped before launch.
- Antigravity workers are temporarily disabled after an inconclusive containment test. Codex workers remain disabled. Both hosts can still lead through MCP.

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
