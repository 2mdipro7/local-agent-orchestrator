# Code signing policy

Local Agent Orchestrator is maintained by [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7).

## Current status

SignPath Foundation application materials are prepared. The project has **not yet been approved**, and no SignPath signing request has been completed. The published v0.3.2 files remain unsigned. A GitHub build result or SHA-256 checksum is not a Windows publisher signature.

We intend to use free code signing provided by [SignPath.io](https://signpath.io), with a certificate supplied by [SignPath Foundation](https://signpath.org), subject to acceptance. The certificate would identify SignPath Foundation; the application's maintainer remains Mehrab Mashrafi. This statement does not imply sponsorship or approval.

## Responsibilities

| Role | Responsible person |
|---|---|
| Author and maintainer | [Mehrab Mashrafi](https://github.com/2mdipro7) |
| Reviewer of outside contributions | [Mehrab Mashrafi](https://github.com/2mdipro7) |
| Release signing approver | [Mehrab Mashrafi](https://github.com/2mdipro7) |

This is currently a solo-maintainer project. Automated and AI-assisted checks support review; they do not count as independent human approval. Contributors without direct write access submit pull requests for maintainer review. Repository and SignPath users with signing responsibilities must use MFA. The maintainer must confirm account enrollment during onboarding; it is not certified by this document.

Every production signing request requires the maintainer's manual approval in SignPath after checking its source commit, successful tests, requested product/version and artifact contents. The submitting automation must not have approval authority. Two requests are needed for a release: the worker, followed by the application that embeds it.

## What may be signed

Only these project executables, built from reviewed source in this public repository on GitHub-hosted runners:

- `LocalAgentOrchestratorMCP.exe`: the stdio MCP server.
- `LocalAgentOrchestrator.exe`: the application and per-user installer. The downloadable `LocalAgentOrchestrator-v<version>-Setup.exe` is a byte-identical copy.

Both must identify the product as `Local Agent Orchestrator` and use the same version from `agenthub/__init__.py`. Separate, exact-file SignPath artifact configurations restrict filename, company, product and version. We do not request signatures on upstream Python, Tcl/Tk, OpenSSL or other third-party binaries under this project's signing policy. These retain their own licenses and any original signatures. External AI clients and model weights are not bundled.

The worker is signed and verified before it is embedded into the application. The application is then signed and verified. Checks compare the embedded worker and portable-package executables with the verified files; checksums are generated last. Signature failure stops the signing workflow with no unsigned fallback. The workflow only produces artifacts for review; it does not publish a release automatically.

An unsigned preparation run can exercise packaging before onboarding. Its artifact names explicitly identify it as unsigned. Production signing remains blocked until the account, Foundation certificate, manually approved policy, repository connection and expected certificate identity are configured. The service-side configuration must enforce GitHub origin verification and restrict this repository and approved release source; configuration files in Git alone do not enforce those controls.

## Privacy and security

See [Privacy policy](PRIVACY.md) for selected-content transmission, provider connections, stored data, installer changes and removal. See [SECURITY.md](SECURITY.md) for reporting and protection limits. Signing authenticates a publisher and detects modification; it does not certify model output, third-party skills or absence of vulnerabilities. SmartScreen reputation is a separate Windows decision.

Maintainer setup and application text: [SignPath application](docs/SIGNPATH-APPLICATION.md).
