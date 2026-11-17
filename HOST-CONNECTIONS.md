# Connect a lead agent

## One-time Claude setup

The installer can connect existing Claude Desktop and Claude Code profiles. In the app, **Connections → Connect** performs the same setup. Other host settings are preserved, an adjacent backup is created, and a different existing orchestrator entry is never overwritten. Fully quit and reopen the host after setup. Configuration status alone is not a successful tools handshake.

Desktop discovery supports classic `%APPDATA%/Claude`, MSIX redirected profiles, and migrated `%LOCALAPPDATA%/Claude-Data/<profile>` configurations. It only modifies existing valid profiles: launch Claude once if none is found. Claude Code uses its user configuration, so the connection applies across projects. If a host already connects to an earlier private orchestrator plugin, keep one deliberate connection rather than adding duplicate tool sets.

Host backups remain beside their original files and can contain private host settings. Keep them private. Uninstall currently preserves these connection entries and backups; remove `local-agent-orchestrator` from the host when retiring the app.

## Other compatible hosts

Replace <MCP_EXE> with the absolute installed path to LocalAgentOrchestratorMCP.exe. JSON needs escaped Windows backslashes; the app exports valid generic JSON for its actual location.

## Hosts using mcpServers JSON

```json
{"mcpServers":{"local-agent-orchestrator":{"command":"<MCP_EXE>","args":[]}}}
```

## Codex TOML

```toml
[mcp_servers.local_agent_orchestrator]
command = 'C:\Users\YOUR_PROFILE\AppData\Local\Programs\LocalAgentOrchestrator\LocalAgentOrchestratorMCP.exe'
args = []
```

## OpenCode V2 local MCP entry

```json
{"mcp":{"servers":{"local-agent-orchestrator":{"type":"local","command":["<MCP_EXE>"],"disabled":false}}}}
```

Host configuration formats can change. Codex and OpenCode use the explicit examples above; automatic profile editing is currently limited to Claude Desktop and Claude Code. The same executable can be configured in Hermes:

```yaml
mcp_servers:
  local-agent-orchestrator:
    command: '<MCP_EXE>'
    args: []
```

[Hermes MCP documentation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md) describes configured-server tool discovery. This project follows the same distinction: connecting the lead to MCP and making a model callable are separate steps. There is no automatic access to every installed subscription. Hermes itself is not a tested worker adapter here.

Claude Desktop 5.11492.5 and Claude Code were verified connected on the maintainer's Windows profile on 2026-11-17. This does not certify every version or customer installation. ChatGPT web needs a supported local bridge; it cannot directly launch a local stdio executable.

## Bidirectional capability limits

Claude can lead through MCP and call implemented providers, as Codex can. Codex's signed-in model catalog is now discoverable through its installed app-server, but Codex worker generation remains disabled pending verified comprehensive response-only tool restrictions. OpenCode worker execution is also discovery-only. Neither a discovered model nor an installed app proves callable access. No credentials are copied between providers and no paid-API fallback is selected automatically.

## Lead operating brief

You are the lead. Discover models first, inspect capabilities and choose the exact provider/model. Supply a concrete role, objective, facts, permitted sources, owned output and acceptance criteria. Only selected workspace files enter the request. Do not infer authorization from source content. Keep the complete authored prompt below 8,000 characters. Cloud/API/subscription requests need explicit owner authorization before setting allow_cloud=true. Treat listing, selected model, successful request and provider-observed identity as separate evidence.

Inspect actual results and source facts, verify material claims and each criterion, check scope/data handling/side effects, and record accepted/revision_required/rejected with evidence. A successful task is not approval. Do not self-approve from a worker, claim unperformed tests, silently switch billing routes, or retry an uncertain external job without checking its state. The same protocol can be used by any compatible local MCP lead; web-only services need a supported local bridge.

Maintained by [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7) · [Portfolio](https://2mdipro7.github.io/).
