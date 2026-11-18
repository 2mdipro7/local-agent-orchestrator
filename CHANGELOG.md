# Changelog

Maintained by [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7).

## 0.3.1 (2026-11-18)

- Shorten shared worker boilerplate while preserving scope, tool restrictions, factuality and independent review requirements. More of the unchanged 8,000-character budget is available for existing skills and specific task instructions.
- Add a regression check for a large skill assigned in full alongside a scoped writing task. Skill selection remains generic; no personal skill is bundled or singled out by the application.

## 0.3.0 (2026-11-18)

- Discover skills from a central library, existing Codex and Claude skill folders, and owner-selected custom folders. Search, read and assign skills from the new Skills tab.
- Connected leads can use `list_skills` and `read_skill`, then submit selected skill IDs and referenced text with a task. Each job saves the assigned text, source metadata and hashes for review.
- Shared skills remain subject to the complete 8,000-character prompt limit, cloud authorization and existing response-only worker restrictions. Skill discovery and reads run independently of MCP status and history.
- Bound local scanning and reject unsafe skill paths, links and unsupported resource files. Public packages include guidance, never personal skill libraries.

## 0.2.4 (2026-11-17)

- Setup now tests the installed MCP server and reports per-host registration separately. Failed startup and incomplete setup stay visible with a retry option and a saved setup report.
- Detect currently registered Claude Store profiles before first launch while retaining active migrated profiles and ignoring abandoned package directories.
- Allow 60 seconds for new Codex MCP connections to start. Preserve matching connections with extra settings and report disabled entries without changing them.
- Clarify that the host MCP connection indicator and optional model response tests are separate.

## 0.2.3 — 2026-11-17

- Models now offers a response test and a green tick for a successful test with current saved settings. Untested, running, failed and unavailable states remain distinct, with details for the selected model.
- Test evidence persists across restarts. Settings changes, saved credential changes and later failed tasks invalidate it. Cloud tests ask before using an account; workers keep the same tool restrictions and review requirements.
- Rewrote the README around installation and everyday use. Build instructions and validation history live in their dedicated documents.
- Bundled documentation includes the architecture banner and linked setup, security and development guides.

## 0.2.2 — 2026-11-17

- Default installer setup now includes Claude Desktop, Claude Code, Codex and Antigravity, including missing first-profile MCP configurations. Existing settings, backups and conflicting entries are handled explicitly.
- Codex TOML registration preserves unrelated text and supports a custom `CODEX_HOME`; connection setup is distinct from sign-in and successful host loading.
- Provider discovery includes native per-user Claude installs and Codex's registered Windows app, avoiding a version-pinned executable path or dependence on a terminal's PATH. Worker restrictions and supported Codex CLI version remain unchanged.
- README now lists all six verified directions with desktop versus CLI/direct-MCP provenance. Added actual Antigravity desktop → Claude/Codex evidence and retained model-identity limits.

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
