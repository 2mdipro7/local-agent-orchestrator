"""Local Windows build. Does not publish or upload artifacts."""
from pathlib import Path
import subprocess
import sys
import ssl

root = Path(__file__).resolve().parent
base = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--distpath", str(root / "dist"), "--specpath", str(root / "build")]
# This bundled build interpreter carries an additional TLS trust-data file.
# Preserve its policy instead of disabling certificate verification or removing
# the interpreter's security changes when freezing the standard library.
trust_data = Path(ssl.__file__).with_name("codex-rejected-cas.pem")
if trust_data.is_file():
    base += ["--add-data", str(trust_data) + ";."]
with (root / "build-mcp.log").open("w", encoding="utf-8") as output:
    subprocess.run(base + ["--console", "--name", "LocalAgentOrchestratorMCP", "--workpath", str(root / "build/mcp"), str(root / "mcp_entry.py")], cwd=root, stdout=output, stderr=subprocess.STDOUT, check=True)
gui = base + ["--windowed", "--name", "LocalAgentOrchestrator", "--workpath", str(root / "build/gui")]
for source, destination in [(root / "dist/LocalAgentOrchestratorMCP.exe", "bin")] + [(root / name, "resources") for name in ("README.md", "HOST-CONNECTIONS.md", "LICENSE", "THIRD-PARTY-NOTICES.txt", "SECURITY.md", "CONTRIBUTING.md", "TEST-RESULTS.md", "CHANGELOG.md", "SECOND-PC-TEST.md")] + [(root / name, "resources/assets") for name in ("assets/architecture-banner.png", "assets/download-windows.svg", "assets/README.md")]:
    gui += ["--add-data", str(source) + ";" + destination]
with (root / "build-gui.log").open("w", encoding="utf-8") as output:
    subprocess.run(gui + [str(root / "app_entry.py")], cwd=root, stdout=output, stderr=subprocess.STDOUT, check=True)
print("Built LocalAgentOrchestrator.exe and LocalAgentOrchestratorMCP.exe")
