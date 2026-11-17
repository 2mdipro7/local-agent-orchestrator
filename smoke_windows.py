"""Check frozen GUI and stdio protocol without contacting providers."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
from unittest.mock import patch

from agenthub import __version__
from agenthub.install import install_to, register_default_hosts
from agenthub.hosts import host_targets, SERVER
from agenthub.connection_check import check_installed_server


def main():
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="orchestrator-smoke-") as temp:
        home = Path(temp) / "data"
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-06-18", "clientInfo": {"name": "ReleaseSmoke"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
                "name": "connection_config", "arguments": {}}},
        ]
        result = subprocess.run([str(root / "dist/LocalAgentOrchestratorMCP.exe"), "--home", str(home)],
                                input="".join(json.dumps(m) + "\n" for m in messages),
                                capture_output=True, text=True, timeout=45, check=True)
        replies = {item["id"]: item for item in map(json.loads, result.stdout.splitlines())}
        assert replies[1]["result"]["serverInfo"] == {"name": "local-agent-orchestrator", "version": __version__}
        assert len(replies[2]["result"]["tools"]) == 9
        config = json.loads(replies[3]["result"]["content"][0]["text"])
        entry = config["mcpServers"]["local-agent-orchestrator"]
        assert Path(entry["command"]).name == "LocalAgentOrchestratorMCP.exe" and entry["args"] == []
        subprocess.run([str(root / "dist/LocalAgentOrchestrator.exe"), "--home", str(home), "--smoke-ms", "1200"],
                       timeout=45, check=True)
        # Use the installer's actual setup functions with a disposable profile.
        # No real host config, registry, sign-in or provider process is touched.
        install = install_to(Path(temp) / 'installed', payload_app=root / 'dist/LocalAgentOrchestrator.exe',
                             payload_worker=root / 'dist/LocalAgentOrchestratorMCP.exe', register=False)
        profile = Path(temp) / 'fresh-user'
        env = {'LOCALAPPDATA': str(profile / 'AppData/Local'), 'APPDATA': str(profile / 'AppData/Roaming')}
        notes = register_default_hosts(install, home=profile, environ=env)
        assert len(notes) == 4 and all(': configured' in note for note in notes), notes
        for target in host_targets(profile, env):
            raw = Path(target['path']).read_text(encoding='utf-8')
            obj = tomllib.loads(raw) if target['format'] == 'toml' else json.loads(raw)
            saved = obj['mcp_servers' if target['format'] == 'toml' else 'mcpServers'][SERVER]
            assert Path(saved['command']) == install / 'LocalAgentOrchestratorMCP.exe'
            if target['format'] == 'toml':
                assert saved['startup_timeout_sec'] == 60
            result = subprocess.run([saved['command'], *saved['args'], '--home', str(home)],
                                    input=json.dumps(messages[0]) + '\n', capture_output=True, text=True,
                                    timeout=45, check=True)
            reply = json.loads(result.stdout)
            assert reply['result']['serverInfo']['version'] == __version__, target['id']
        assert all('already configured' in note for note in register_default_hosts(install, home=profile, environ=env))
        # Exercise the real install-time handshake against the frozen executable,
        # using this disposable profile for the server's own local database.
        with patch.dict(os.environ, env):
            assert check_installed_server(install)['ok']
    print("PASS: frozen GUI/MCP, nine tools, disposable install, four fresh-profile handshakes, Codex timeout and install-time probe; no inference calls or real profile edits.")


if __name__ == "__main__":
    main()
