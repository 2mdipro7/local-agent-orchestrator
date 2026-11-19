"""Require a new, tagged main-branch build before production signing."""
import json
import os
import subprocess
from urllib import error, request

from agenthub import __version__
from release_metadata import windows_version

REPOSITORY = '2mdipro7/local-agent-orchestrator'


def check_configuration(environ=None):
    env = os.environ if environ is None else environ
    if env.get('SIGNPATH_ENABLED') != 'true':
        raise ValueError('Foundation onboarding is not enabled')
    for key in ('SIGNPATH_ORGANIZATION_ID', 'SIGNPATH_API_TOKEN', 'SIGNPATH_EXPECTED_SUBJECT'):
        if not env.get(key, '').strip():
            raise ValueError('Missing ' + key)


def check_source(version=__version__):
    windows_version(version)
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise ValueError('Production signing runs only from the canonical main branch')
    tag = 'v' + version
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    tagged = subprocess.check_output(['git', 'rev-parse', '--verify', 'refs/tags/' + tag + '^{commit}'], text=True).strip()
    if head != tagged:
        raise ValueError('Version tag must identify this exact reviewed commit')
    url = 'https://api.github.com/repos/' + REPOSITORY + '/releases/tags/' + tag
    req = request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'LocalAgentOrchestrator-release-check'})
    try:
        with request.urlopen(req, timeout=20):
            raise ValueError('This version already has a published release; use a new version')
    except error.HTTPError as exc:
        code = exc.code
        exc.close()
        if code != 404:
            raise RuntimeError('Could not establish that this release version is unused') from None
    print(json.dumps({'source_commit': head, 'version_tag': tag, 'published_release_absent': True}))


if __name__ == '__main__':
    check_configuration()
    check_source()
