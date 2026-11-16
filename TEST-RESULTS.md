# Version 0 validation

[Local Agent Orchestrator](https://github.com/2mdipro7/local-agent-orchestrator) · Created by [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7) · [Portfolio](https://2mdipro7.github.io/portfolio/).

Date: 16 November 2026 (Asia/Dhaka). Version: 0.0.0.

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
