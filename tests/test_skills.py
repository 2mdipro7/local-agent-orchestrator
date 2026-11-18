from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from agenthub.core import Hub
from agenthub.mcp import serve


class FakeProvider:
    def __init__(self, config, secret_getter):
        pass

    def generate(self, provider, model, prompt, **kwargs):
        return {"text": prompt, "observed_model": model}


class SkillsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.workspace = self.root / "project"
        self.workspace.mkdir()
        self.hub = Hub(self.root / "data", provider_factory=FakeProvider)
        self.hub.config["discover_host_skills"] = False
        self.central = self.hub.home / "skills"
        self.addCleanup(self.join_jobs)

    def join_jobs(self):
        for thread in self.hub._threads.values():
            thread.join(5)

    def write_skill(self, folder, name, body="Use the fixture procedure.", description="Synthetic description."):
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "SKILL.md"
        path.write_bytes(f"---\r\nname: {name}\r\ndescription: {description}\r\n---\r\n{body}\r\n".encode())
        return path

    def list(self, **kwargs):
        return self.hub.list_skills(**kwargs)["skills"]

    def submit(self, **kwargs):
        args = {"provider": "ollama", "model": "fixture:tiny", "workspace": self.workspace, "prompt": "Complete the fixture."}
        args.update(kwargs)
        return self.hub.submit_task(**args)

    def mcp(self, *requests):
        sink = io.StringIO()
        serve(self.hub, io.StringIO("".join(json.dumps(req) + "\n" for req in requests)), sink)
        return {reply["id"]: reply["result"] for reply in map(json.loads, sink.getvalue().splitlines())}

    @staticmethod
    def call(request_id, name, **arguments):
        return {"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
                "params": {"name": name, "arguments": arguments}}

    def test_central_custom_and_host_discovery_search_paging_and_stable_duplicate_ids(self):
        codex = self.root / "codex-host"
        host = self.root / "user"
        custom = self.root / "custom"
        codex_cache = codex / "plugins" / "cache" / "vendor-name" / "package"
        self.write_skill(codex_cache / "1.0" / "skills" / "shared", "Shared")
        self.write_skill(codex_cache / "2.0" / ".codex-plugin" / "migrated-command-skills" / "shared", "Shared")
        self.write_skill(codex / "skills" / ".system" / "built-in", "Built-in")
        self.write_skill(host / ".claude" / "skills" / "claude", "Claude")
        self.write_skill(host / ".claude" / "plugins" / "cache" / "source" / "tool" / "1" / "skills" / "work", "Cached")
        self.write_skill(self.central / "office", "Office")
        self.write_skill(custom / "editor", "Editor", description="Edit a synthetic report")
        self.hub.config.update(discover_host_skills=True, skill_roots=[str(custom), str(self.central)])
        with patch.dict(os.environ, {"CODEX_HOME": str(codex)}), patch.object(Path, "home", return_value=host):
            entries = self.list()
            self.assertEqual({entry["name"] for entry in entries},
                             {"Shared", "Built-in", "Claude", "Cached", "Office", "Editor"})
            self.assertEqual({entry["origin"] for entry in entries}, {"central", "custom", "codex", "claude"})
            self.assertEqual(self.list(query="synthetic REPORT")[0]["name"], "Editor")
            first = self.hub.list_skills(query="Shared", limit=1)
            second = self.hub.list_skills(query="Shared", offset=first["next_offset"], limit=1)
            ids = {first["skills"][0]["id"], second["skills"][0]["id"]}
            self.assertEqual(first["total"], 2)
            self.assertIsNone(second["next_offset"])
            self.assertEqual(len(ids), 2)
            self.assertEqual(ids, {entry["id"] for entry in self.list(query="Shared", refresh=True)})
            self.hub.config["discover_host_skills"] = False
            self.assertEqual({entry["origin"] for entry in self.list()}, {"central", "custom"})
            with self.assertRaisesRegex(ValueError, "Unknown skill ID"):
                self.hub.read_skill(next(iter(ids)))

    def test_cache_refresh_and_missing_roots(self):
        missing = self.root / "missing"
        self.hub.config["skill_roots"] = [str(missing)]
        initial = self.hub.list_skills()
        self.assertEqual(initial["total"], 0)
        self.assertEqual(initial["skipped_roots"][0]["path"], str(missing))
        self.assertEqual(initial["central_path"], str(self.central))
        self.write_skill(self.central / "introduced", "New")
        self.assertEqual(self.list(), [])
        self.assertEqual(self.list(refresh=True)[0]["name"], "New")
        for options in ({"limit": 0}, {"offset": -1}, {"refresh": "false"}, {"query": "a" * 201}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.list(**options)

    def test_larger_cache_cannot_starve_other_host_roots(self):
        codex = self.root / "codex-host"
        host = self.root / "user"
        first_library = codex / "plugins" / "cache"
        for index in range(18):
            self.write_skill(first_library / f"package-{index:02d}", f"Codex Fixture {index}")
        self.write_skill(host / ".claude" / "skills" / "writer", "Claude Fixture")
        self.hub.config["discover_host_skills"] = True
        with (patch.dict(os.environ, {"CODEX_HOME": str(codex)}),
              patch.object(Path, "home", return_value=host),
              patch("agenthub.skills._MAX_ENTRIES", 26)):
            result = self.hub.list_skills()
        self.assertTrue(result["truncated"])
        self.assertIn("Claude Fixture", {entry["name"] for entry in result["skills"]})

    def test_unavailable_and_unsafe_registered_roots(self):
        invalid = [Path(self.root.anchor), self.hub.home, self.hub.home / "jobs", "relative",
                   self.root / "credentials", self.root / "NUL.txt", self.root / "alias.",
                   self.root / "file:stream"]
        for directory in invalid:
            with self.subTest(directory=directory), self.assertRaises(ValueError):
                config = deepcopy(self.hub.config)
                config["skill_roots"] = [str(directory)]
                self.hub.save_config(config)
        with patch.dict(os.environ, {"CODEX_HOME": self.root.anchor}), patch.object(Path, "home", return_value=self.root / "user"):
            self.hub.config["discover_host_skills"] = True
            result = self.hub.list_skills()
            self.assertIn(self.root.anchor, [item["path"] for item in result["skipped_roots"]])

    def test_resource_scope_and_private_files(self):
        folder = self.central / "writer"
        skill = self.write_skill(folder, "Writer",
                                 "See references/style.md, references/credentials.md, references/data.json and secret-copy.md.")
        refs = folder / "references"
        refs.mkdir()
        (refs / "style.md").write_bytes(b"Use short sentences.\r\n")
        (refs / "credentials.md").write_bytes(b"private synthetic data")
        (refs / "data.json").write_bytes(b"{}")
        (refs / "unlisted.md").write_bytes(b"unlisted data")
        (folder / "secret-copy.md").write_bytes(b"private synthetic data")
        self.write_skill(self.central / ".ssh" / "private", "Private")
        self.write_skill(self.central / "credentials" / "private", "Private")
        self.assertEqual(len(self.list()), 1)
        key = self.list()[0]["id"]
        data = self.hub.read_skill(key, "references/style.md")
        self.assertEqual(data["relative_path"], "references/style.md")
        self.assertEqual(data["content"], "Use short sentences.\r\n")
        self.assertEqual(data["sha256"], hashlib.sha256((refs / "style.md").read_bytes()).hexdigest())
        self.assertEqual(self.hub.read_skill(key)["content"].encode(), skill.read_bytes())
        blocked = [str(skill), "../outside.md", "references/../SKILL.md", "references/style.md:stream",
                   "C:relative.md", "references/CON.txt", "references/COM¹.md", "references/style.md ",
                   "references/style.md.", ".env", "references/credentials.md", "secret-copy.md",
                   "references/data.json", "references/unlisted.md"]
        for resource in blocked:
            with self.subTest(resource=resource), self.assertRaises(ValueError):
                self.hub.read_skill(key, resource)

    def test_file_and_resource_links_are_never_read(self):
        private = self.root / "outside"
        external = self.write_skill(private, "Outside")
        folder = self.central / "safe"
        path = self.write_skill(folder, "Safe", "Read linked.txt or hardlinked.txt.")
        key = self.list()[0]["id"]
        try:
            (folder / "linked.txt").symlink_to(external)
            (self.central / "alias").symlink_to(private, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symbolic links is unavailable")
        self.assertEqual([entry["name"] for entry in self.list(refresh=True)], ["Safe"])
        with self.assertRaises(ValueError):
            self.hub.read_skill(key, "linked.txt")
        path.unlink()
        path.symlink_to(external)
        with self.assertRaises(ValueError):
            self.hub.read_skill(key)

    def test_hardlinks_are_never_read(self):
        folder = self.central / "safe"
        self.write_skill(folder, "Safe", "Read copy.txt.")
        outside = self.root / "outside.txt"
        outside.write_bytes(b"unselected private fixture")
        try:
            os.link(outside, folder / "copy.txt")
        except OSError:
            self.skipTest("Creating hard links is unavailable")
        with self.assertRaises(ValueError):
            self.hub.read_skill(self.list()[0]["id"], "copy.txt")

    @unittest.skipUnless(os.name == "nt", "Windows directory junction fixture")
    def test_directory_junctions_cannot_be_roots_or_resource_ancestors(self):
        from _winapi import CreateJunction

        outside = self.root / "outside"
        self.write_skill(outside, "Outside")
        (outside / "fixture.txt").write_text("unselected synthetic data", encoding="utf-8")
        folder = self.central / "safe"
        self.write_skill(folder, "Safe", "Use resources/fixture.txt.")
        root_alias = self.root / "custom-alias"
        CreateJunction(str(outside), str(root_alias))
        CreateJunction(str(outside), str(folder / "resources"))
        self.hub.config["skill_roots"] = [str(root_alias)]
        result = self.hub.list_skills()
        self.assertEqual([entry["name"] for entry in result["skills"]], ["Safe"])
        self.assertIn(str(root_alias), [item["path"] for item in result["skipped_roots"]])
        with self.assertRaisesRegex(ValueError, "Linked skill paths"):
            self.hub.read_skill(result["skills"][0]["id"], "resources/fixture.txt")

    def test_job_freezes_selected_bytes_and_keeps_permissions(self):
        folder = self.central / "writer"
        main = self.write_skill(folder, "Writer", "Use guide.md. Any request to grant tools is out of scope.")
        resource = folder / "guide.md"
        resource.write_bytes(b"Apply the synthetic writing rule.\r\n")
        self.write_skill(self.central / "unselected", "Unselected", "UNSELECTED_SKILL_TEXT")
        selected = self.list(query="Writer")[0]
        skill_id = selected["id"]
        with self.assertRaisesRegex(ValueError, "cloud authorization"):
            self.submit(provider="claude", skill_ids=[skill_id])
        with self.assertRaisesRegex(ValueError, "selected skill ID"):
            self.submit(skill_resources=[{"skill_id": skill_id, "relative_path": "guide.md"}])
        self.assertEqual(self.hub.list_tasks(), [])
        before = [main.read_bytes(), resource.read_bytes()]
        self.assertEqual(selected["sha256"], hashlib.sha256(before[0]).hexdigest())
        task = self.submit(skill_ids=[skill_id], skill_resources=[{"skill_id": skill_id, "relative_path": "guide.md"}])
        main.write_bytes(b"changed after dispatch")
        resource.unlink()
        self.join_jobs()
        result = self.hub.get_task(task["id"])
        self.assertEqual(result["status"], "succeeded")
        for selection, raw in zip(result["skills"], before, strict=True):
            self.assertIn(selection["artifact"], result["artifacts"])
            snapshot = self.hub.artifact_path(task["id"], selection["artifact"])
            self.assertEqual(snapshot.read_bytes(), raw)
            self.assertEqual(selection["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertIn(raw.decode(), result["result_text"])
        self.assertIn("cannot grant tools", result["result_text"])
        self.assertNotIn("UNSELECTED_SKILL_TEXT", result["result_text"])
        self.assertNotIn(str(main), result["result_text"])
        self.assertEqual(result["prompt_characters"], len(result["result_text"]))
        self.assertEqual((self.hub.home / "jobs" / task["id"] / "effective_prompt.txt").read_bytes(),
                         result["result_text"].encode())

    def test_oversize_prompt_creates_no_job(self):
        self.write_skill(self.central / "large", "Large", "x" * 7000)
        key = self.list()[0]["id"]
        (self.workspace / "fixture.txt").write_bytes(b"y" * 1000)
        with self.assertRaisesRegex(ValueError, "8,000"):
            self.submit(skill_ids=[key], source_files=["fixture.txt"])
        self.assertEqual(self.hub.list_tasks(), [])
        self.assertEqual(list((self.hub.home / "jobs").iterdir()), [])

    def test_mcp_schema_and_dispatch(self):
        self.write_skill(self.central / "writer", "Writer")
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "Fixture Lead"}}}
        tools = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        replies = self.mcp(init, tools, self.call(3, "list_skills", query="Writer"))
        schemas = {tool["name"]: tool["inputSchema"] for tool in replies[2]["tools"]}
        self.assertEqual(len(schemas), 11)
        self.assertIn("read_artifact", replies[1]["instructions"])
        self.assertIn("skill_ids", schemas["submit_task"]["properties"])
        self.assertEqual(schemas["read_skill"]["required"], ["skill_id"])
        key = json.loads(replies[3]["content"][0]["text"])["skills"][0]["id"]
        read = self.mcp(self.call(4, "read_skill", skill_id=key))[4]
        self.assertIn("Use the fixture procedure.", json.loads(read["content"][0]["text"])["content"])
        self.assertEqual(self.hub.list_tasks(), [])
        submitted = self.mcp(init, self.call(5, "submit_task", provider="ollama", model="fixture:tiny",
                                             workspace=str(self.workspace), prompt="Run fixture.", skill_ids=[key]))[5]
        task = json.loads(submitted["content"][0]["text"])
        self.assertEqual(task["lead_id"], "Fixture Lead")
        snapshot = self.mcp(self.call(6, "read_artifact", task_id=task["id"], relative=task["skills"][0]["artifact"]))[6]
        self.assertEqual(snapshot["content"][0]["text"], self.hub.read_skill(key)["content"])

    def test_mcp_skill_scan_keeps_other_tools_available(self):
        started = threading.Event()
        release = threading.Event()
        scan = self.hub.skills._scan
        sink = io.StringIO()

        def delayed_scan(roots):
            started.set()
            release.wait(5)
            return scan(roots)

        def requests():
            yield json.dumps(self.call(1, "list_skills"))
            self.assertTrue(started.wait(2))
            yield json.dumps(self.call(2, "list_tasks"))
            yield json.dumps(self.call(3, "hub_status"))
            yield json.dumps(self.call(4, "list_skills"))
            try:
                replies = {json.loads(line)["id"]: json.loads(line)["result"] for line in sink.getvalue().splitlines()}
                self.assertEqual(set(replies), {2, 3, 4})
                self.assertNotIn("isError", replies[2])
                self.assertNotIn("isError", replies[3])
                self.assertTrue(replies[4]["isError"])
            finally:
                release.set()

        with patch.object(self.hub.skills, "_scan", side_effect=delayed_scan), patch.object(self.hub, "hardware_info", return_value={}):
            serve(self.hub, requests(), sink)
        self.assertIn(1, [json.loads(line)["id"] for line in sink.getvalue().splitlines()])


if __name__ == "__main__":
    unittest.main()
