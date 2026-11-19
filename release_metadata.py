"""Generate trusted PyInstaller Windows version resources for release builds."""
import re

_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z", re.ASCII)


def windows_version(version):
    """Validate SemVer and return its four-part Windows numeric version."""
    match = _VERSION.fullmatch(version) if isinstance(version, str) else None
    if not match:
        raise ValueError(f"Invalid release version: {version!r}")
    if match[4] and any(part.isdigit() and len(part) > 1 and part[0] == '0' for part in match[4].split('.')):
        raise ValueError(f"Invalid release version: {version!r}")
    parts = tuple(int(part) for part in match.group(1, 2, 3))
    if any(part > 65535 for part in parts):
        raise ValueError("Windows version components must be at most 65535")
    return (*parts, 0)


def version_resource(version, *, worker):
    numeric = windows_version(version)
    name = 'LocalAgentOrchestratorMCP' if worker else 'LocalAgentOrchestrator'
    description = 'Local Agent Orchestrator MCP Server' if worker else 'Local Agent Orchestrator'
    fields = {
        'CompanyName': 'Mehrab Mashrafi',
        'FileDescription': description,
        'FileVersion': version,
        'InternalName': name,
        'OriginalFilename': name + '.exe',
        'ProductName': 'Local Agent Orchestrator',
        'ProductVersion': version,
    }
    strings = ',\n'.join(f'          StringStruct({key!r}, {value!r})' for key, value in fields.items())
    return f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={numeric!r}, prodvers={numeric!r}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
{strings}
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
'''
