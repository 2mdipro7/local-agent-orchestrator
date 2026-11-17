# Validation history

[Local Agent Orchestrator](https://github.com/2mdipro7/local-agent-orchestrator) · Created by [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7) · [Portfolio](https://2mdipro7.github.io/).

Date: 16 November 2026 (Asia/Dhaka). Version: 0.0.0.

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
