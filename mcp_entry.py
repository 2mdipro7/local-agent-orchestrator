import argparse
from agenthub import __version__
from agenthub.core import Hub
from agenthub.mcp import serve

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local Agent Orchestrator MCP worker coordinator")
    parser.add_argument("--home", help="Explicit per-user data directory override")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--diagnose-local", action="store_true", help="Diagnose only the fixed loopback Ollama endpoint; no secrets or cloud calls")
    args = parser.parse_args()
    hub = Hub(args.home)
    if args.diagnose_local:
        import json, traceback
        from urllib import request
        try:
            with request.urlopen('http://127.0.0.1:11434/api/version', timeout=5) as response:
                print(json.dumps({'local_probe': json.load(response)}))
        except Exception:
            traceback.print_exc()
    elif args.status:
        import json
        print(json.dumps({"version": __version__, "data_location": str(hub.home), "hardware": hub.hardware_info()}))
    else:
        serve(hub)
