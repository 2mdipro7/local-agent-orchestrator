# Privacy policy

Local Agent Orchestrator is an open-source Windows application maintained by [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7). This policy describes the application, not the privacy practices of independently installed AI services or GitHub.

## Information on your PC

Settings, task instructions, selected source and skill snapshots, responses, artifacts, usage information and review history are stored in your Windows profile under `%LOCALAPPDATA%\LocalAgentOrchestrator\data`. API credentials saved through the application use Windows CurrentUser DPAPI encryption. Task content and history are ordinary local files; another process with access to your Windows account may read them. Host registration can create backups of existing host settings beside their original files.

## Connections and selected content

The application has no advertising, analytics or maintainer telemetry endpoint. It does not automatically send task content to the maintainer or SignPath. Its stdio MCP server does not open a public listener.

Model discovery and connection tests contact enabled, configured provider endpoints or invoke installed provider clients. These services can receive connection metadata. A model test sends a small test prompt. A task sends its instructions and the source files, images and skill text explicitly selected for that task to the chosen provider. Cloud, subscription and API task execution requires authorization; a connected lead conveys that authorization. Check selected content before authorizing it.

Supported external providers include OpenAI/Codex, Anthropic/Claude, Google/Gemini/Antigravity, OpenCode and user-configured OpenAI-compatible services. Local endpoints include Ollama and LM Studio; an endpoint or client you configure may itself use remote services. Provider accounts, clients and endpoints have their own privacy, retention and billing terms. Consult the terms attached to the account and endpoint you actually use. This application cannot enforce provider-side deletion or stop a remote request already issued.

Third-party skills can contain untrusted instructions. Selecting a skill sends its selected text as part of the task; it does not grant additional worker tools. The application does not certify a skill's content.

## Installation and removal

Setup writes application files in your per-user Programs directory, creates a Start-menu shortcut and a Windows uninstall entry. The checked host-connection option adds an MCP entry to supported Claude, Codex and Antigravity configuration files while preserving other settings. You can clear that option before installation. It does not install the external AI clients, model weights, a public service or a startup task.

Windows Installed apps removes the application. Saved jobs, credentials, host entries and configuration backups are retained. When retiring the app, remove its MCP entries from each host and delete its data directory and unneeded configuration backups after checking what you want to keep. Data previously sent to a provider remains governed by that provider's policies.

## Project services

GitHub hosts source, issues, downloads and build logs under GitHub's own privacy terms. Planned SignPath signing sends public build artifacts and build-origin metadata to SignPath; it does not require users' prompts, credentials or profile files. Maintainer onboarding separately requires contact information and consent through SignPath's application form. Do not post private task content or credentials in public issues. Use the private reporting route in [SECURITY.md](SECURITY.md).
