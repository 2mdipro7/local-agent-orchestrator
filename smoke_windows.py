"""Check frozen GUI and stdio protocol without contacting providers."""
import json
from pathlib import Path
import subprocess
import tempfile

from agenthub import __version__


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
    print("PASS: frozen GUI, MCP identity/version, nine tools and connection export; no inference calls.")


if __name__ == "__main__":
    main()
