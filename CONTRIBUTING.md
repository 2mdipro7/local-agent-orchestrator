# Contributing

Created and maintained by [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7) · [Portfolio](https://2mdipro7.github.io/).

Use Python 3.14.10 or a newer 3.14 security patch on Windows x64, with Tcl/Tk from the standard Windows Python installer. The app uses Python's standard library; provider tools are separate installations.

```powershell
git clone https://github.com/2mdipro7/local-agent-orchestrator.git
cd local-agent-orchestrator
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe app_entry.py
```

Run checks and build the Windows package:

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe build_windows.py
.\.venv\Scripts\python.exe smoke_windows.py
.\.venv\Scripts\python.exe package_release.py
```

Release metadata tests use the pinned PyInstaller build tools. For SignPath preparation, see [the maintainer guide](docs/SIGNPATH-APPLICATION.md) and [Code signing policy](CODE-SIGNING.md). `build_windows.py --stage worker` and `--stage app` allow the worker to be signed before embedding. Normal local builds remain unsigned.

`dist/` contains the app and MCP executables. `release/` contains the setup executable, portable ZIP and checksums. The smoke check uses a disposable profile and makes no inference requests. Use `mcp_entry.py` with the virtual environment interpreter for a source MCP connection.

Open an issue with a small reproducible example before proposing a major provider or permission change. Pull requests should explain the user-visible behavior, relevant tests and limits. Keep contributions under the repository's MIT license.

Never commit API keys, local settings, job histories, prompts from real customer work, model weights or generated executables. Use synthetic fixtures and mocked provider calls in tests. Real paid-provider checks require your own explicit authorization and credentials; automated CI must not make such calls.

Preserve the 8,000-character assembled prompt cap, explicit cloud consent, workspace/input restrictions, cancellation accounting and evidence review. A model listing is not a guarantee of access. Describe tools actually available to a provider, and distinguish mocks from live validation. Avoid hardcoded personal paths and account-specific defaults. Any new data flow or changed permission needs a concrete explanation and regression coverage.

Security findings: see SECURITY.md. Keep discussions respectful and focused on the work.
