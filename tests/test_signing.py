import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import zipfile

import check_signing_source
from verify_signing import APP, WORKER, validate_inspection, verify_embedded_worker, verify_package


class SigningVerificationTests(unittest.TestCase):
    def test_trust_identity_timestamp_and_metadata_fail_closed(self):
        # Synthetic certificate metadata only; does not claim actual signing.
        valid = {'status': 'Valid', 'signature_type': 'Authenticode', 'subject': 'CN=Synthetic approved publisher',
                 'timestamp_subject': 'CN=Synthetic timestamp', 'product': 'Local Agent Orchestrator',
                 'product_version': '1.2.3', 'file_version': '1.2.3', 'company': 'Mehrab Mashrafi',
                 'original_filename': APP}
        options = {'require_signed': True, 'expected_subject': valid['subject']}
        validate_inspection(valid, APP, '1.2.3', **options)
        for key, value in [('status', 'NotSigned'), ('status', 'HashMismatch'), ('status', 'UnknownError'),
                           ('signature_type', 'Catalog'), ('subject', 'CN=Wrong publisher'),
                           ('timestamp_subject', ''), ('product', 'Different application'),
                           ('file_version', '0.0.0'), ('product_version', '0.0.0'),
                           ('company', 'Other company'), ('original_filename', 'other.exe')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_inspection({**valid, key: value}, APP, '1.2.3', **options)
        with self.assertRaises(ValueError):
            validate_inspection(valid, APP, '1.2.3', require_signed=True, expected_subject='')
        validate_inspection({**valid, 'status': 'NotSigned'}, APP, '1.2.3', require_signed=False, expected_subject='')
        with self.assertRaises(ValueError):
            validate_inspection(valid, APP, '1.2.3', require_signed=False, expected_subject='')

    def test_embedded_worker_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = Path(temp) / WORKER
            worker.write_bytes(b'verified worker bytes')
            with patch('PyInstaller.archive.readers.CArchiveReader') as reader:
                reader.return_value.toc = {'bin\\' + WORKER: ()}
                reader.return_value.extract.return_value = worker.read_bytes()
                verify_embedded_worker(Path(temp) / APP, worker)
                worker.write_bytes(b'verified worker byteX')
                with self.assertRaises(ValueError):
                    verify_embedded_worker(Path(temp) / APP, worker)
                reader.return_value.toc = {}
                with self.assertRaises(ValueError):
                    verify_embedded_worker(Path(temp) / APP, worker)

    def test_package_executable_and_checksum_tamper_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            app, worker = root / APP, root / WORKER
            app.write_bytes(b'approved signed app fixture')
            worker.write_bytes(b'approved signed worker fixture')
            setup = root / 'LocalAgentOrchestrator-v1.2.3-Setup.exe'
            portable = root / 'LocalAgentOrchestrator-v1.2.3-Portable.zip'
            setup.write_bytes(app.read_bytes())
            def package(worker_bytes):
                with zipfile.ZipFile(portable, 'w') as archive:
                    archive.writestr('LocalAgentOrchestrator/' + APP, app.read_bytes())
                    archive.writestr('LocalAgentOrchestrator/' + WORKER, worker_bytes)
                (root / 'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in (setup, portable)), encoding='utf-8')
            package(worker.read_bytes())
            verify_package(root, app, worker, '1.2.3')
            setup.write_bytes(b'tampered setup')
            with self.assertRaises(ValueError):
                verify_package(root, app, worker, '1.2.3')
            setup.write_bytes(app.read_bytes())
            package(b'tampered worker')
            with self.assertRaises(ValueError):
                verify_package(root, app, worker, '1.2.3')
            package(worker.read_bytes())
            (root / 'SHA256SUMS.txt').write_text('incorrect hashes', encoding='utf-8')
            with self.assertRaises(ValueError):
                verify_package(root, app, worker, '1.2.3')


class SigningSourceTests(unittest.TestCase):
    def test_every_missing_prerequisite_blocks_signing(self):
        values = {'SIGNPATH_ENABLED': 'true', 'SIGNPATH_ORGANIZATION_ID': 'synthetic-organization',
                  'SIGNPATH_API_TOKEN': 'synthetic-not-a-token', 'SIGNPATH_EXPECTED_SUBJECT': 'CN=Synthetic'}
        check_signing_source.check_configuration(values)
        for key in values:
            for missing in ('', ' ', None):
                candidate = dict(values)
                if missing is None:
                    del candidate[key]
                else:
                    candidate[key] = missing
                with self.subTest(key=key, missing=missing), self.assertRaises(ValueError):
                    check_signing_source.check_configuration(candidate)

    def test_ref_tag_and_previously_published_version_gates(self):
        env = {'GITHUB_REPOSITORY': check_signing_source.REPOSITORY, 'GITHUB_REF': 'refs/heads/main'}
        with patch.dict(os.environ, env), patch('check_signing_source.subprocess.check_output', side_effect=['abc\n', 'abc\n']), patch('check_signing_source.request.urlopen', side_effect=HTTPError('https://example.invalid', 404, 'Not Found', {}, io.BytesIO())):
            check_signing_source.check_source('1.2.3')
        with patch.dict(os.environ, env), patch('check_signing_source.subprocess.check_output', side_effect=['abc', 'different']), patch('check_signing_source.request.urlopen') as network:
            with self.assertRaises(ValueError):
                check_signing_source.check_source('1.2.3')
            network.assert_not_called()
        for field, value in [('GITHUB_REPOSITORY', 'someone/fork'), ('GITHUB_REF', 'refs/pull/1/merge')]:
            with patch.dict(os.environ, {**env, field: value}), patch('check_signing_source.subprocess.check_output') as git:
                with self.assertRaises(ValueError):
                    check_signing_source.check_source('1.2.3')
                git.assert_not_called()
        for code in (200, 403, 500):
            with patch.dict(os.environ, env), patch('check_signing_source.subprocess.check_output', side_effect=['abc', 'abc']), patch('check_signing_source.request.urlopen') as response:
                if code != 200:
                    response.side_effect = HTTPError('https://example.invalid', code, 'Error', {}, io.BytesIO())
                with self.assertRaises((ValueError, RuntimeError)):
                    check_signing_source.check_source('1.2.3')


if __name__ == '__main__':
    unittest.main()
