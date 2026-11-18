"""Exercise skill selection through the real Tk widgets with synthetic files."""
import copy
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from agenthub.core import Hub
from agenthub.gui import App
from test_core import FakeProvider


class SkillGuiTests(unittest.TestCase):
    def test_discovery_assignment_and_task_snapshot(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        root.withdraw()
        with tempfile.TemporaryDirectory() as temp:
            hub = Hub(Path(temp) / "data", provider_factory=FakeProvider)
            config = copy.deepcopy(hub.config)
            config["discover_host_skills"] = False
            hub.save_config(config)
            folder = hub.home / "skills" / "writing"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "SKILL.md").write_text("---\nname: writing-check\ndescription: Check supplied facts.\n---\nUse supplied facts only.\n", encoding="utf-8")
            with patch.object(hub, "hardware_info", return_value={}):
                app = App(hub, master=root)
            errors = []
            app._error = lambda title, exc: errors.append((title, str(exc)))
            app._warning = lambda title, text: errors.append((title, text))
            try:
                app.models = hub.discover_models()
                app._display_models()
                app.refresh_skills()
                deadline = time.monotonic() + 8
                while app.skills_loading and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.02)
                self.assertFalse(app.skills_loading)
                self.assertEqual(len(app.models), 1, "Skill events must not clear model discovery")
                skill_id = app.skills[0]["id"]
                app.skill_tree.selection_set(skill_id)
                app._assign_selected_skills()
                self.assertIn(skill_id, app.assigned_skills)
                app.workspace.set(temp)
                app.prompt.insert("1.0", "Summarize these supplied facts: the example task is complete.")
                app._submit()
                self.assertFalse(errors, errors)
                task = hub.list_tasks()[0]
                deadline = time.monotonic() + 3
                while task["status"] in ("queued", "running") and time.monotonic() < deadline:
                    time.sleep(.02)
                    task = hub.get_task(task["id"])
                self.assertEqual(task["status"], "succeeded")
                self.assertEqual(task["skills"][0]["id"], skill_id)
                self.assertIn("Use supplied facts only.", hub.artifact_path(task["id"], task["skills"][0]["artifact"]).read_text(encoding="utf-8"))
                app._load_task(task["id"])
                self.assertIn("Assigned skill snapshots", app.output_box.get("1.0", "end"))
                app._clear_skills()
                self.assertFalse(app.assigned_skills)
            finally:
                app.close()


if __name__ == "__main__":
    unittest.main()
