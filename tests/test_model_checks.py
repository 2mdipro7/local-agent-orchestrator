import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agenthub.core import Hub
from agenthub.gui import App
from agenthub.providers import ProviderError


class Provider:
    response = "LAO_MODEL_CHECK=42"
    calls = []
    gate = None
    def _executable(self, *args):
        raise AssertionError("Status must not resolve a provider executable")
    def __init__(self, config, getter): pass
    def discover(self): return [{"provider": "ollama", "id": "tiny", "modality": "text", "status": "available"}]
    def generate(self, provider, model, prompt, **kwargs):
        self.calls.append((provider, model, prompt, kwargs))
        if self.gate:
            self.gate.wait(3)
        if self.response == "RAISE":
            raise ProviderError("Provider unavailable; check settings")
        return {"text": self.response, "artifacts": [], "observed_model": None}


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "data"
        self.hub = Hub(self.home, provider_factory=Provider)
        Provider.response = "LAO_MODEL_CHECK=42"
        Provider.calls = []
        Provider.gate = None
    def tearDown(self):
        if Provider.gate:
            Provider.gate.set()
        for thread in self.hub._threads.values(): thread.join(5)
        self.tmp.cleanup()
    def finish(self, task):
        self.hub._threads[task["id"]].join(5)
        return self.hub.get_task(task["id"])
    def test_evidence_persists_and_invalidates(self):
        self.assertEqual(self.hub.model_test_status("ollama", "tiny")["state"], "untested")
        task = self.finish(self.hub.test_model("ollama", "tiny"))
        self.assertEqual(task["review_status"], "pending")
        self.assertEqual(task["source_hashes"], {})
        self.assertIsNone(task["observed_model"])
        self.assertEqual(Hub(self.home, provider_factory=Provider).model_test_status("ollama", "tiny")["state"], "tested")
        Provider.response = "wrong"
        self.finish(self.hub.test_model("ollama", "tiny"))
        self.assertEqual(self.hub.model_test_status("ollama", "tiny")["state"], "failed")
        Provider.response = "LAO_MODEL_CHECK=42"
        self.finish(self.hub.test_model("ollama", "tiny"))
        Provider.response = "RAISE"
        failed = self.finish(self.hub.test_model("ollama", "tiny"))
        self.assertEqual(failed["status"], "failed")
        self.assertIn("check settings", self.hub.model_test_status("ollama", "tiny")["reason"])
        Provider.response = "LAO_MODEL_CHECK=42"
        self.finish(self.hub.test_model("ollama", "tiny"))
        self.hub.config["providers"]["ollama"]["base_url"] = "http://127.0.0.1:9999"
        self.assertEqual(self.hub.model_test_status("ollama", "tiny")["state"], "untested")
        self.hub.config["providers"]["ollama"]["base_url"] = "http://127.0.0.1:11434"
        self.hub.secrets.path.write_text('{}')
        self.assertEqual(self.hub.model_test_status("ollama", "tiny")["state"], "untested")
    def test_batch_and_completion_time_survive_review(self):
        task = self.finish(self.hub.test_model("claude", "exact", allow_cloud=True))
        with patch.object(self.hub, "_db", wraps=self.hub._db) as db, \
             patch.object(self.hub, "_provider_evidence", wraps=self.hub._provider_evidence) as evidence:
            statuses = self.hub.model_test_statuses([("claude", "exact"), ("claude", "other"), ("ollama", "tiny")])
        self.assertEqual(db.call_count, 1)
        self.assertEqual(evidence.call_count, 2)
        self.assertEqual(statuses[("claude", "exact")]["state"], "tested")
        reviewed = self.hub.review_task(task["id"], "desktop-user", "rejected", {"summary": "Synthetic review fixture"})
        self.assertEqual(reviewed["completed_at"], task["completed_at"])
        self.assertEqual(self.hub.model_test_status("claude", "exact")["task"]["completed_at"], task["completed_at"])

    def test_later_failed_ordinary_job_and_exact_response(self):
        for response, expected in [("LAO_MODEL_CHECK=42\n", "tested"), (" LAO_MODEL_CHECK=42", "failed"), ("LAO_MODEL_CHECK=42\n\n", "failed")]:
            Provider.response = response
            self.finish(self.hub.test_model("ollama", "tiny"))
            self.assertEqual(self.hub.model_test_status("ollama", "tiny")["state"], expected)
        Provider.response = "LAO_MODEL_CHECK=42"
        self.finish(self.hub.test_model("ollama", "tiny"))
        Provider.response = "RAISE"
        workspace = self.home / "ordinary-workspace"
        workspace.mkdir()
        self.finish(self.hub.submit_task("ollama", "tiny", "Synthetic task", workspace))
        self.assertEqual(self.hub.model_test_status("ollama", "tiny")["state"], "failed")

    def test_duplicate_active_test_rejected(self):
        Provider.gate = threading.Event()
        task = self.hub.test_model("ollama", "tiny")
        with self.assertRaisesRegex(ValueError, "already running"):
            self.hub.test_model("ollama", "tiny")
        self.assertEqual(self.hub.model_test_status("ollama", "tiny")["state"], "testing")
        Provider.gate.set()
        self.finish(task)

    def test_cloud_consent_and_gui_selection(self):
        class Tree:
            def selection(self): return ("0",)
        class Status:
            def set(self, value): pass
        class FakeApp:
            models = [{"provider": "claude", "id": "exact-model", "modality": "text", "status": "available"}]
            model_tree = Tree()
            hub = self.hub
            root = None
            status = Status()
            _model_status = App._model_status
            _model_id = staticmethod(App._model_id)
            def _display_models(self, **kwargs): pass
            def _error(self, title, exc): raise exc
        app = FakeApp()
        self.assertEqual(app._model_status({"provider": "claude", "id": "exact-model", "modality": "text", "status": "discovery_only"})["state"], "unavailable")
        self.assertEqual(app._model_status({"provider": "claude", "id": "exact-model", "modality": "image", "status": "available"})["state"], "unsupported")
        with patch("agenthub.gui.messagebox.askyesno", return_value=False):
            App._test_selected_model(app)
        self.assertEqual(Provider.calls, [])
        with patch("agenthub.gui.messagebox.askyesno", return_value=True):
            App._test_selected_model(app)
        task = self.finish(self.hub.list_tasks()[0])
        self.assertEqual((task["provider"], task["model"]), ("claude", "exact-model"))
        self.assertTrue(task["cloud_authorized"])
        self.assertEqual(task["source_hashes"], {})
        self.assertEqual(task["review_status"], "pending")
        self.assertIn("LAO_MODEL_CHECK=42", Provider.calls[0][2])
        self.assertEqual(Provider.calls[0][3]["images"], [])

if __name__ == '__main__': unittest.main()
