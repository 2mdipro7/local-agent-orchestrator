"""Record bundled onefile entries and hashes for signing review, not license certification."""
import hashlib
import json
from pathlib import Path
from PyInstaller.archive.readers import CArchiveReader
from agenthub import __version__


def inventory(path):
    reader = CArchiveReader(str(path))
    entries = []
    for name, entry in reader.toc.items():
        data = reader.extract(name)
        entries.append({'path': name.replace('\\', '/'), 'type': entry[-1],
                        'bytes': len(data) if data is not None else 0,
                        'sha256': hashlib.sha256(data).hexdigest() if data is not None else None})
    return {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'entries': entries}


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    output = root / 'signing-evidence'
    output.mkdir(exist_ok=True)
    value = {'version': __version__, 'scope': 'PyInstaller CArchive entries; PYZ/base_library archives are opaque entries, not a full SBOM',
             'license_map': 'signing/COMPONENTS.md', 'artifacts': [inventory(root / 'dist' / name) for name in
             ('LocalAgentOrchestratorMCP.exe', 'LocalAgentOrchestrator.exe')]}
    (output / 'bundled-inventory.json').write_text(json.dumps(value, indent=2), encoding='utf-8')
    print('Wrote signing-evidence/bundled-inventory.json')
