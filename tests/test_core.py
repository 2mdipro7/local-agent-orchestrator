from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from agenthub.core import Hub, ACCEPTANCE, secure_source_bytes
from agenthub import __version__
from agenthub.mcp import serve
from agenthub.secrets import SecretStore
from agenthub.install import install_to


class FakeProvider:
    gate = None
    active = 0
    peak = 0
    calls = []
    image_contents = []
    lock = threading.Lock()

    def __init__(self, config, secret_getter):
        self.config = config

    def discover(self):
        return [{"provider": "ollama", "id": "fixture:tiny", "name": "Fixture", "modality": "text", "status": "available"}]

    def generate(self, provider, model, prompt, **kwargs):
        with self.lock:
            type(self).active += 1
            type(self).peak = max(type(self).peak, type(self).active)
            type(self).calls.append((provider, model, prompt))
        try:
            if self.gate is not None:
                self.gate.wait(3)
            for image in kwargs.get('images', []):
                type(self).image_contents.append(Path(image).read_bytes())
            time.sleep(.02)
            return {"text": "fixture result", "artifacts": [], "observed_model": model, "usage": {"tokens": 2}}
        finally:
            with self.lock:
                type(self).active -= 1


class HubTests(unittest.TestCase):
    def test_provider_migration_preserves_disabled_provider_and_adds_codex(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'settings.json').write_text(json.dumps({'providers': {'claude': {'enabled': False}}, 'timeout_seconds': 90}))
            hub = Hub(path, provider_factory=FakeProvider)
            self.assertFalse(hub.config['providers']['claude']['enabled'])
            self.assertTrue(hub.config['providers']['codex']['enabled'])
            self.assertEqual(hub.config['timeout_seconds'], 90)

    def test_codex_worker_rejected_before_job_creation(self):
        with self.assertRaisesRegex(ValueError, 'not callable workers'):
            self.hub.submit_task('codex', 'gpt-6.1-sol', 'Test only', self.workspace, allow_cloud=True)
        self.assertEqual(self.hub.list_tasks(), [])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Windows CI can expose TEMP through an 8.3 alias (for example RUNNER~1).
        # Match submit_task's canonical workspace before testing the reader itself.
        self.root = Path(self.tmp.name).resolve()
        self.workspace = self.root / "project"
        self.workspace.mkdir()
        self.hub = Hub(self.root / "data", provider_factory=FakeProvider)
        FakeProvider.gate = None; FakeProvider.peak = 0; FakeProvider.calls = []; FakeProvider.image_contents = []

    def tearDown(self):
        if FakeProvider.gate:
            FakeProvider.gate.set()
        for task in self.hub._threads.values():
            task.join(5)
        self.tmp.cleanup()

    def submit(self, **kwargs):
        values = dict(provider="ollama", model="fixture:tiny", prompt="Role: extractor. Return the supplied fact only: fixture.", workspace=str(self.workspace))
        values.update(kwargs)
        return self.hub.submit_task(**values)

    def wait(self, task_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            task = self.hub.get_task(task_id)
            if task["status"] not in ("queued", "running"):
                return task
            time.sleep(.03)
        self.fail("Fixture did not finish")

    def test_success_is_not_acceptance_and_evidence_is_required(self):
        task = self.wait(self.submit()["id"])
        self.assertEqual(task["status"], "succeeded")
        self.assertEqual(task["review_status"], "pending")
        with self.assertRaises(ValueError):
            self.hub.review_task(task["id"], "desktop-user", "accepted", {"summary": "looks fine"})
        review = {"summary": "Inspected fixture response", "criteria": [{"criterion": ACCEPTANCE, "verdict": "pass", "evidence": "response.md matches fixture source"}], "boundary_review": "Synthetic content only, no side effects", "limitations": ["Mock provider"]}
        accepted = self.hub.review_task(task["id"], "desktop-user", "accepted", review)
        self.assertEqual(accepted["review_status"], "accepted")
        review["criteria"][0]["verdict"] = "not_checked"
        with self.assertRaises(ValueError):
            self.hub.review_task(task["id"], "desktop-user", "accepted", review)

    def test_cloud_requires_explicit_authorization_and_no_call_on_denial(self):
        with self.assertRaisesRegex(ValueError, "cloud authorization"):
            self.submit(provider="claude", model="claude-sonnet-5-5")
        self.assertEqual(FakeProvider.calls, [])
        self.assertEqual(self.hub.list_tasks(), [])
        with self.assertRaisesRegex(ValueError, "cloud authorization"):
            self.submit(provider="ollama", model="example:8b-cloud")

    def test_full_prompt_cap_and_source_scope(self):
        inside = self.workspace / "source.txt"; inside.write_text("exact source fact")
        outside = self.root / "outside.txt"; outside.write_text("private")
        with self.assertRaises(ValueError): self.submit(source_files=[str(outside)])
        with self.assertRaisesRegex(ValueError, "8,000"): self.submit(prompt="x" * 8000)
        (self.workspace / ".env").write_text("TOKEN=synthetic")
        with self.assertRaises(ValueError): self.submit(source_files=[".env"])
        task = self.wait(self.submit(source_files=["source.txt"])["id"])
        self.assertIn("exact source fact", FakeProvider.calls[0][2])
        self.assertIn("untrusted_source", FakeProvider.calls[0][2])
        self.assertLessEqual(task["prompt_characters"], 8000)
        self.assertEqual(inside.read_text(), "exact source fact")

    def test_artifact_traversal_and_hub_credentials_source_block(self):
        task = self.wait(self.submit()["id"])
        self.assertTrue(self.hub.artifact_path(task["id"], "response.md").is_file())
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.hub.artifact_path(task["id"], "../../settings.json")
        with self.assertRaises(ValueError):
            self.hub.artifact_path(task["id"], str(self.root / "outside.txt"))
        marker = self.hub.home / "credentials.dpapi.json"; marker.write_text('{}')
        with self.assertRaises(ValueError):
            self.submit(workspace=str(self.root), source_files=[str(marker)])

    def test_image_is_snapshotted_before_async_provider_execution(self):
        selected = b'\x89PNG\r\n\x1a\nselected-fixture'
        source = self.workspace / 'scene.png'; source.write_bytes(selected)
        FakeProvider.gate = threading.Event()
        task = self.submit(images=['scene.png'])
        source.write_bytes(b'\x89PNG\r\n\x1a\nchanged-after-submission')
        snapshot = self.hub.home / 'jobs' / task['id'] / 'inputs' / 'image-1.png'
        self.assertEqual(snapshot.read_bytes(), selected)
        FakeProvider.gate.set()
        self.assertEqual(self.wait(task['id'])['status'], 'succeeded')
        self.assertEqual(FakeProvider.image_contents, [selected])

    @unittest.skipUnless(os.name == 'nt', 'Windows stable-handle reader')
    def test_secure_reader_rejects_source_link_replacement(self):
        original = self.workspace / 'selected.txt'; original.write_text('selected')
        outside = self.root / 'not-selected.txt'; outside.write_text('private synthetic fixture')
        verified = self.hub._source(self.workspace, original)
        original.unlink()
        try:
            original.symlink_to(outside)
        except OSError:
            self.skipTest('Creating test links is not permitted for this Windows user')
        with self.assertRaises(ValueError):
            secure_source_bytes(verified, 32000)

    def test_global_admission_and_one_gpu_across_hub_instances(self):
        FakeProvider.gate = threading.Event()
        other = Hub(self.root / "data", provider_factory=FakeProvider)
        def add(i):
            try:
                hub = self.hub if i % 2 else other
                return hub.submit_task("ollama", "fixture:tiny", "Return fixture", str(self.workspace))
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(add, range(8)))
        self.assertEqual(sum(v is not None for v in results), 4)
        time.sleep(.1)
        self.assertEqual(FakeProvider.peak, 1)
        FakeProvider.gate.set()
        for task in results:
            if task: self.wait(task["id"])
        for thread in other._threads.values(): thread.join(5)
        self.assertEqual(FakeProvider.peak, 1)

    def test_cancel_keeps_capacity_until_adapter_really_exits(self):
        FakeProvider.gate = threading.Event()
        self.hub.config["max_workers"] = 1
        task = self.submit()
        time.sleep(.1)
        self.hub.cancel_task(task["id"])
        with self.assertRaises(ValueError): self.submit()
        self.assertIn(self.hub.get_task(task["id"])["status"], ("queued", "running"))
        FakeProvider.gate.set()
        self.assertEqual(self.wait(task["id"])["status"], "cancelled")

    def test_settings_do_not_persist_plaintext_keys_or_remote_local_endpoints(self):
        config = dict(self.hub.config)
        config["providers"] = dict(config["providers"])
        config["providers"]["gemini"] = {"enabled": True, "api_key": "fixture-secret"}
        with self.assertRaises(ValueError): self.hub.save_config(config)
        config["providers"]["gemini"] = {"enabled": False}
        config["providers"]["ollama"] = {"enabled": True, "base_url": "https://example.com"}
        with self.assertRaises(ValueError): self.hub.save_config(config)

    def test_mcp_is_provider_neutral_and_stdio_only(self):
        requests = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "AnyCompatibleLead"}}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_models", "arguments": {}}}]
        sink = io.StringIO()
        serve(self.hub, io.StringIO(''.join(json.dumps(x) + '\n' for x in requests)), sink)
        replies = [json.loads(line) for line in sink.getvalue().splitlines()]
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(replies[0]["result"]["serverInfo"], {"name": "local-agent-orchestrator", "version": __version__})
        self.assertEqual(len(replies[1]["result"]["tools"]), 9)
        self.assertIn("fixture:tiny", replies[2]["result"]["content"][0]["text"])

    def test_connection_config_recognizes_renamed_worker(self):
        worker = r"C:\Program Files\LocalAgentOrchestratorMCP.exe"
        config = self.hub.connection_config(worker)["mcpServers"]["local-agent-orchestrator"]
        self.assertEqual(config, {"command": worker, "args": []})
        python_config = self.hub.connection_config("python.exe")["mcpServers"]["local-agent-orchestrator"]
        self.assertEqual(Path(python_config["args"][0]).name, "mcp_entry.py")

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI")
    def test_dpapi_round_trip_never_stores_plaintext(self):
        store = SecretStore(self.root / "vault.json")
        store.set("fixture", "not-a-real-key-76543")
        self.assertTrue(store.has("fixture"))
        self.assertNotIn("not-a-real-key", (self.root / "vault.json").read_text())
        self.assertEqual(store.get("fixture"), "not-a-real-key-76543")
        store.set("fixture", "")
        self.assertFalse(store.has("fixture"))

    def test_installer_payload_is_per_destination_and_preserves_data(self):
        app = self.root / "app-payload.exe"; app.write_bytes(b'MZfake-app-fixture')
        worker = self.root / "worker-payload.exe"; worker.write_bytes(b'MZfake-worker-fixture')
        target = self.root / "installed"
        install_to(target, payload_app=app, payload_worker=worker, register=False)
        self.assertEqual((target / "LocalAgentOrchestrator.exe").read_bytes(), app.read_bytes())
        self.assertEqual((target / "LocalAgentOrchestratorMCP.exe").read_bytes(), worker.read_bytes())
        self.assertTrue(self.hub.home.is_dir())


if __name__ == "__main__": unittest.main()
