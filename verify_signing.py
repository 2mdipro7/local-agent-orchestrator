"""Fail-closed release checks. Does not sign, install, or publish files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile

from agenthub import __version__

ROOT = Path(__file__).resolve().parent
APP = 'LocalAgentOrchestrator.exe'
WORKER = 'LocalAgentOrchestratorMCP.exe'


def inspect_windows_file(path):
    """Use Windows Authenticode validation; never interpolate paths into code."""
    if os.name != 'nt':
        raise RuntimeError('Authenticode verification requires Windows')
    script = r'''
$ErrorActionPreference = 'Stop'
$item = Get-Item -LiteralPath $env:LAO_VERIFY_FILE
$sig = Get-AuthenticodeSignature -LiteralPath $item.FullName
$v = $item.VersionInfo
[pscustomobject]@{
  status = [string]$sig.Status
  signature_type = [string]$sig.SignatureType
  subject = $(if ($sig.SignerCertificate) { $sig.SignerCertificate.Subject } else { '' })
  thumbprint = $(if ($sig.SignerCertificate) { $sig.SignerCertificate.Thumbprint } else { '' })
  timestamp_subject = $(if ($sig.TimeStamperCertificate) { $sig.TimeStamperCertificate.Subject } else { '' })
  product = $v.ProductName
  product_version = $v.ProductVersion
  file_version = $v.FileVersion
  company = $v.CompanyName
  original_filename = $v.OriginalFilename
} | ConvertTo-Json -Compress
'''
    env = os.environ.copy()
    env['LAO_VERIFY_FILE'] = str(path.resolve(strict=True))
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    # A Python child can inherit PowerShell 7's module path; load only this
    # Windows PowerShell installation's built-in verification modules.
    env['PSModulePath'] = str(powershell.parent / 'Modules')
    result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-Command', script],
                            env=env, capture_output=True, text=True, check=True, timeout=60)
    return json.loads(result.stdout)


def validate_inspection(info, filename, version, *, require_signed, expected_subject):
    expected = {'product': 'Local Agent Orchestrator', 'product_version': version,
                'file_version': version, 'company': 'Mehrab Mashrafi', 'original_filename': filename}
    for key, value in expected.items():
        if info.get(key) != value:
            raise ValueError(f'{filename}: incorrect {key}')
    if require_signed:
        if not expected_subject or not expected_subject.strip():
            raise ValueError('Production signing requires the approved certificate subject')
        if info.get('status') != 'Valid' or info.get('signature_type') != 'Authenticode':
            raise ValueError(f'{filename}: trusted embedded Authenticode signature required')
        if info.get('subject') != expected_subject:
            raise ValueError(f'{filename}: unexpected signing identity')
        if not info.get('timestamp_subject'):
            raise ValueError(f'{filename}: timestamp required')
    elif info.get('status') != 'NotSigned':
        raise ValueError(f'{filename}: unsigned preparation expects an unsigned file')


def verify_file(path, *, filename=None, version=__version__, require_signed=True, expected_subject=''):
    info = inspect_windows_file(path)
    validate_inspection(info, filename or path.name, version,
                        require_signed=require_signed, expected_subject=expected_subject)
    return {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), **info}


def verify_embedded_worker(app, worker):
    from PyInstaller.archive.readers import CArchiveReader
    reader = CArchiveReader(str(app))
    names = [name for name in reader.toc if name.replace('\\', '/') == 'bin/' + WORKER]
    if len(names) != 1 or reader.extract(names[0]) != worker.read_bytes():
        raise ValueError('Embedded worker does not match the verified worker bytes')


def verify_package(output, app, worker, version=__version__):
    prefix = 'LocalAgentOrchestrator-v' + version
    setup, portable = output / (prefix + '-Setup.exe'), output / (prefix + '-Portable.zip')
    if setup.read_bytes() != app.read_bytes():
        raise ValueError('Setup executable differs from verified application')
    with zipfile.ZipFile(portable) as archive:
        if archive.testzip() is not None:
            raise ValueError('Corrupt portable archive')
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate portable archive entries')
        for file in (app, worker):
            if archive.read('LocalAgentOrchestrator/' + file.name) != file.read_bytes():
                raise ValueError('Portable executable differs from verified file')
    expected = ''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
                       for p in (setup, portable))
    if (output / 'SHA256SUMS.txt').read_text(encoding='utf-8') != expected:
        raise ValueError('Checksums do not match final release files')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=('worker', 'app', 'package'), required=True)
    parser.add_argument('--file', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'release')
    parser.add_argument('--unsigned-preparation', action='store_true')
    args = parser.parse_args()
    options = {'require_signed': not args.unsigned_preparation,
               'expected_subject': os.environ.get('SIGNPATH_EXPECTED_SUBJECT', '')}
    app, worker = ROOT / 'dist' / APP, ROOT / 'dist' / WORKER
    if args.stage in ('worker', 'app'):
        filename = WORKER if args.stage == 'worker' else APP
        report = [verify_file(args.file or ROOT / 'dist' / filename, filename=filename, **options)]
    else:
        report = [verify_file(file, **options) for file in (app, worker)]
        verify_embedded_worker(app, worker)
        verify_package(args.output, app, worker)
        report.append({'nested_worker_matches': True, 'package_matches': True})
    print(json.dumps({'mode': 'unsigned-preparation' if args.unsigned_preparation else 'signed',
                      'version': __version__, 'checks': report}, indent=2))


if __name__ == '__main__':
    main()
