"""Per-user installation. No elevation, PATH, service or startup changes."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__


def install_dir():
    return (Path(os.environ["LOCALAPPDATA"]) / "Programs" / "LocalAgentOrchestrator").resolve()


def _shortcuts():
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Local Agent Orchestrator.lnk"


def install_to(destination=None, *, payload_app=None, payload_worker=None, register=True):
    target = Path(destination or install_dir()).resolve()
    if target == Path(target.anchor) or target == Path.home():
        raise ValueError("Invalid installation directory")
    if register and (os.name != "nt" or target != install_dir()):
        raise ValueError("Registered installation must use the current user's application directory")
    app = Path(payload_app or sys.executable).resolve()
    resource = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    worker = Path(payload_worker or resource / "bin" / "LocalAgentOrchestratorMCP.exe").resolve()
    if not app.is_file() or not worker.is_file():
        raise ValueError("Installer payload is incomplete; use the packaged Setup executable")
    target.mkdir(parents=True, exist_ok=True)
    for source, filename in ((app, "LocalAgentOrchestrator.exe"), (worker, "LocalAgentOrchestratorMCP.exe")):
        destination_file = target / filename
        if source != destination_file:
            temporary = target / (filename + ".new")
            shutil.copy2(source, temporary)
            os.replace(temporary, destination_file)
    for filename in ("README.md", "HOST-CONNECTIONS.md", "LICENSE", "THIRD-PARTY-NOTICES.txt"):
        document = resource / "resources" / filename
        if not document.is_file():
            document = resource / filename
        if document.is_file():
            shutil.copy2(document, target / filename)
    if register:
        if os.name != "nt" or target != install_dir():
            raise ValueError("Registered installation must use the current user's application directory")
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalAgentOrchestrator"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            values = {"DisplayName": "Local Agent Orchestrator", "DisplayVersion": __version__,
                      "Publisher": "Mehrab Mashrafi", "InstallLocation": str(target),
                      "UninstallString": '"' + str(target / "LocalAgentOrchestrator.exe") + '" --uninstall'}
            for name, value in values.items():
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        # Static script; file paths are passed through child-only environment,
        # never interpolated into command text or used for shell deletion.
        env = os.environ.copy()
        env["HUB_SHORTCUT"] = str(_shortcuts())
        env["HUB_EXECUTABLE"] = str(target / "LocalAgentOrchestrator.exe")
        env["HUB_WORKDIR"] = str(target)
        script = "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:HUB_SHORTCUT);$s.TargetPath=$env:HUB_EXECUTABLE;$s.WorkingDirectory=$env:HUB_WORKDIR;$s.Save()"
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                       check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return target


def installer_ui():
    root = tk.Tk()
    root.title("Install Local Agent Orchestrator")
    root.geometry("650x490")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=30)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Local Agent Orchestrator", font=("Segoe UI", 22, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Version 0 · open-source preview · installs for your profile", font=("Segoe UI", 11)).pack(anchor="w", pady=(4, 22))
    ttk.Label(frame, text="Connect compatible lead agents to local models, subscribed\nCLI workers and your configured API providers.\n\nNo administrator access, public server or startup entry.\nExternal providers and model weights are not bundled.", justify="left").pack(anchor="w")
    ttk.Label(frame, text="Created by Mehrab Mashrafi (@2mdipro7)").pack(anchor="w", pady=(8, 0))
    ttk.Label(frame, text=str(install_dir()), wraplength=530).pack(anchor="w", pady=18)
    connect_claude = tk.BooleanVar(value=True)
    ttk.Checkbutton(frame, text="Connect detected Claude Desktop and Claude Code profiles", variable=connect_claude).pack(anchor="w")
    def install():
        try:
            path = install_to()
            notes = []
            if connect_claude.get():
                from .hosts import host_targets, register_host
                entry = {'command': str(path / 'LocalAgentOrchestratorMCP.exe'), 'args': []}
                for target in host_targets():
                    try:
                        register_host(target['path'], entry)
                        notes.append(target['name'] + ': configured; restart this host.')
                    except (OSError, ValueError):
                        notes.append(target['name'] + ': unchanged; check Connections in the app.')
            messagebox.showinfo("Installed", "Installed for your Windows profile.\nOpen Local Agent Orchestrator from the Start menu.\n\n" + '\n'.join(notes) + '\n' + str(path), parent=root)
            root.destroy()
        except Exception as exc:
            messagebox.showerror("Installation could not finish", "Close any running Local Agent Orchestrator copies and try again.\n" + str(exc)[:300], parent=root)
    ttk.Button(frame, text="Install for this user", command=install).pack(anchor="e")
    root.mainloop()


def uninstall():
    root = tk.Tk()
    root.withdraw()
    if not messagebox.askyesno("Remove Local Agent Orchestrator", "Remove the app and Start-menu shortcut?\nYour saved jobs, settings and encrypted keys will be kept.", parent=root):
        root.destroy()
        return
    target = install_dir()
    if Path(sys.executable).resolve().parent != target:
        raise ValueError("Uninstall must be launched from the installed application")
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalAgentOrchestrator")
    except FileNotFoundError:
        pass
    env = os.environ.copy()
    env["HUB_REMOVE_DIR"] = str(target)
    env["HUB_REMOVE_SHORTCUT"] = str(_shortcuts())
    env["HUB_WAIT_PID"] = str(os.getpid())
    script = r"""Wait-Process -Id ([int]$env:HUB_WAIT_PID) -ErrorAction SilentlyContinue
$expected=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\LocalAgentOrchestrator'))
$actual=[IO.Path]::GetFullPath($env:HUB_REMOVE_DIR)
if($actual -ne $expected){exit 1}
Remove-Item -LiteralPath (Join-Path $actual 'LocalAgentOrchestrator.exe') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $actual 'LocalAgentOrchestratorMCP.exe') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $actual 'README.md') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $actual 'HOST-CONNECTIONS.md') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $actual 'LICENSE') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $actual 'THIRD-PARTY-NOTICES.txt') -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $env:HUB_REMOVE_SHORTCUT -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $actual -ErrorAction SilentlyContinue
"""
    subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW)
    root.destroy()
