import argparse
import sys
from agenthub import __version__
from agenthub.core import Hub
from agenthub.mcp import serve

if __name__ == "__main__":
    # MCP transport is UTF-8, independent of the Windows console code page.
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8', newline='\n')
    parser = argparse.ArgumentParser(description="Local Agent Orchestrator MCP worker coordinator")
    parser.add_argument("--home", help="Explicit per-user data directory override")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--diagnose-local", action="store_true", help="Diagnose only the fixed loopback Ollama endpoint; no secrets or cloud calls")
    args = parser.parse_args()
    hub = Hub(args.home)
    if args.diagnose_local:
        import json
        from agenthub.providers import ProviderError
        try:
            print(json.dumps({'local_probe': hub.providers._http('GET', 'http://127.0.0.1:11434/api/version', timeout=5)}))
        except ProviderError as exc:
            print(json.dumps({'error': str(exc)}))
    elif args.status:
        import json
        print(json.dumps({"version": __version__, "data_location": str(hub.home), "hardware": hub.hardware_info()}))
    else:
        # Decode each bounded frame separately so malformed UTF-8 cannot poison
        # the text stream or prevent the next valid request from being handled.
        serve(hub, source=sys.stdin.buffer)
