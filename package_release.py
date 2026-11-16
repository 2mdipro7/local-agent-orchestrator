"""Package only explicit public release files; never include profile data."""
import hashlib
from pathlib import Path
import shutil
import zipfile

from agenthub import __version__


def main():
    root = Path(__file__).resolve().parent
    output = root / "release"
    output.mkdir(exist_ok=True)
    prefix = "LocalAgentOrchestrator-v" + __version__
    setup = output / (prefix + "-Setup.exe")
    portable = output / (prefix + "-Portable.zip")
    documents = ["README.md", "HOST-CONNECTIONS.md", "LICENSE", "THIRD-PARTY-NOTICES.txt",
                 "TEST-RESULTS.md", "CHANGELOG.md", "AUTHORS.md", "SECURITY.md"]
    payload = [root / "dist/LocalAgentOrchestrator.exe", root / "dist/LocalAgentOrchestratorMCP.exe"]
    payload.extend(root / name for name in documents)
    for file in payload:
        if not file.is_file():
            raise FileNotFoundError(file.name)
    shutil.copy2(payload[0], setup)
    with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in payload:
            archive.write(file, "LocalAgentOrchestrator/" + file.name)
    with zipfile.ZipFile(portable) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {"LocalAgentOrchestrator/" + file.name for file in payload}
    hashes = "".join(hashlib.sha256(file.read_bytes()).hexdigest() + "  " + file.name + "\n"
                     for file in (setup, portable))
    (output / "SHA256SUMS.txt").write_text(hashes, encoding="utf-8")
    print("Packaged " + setup.name + " and " + portable.name + " with SHA256SUMS.txt")


if __name__ == "__main__":
    main()
