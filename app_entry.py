import argparse
from pathlib import Path
import sys
from agenthub.core import Hub

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local Agent Orchestrator open-source preview")
    parser.add_argument("--home")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--smoke-ms", type=int)
    args = parser.parse_args()
    if args.uninstall:
        from agenthub.install import uninstall
        uninstall()
    elif args.install or "setup" in Path(sys.executable).stem.lower():
        from agenthub.install import installer_ui
        installer_ui()
    else:
        from agenthub.gui import run_gui
        hub = Hub(args.home)
        worker = str(Path(sys.executable).with_name("LocalAgentOrchestratorMCP.exe")) if getattr(sys, "frozen", False) else sys.executable
        run_gui(hub, mcp_executable=worker, auto_close_ms=args.smoke_ms)
