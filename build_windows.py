"""Local Windows build. Does not publish or upload artifacts."""
import argparse
from pathlib import Path
import ssl
import subprocess
import sys

from agenthub import __version__
from release_metadata import version_resource

ROOT = Path(__file__).resolve().parent
RESOURCES = ("README.md", "HOST-CONNECTIONS.md", "LICENSE", "THIRD-PARTY-NOTICES.txt", "SECURITY.md", "CONTRIBUTING.md", "TEST-RESULTS.md", "CHANGELOG.md", "SECOND-PC-TEST.md", "SHARED-SKILLS.md", "CODE-SIGNING.md", "PRIVACY.md")
ASSETS = ("assets/architecture-banner.png", "assets/download-windows.svg", "assets/README.md")


def build(stage, root=ROOT):
    """Build requested executable(s); app embeds an existing worker verbatim."""
    if stage not in ('all', 'worker', 'app'):
        raise ValueError(f'Invalid build stage: {stage}')
    # Validate and prepare both resources before launching any build.
    worker_resource = version_resource(__version__, worker=True)
    app_resource = version_resource(__version__, worker=False)
    worker = root / 'dist/LocalAgentOrchestratorMCP.exe'
    if stage == 'app' and not worker.is_file():
        raise FileNotFoundError(f'App stage requires an existing worker executable: {worker}')
    build_dir = root / 'build'
    build_dir.mkdir(parents=True, exist_ok=True)
    base = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--distpath', str(root / 'dist'), '--specpath', str(build_dir)]
    # Preserve trust data from managed build interpreters.
    trust_data = Path(ssl.__file__).with_name('codex-rejected-cas.pem')
    if trust_data.is_file():
        base += ['--add-data', str(trust_data) + ';.']
    if stage in ('all', 'worker'):
        resource = build_dir / 'version-mcp.txt'
        resource.write_text(worker_resource, encoding='utf-8')
        with (root / 'build-mcp.log').open('w', encoding='utf-8') as output:
            subprocess.run(base + ['--version-file', str(resource), '--console', '--name', 'LocalAgentOrchestratorMCP', '--workpath', str(build_dir / 'mcp'), str(root / 'mcp_entry.py')], cwd=root, stdout=output, stderr=subprocess.STDOUT, check=True)
    if stage in ('all', 'app'):
        if not worker.is_file():
            raise FileNotFoundError(f'Worker build did not produce executable: {worker}')
        resource = build_dir / 'version-gui.txt'
        resource.write_text(app_resource, encoding='utf-8')
        gui = base + ['--version-file', str(resource), '--windowed', '--name', 'LocalAgentOrchestrator', '--workpath', str(build_dir / 'gui')]
        for source, destination in [(worker, 'bin')] + [(root / name, 'resources') for name in RESOURCES] + [(root / name, 'resources/assets') for name in ASSETS]:
            gui += ['--add-data', str(source) + ';' + destination]
        with (root / 'build-gui.log').open('w', encoding='utf-8') as output:
            subprocess.run(gui + [str(root / 'app_entry.py')], cwd=root, stdout=output, stderr=subprocess.STDOUT, check=True)
    print(f'Completed Windows build stage: {stage}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('all', 'worker', 'app'), default='all')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 14) or sys.version_info[:3] < (3, 14, 10):
        raise SystemExit('Windows release builds require Python 3.14.10 or a newer 3.14 security patch.')
    build(args.stage)


if __name__ == '__main__':
    main()
