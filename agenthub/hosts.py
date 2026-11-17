"""Explicit, per-profile MCP registration; preserve other host settings."""
import json
import os
from pathlib import Path
import tempfile
import tomllib
import uuid

SERVER = 'local-agent-orchestrator'


def desktop_configs(home=None, environ=None):
    """Choose actual desktop profiles, avoiding empty migration remnants."""
    home = Path(home or Path.home())
    env = os.environ if environ is None else environ
    local = Path(env.get('LOCALAPPDATA', home / 'AppData/Local'))
    roaming = Path(env.get('APPDATA', home / 'AppData/Roaming'))
    classic = roaming / 'Claude/claude_desktop_config.json'
    dirs = sorted((local / 'Claude-Data').glob('*')) + sorted((local / 'Packages').glob('Claude_*/LocalCache/Roaming/Claude'))
    def active(directory):
        return directory.is_dir() and any((directory / marker).exists() for marker in
            ('claude_desktop_config.json', 'Preferences', 'Local State', 'Session Storage'))
    paths = [d / 'claude_desktop_config.json' for d in dirs if active(d)]
    if classic.is_file() or (not paths):
        paths.append(classic)
    return list(dict.fromkeys(paths))


def host_targets(home=None, environ=None):
    home = Path(home or Path.home())
    env = os.environ if environ is None else environ
    result = [{'id': 'claude-desktop-' + str(i), 'name': 'Claude Desktop (' + str(p.parent) + ')', 'path': str(p), 'format': 'json'}
              for i, p in enumerate(desktop_configs(home, env))]
    codex_home = Path(env['CODEX_HOME']) if env.get('CODEX_HOME') else home / '.codex'
    result.extend([
        {'id': 'claude-code', 'name': 'Claude Code (all projects)', 'path': str(home / '.claude.json'), 'format': 'json'},
        {'id': 'codex', 'name': 'Codex (global)', 'path': str(codex_home / 'config.toml'), 'format': 'toml'},
        {'id': 'antigravity', 'name': 'Google Antigravity (all projects)', 'path': str(home / '.gemini/config/mcp_config.json'), 'format': 'json'},
    ])
    return result


def _check_path(path):
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, 'is_junction') and part.is_junction()):
            raise ValueError('Linked host configuration paths are not supported')


def _read(path, format=None):
    path = Path(path).absolute()
    format = _format(path, format)
    _check_path(path)
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Host configuration exceeds size limit')
    raw = path.read_bytes()
    try:
        if format == 'toml':
            obj = tomllib.loads(raw.decode('utf-8'))
            key = 'mcp_servers'
        else:
            def unique(items):
                out = {}
                for key, value in items:
                    if key in out:
                        raise ValueError('Duplicate configuration key')
                    out[key] = value
                return out
            empty_antigravity = path.name == 'mcp_config.json' and path.parent.name == 'config' and path.parent.parent.name == '.gemini'
            obj = {} if not raw.strip() and empty_antigravity else json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique)
            key = 'mcpServers'
    except (ValueError, UnicodeError):
        raise ValueError('Host configuration is invalid; no changes made') from None
    if not isinstance(obj, dict) or not isinstance(obj.get(key, {}), dict):
        raise ValueError('Host MCP configuration must be an object')
    return raw, obj


def _format(path, format):
    format = format or ('toml' if Path(path).suffix.lower() == '.toml' else 'json')
    if format not in ('json', 'toml'):
        raise ValueError('Unsupported host configuration format')
    return format


def connection_status(path, entry, format=None):
    format = _format(path, format)
    try:
        _, obj = _read(path, format)
        servers = obj.get('mcp_servers' if format == 'toml' else 'mcpServers', {})
        if SERVER not in servers:
            return 'Not connected'
        if servers[SERVER] == entry:
            return 'Configured (restart host to load)'
        return 'Different entry exists; left unchanged'
    except FileNotFoundError:
        try:
            _check_path(Path(path).absolute())
            return 'Not connected'
        except ValueError:
            return 'Configuration unreadable or invalid; left unchanged'
    except (OSError, ValueError):
        return 'Configuration unreadable or invalid; left unchanged'


def register_host(path, entry, format=None):
    """Merge an owned entry; preserve existing files and refuse conflicts."""
    path = Path(path).absolute()
    format = _format(path, format)
    if not isinstance(entry, dict) or not isinstance(entry.get('command'), str) or not isinstance(entry.get('args', []), list) or not all(isinstance(a, str) for a in entry.get('args', [])):
        raise ValueError('Invalid MCP command')
    if format == 'toml' and set(entry) - {'command', 'args'}:
        raise ValueError('Unsupported Codex MCP entry fields')
    command = Path(entry['command'])
    if not command.is_absolute() or not command.is_file():
        raise ValueError('MCP executable is missing; install the application first')
    _check_path(path)
    try:
        raw, obj = _read(path, format)
        existed = True
    except FileNotFoundError:
        raw, obj, existed = b'', {}, False
    key = 'mcp_servers' if format == 'toml' else 'mcpServers'
    servers = obj.get(key, {})
    if SERVER in servers:
        if servers[SERVER] == entry:
            return {'changed': False, 'restart_required': True, 'path': str(path)}
        raise ValueError('A different orchestrator entry exists; it was left unchanged')
    if format == 'toml':
        # Appending a table preserves every original byte and is validated before writing.
        separator = b'' if not raw else (b'\n' if raw.endswith(b'\n') else b'\n\n')
        section = '[mcp_servers."' + SERVER + '"]\ncommand = ' + json.dumps(entry['command'], ensure_ascii=False) + '\n'
        if 'args' in entry:
            section += 'args = ' + json.dumps(entry['args'], ensure_ascii=False) + '\n'
        encoded = raw + separator + section.encode('utf-8')
        try:
            parsed = tomllib.loads(encoded.decode('utf-8'))
            if parsed[key][SERVER] != entry:
                raise ValueError()
        except (ValueError, UnicodeError, KeyError, TypeError):
            raise ValueError('Cannot safely add the Codex entry to this configuration') from None
    else:
        obj.setdefault(key, {})[SERVER] = entry
        encoded = (json.dumps(obj, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    path.parent.mkdir(parents=True, exist_ok=True)
    _check_path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.lao-', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        _check_path(path)
        if not existed:
            # Hard-link creation is atomic and fails if another writer created the target.
            try:
                os.link(temporary, path)
            except FileExistsError:
                raise ValueError('Host settings appeared during setup; retry') from None
            return {'changed': True, 'restart_required': True, 'path': str(path)}
        if _read(path, format)[0] != raw:
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
    return [{**target, 'status': connection_status(target['path'], entry, target['format'])} for target in host_targets()]
