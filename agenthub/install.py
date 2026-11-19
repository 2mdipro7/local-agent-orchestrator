"""Per-user installation. No elevation, PATH, service or startup changes."""
import json
import os
import queue
import threading
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__
from .providers import _system_tool
from .fileio import check_write_path as _check_install_path, atomic_write as _atomic_install_write



def install_dir():
    return (Path(os.environ["LOCALAPPDATA"]) / "Programs" / "LocalAgentOrchestrator").absolute()


def _shortcuts():
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Local Agent Orchestrator.lnk"


def install_to(destination=None, *, payload_app=None, payload_worker=None, register=True):
    target = Path(destination or install_dir()).absolute()
    _check_install_path(target)
    if target == Path(target.anchor) or target == Path.home():
        raise ValueError("Invalid installation directory")
    if register and (os.name != "nt" or target != install_dir()):
        raise ValueError("Registered installation must use the current user's application directory")
    app = Path(payload_app or sys.executable).resolve()
    resource = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    worker = Path(payload_worker or resource / "bin" / "LocalAgentOrchestratorMCP.exe").resolve()
    if not app.is_file() or not worker.is_file():
        raise ValueError("Installer payload is incomplete; use the packaged Setup executable")
    documents = ("README.md", "HOST-CONNECTIONS.md", "LICENSE", "THIRD-PARTY-NOTICES.txt", "SECURITY.md", "CONTRIBUTING.md", "TEST-RESULTS.md", "CHANGELOG.md", "SECOND-PC-TEST.md", "SHARED-SKILLS.md", "CODE-SIGNING.md", "PRIVACY.md", "assets/README.md", "assets/architecture-banner.png", "assets/download-windows.svg")
    # Preflight every destination before changing any installed file.
    for filename in ("LocalAgentOrchestrator.exe", "LocalAgentOrchestratorMCP.exe", "setup-report.json", *documents):
        _check_install_path(target / filename)
    if register:
        _check_install_path(_shortcuts())
    target.mkdir(parents=True, exist_ok=True)
    for source, filename in ((app, "LocalAgentOrchestrator.exe"), (worker, "LocalAgentOrchestratorMCP.exe")):
        destination_file = target / filename
        if source != destination_file:
            _atomic_install_write(destination_file, source=source)
    for filename in documents:
        document = resource / "resources" / filename
        if not document.is_file():
            document = resource / filename
        if document.is_file():
            installed_document = target / filename
            _atomic_install_write(installed_document, source=document)
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
        _check_install_path(_shortcuts())
        subprocess.run([_system_tool('WindowsPowerShell/v1.0/powershell.exe'), "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                       check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return target


def register_default_hosts(path, *, home=None, environ=None, detailed=False):
    """Register hosts independently; legacy callers receive a list of notes."""
    from .hosts import host_targets, register_host
    entry = {'command': str(Path(path) / 'LocalAgentOrchestratorMCP.exe'), 'args': []}
    outcomes = []
    safe_reasons = {
        'The orchestrator is disabled in this host; enable it in the host settings and retry': 'Disabled in host settings; enable it and retry.',
        'A different orchestrator entry exists; it was left unchanged': 'A different entry already exists; review it in host settings.',
        'MCP executable is missing; install the application first': 'MCP executable is missing; reinstall and retry.',
        'Host configuration is invalid; no changes made': 'Host configuration is invalid; repair it and retry.',
        'Host MCP configuration must be an object': 'Host configuration is invalid; repair it and retry.',
    }
    for target in host_targets(home, environ):
        item = {'id': target['id'], 'name': target['name'], 'path': target['path']}
        try:
            result = register_host(target['path'], entry, target['format'])
            item.update(status='configured' if result['changed'] else 'already configured', reason='')
        except ValueError as exc:
            item.update(status='unchanged', reason=safe_reasons.get(str(exc), 'Configuration could not be safely updated; inspect host settings and retry.'))
        except OSError:
            item.update(status='unchanged', reason='Could not read or write host settings; check permissions and retry.')
        outcomes.append(item)
    if detailed:
        return outcomes
    return [item['name'] + ': ' + item['status'] + (' — ' + item['reason'] if item['reason'] else '') for item in outcomes]


def setup_installation(*, connect=True, progress=lambda message: None):
    """Install, register selected hosts and check the installed server."""
    from .connection_check import check_installed_server
    progress("Installing files and shortcuts…")
    path = install_to()
    progress("Configuring host connections…")
    try:
        hosts = register_default_hosts(path, detailed=True) if connect else []
    except Exception:
        hosts = [{'id': 'registration', 'name': 'Host registration', 'path': '',
                  'status': 'unchanged', 'reason': 'Could not inspect host settings; check permissions and retry.'}]
    progress("Checking the installed MCP server…")
    probe = check_installed_server(path)
    report = {"version": __version__, "executable": str(path / "LocalAgentOrchestratorMCP.exe"),
              "host_registration": "attempted" if connect else "skipped",
              "hosts": hosts, "probe": probe}
    report["ok"] = probe["ok"] and all(h["status"] != "unchanged" for h in hosts)
    try:
        _atomic_install_write(path / "setup-report.json", data=(json.dumps(report, indent=2) + "\n").encode('utf-8'))
    except (OSError, ValueError):
        report["ok"] = False
        report["report_error"] = "Could not save setup report"
    return report


def installer_ui():
    root = tk.Tk()
    root.title("Install Local Agent Orchestrator")
    root.geometry("650x550")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=30)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Local Agent Orchestrator", font=("Segoe UI", 22, "bold")).pack(anchor="w")
    ttk.Label(frame, text="Version " + __version__ + " · open-source preview · installs for your profile", font=("Segoe UI", 11)).pack(anchor="w", pady=(4, 22))
    ttk.Label(frame, text="Connect compatible lead agents to local models, subscribed\nCLI workers and your configured API providers.\n\nNo administrator access, public server or startup entry.\nExternal providers and model weights are not bundled.", justify="left").pack(anchor="w")
    ttk.Label(frame, text="Created by Mehrab Mashrafi (@2mdipro7)").pack(anchor="w", pady=(8, 0))
    ttk.Label(frame, text=str(install_dir()), wraplength=530).pack(anchor="w", pady=18)
    ttk.Label(frame, text="Setup adds app files, a Start-menu shortcut and an uninstall entry.\nThe option below also updates host MCP settings and keeps backups.\nUninstall retains saved tasks, keys and host settings. See PRIVACY.md.", justify="left").pack(anchor="w", pady=(0, 10))
    connect_hosts = tk.BooleanVar(value=True)
    check = ttk.Checkbutton(frame, text="Configure Claude Desktop, Claude Code, Codex and Antigravity", variable=connect_hosts)
    check.pack(anchor="w")
    status = ttk.Label(frame, text="Ready to install")
    status.pack(anchor="w", pady=(10, 0))
    events = queue.Queue()
    busy = False

    def poll():
        nonlocal busy
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == "progress":
                    status.config(text=value)
                elif kind == "done":
                    busy = False
                    button.config(state="normal")
                    check.config(state="normal")
                    lines = [h['name'] + ': ' + h['status'] + ((' — ' + h['reason']) if h['reason'] else '') for h in value['hosts']]
                    if value['host_registration'] == 'skipped':
                        lines.append('Host configuration skipped')
                    lines.append(value['probe']['status'])
                    if value['host_registration'] == 'attempted':
                        lines.append('Restart configured hosts to load the connection.')
                    lines.append('Setup report: ' + str(Path(value['executable']).parent / 'setup-report.json'))
                    lines.append('No JSON editing is normally needed. Server response does not confirm a host has loaded it.')
                    if value.get('report_error'):
                        lines.append(value['report_error'])
                    status.config(text="Setup complete" if value['ok'] else "Setup needs attention; you can retry")
                    show = messagebox.showinfo if value['ok'] else messagebox.showwarning
                    show("Installed" if value['ok'] else "Installation needs attention", "\n".join(lines), parent=root)
                else:
                    busy = False
                    button.config(state="normal")
                    check.config(state="normal")
                    status.config(text="Setup could not finish; you can retry")
                    messagebox.showerror("Installation could not finish", "Close running copies and try again. " + value, parent=root)
        except queue.Empty:
            pass
        root.after(100, poll)

    def install():
        nonlocal busy
        if busy:
            return
        busy = True
        button.config(state="disabled")
        check.config(state="disabled")
        connect = connect_hosts.get()
        def work():
            try:
                result = setup_installation(connect=connect, progress=lambda value: events.put(("progress", value)))
                events.put(("done", result))
            except Exception:
                events.put(("error", "Check the installation folder and permissions."))
        threading.Thread(target=work, daemon=True).start()
    button = ttk.Button(frame, text="Install for this user", command=install)
    button.pack(anchor="e")
    def close_window():
        if busy:
            messagebox.showinfo("Setup in progress", "Please wait for setup to finish before closing this window.", parent=root)
        else:
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", close_window)
    root.after(100, poll)
    root.mainloop()


def uninstall():
    root = tk.Tk()
    root.withdraw()
    if not messagebox.askyesno("Remove Local Agent Orchestrator", "Remove the app and Start-menu shortcut?\nYour saved jobs, settings and encrypted keys will be kept.", parent=root):
        root.destroy()
        return
    target = install_dir()
    _check_install_path(target)
    _check_install_path(_shortcuts())
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
    subprocess.Popen([_system_tool('WindowsPowerShell/v1.0/powershell.exe'), "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW)
    root.destroy()
