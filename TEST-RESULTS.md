# Validation history

[Local Agent Orchestrator](https://github.com/2mdipro7/local-agent-orchestrator) · Created by [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7) · [Portfolio](https://2mdipro7.github.io/).

Date: 16 November 2026 (Asia/Dhaka). Version: 0.0.0.

## Version 0.2.0 checks — 17 November 2026

60 automated tests: **59 passed, 1 skipped** (unchanged Windows symbolic-link privilege requirement). Frozen GUI/MCP smoke checks passed, including version 0.2.0 and nine tools. A separate frozen Codex task returned `FROZEN_CODEX=42`, with a 927-character assembled prompt; root independently verified 31+11 and accepted the inspected artifact.

All six directed routes completed actual synthetic inference, MCP artifact retrieval and independent root review:

| Lead | Worker | Task ID | Exact output |
|---|---|---|---|
| Codex assistant | Claude Haiku 5.5 | `976109d13623447ea199553dad589ea9` | `CODEX_TO_CLAUDE=42` |
| Codex assistant | Antigravity Gemini 3.8 Flash Medium | `01406f03a5dc4b7da1e37c3d617a1c3e` | `CODEX_TO_ANTIGRAVITY=42` |
| Claude Haiku 5.5 | Codex gpt-6-luna | `f23a3d7fb26b4908ad1082b8c8f75adc` | `CLAUDE_TO_CODEX=42` |
| Claude Haiku 5.5 | Antigravity Gemini 3.8 Flash Medium | `d4974d7992bd4a58a9a06963fc777857` | `CLAUDE_TO_ANTIGRAVITY=42` |
| Antigravity Gemini 3.8 Flash Medium | Claude Haiku 5.5 | `701ac583932849b7a4b02c82ea441bc8` | `ANTIGRAVITY_TO_CLAUDE=42` |
| Antigravity Gemini 3.8 Flash Medium | Codex gpt-6-luna | `d90237d7572d4e69bd5d3bc4b8121e34` | `ANTIGRAVITY_TO_CODEX=42` |

The Codex lead was the current assistant invoking an MCP client through its shell tool, not a nested Codex CLI or ChatGPT web session. Those two routes used the frozen executable. Claude and Antigravity were actual headless CLI leads using the source MCP entrypoint; their final traces contained no errors and exactly two submissions each. Claude completed in 35.66 seconds, Antigravity in 58.66 seconds. Workers did not approve themselves. Root inspected prompts, response artifacts, persisted results and lead traces, independently calculated 17+25, and recorded accepted reviews.

One earlier Antigravity lead test used its old global server despite a same-name workspace entry. It completed one Claude worker, then guessed invalid artifact parameters repeatedly. Root stopped that lead after inspecting the completed job. The corrected run used a distinct temporary global MCP entry and exact argument schemas; the temporary entry was removed afterward. This is a harness/connection correction, not a permission bypass. The first run is not counted as a successful direction test. Workspace configuration precedence is not assumed reliable for this CLI.

Codex is pinned to CLI `0.169.0-alpha.11.1`. Root checked the version-matched shell, patch, code-mode, MCP binding and extension gates against OpenAI source. Child-specific catalog/settings narrow capabilities; external-server status must show disabled entries with no tools before inference. Synthetic file-write, command and subagent prompts produced no observed side effects; they do not prove that the model attempted a blocked call. Mock tests exercise forbidden tool events and failure/mismatch paths. Existing owner-configured lifecycle, authentication, host state and managed protections remain active. Automatic project documentation is suppressed for this child.

Antigravity uses documented constant-output pre-tool denial hooks and sensitive-action denies. Live source tests showed read/write/command attempts denied before effects; delegation triggered the deny guard. A hook-error no-op was blocked in the tested version, but that is not a guarantee against every hook/OS failure. Root inspected the implementation, ran guard tests, and verified frozen execution with the PowerShell hook commands; Python is not required by the packaged guards. The all-tools hook and MCP/network deny rules are source-checked; no live external network action was attempted.

Claude reported the matching generation model in provider metadata. Codex and Antigravity confirmed selected models but did not provide independent generation identities; their records retain `observed_model=null` and warnings. These are same-user application controls, not OS isolation or a cross-user security boundary.

For the reported Desktop timeout, root found running old canonical executables while saved config pointed to staged 0.1.1. A fresh installed 0.1.1 server returned history immediately, status in 2.02 seconds and 31 model/status records in 5.44 seconds while discovery was concurrent. Offline Ollama/LM Studio did not block responses. Root stopped only the stale orchestrator processes (zero active jobs) and replaced the old executable path. Claude Desktop was being used for other work, so no completed Desktop restart or post-restart Desktop tool call is claimed. Current status responses expose version and executable path to identify stale sessions.

After installing 0.2.0, binary hashes matched the build and all three existing host profiles pointed to its staged server, with original-byte backups. The installed server initialized in 0.69 seconds; concurrent history, status and model requests returned in 0.01, 2.12 and 4.89 seconds respectively. It reported 31 model/status records and unavailable offline Ollama/LM Studio providers, with no active jobs. Desktop still needs a full quit/reopen to load that connection.

Native adapter deliverables were accepted after root inspected the actual implementations, relevant sources, focused/full test results and frozen outputs. A separate Claude source audit was rejected because it asserted an unsupported web-tool gap and exceeded its output limit; its useful findings were independently checked, not accepted wholesale.

### Repeating the synthetic direction checks

Run `python verify_live_routes.py --lead LEAD --output NEW_ABSOLUTE_DIRECTORY --allow-cloud` separately for `codex-root`, `claude` and `antigravity`. Existing CLI sign-ins and the listed models are required. Each run creates two subscription inference tasks and retains private evidence in a new directory; it refuses to reuse an existing directory. The `codex-root` option is a direct MCP client, so identify the actual assistant operating it rather than claiming an autonomous Codex CLI lead.

For Antigravity, also pass `--temporary-antigravity-connection`. This explicitly backs up its global MCP profile beside the original, adds one distinct test connection, and removes only that connection on exit while preserving other edits. Backups can contain existing private settings: keep them private. A conflicting test entry stops the run. Use `--server ABSOLUTE_MCP_EXE` to test a frozen server. Inspect pending jobs and traces before retrying failures; the harness checks results but does not approve workers on the lead's behalf.

## Version 0.1.1 checks — 17 November 2026

53 tests: **52 passed, 1 skipped** (unchanged Windows symbolic-link privilege limitation). Added checks cover blocked discovery without blocking history, duplicate-probe prevention, partial results, worker recursion rejection, Claude tool/MCP/status/model checks, Antigravity protocol failures and host setup.

Frozen 0.1.1 GUI/MCP checks passed: startup/exit, server version, nine tools and connection export. A staged installed 0.1.1 server returned history in 0.77 seconds and 31 model/status records in 5.89 seconds. Claude Code reported that staged server Connected at user scope. Claude Desktop was actively running unrelated work, so its configuration was updated with backup for the next restart; no current Desktop reload is claimed. Antigravity's global profile was registered with the staged server.

An isolated installed 0.1.0 process returned both model discovery and history after 12.34 seconds: the reported 80-second timeout was not reproduced, but serialization was. Updated source returned history in 0.34 seconds while discovery completed in 6.69 seconds. Ollama and LM Studio refused connections; their models are not verified running.

Live Claude Haiku returned the exact synthetic echo with empty built-in/MCP tool lists, matching model metadata and no workspace files created. A real Antigravity lead selected Gemini 3.8 Flash Medium, submitted one Claude Haiku task through MCP, retrieved `SUM=42`, and left review to root. Root recomputed the answer, inspected the artifact and recorded acceptance. The lead corrected an initially wrong artifact filename using returned metadata. The test exited normally in 64.38 seconds; assembled worker prompt was 956 characters.

A real Claude Haiku lead completed discovery, history, task and artifact reads in 19.75 seconds overall. Its single Codex submission was rejected before a job or inference was created. It did not retry or switch providers. This verifies the failure boundary, not Claude→Codex execution.

Antigravity ACP 1.5.10 returned an exact echo, but an adversarial canary emitted an unclassified tool notification despite its configured filter. The adapter rejected it and reaped its child; the disposable workspace remained unchanged. The notification's name/status were not retained, so preexecution exclusion is unverified. Production Antigravity workers are disabled. Codex's installed model-driven tool registry also lacks a verified public response-only restriction. No API fallback, credential copying or global permission changes forced either route.

## Version 0.1.0 checks — 17 November 2026

The lead ran 37 tests: **36 passed, 1 skipped** (Windows symbolic-link privilege unavailable; permissions unchanged). New checks cover preservation of other host settings, original-byte backups, idempotent setup, conflicting/malformed/duplicate-key JSON rejection, migrated Claude Desktop discovery, provider-settings migration, Codex protocol pagination and discovery-only execution refusal.

Frozen Windows GUI and MCP smoke checks passed for 0.1.0: correct server version, nine tools, connection export, GUI startup and exit. A live signed-in Codex app-server catalog returned eight model entries; no inference turn was started, account identifiers were not returned, and its process was stopped after discovery.

Claude Code reported the installed server **Connected** at user scope (all projects). After a full restart, Claude Desktop 5.11492.5 visibly reported **local-agent-orchestrator — Running**. Those connection checks initially used the already-installed 0.0.0 server; they establish host registration independently of the subsequent 0.1.0 build. No claim is made that Claude successfully delegated an inference task to Codex: Codex worker execution remains disabled.

Independent Antigravity static review informed multi-profile labels; the lead checked findings against source and the installed protocol schema, corrected unsupported defect claims, and reran checks. Static worker review does not substitute for host or inference testing.

## Version 0 checks

The lead reran all 27 automated tests: **26 passed, 1 skipped**. The skipped test requires Windows permission to create a symbolic link; permissions were not changed. Source snapshot replacement, stable-handle reads, artifact containment, cloud consent, DPAPI with a synthetic key, assembled prompt cap, four-job admission across processes, serialized local requests, cancellation accounting, provider request shapes and renamed MCP connection export passed.

Provider protocol checks use mocks except for the historical runs below. No production key is required. GitHub Actions runs tests and builds on Windows without provider accounts; its current status appears in the Actions tab.

The lead ran `smoke_windows.py` against the Version 0 executables: **passed**. The frozen GUI started/exited, MCP reported the correct product/version, nine tools were exposed and the connection export targeted the renamed executable. The running desktop Overview was visually inspected: the product name, Version 0 label, creator credit and GitHub/portfolio links were visible and readable. It uses a temporary profile and makes no inference requests. Release files are packaged from an explicit list with SHA-256 checksums.

## Historical prototype live checks

The earlier Local Agent Hub prototype was tested on Windows with 32 GB RAM and an RTX 4070 Laptop GPU (8 GB VRAM). Packaged Ollama tasks succeeded: Qwen `qwen3:1.7b` returned `LOCAL_READY`; Moondream `moondream:latest` identified a synthetic red square. Both outputs were independently inspected. Sample warm runs were 8.58 and 9.09 seconds; initial loads were slower. These are historical smoke samples, not benchmarks or a fresh live inference certification of Version 0.

The earlier prototype's installation and Start-menu registration worked without elevation. New branding uses separate program/data directories. Uninstaller safeguards are inspected in source; a full interactive uninstall of the final version is not claimed.

## Limits

- Hosted Gemini/OpenAI-compatible inference and image generation: mocked tests, no paid calls.
- LM Studio: mocked tests, no live service check.
- Claude/Antigravity adapters: mocked argument/restriction checks, not proof of every account/model/version.
- OpenCode worker: discovery only; execution disabled pending verified confinement. Host examples are not all tested in actual host UIs.
- Vision input is image understanding. No image-generation weights or ComfyUI engine are bundled.
- Vertex AI OAuth, other Google APIs, autonomous task decomposition/model routing, signed updates and arbitrary worker shell/file tools are not implemented.
- Binaries are unsigned. Broader accessibility, security, customer-machine and host-app testing remain open work.

API keys use Windows CurrentUser DPAPI. Prompts, source snapshots, output and history are ordinary profile files. Same-user processes are not isolated; MCP lead labels are not authentication. This application is not an operating-system sandbox. See SECURITY.md and README.md.
