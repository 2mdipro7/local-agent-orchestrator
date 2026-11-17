"""Explicit, per-profile MCP registration; preserve other host settings."""
import json
import os
from pathlib import Path
import tempfile
import uuid

SERVER = 'local-agent-orchestrator'


def desktop_configs(home=None, environ=None):
    """Find classic, MSIX-redirected and migrated Claude Desktop profiles."""
    home = Path(home or Path.home())
    env = os.environ if environ is None else environ
    local = Path(env.get('LOCALAPPDATA', home / 'AppData/Local'))
    roaming = Path(env.get('APPDATA', home / 'AppData/Roaming'))
    migrated = list((local / 'Claude-Data').glob('*/claude_desktop_config.json'))
    redirected = list((local / 'Packages').glob('Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json'))
    classic = roaming / 'Claude/claude_desktop_config.json'
    paths = sorted(migrated) + sorted(redirected) + ([classic] if classic.is_file() else [])
    # Empty migration markers are not profiles. Never create a stale path merely
    # because its old directory survived an application migration.
    return list(dict.fromkeys(p for p in paths if p.is_file()))


def host_targets(home=None, environ=None):
    home = Path(home or Path.home())
    result = [{'id': 'claude-desktop-' + str(i), 'name': 'Claude Desktop (' + str(p.parent) + ')', 'path': str(p)}
              for i, p in enumerate(desktop_configs(home, environ))]
    cli = home / '.claude.json'
    if cli.is_file():
        result.append({'id': 'claude-code', 'name': 'Claude Code (all projects)', 'path': str(cli)})
    return result


def _read(path):
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Linked host configuration paths are not supported')
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Host configuration exceeds size limit')
    raw = path.read_bytes()
    try:
        def unique(items):
            out = {}
            for key, value in items:
                if key in out:
                    raise ValueError('Duplicate configuration key')
                out[key] = value
            return out
        obj = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique)
    except (ValueError, UnicodeError):
        raise ValueError('Host configuration is invalid; no changes made') from None
    if not isinstance(obj, dict) or not isinstance(obj.get('mcpServers', {}), dict):
        raise ValueError('Host MCP configuration must be a JSON object')
    return raw, obj


def connection_status(path, entry):
    try:
        _, obj = _read(path)
        servers = obj.get('mcpServers', {})
        if SERVER not in servers:
            return 'Not connected'
        if servers[SERVER] == entry:
            return 'Configured (restart host to load)'
        return 'Different entry exists; left unchanged'
    except (OSError, ValueError):
        return 'Configuration unreadable or invalid; left unchanged'


def register_host(path, entry):
    """Merge one owned entry with backup and atomic replace. Never overwrite conflicts."""
    path = Path(path).absolute()
    if not isinstance(entry, dict) or not isinstance(entry.get('command'), str):
        raise ValueError('Invalid MCP command')
    command = Path(entry['command'])
    if not command.is_absolute() or not command.is_file():
        raise ValueError('MCP executable is missing; install the application first')
    raw, obj = _read(path)
    servers = obj.setdefault('mcpServers', {})
    if SERVER in servers:
        if servers[SERVER] == entry:
            return {'changed': False, 'restart_required': True, 'path': str(path)}
        raise ValueError('A different orchestrator entry exists; it was left unchanged')
    servers[SERVER] = entry
    encoded = (json.dumps(obj, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.lao-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        # A second read prevents overwriting edits observed during preparation.
        # Hosts should be restarted afterwards; this is not a lock on their writers.
        if _read(path)[0] != raw:
            raise ValueError('Host settings changed during setup; retry after closing the host')
        backup = path.with_name(path.name + '.lao-backup-' + uuid.uuid4().hex)
        with backup.open('xb') as stream:
            stream.write(raw)
        os.replace(temporary, path)
        return {'changed': True, 'restart_required': True, 'path': str(path), 'backup': str(backup)}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def host_statuses(entry):
    return [{**target, 'status': connection_status(target['path'], entry)} for target in host_targets()]
