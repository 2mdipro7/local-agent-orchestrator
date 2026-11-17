"""Bounded, read-only handshake with the installed stdio MCP server."""
import json
import signal
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from . import __version__
from .mcp import TOOLS


class _ProcessGroup:
    """Own the probe and descendants, including the frozen bootloader child."""
    def __init__(self):
        self.job = None
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            class Basic(ctypes.Structure):
                _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
                            ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                            ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                            ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]
            class IO(ctypes.Structure):
                _fields_ = [(name, ctypes.c_ulonglong) for name in ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
            class Extended(ctypes.Structure):
                _fields_ = [('BasicLimitInformation', Basic), ('IoInfo', IO), ('ProcessMemoryLimit', ctypes.c_size_t),
                            ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            kernel.CreateJobObjectW.restype = wintypes.HANDLE
            kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
            kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel = kernel
            self.job = kernel.CreateJobObjectW(None, None)
            if not self.job:
                raise OSError('Unable to create process job')
            limits = Extended()
            limits.BasicLimitInformation.LimitFlags = 0x2000
            if not kernel.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                kernel.CloseHandle(self.job)
                self.job = None
                raise OSError('Unable to configure process job')

    def assign(self, process):
        if self.job and not self.kernel.AssignProcessToJobObject(self.job, int(process._handle)):
            raise OSError('Unable to contain process')

    def close(self, process):
        if self.job:
            self.kernel.CloseHandle(self.job)
            self.job = None
        elif os.name != 'nt' and process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass


def _exchange(command, timeout=25):
    deadline = time.monotonic() + timeout
    messages = queue.Queue(maxsize=8)
    process = None
    group = None
    reader = None
    success = False
    try:
        env = os.environ.copy()
        # A separately packaged PyInstaller executable must not reuse our bootloader state.
        env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        group = _ProcessGroup()
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, env=env,
                                   start_new_session=(os.name != 'nt'),
                                   creationflags=(getattr(subprocess, 'CREATE_NO_WINDOW', 0) | (4 if os.name == 'nt' else 0)))
        group.assign(process)
        if os.name == 'nt':
            import ctypes
            resume = ctypes.WinDLL('ntdll').NtResumeProcess
            resume.argtypes = [ctypes.c_void_p]
            resume.restype = ctypes.c_long
            if resume(int(process._handle)) != 0:
                raise OSError('Unable to start contained process')

        def read_replies():
            try:
                while True:
                    line = process.stdout.readline(262145)
                    if not line:
                        messages.put_nowait(None)
                        return
                    if len(line) > 262144 or not line.endswith(b'\n'):
                        messages.put_nowait('oversize')
                        return
                    messages.put_nowait(line)
            except (OSError, ValueError, queue.Full):
                return

        reader = threading.Thread(target=read_replies, daemon=True)
        reader.start()

        def send(value):
            process.stdin.write((json.dumps(value) + '\n').encode('utf-8'))
            process.stdin.flush()

        def receive(request_id):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            try:
                line = messages.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError
            if not isinstance(line, bytes):
                raise ValueError('invalid response')
            reply = json.loads(line)
            if not isinstance(reply, dict) or reply.get('jsonrpc') != '2.0' or reply.get('id') != request_id or 'error' in reply:
                raise ValueError('invalid response')
            return reply['result']

        send({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
            'protocolVersion': '2025-03-26', 'capabilities': {},
            'clientInfo': {'name': 'local-installer-check', 'version': __version__}}})
        info = receive(1)
        if info.get('protocolVersion') != '2025-03-26' or not isinstance(info.get('capabilities', {}).get('tools'), dict):
            return {'ok': False, 'status': 'server protocol or capabilities mismatch'}
        if info.get('serverInfo') != {'name': 'local-agent-orchestrator', 'version': __version__}:
            return {'ok': False, 'status': 'server identity or version mismatch'}
        send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        send({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}})
        result = receive(2)
        names = {item['name'] for item in result['tools']}
        if names != {name for name, _, _ in TOOLS}:
            return {'ok': False, 'status': 'server tools mismatch'}
        success = True
        return {'ok': True, 'status': 'MCP server responded'}
    except TimeoutError:
        return {'ok': False, 'status': 'connection timed out'}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {'ok': False, 'status': 'server did not respond correctly'}
    finally:
        # Close input on success so the server can exit naturally. Closing the job
        # then terminates any remaining descendant still holding a pipe open.
        if process is not None:
            if success:
                try:
                    process.stdin.close()
                    process.wait(timeout=max(0.01, min(1, deadline - time.monotonic())))
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    pass
            if group is not None:
                group.close(process)
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
            if reader is not None:
                reader.join(timeout=2)
            # Do not close a pipe while another thread is blocked reading it.
            if reader is None or not reader.is_alive():
                for pipe in (process.stdin, process.stdout):
                    if pipe:
                        try:
                            pipe.close()
                        except (OSError, ValueError):
                            pass
        elif group is not None:
            group.close(None)


def check_installed_server(install_path, timeout=25):
    """Launch only the installed executable; return no raw server output."""
    executable = Path(install_path).resolve() / 'LocalAgentOrchestratorMCP.exe'
    if not executable.is_file():
        return {'ok': False, 'status': 'installed server executable missing'}
    return _exchange([str(executable)], timeout=timeout)
