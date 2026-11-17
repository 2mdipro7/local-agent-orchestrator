# Local Agent Orchestrator — Version 0

**Created and maintained by [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7)** · [Portfolio](https://2mdipro7.github.io/) · [Downloads](https://github.com/2mdipro7/local-agent-orchestrator/releases/tag/v0.1.1) · [MIT license](LICENSE)

A per-user Windows coordinator that lets a compatible MCP host act as the lead and delegate bounded tasks to configured model providers. This preview has no public server, telemetry, automatic model download, startup service, or bundled credentials/model weights. It does not replace a model subscription.

## Install and start

1. Download `LocalAgentOrchestrator-v0.1.1-Setup.exe` from [Releases](https://github.com/2mdipro7/local-agent-orchestrator/releases/tag/v0.1.1), run it and choose **Install for this user**. No administrator access is needed.
2. Open **Local Agent Orchestrator** from the Start menu. For portable use, keep LocalAgentOrchestrator.exe and LocalAgentOrchestratorMCP.exe together.
3. Start your existing local model server, or configure a provider in Settings. Refresh Models. Listed candidates and successful inference are different evidence.
4. Choose the exact provider/model, a task folder and specific prompt. Attach only relevant text/image sources. The app never silently uploads a whole folder.
5. Cloud/API/subscription use requires the per-task authorization checkbox. This is consent to use your own configured account, not a hard price cap. No API key is included.
6. Review actual output. Execution success remains pending until the lead records criterion evidence and boundary findings.
7. Connect detected Claude Desktop, Claude Code or Antigravity profiles during installation or from Connections. Fully quit and reopen the host. For other leads, export connection JSON and adapt it using HOST-CONNECTIONS.md. Any host must support local stdio MCP; a web-only chat without a local connector cannot invoke this executable directly.

## Provider support

| Route | Preview behavior | Validation |
|---|---|---|
| Ollama | Installed-model discovery; local text and vision input | Real local Qwen text check completed; vision check recorded in TEST-RESULTS.md |
| LM Studio | Loopback OpenAI-compatible text/vision requests | Protocol tests; service not installed/running on this PC |
| Claude Code | Existing CLI sign-in; explicit model; response-only worker | Live test verifies empty built-in/MCP tool lists and matching model metadata; no recursive delegation |
| Antigravity CLI | MCP lead and model discovery | Live Antigravity→Claude delegation passed; worker generation temporarily disabled pending tool-filter verification |
| OpenAI-compatible API | HTTPS with your key, or optional-key loopback server; text/vision and base64 image generation | Mock protocol tests; no billable API requests made |
| Google Gemini API | Explicit model discovery/text/vision/image requests with your key | Mock protocol tests; no billable API requests made |
| Codex | Compatible lead via MCP; signed-in model catalog discovery | Live catalog discovery tested; worker execution deliberately unavailable until response-only restrictions are verified |
| OpenCode | Compatible lead via MCP; worker model discovery | Worker execution is deliberately unavailable until version-specific confinement is verified |

Image understanding and image generation are different. Ollama vision models analyze supplied images; this app does not turn them into image generators. Image creation requires a configured image-capable Gemini/OpenAI-compatible service, including a compatible local image server if you already run one. No local image-generation weights or ComfyUI workflow engine are bundled. Vertex AI/service-account OAuth and other Google APIs are not implemented by this preview.

## Boundaries

- Four active queued/running requests maximum across Orchestrator processes sharing the profile. One local-model request is dispatched at a time. External server workloads are outside the Orchestrator's control.
- Complete authored task prompt, guardrails, source excerpts and criteria must fit 8,000 characters. Oversized tasks are rejected, never silently truncated.
- Source paths must be contained in the declared workspace. Conventional credential files and Orchestrator private data cannot be attached. Filename filtering cannot identify every secret; review selected content before consenting to cloud use.
- API keys are encrypted using Windows CurrentUser DPAPI. This protects stored data but does not isolate it from every process running as that same Windows user. No cross-user or tenant isolation is claimed.
- Source-injection handling is a prompt-level control. CLI permissions, data selection and HTTP endpoint checks add boundaries; this app is not an operating-system sandbox.
- Lead labels are audit labels, not cryptographically authenticated identities. Every MCP host runs with the local user's authority. Workers have no lead-review tools in their response-only assignment.
- Cancellation keeps a slot until the adapter returns. A remote/local server may finish a request after a timeout or disconnect; inspect before retrying. No claim of terminating another application's GPU work is made.
- No task output is automatically accepted, sent, published, deployed or executed. The preview is for attended evaluation, not unattended high-stakes operation.

## Open-source release

Version **0.0.0** was the first public release, called **Version 0**. Version **0.1.1** fixes discovery blocking other MCP calls, isolates Claude workers and adds Antigravity host setup. Claude→Codex task execution remains unavailable; the installer does not claim universal bidirectional execution. Application source is licensed under MIT; see [LICENSE](LICENSE). External providers, runtimes and model weights retain their own licenses and terms. Third-party runtime notices are in [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).

This is an unsigned early preview for attended use. Code signing, signed updates, broader accessibility/security review and independent customer-host testing remain future work. The application coordinates response-only requests; it does not yet offer arbitrary worker file edits, shell execution, an autonomous task planner or automatic model benchmarking/routing. The external lead chooses models and reviews results. Provider availability depends on each user's installed tools, account and endpoint.

## Run from source

Use Windows x64 and Python 3.12 with Tcl/Tk (included in the standard Windows Python installer). The application uses Python's standard library; providers are optional separate installations.

```powershell
git clone https://github.com/2mdipro7/local-agent-orchestrator.git
cd local-agent-orchestrator
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe app_entry.py
```

For a source MCP connection, run `mcp_entry.py` with that interpreter. Export client settings from Connections. API keys saved by the app use Windows DPAPI; other operating systems are not supported in Version 0.

## Test and build

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe build_windows.py
.\.venv\Scripts\python.exe smoke_windows.py
.\.venv\Scripts\python.exe package_release.py
```

`dist/` contains the GUI and MCP executables; `release/` contains the setup executable, portable ZIP and SHA-256 checksums. `smoke_windows.py` uses a temporary data directory and does not call model providers. `validate_windows.py` is an optional real-model check: start Ollama with `qwen3:1.7b` and `moondream:latest` already installed. It performs local inference and writes ignored validation output; it does not download models. [TEST-RESULTS.md](TEST-RESULTS.md) separates previous model checks from Version 0 checks.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [CHANGELOG.md](CHANGELOG.md) and [host connection instructions](HOST-CONNECTIONS.md).

## Files and removal

Installed program: %LOCALAPPDATA%\Programs\LocalAgentOrchestrator
User jobs/settings/encrypted keys: %LOCALAPPDATA%\LocalAgentOrchestrator\data

Remove the app using Windows Installed apps. Uninstall preserves user data. Removing that data and encrypted keys is a separate deliberate user action. The installer does not edit PATH, firewall rules or startup entries. Its optional host connection step adds one MCP entry with a backup. Uninstall preserves host entries and backups; remove the entry in the host when retiring the app.

### Earlier private preview

Version 0 installs separately from the earlier Local Agent Hub preview. Existing settings and jobs are not automatically moved. To deliberately reuse the old profile, pass `--home "$env:LOCALAPPDATA\LocalAgentHub\data"` to the new GUI/MCP executable. Stop old app instances before sharing that data directory. Alternatively start fresh with the new default. Uninstalling either app preserves saved data.

## Creator

[Mehrab Mashrafi](https://github.com/2mdipro7) · [GitHub @2mdipro7](https://github.com/2mdipro7) · [Portfolio](https://2mdipro7.github.io/).

This is an independent community project; provider names identify integrations, not endorsement.
