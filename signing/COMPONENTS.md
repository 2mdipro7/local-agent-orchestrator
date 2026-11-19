# Components for SignPath review

The application uses PyInstaller onefile executables. Signing the outer executable does not add project signatures to each runtime DLL. `signing_inventory.py` records every outer CArchive member, byte size and SHA-256 for the two actual build outputs; nested Python archives are recorded as archive entries, not a recursively resolved SBOM. The application contains another full copy of the MCP executable, whose inventory is also recorded separately.

| Component | Observed role / license family | Review evidence |
|---|---|---|
| Local Agent Orchestrator | Application and entry points; MIT | `LICENSE`, repository source |
| CPython and standard-library extension modules | Python 3.14 runtime; PSF license and bundled notices | `THIRD-PARTY-NOTICES.txt`, official Python distribution `LICENSE.txt` |
| PyInstaller bootloader and runtime hooks | GPL with bootloader exception permitting bundled applications | `THIRD-PARTY-NOTICES.txt`, pinned PyInstaller distribution |
| OpenSSL | `libcrypto-3.dll`, `libssl-3.dll`; Apache-2.0 | OpenSSL notice in `THIRD-PARTY-NOTICES.txt` |
| Tcl/Tk | GUI runtime, including embedded script libraries; Tcl/Tk permissive terms | Tcl/Tk notices in `THIRD-PARTY-NOTICES.txt` |
| libffi | `libffi-8.dll`; MIT-style license | CPython distribution notices |
| SQLite | `sqlite3.dll`; public domain | CPython distribution notices; https://sqlite.org/copyright.html |
| zlib / bzip2 / LZMA / Zstandard | Compression libraries used by the runtime; respective upstream licenses | CPython distribution notices; build-specific embedded modules and DLL inventory |
| LibTomMath | `libtommath.dll` supporting Tcl; permissive/public-domain upstream terms | Tcl runtime distribution and upstream license |
| Microsoft runtime and Windows API-set libraries | `VCRUNTIME140.dll`, `VCRUNTIME140_1.dll`, `ucrtbase.dll`, `api-ms-win-*.dll`; Microsoft system/runtime redistribution terms, **not claimed to be OSI-licensed** | Actual inventory from the official Windows Python build; Foundation must confirm its system-library exception applies |

This is a review map, not a legal conclusion about every transitive component. The Python distribution's license file includes notices for its incorporated libraries. Additional build dependencies are pinned in `requirements-build.txt`; those used only for building are not automatically application runtime components. Review the inventory after each runtime or packager upgrade.

**Question for SignPath onboarding:** may the Microsoft runtime/API-set DLLs redistributed with the official CPython Windows runtime remain inside this onefile bundle under the system-library exception? Do not enable production signing until SignPath has accepted the package composition. If a component is rejected, change the bundle and rerun validation rather than relabeling it as open source.

No Claude, Codex, Antigravity, Ollama, LM Studio, OpenCode executable or model weight is included. They are separately installed and used under their own terms. The project must disclose its AI orchestration behavior and response-only worker restrictions; signing is not approval of arbitrary model output.
