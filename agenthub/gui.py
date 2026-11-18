"""Native, standard-library desktop interface for Local Agent Orchestrator.

All Tk work stays on the main thread. Discovery results cross a queue; task
execution, policy checks, credential encryption and containment belong to Hub.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import queue
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .core import local_url


PROVIDER_LABELS = {
    "ollama": "Ollama", "lmstudio": "LM Studio",
    "openai_compatible": "OpenAI-compatible API", "gemini": "Google Gemini API",
    "claude": "Claude Code", "antigravity": "Antigravity",
    "opencode": "OpenCode", "codex": "Codex",
}
DEFAULT_URLS = {
    "ollama": "http://127.0.0.1:11434",
    "lmstudio": "http://127.0.0.1:1234/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
}


class App(ttk.Frame):
    """Embeddable application frame; constructing it does not start mainloop."""

    def __init__(self, hub, mcp_executable: str = "", master=None):
        self.root = master if master is not None else tk.Tk()
        super().__init__(self.root)
        self.hub = hub
        self.mcp_executable = mcp_executable
        self.models = []
        self.discovery_done = False
        self.events = queue.Queue()
        self.source_files = []
        self.images = []
        self.skills = []
        self.assigned_skills = {}
        self.skills_loading = False
        self.skills_offset = 0
        self.skills_next = None
        self.selected_task = None
        self.detail_signature = None
        self.review_fields = []
        self._closed = False
        self._timer = None
        self._model_refresh_signature = None
        self._model_status_snapshot = {}
        self._setup_style()
        self.root.title(f"Local Agent Orchestrator · {__version__}")
        self.root.geometry("1180x880")
        self.root.minsize(940, 730)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.pack(fill="both", expand=True)
        self._build()
        self._refresh_tasks()
        self._timer = self.root.after(700, self._poll)

    def _setup_style(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background="#f4f6fa", foreground="#18263b")
        style.configure("TFrame", background="#f4f6fa")
        style.configure("TLabel", background="#f4f6fa")
        style.configure("Muted.TLabel", foreground="#58687d")
        style.configure("Title.TLabel", font=("Segoe UI", 19, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("TButton", padding=(13, 8))
        style.configure("TNotebook", tabmargins=(0, 9, 0, 0))
        style.configure("TNotebook.Tab", padding=(16, 10))
        style.configure("Treeview", rowheight=31, background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=(8, 9))
        style.configure("Accent.TButton", foreground="white", background="#285cc4")
        style.map("Accent.TButton", background=[("active", "#194aa8")])

    def _build(self):
        header = tk.Frame(self, background="#14243e", padx=27, pady=19)
        header.pack(fill="x")
        tk.Label(header, text="Local Agent Orchestrator", font=("Segoe UI", 21, "bold"),
                 foreground="white", background="#14243e").pack(anchor="w")
        tk.Label(header, text="Your models. Your accounts. A visible review before acceptance.",
                 font=("Segoe UI", 10), foreground="#c4d1e5", background="#14243e").pack(anchor="w", pady=(4, 0))
        body = ttk.Frame(self, padding=(23, 8, 23, 10))
        body.pack(fill="both", expand=True)
        self.notebook = ttk.Notebook(body)
        self.notebook.pack(fill="both", expand=True)
        self.pages = {}
        for name in ("Overview", "Models", "Skills", "Run task", "Tasks & review", "Settings", "Connections"):
            page = ttk.Frame(self.notebook, padding=19)
            self.notebook.add(page, text=name)
            self.pages[name] = self._scrollable(page) if name in ("Run task", "Settings") else page
        self._overview()
        self._models()
        self._skills()
        self._run_task()
        self._tasks()
        self._settings()
        self._connections()
        self.status = tk.StringVar(value="Ready. Refresh models when your providers are configured.")
        ttk.Label(body, textvariable=self.status, style="Muted.TLabel", padding=(2, 10, 0, 0)).pack(fill="x")

    def _heading(self, parent, title, description):
        ttk.Label(parent, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(parent, text=description, style="Muted.TLabel", wraplength=1000).pack(anchor="w", pady=(5, 17))

    def _scrollable(self, parent):
        canvas = tk.Canvas(parent, background="#f4f6fa", highlightthickness=0)
        bar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        interior = ttk.Frame(canvas, padding=(0, 0, 12, 0))
        window = canvas.create_window((0, 0), window=interior, anchor="nw")
        interior.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        return interior

    @staticmethod
    def _text(parent, height=6, editable=True):
        holder = ttk.Frame(parent)
        box = tk.Text(holder, height=height, wrap="word", font=("Segoe UI", 10),
                      relief="solid", borderwidth=1, padx=10, pady=9, background="white",
                      foreground="#18263b", selectbackground="#bed4f6", undo=editable)
        scrollbar = ttk.Scrollbar(holder, orient="vertical", command=box.yview)
        box.configure(yscrollcommand=scrollbar.set)
        box.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        holder.pack(fill="both", expand=True, pady=(5, 10))
        if not editable:
            box.configure(state="disabled")
        return box

    @staticmethod
    def _put(box, text):
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")

    def _overview(self):
        page = self.pages["Overview"]
        self._heading(page, "A local workspace for agent work", "Discover configured providers, run a bounded task, then inspect and review its result.")
        row = ttk.Frame(page)
        row.pack(fill="x", pady=(0, 18))
        self.model_summary = tk.StringVar(value="Models\nNot refreshed yet")
        self.task_summary = tk.StringVar(value="Tasks\nLoading…")
        for title in (self.model_summary, self.task_summary):
            card = ttk.LabelFrame(row, padding=18)
            card.pack(side="left", fill="both", expand=True, padx=(0, 12))
            ttk.Label(card, textvariable=title, font=("Segoe UI", 12), justify="left").pack(anchor="w")
        ttk.Label(page, text="This computer", style="Section.TLabel").pack(anchor="w", pady=(3, 5))
        self.hardware_box = self._text(page, height=8, editable=False)
        try:
            hardware = self.hub.hardware_info()
            self._put(self.hardware_box, self._hardware_text(hardware))
        except Exception:
            self._put(self.hardware_box, "Hardware details could not be read on this computer.")
        ttk.Label(page, text=f"Version {__version__} · Open-source preview", style="Section.TLabel").pack(anchor="w", pady=(8, 5))
        ttk.Label(page, wraplength=980, justify="left", style="Muted.TLabel", text=(
            "The Orchestrator has no telemetry or public listener. Local providers keep work local when configured that way. "
            "Cloud APIs and subscription tools send task data to their provider and may use your account allowance or incur charges. "
            "External models, tools and providers keep their own licenses and terms."
        )).pack(anchor="w")
        credit = ttk.Frame(page)
        credit.pack(anchor="w", pady=(12, 0))
        ttk.Label(credit, text="Created by Mehrab Mashrafi (@2mdipro7) · ", style="Muted.TLabel").pack(side="left")
        for label, url in (("GitHub", "https://github.com/2mdipro7"),
                           ("Portfolio", "https://2mdipro7.github.io/")):
            link = tk.Label(credit, text=label, foreground="#285cc4", background="#f4f6fa", cursor="hand2", font=("Segoe UI", 10, "underline"))
            link.pack(side="left", padx=(0, 10))
            link.bind("<Button-1>", lambda _event, target=url: webbrowser.open(target))
        ttk.Button(page, text="Refresh available models", command=self.refresh_models, style="Accent.TButton").pack(anchor="w", pady=19)

    @staticmethod
    def _hardware_text(hardware):
        if not isinstance(hardware, dict):
            return str(hardware)
        lines = []
        gpu_rows = str(hardware.get("gpu") or "Not detected").splitlines()
        for index, row in enumerate(gpu_rows, start=1):
            values = [value.strip() for value in row.split(",", 2)]
            label = f"GPU {index}" if len(gpu_rows) > 1 else "GPU"
            lines.append(f"{label}: {values[0]}")
            if len(values) == 3:
                lines.extend((f"Video memory: {values[1]}", f"Available video memory: {values[2]}"))
            lines.append("")
        threads = hardware.get("logical_processors")
        lines.append(f"CPU threads: {threads if threads is not None else 'Not available'}")
        if hardware.get("gpu_policy"):
            lines.append(f"Local task policy: {hardware['gpu_policy']}")
        return "\n".join(lines)

    def _models(self):
        page = self.pages["Models"]
        self._heading(page, "Available models", "Only provider discovery results appear here. Refresh after changing settings or starting a local model server.")
        self.refresh_button = ttk.Button(page, text="Refresh models", command=self.refresh_models)
        self.refresh_button.pack(anchor="w", pady=(0, 4))
        self.test_button = ttk.Button(page, text="Test selected model", command=self._test_selected_model)
        self.test_button.pack(anchor="w", pady=(0, 12))
        self.model_tree = self._tree(page, [("provider", "Provider", 170), ("model", "Model", 440),
                                             ("modality", "Modality", 140), ("status", "Last response test", 240)])
        self.model_tree.tag_configure("tested", foreground="#087c32")
        self.model_tree.bind("<<TreeviewSelect>>", self._model_selected)
        self.model_detail = tk.StringVar(value="Select a model to see its last response test.")
        ttk.Label(page, textvariable=self.model_detail, wraplength=1000).pack(anchor="w", pady=(8, 0))
        self.discovery_note = tk.StringVar(value="No discovery has run yet.")
        ttk.Label(page, textvariable=self.discovery_note, style="Muted.TLabel", wraplength=1000).pack(anchor="w", pady=10)

    def _tree(self, parent, columns, height=8):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=height, selectmode="browse")
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=75, stretch=True)
        y = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        x = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def _skills(self):
        page = self.pages["Skills"]
        self._heading(page, "Shared skills", "Find guidance from your Codex and Claude folders or a shared library. Only skills you assign are included in a worker request.")
        self.host_skills = tk.BooleanVar(value=self.hub.config.get("discover_host_skills", True))
        ttk.Checkbutton(page, text="Discover existing Codex and Claude skills", variable=self.host_skills,
                        command=self._save_skill_discovery).pack(anchor="w")
        folders = ttk.Frame(page)
        folders.pack(fill="x", pady=(6, 4))
        ttk.Button(folders, text="Open central library", command=self._open_skill_library).pack(side="left", padx=(0, 8))
        ttk.Button(folders, text="Add skill folder…", command=self._add_skill_root).pack(side="left", padx=(0, 8))
        ttk.Button(folders, text="Remove custom folders", command=self._clear_skill_roots).pack(side="left")
        self.skill_roots_note = tk.StringVar()
        ttk.Label(page, textvariable=self.skill_roots_note, wraplength=1000, style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        self._skill_roots_status()
        search = ttk.Frame(page)
        search.pack(fill="x", pady=(0, 8))
        self.skill_query = tk.StringVar()
        entry = ttk.Entry(search, textvariable=self.skill_query)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        entry.bind("<Return>", lambda _e: self.refresh_skills())
        self.skill_refresh = ttk.Button(search, text="Find / refresh skills", command=self.refresh_skills)
        self.skill_refresh.pack(side="left")
        self.skill_next_button = ttk.Button(search, text="Next page", command=self._next_skills, state="disabled")
        self.skill_next_button.pack(side="left", padx=(8, 0))
        self.skill_tree = self._tree(page, [("name", "Skill", 230), ("origin", "Source", 160), ("description", "Description", 550)], height=5)
        self.skill_tree.configure(selectmode="extended")
        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=7)
        ttk.Button(actions, text="Read selected skill", command=self._read_selected_skill).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Assign selected to next task", command=self._assign_selected_skills).pack(side="left")
        self.skill_note = tk.StringVar(value="Refresh to discover skills. Discovery reads local skill files and makes no model requests.")
        ttk.Label(page, textvariable=self.skill_note, wraplength=1000, style="Muted.TLabel").pack(anchor="w")
        self.skill_preview = self._text(page, height=6, editable=False)

    def _skill_roots_status(self):
        roots = self.hub.config.get("skill_roots", [])
        text = "Central library: " + str(self.hub.home / "skills")
        if roots:
            text += "\nCustom folders: " + "; ".join(roots)
        self.skill_roots_note.set(text)

    def _save_skill_config(self, config):
        try:
            self.hub.save_config(config)
            self._clear_skills()
            self._skill_roots_status()
            self.refresh_skills()
        except Exception as exc:
            self.host_skills.set(self.hub.config.get("discover_host_skills", True))
            self._error("Could not save skill folders", exc)

    def _save_skill_discovery(self):
        config = copy.deepcopy(self.hub.config)
        config["discover_host_skills"] = self.host_skills.get()
        self._save_skill_config(config)

    def _add_skill_root(self):
        folder = filedialog.askdirectory(parent=self.root, title="Choose a folder containing skills", mustexist=True)
        if folder:
            config = copy.deepcopy(self.hub.config)
            roots = config.setdefault("skill_roots", [])
            if folder not in roots:
                roots.append(folder)
            self._save_skill_config(config)

    def _clear_skill_roots(self):
        config = copy.deepcopy(self.hub.config)
        config["skill_roots"] = []
        self._save_skill_config(config)

    def _open_skill_library(self):
        try:
            folder = self.hub.home / "skills"
            folder.mkdir(exist_ok=True)
            os.startfile(str(folder))
        except Exception as exc:
            self._error("Could not open skill library", exc)

    def refresh_skills(self, offset=0):
        if self.skills_loading:
            return
        self.skills_loading = True
        self.skill_refresh.configure(state="disabled")
        self.skill_next_button.configure(state="disabled")
        self.skill_note.set("Reading local skill metadata…")
        query = self.skill_query.get().strip()

        def discover():
            try:
                result = self.hub.list_skills(query=query, offset=offset, limit=50, refresh=offset == 0)
                self.events.put(("skills_list", (offset, result)))
            except Exception as exc:
                self.events.put(("skills_error", exc))
        threading.Thread(target=discover, daemon=True, name="hub-skill-discovery").start()

    def _next_skills(self):
        if self.skills_next is not None:
            self.refresh_skills(self.skills_next)

    def _skill_event(self, event, payload):
        if event == "skills_preview":
            self._put(self.skill_preview, payload)
            return
        self.skills_loading = False
        self.skill_refresh.configure(state="normal")
        if event == "skills_error":
            self.skill_note.set("Could not read the skill library. Check its folders and try again.")
            self._error("Could not read skills", payload)
            return
        self.skills_offset, result = payload
        self.skills = result["skills"]
        self.skills_next = result.get("next_offset")
        self.skill_tree.delete(*self.skill_tree.get_children())
        for skill in self.skills:
            self.skill_tree.insert("", "end", iid=skill["id"], values=(skill["name"], skill.get("origin", ""), skill.get("description", "")))
        self.skill_next_button.configure(state="normal" if self.skills_next is not None else "disabled")
        note = f"Showing {len(self.skills)} of {result['total']} matching skills. Select one to read; Ctrl-click to select several."
        if result.get("truncated"):
            note += " Discovery reached its scan limit; use a smaller skill folder for missing entries."
        if result.get("skipped_roots"):
            note += f" {len(result['skipped_roots'])} unavailable or skipped folder(s)."
        self.skill_note.set(note)

    def _read_selected_skill(self):
        selected = self.skill_tree.selection()
        if not selected:
            return self._warning("Choose a skill", "Select a skill to read its instructions.")
        skill_id = selected[0]

        def read():
            try:
                skill = self.hub.read_skill(skill_id)
                text = f"{skill['name']}\nSource: {skill.get('path', '')}\nSHA-256: {skill['sha256']}\n\n{skill['content']}"
                self.events.put(("skills_preview", text))
            except Exception as exc:
                self.events.put(("skills_error", exc))
        threading.Thread(target=read, daemon=True, name="hub-skill-preview").start()

    def _assign_selected_skills(self):
        selected = set(self.skill_tree.selection())
        if not selected:
            return self._warning("Choose a skill", "Select the skills needed for your next task.")
        for skill in self.skills:
            if skill["id"] in selected:
                self.assigned_skills[skill["id"]] = skill["name"]
        self.assigned_skill_note.set("Assigned skills: " + "; ".join(self.assigned_skills.values()))
        self.status.set("Skills assigned to the next task. Their full text counts toward the prompt limit.")

    def _clear_skills(self):
        self.assigned_skills.clear()
        self.assigned_skill_note.set("No shared skills assigned. Choose skills in the Skills tab.")

    def _run_task(self):
        page = self.pages["Run task"]
        self._heading(page, "Give a model a specific task", "Choose a discovered model and attach only the files this task needs, within the chosen workspace. The Orchestrator does not silently read a workspace folder.")
        form = ttk.Frame(page)
        form.pack(fill="x")
        self.provider = tk.StringVar()
        self.model = tk.StringVar()
        self.kind = tk.StringVar(value="text")
        self.provider_pick = ttk.Combobox(form, textvariable=self.provider, state="readonly", width=23)
        self.model_pick = ttk.Combobox(form, textvariable=self.model, state="readonly", width=43)
        for col, (label, widget) in enumerate((
            ("Provider", self.provider_pick), ("Model", self.model_pick),
            ("Task kind", ttk.Combobox(form, textvariable=self.kind, values=("text", "image"), state="readonly", width=12))
        )):
            ttk.Label(form, text=label).grid(row=0, column=col, sticky="w", padx=(0, 12))
            widget.grid(row=1, column=col, sticky="ew", padx=(0, 12), pady=(5, 12))
        form.columnconfigure(1, weight=1)
        self.provider_pick.bind("<<ComboboxSelected>>", self._provider_changed)
        self.workspace = tk.StringVar(value=str(Path.cwd()))
        pathrow = ttk.Frame(page)
        pathrow.pack(fill="x", pady=(0, 10))
        ttk.Label(pathrow, text="Workspace", width=12).pack(side="left")
        ttk.Entry(pathrow, textvariable=self.workspace).pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Button(pathrow, text="Browse…", command=self._browse_workspace).pack(side="left")
        caption = ttk.Frame(page)
        caption.pack(fill="x")
        ttk.Label(caption, text="Task prompt", style="Section.TLabel").pack(side="left")
        self.prompt_count = tk.StringVar(value="0 / 8,000 characters")
        ttk.Label(caption, textvariable=self.prompt_count, style="Muted.TLabel").pack(side="right")
        self.prompt = self._text(page, height=7)
        self.prompt.bind("<<Modified>>", self._count_prompt)
        ttk.Label(page, text="Include the outcome, audience, constraints and how the result will be checked. Guardrails, selected skills and attachments also use the 8,000-character assembled limit.",
                  wraplength=1000, style="Muted.TLabel").pack(anchor="w")
        attach = ttk.Frame(page)
        attach.pack(fill="x", pady=(10, 4))
        ttk.Button(attach, text="Attach source files…", command=lambda: self._attach(False)).pack(side="left", padx=(0, 8))
        ttk.Button(attach, text="Attach images…", command=lambda: self._attach(True)).pack(side="left", padx=(0, 8))
        ttk.Button(attach, text="Clear attachments", command=self._clear_attachments).pack(side="left")
        self.attachment_note = tk.StringVar(value="No files attached.")
        ttk.Label(page, textvariable=self.attachment_note, wraplength=1000, style="Muted.TLabel").pack(anchor="w", pady=(3, 10))
        self.assigned_skill_note = tk.StringVar(value="No shared skills assigned. Choose skills in the Skills tab.")
        ttk.Label(page, textvariable=self.assigned_skill_note, wraplength=1000).pack(anchor="w", pady=(0, 5))
        skill_actions = ttk.Frame(page)
        skill_actions.pack(fill="x", pady=(0, 10))
        ttk.Button(skill_actions, text="Choose shared skills", command=lambda: self.notebook.select(self.pages["Skills"])).pack(side="left", padx=(0, 8))
        ttk.Button(skill_actions, text="Clear assigned skills", command=self._clear_skills).pack(side="left")
        self.allow_cloud = tk.BooleanVar(value=False)
        ttk.Checkbutton(page, variable=self.allow_cloud, text="Allow this task to use the configured cloud/API or subscription provider").pack(anchor="w")
        ttk.Label(page, text="Task data leaves this PC. Your own provider account may be charged or use its subscription allowance.",
                  style="Muted.TLabel", wraplength=1000).pack(anchor="w", pady=(3, 8))
        ttk.Button(page, text="Submit task", style="Accent.TButton", command=self._submit).pack(anchor="w")

    def _tasks(self):
        page = self.pages["Tasks & review"]
        self._heading(page, "Tasks & human review", "A completed run still needs a review. Inspect the output and sources before accepting any result.")
        self.task_tree = self._tree(page, [("id", "Task", 180), ("provider", "Provider", 130),
            ("model", "Model", 210), ("status", "Run status", 100), ("review", "Review", 130)], height=4)
        self.task_tree.bind("<<TreeviewSelect>>", self._task_selected)
        actions = ttk.Frame(page)
        actions.pack(fill="x", pady=8)
        ttk.Button(actions, text="Refresh tasks", command=self._refresh_tasks).pack(side="left")
        self.cancel_button = ttk.Button(actions, text="Cancel selected task", command=self._cancel_task, state="disabled")
        self.cancel_button.pack(side="left", padx=8)
        self.detail_tabs = ttk.Notebook(page)
        self.detail_tabs.pack(fill="both", expand=True)
        output = ttk.Frame(self.detail_tabs, padding=10)
        review_page = ttk.Frame(self.detail_tabs, padding=10)
        self.detail_tabs.add(output, text="Output & artifacts")
        self.detail_tabs.add(review_page, text="Review decision")
        review = self._scrollable(review_page)
        self.output_box = self._text(output, height=7, editable=False)
        self.artifacts = tk.Listbox(output, height=2, font=("Segoe UI", 10), background="white", exportselection=False)
        self.artifacts.pack(fill="x")
        self.artifact_refs = []
        ttk.Button(output, text="Open selected job output", command=self._open_artifact).pack(anchor="w", pady=(7, 0))
        reviewer = ttk.Frame(review)
        reviewer.pack(fill="x")
        ttk.Label(reviewer, text="Reviewer label").pack(side="left")
        self.lead_id = tk.StringVar(value="desktop-user")
        ttk.Entry(reviewer, textvariable=self.lead_id, width=25).pack(side="left", padx=10)
        ttk.Label(reviewer, text="Audit label only; it does not authenticate identity.", style="Muted.TLabel").pack(side="left")
        self.criteria_frame = ttk.Frame(review)
        self.criteria_frame.pack(fill="x", pady=8)
        ttk.Label(review, text="Review summary and independent checks").pack(anchor="w")
        self.review_summary = self._text(review, height=2)
        ttk.Label(review, text="Boundary review: scope, permissions, sources and side effects").pack(anchor="w")
        self.boundary = tk.StringVar()
        ttk.Entry(review, textvariable=self.boundary).pack(fill="x", pady=(5, 7))
        ttk.Label(review, text="Limitations or skipped checks (optional; separate with semicolons)").pack(anchor="w")
        self.limitations = tk.StringVar()
        ttk.Entry(review, textvariable=self.limitations).pack(fill="x", pady=(5, 7))
        bottom = ttk.Frame(review)
        bottom.pack(fill="x")
        self.decision = tk.StringVar(value="revision_required")
        ttk.Combobox(bottom, textvariable=self.decision, values=("accepted", "revision_required", "rejected"), state="readonly", width=20).pack(side="left")
        ttk.Button(bottom, text="Record explicit review", command=self._review).pack(side="left", padx=10)
        ttk.Label(bottom, text="Acceptance requires every criterion to pass with evidence.", style="Muted.TLabel").pack(side="left")

    def _settings(self):
        page = self.pages["Settings"]
        self._heading(page, "Provider settings", "Enable the providers you use. API keys are stored with Windows protection, separately from settings, and are never displayed after saving.")
        self.setting_fields = {}
        rows = ttk.Frame(page)
        rows.pack(fill="x")
        for col, title in enumerate(("Provider", "Enabled", "Base URL", "New API key (optional)")):
            ttk.Label(rows, text=title, style="Section.TLabel").grid(row=0, column=col, sticky="w", padx=(0, 12), pady=(0, 10))
        config = self.hub.config.get("providers", {})
        for row, (name, label) in enumerate(PROVIDER_LABELS.items(), start=1):
            saved = config.get(name, {})
            enabled = tk.BooleanVar(value=bool(saved.get("enabled", False)))
            url = tk.StringVar(value=saved.get("base_url", DEFAULT_URLS.get(name, "")))
            key = tk.StringVar()
            ttk.Label(rows, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=9)
            ttk.Checkbutton(rows, variable=enabled).grid(row=row, column=1, sticky="w")
            ttk.Entry(rows, textvariable=url, width=41).grid(row=row, column=2, sticky="ew", padx=(0, 12))
            ttk.Entry(rows, textvariable=key, show="●", width=25).grid(row=row, column=3, sticky="ew")
            self.setting_fields[name] = (enabled, url, key)
        rows.columnconfigure(2, weight=1)
        ttk.Label(page, text="Leave a new-key field blank to keep the existing secret. This screen never reads keys from environment variables. CLI login and installation happen outside this app.",
                  wraplength=1000, style="Muted.TLabel").pack(anchor="w", pady=(18, 12))
        ttk.Button(page, text="Save provider settings", command=self._save_settings, style="Accent.TButton").pack(anchor="w")
        self.settings_status = tk.StringVar()
        ttk.Label(page, textvariable=self.settings_status, style="Muted.TLabel", wraplength=1000).pack(anchor="w", pady=12)

    def _connections(self):
        page = self.pages["Connections"]
        self._heading(page, "Connect your lead assistant", "Any compatible MCP lead can use the Orchestrator: Codex, Claude, OpenCode and other clients with local MCP support.")
        ttk.Label(page, text="Configure Claude Desktop, Claude Code, Codex or Antigravity below. Missing configuration files are created. Each host must be installed, signed in and restarted separately. Other clients can use the exported connection; web-only services need a compatible local connector.",
                  wraplength=1000, style="Muted.TLabel").pack(anchor="w", pady=(0, 12))
        self.connection_box = self._text(page, height=6, editable=False)
        try:
            self.connection_json = json.dumps(self.hub.connection_config(self.mcp_executable), indent=2)
            self._put(self.connection_box, self.connection_json)
        except Exception:
            self.connection_json = ""
            self._put(self.connection_box, "Connection settings could not be generated. Check the Orchestrator installation path.")
        actions = ttk.Frame(page)
        actions.pack(fill="x")
        ttk.Button(actions, text="Copy JSON", command=self._copy_connection).pack(side="left", padx=(0, 10))
        ttk.Button(actions, text="Export JSON…", command=self._export_connection).pack(side="left")
        ttk.Label(page, text="Connected leads can submit and review tasks. Keep access to your local account and MCP client under your control.",
                  wraplength=1000, style="Muted.TLabel").pack(anchor="w", pady=17)
        self.host_frame = ttk.Frame(page)
        self.host_frame.pack(fill="x")
        self._refresh_hosts()

    def _refresh_hosts(self):
        from .hosts import host_statuses, SERVER
        for child in self.host_frame.winfo_children():
            child.destroy()
        if not self.connection_json:
            return
        entry = json.loads(self.connection_json)['mcpServers'][SERVER]
        targets = host_statuses(entry)
        ttk.Button(self.host_frame, text="Refresh connection locations", command=self._refresh_hosts).pack(anchor="w")
        for target in targets:
            row = ttk.Frame(self.host_frame)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=target['name'] + '\n' + target['status'], wraplength=840).pack(side="left")
            if target['status'] == 'Not connected':
                ttk.Button(row, text="Connect", command=lambda t=target: self._connect_host(t)).pack(side="right")
        if not targets:
            ttk.Label(self.host_frame, text="No supported host configuration found. Open the host's local MCP settings and create its configuration, then refresh, or use the exported configuration.", wraplength=950).pack(anchor="w")

    def _connect_host(self, target):
        from .hosts import register_host, SERVER
        try:
            entry = json.loads(self.connection_json)['mcpServers'][SERVER]
            register_host(target['path'], entry, target['format'])
            self._refresh_hosts()
            self.status.set('Configured ' + target['name'] + '. Fully quit and reopen that app to load its tools.')
        except (ValueError, OSError) as exc:
            self._error('Connection was not changed', exc)

    def refresh_models(self):
        if getattr(self, "discovering", False):
            return
        self.discovering = True
        self.refresh_button.configure(state="disabled")
        self.discovery_note.set("Checking configured providers…")
        self.status.set("Discovering models. You can continue using the Orchestrator.")

        def discover():
            try:
                self.events.put(("models", self.hub.discover_models()))
            except Exception:
                self.events.put(("discovery_error", None))
        threading.Thread(target=discover, daemon=True, name="hub-model-discovery").start()

    def _poll(self):
        if self._closed:
            return
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event.startswith("skills"):
                    self._skill_event(event, payload)
                    continue
                self.discovering = False
                self.refresh_button.configure(state="normal")
                if event == "models":
                    self.models = list(payload or [])
                    self.discovery_done = True
                    self._display_models()
                else:
                    self.models = []
                    self._display_models(update_summary=False)
                    self.discovery_note.set("Model discovery did not finish. Check provider settings and try again.")
                    self.status.set("Could not refresh available models.")
        except queue.Empty:
            pass
        tasks = self._refresh_tasks(quiet=True)
        if self.discovery_done and tasks is not None:
            try:
                credential_stat = self.hub.secrets.path.stat()
                credential_revision = (credential_stat.st_mtime_ns, credential_stat.st_size)
            except FileNotFoundError:
                credential_revision = None
            signature = (tuple((t["id"], t.get("updated_at")) for t in tasks),
                         json.dumps(self.hub.config["providers"], sort_keys=True), credential_revision)
            if signature != self._model_refresh_signature:
                self._model_refresh_signature = signature
                self._display_models(update_summary=False)
        self._timer = self.root.after(1100, self._poll)

    @staticmethod
    def _model_id(model):
        return str(model.get("id") or model.get("model") or model.get("name") or "")

    def _model_status(self, model):
        provider, mid = model.get("provider", ""), self._model_id(model)
        if model.get("status") in ("unavailable", "discovery_only") or not mid:
            return {"state": "unavailable", "reason": model.get("reason") or "Unavailable for text testing; check provider setup."}
        modality = model.get("modality", model.get("modalities", "text"))
        if isinstance(modality, list):
            modality = ", ".join(str(x) for x in modality)
        if "text" not in str(modality).lower():
            return {"state": "unsupported", "reason": "Text response testing is not supported for this entry."}
        snapshot = getattr(self, "_model_status_snapshot", {})
        return snapshot.get((provider, mid)) or self.hub.model_test_status(provider, mid)

    def _model_selected(self, _event=None):
        selected = self.model_tree.selection()
        if not selected:
            return
        model = self.models[int(selected[0])]
        info = self._model_status(model)
        task = info.get("task", {})
        if info["state"] == "tested":
            completed = task.get("completed_at")
            timestamp = completed or task.get("updated_at") or task.get("created_at", "unknown")
            time_label = timestamp if completed else f"{timestamp} (legacy record; completion time unavailable)"
            message = f"Last response tested {time_label} · job {task.get('id', '')}. Requested model; provider identity may not be reported. CLI installation and account state may change. Retest after changes."
        else:
            message = info.get("reason") or (f"Test running · job {task.get('id', '')}" if info["state"] == "testing" else "Not tested.")
            if task and info["state"] == "failed":
                message += f" · job {task.get('id', '')} · {task.get('completed_at') or task.get('updated_at', '')}"
        self.model_detail.set(message)
        self.test_button.configure(state="disabled" if info["state"] in ("testing", "unavailable", "unsupported") else "normal")

    def _test_selected_model(self):
        selected = self.model_tree.selection()
        if not selected:
            return self._warning("Choose a model", "Select a model first.")
        model = self.models[int(selected[0])]
        if self._model_status(model)["state"] in ("testing", "unavailable", "unsupported"):
            return
        provider, mid = model.get("provider", ""), self._model_id(model)
        cfg = self.hub.config["providers"].get(provider, {})
        local = provider in ("ollama", "lmstudio") or (provider == "openai_compatible" and local_url(cfg.get("base_url", "")))
        if provider == "ollama" and (mid.lower().endswith("-cloud") or ":cloud" in mid.lower()):
            local = False
        if not local and not messagebox.askyesno("Test using your account?", f"This test sends a short synthetic arithmetic prompt to {provider} / {mid} using your configured account or API service. It may consume subscription or API usage. Continue?", parent=self.root):
            return
        try:
            task = self.hub.test_model(provider, mid, allow_cloud=not local)
            self.status.set(f"Model response test submitted: {task['id']}.")
            self._display_models(update_summary=False)
        except Exception as exc:
            self._error("Model test was not submitted", exc)

    def _display_models(self, update_summary=True):
        selected = self.model_tree.selection()
        selected_key = None
        if selected:
            values = self.model_tree.item(selected[0], "values")
            selected_key = tuple(values[:2])
        self._model_status_snapshot = self.hub.model_test_statuses(
            [(m.get("provider", ""), self._model_id(m)) for m in self.models])
        self.model_tree.delete(*self.model_tree.get_children())
        labels = {"tested": "✓ Last response tested", "testing": "Testing…", "untested": "Untested", "failed": "Failed", "unavailable": "Unavailable", "unsupported": "Unsupported"}
        for index, model in enumerate(self.models):
            modality = model.get("modality", model.get("modalities", "text"))
            if isinstance(modality, list):
                modality = ", ".join(str(x) for x in modality)
            info = self._model_status(model)
            key = (model.get("provider", ""), self._model_id(model))
            iid = str(index)
            self.model_tree.insert("", "end", iid=iid, values=(*key, modality, labels[info["state"]]), tags=(info["state"],))
            if key == selected_key:
                self.model_tree.selection_set(iid)
        if self.model_tree.selection():
            self._model_selected()
        selectable = self._selectable_models()
        providers = sorted({str(m.get("provider", "")) for m in selectable if m.get("provider")})
        self.provider_pick.configure(values=providers)
        if self.provider.get() not in providers:
            self.provider.set(providers[0] if providers else "")
        self._provider_changed()
        self.model_summary.set(f"Discovered models\n{len(selectable)} across {len(providers)} providers")
        if update_summary:
            self.discovery_note.set(f"Discovery returned {len(selectable)} selectable models. A green tick means the last synthetic response test passed with current saved settings. CLI installs and accounts can change; retest after changes.")
            self.status.set("Model discovery finished.")

    def _selectable_models(self):
        return [m for m in self.models if m.get("status") not in ("unavailable", "discovery_only") and (m.get("id") or m.get("model"))]

    def _provider_changed(self, _event=None):
        models = [self._model_id(m) for m in self._selectable_models() if m.get("provider") == self.provider.get()]
        self.model_pick.configure(values=models)
        if self.model.get() not in models:
            self.model.set(models[0] if models else "")

    def _browse_workspace(self):
        folder = filedialog.askdirectory(parent=self.root, title="Choose task workspace", mustexist=True)
        if folder:
            self.workspace.set(folder)

    def _attach(self, image):
        paths = filedialog.askopenfilenames(parent=self.root, title="Choose task images" if image else "Choose explicit source files",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")] if image else [("All files", "*.*")])
        target = self.images if image else self.source_files
        for path in paths:
            if path not in target:
                target.append(path)
        self._attachment_status()

    def _clear_attachments(self):
        self.source_files.clear()
        self.images.clear()
        self._attachment_status()

    def _attachment_status(self):
        names = ["Source: " + Path(p).name for p in self.source_files] + ["Image: " + Path(p).name for p in self.images]
        self.attachment_note.set("; ".join(names) if names else "No files attached.")

    def _count_prompt(self, _event=None):
        if not self.prompt.edit_modified():
            return
        count = len(self.prompt.get("1.0", "end-1c"))
        suffix = " — leave room for guardrails and attached source content" if count > 6500 else ""
        self.prompt_count.set(f"{count:,} / 8,000 characters{suffix}")
        self.prompt.edit_modified(False)

    def _submit(self):
        prompt = self.prompt.get("1.0", "end-1c").strip()
        if not self.provider.get() or not self.model.get():
            return self._warning("Choose a model", "Refresh models, then choose a provider and model.")
        if not prompt:
            return self._warning("Add a task prompt", "Describe the outcome and how it should be checked.")
        if len(prompt) > 8000:
            return self._warning("Shorten this prompt", "The prompt exceeds 8,000 characters. Guardrails and attachments need space within that limit too.")
        if self.kind.get() == "image" and self.provider.get() not in ("gemini", "openai_compatible"):
            return self._warning("Choose an image-capable provider", "Image generation in this preview uses Gemini or an image-capable OpenAI-compatible endpoint. Choose a model that supports image output.")
        if self.images and self.provider.get() in ("claude", "antigravity", "codex", "opencode"):
            return self._warning("Image input is unavailable", "Image attachments are not supported by this subscription-tool adapter. Choose a provider with image input or remove the images.")
        if self.provider.get() in ("gemini", "openai_compatible", "claude", "antigravity", "codex", "opencode") and not self.allow_cloud.get():
            return self._warning("This task needs cloud consent", "This provider sends task data outside this PC and may use your account allowance or incur charges. Enable the task-specific cloud checkbox to submit.")
        try:
            result = self.hub.submit_task(self.provider.get(), self.model.get(), prompt, self.workspace.get().strip(),
                lead_id=self.lead_id.get().strip() or "desktop-user", task_kind=self.kind.get(),
                source_files=list(self.source_files), images=list(self.images), allow_cloud=self.allow_cloud.get(),
                skill_ids=list(self.assigned_skills))
            self.allow_cloud.set(False)
            self._clear_skills()
            self.status.set(f"Task submitted: {result['id']}")
            self._refresh_tasks()
            self.notebook.select(self.pages["Tasks & review"])
            task_id = str(result["id"])
            if self.task_tree.exists(task_id):
                self.task_tree.selection_set(task_id)
                self.task_tree.see(task_id)
                self._task_selected()
        except Exception as exc:
            self._error("Task was not submitted", exc)

    def _refresh_tasks(self, quiet=False):
        try:
            tasks = self.hub.list_tasks()
            found = set()
            for task in tasks:
                task_id = str(task["id"])
                found.add(task_id)
                values = (task_id, task.get("provider", ""), task.get("model", ""), task.get("status", ""), task.get("review_status", "pending"))
                if self.task_tree.exists(task_id):
                    self.task_tree.item(task_id, values=values)
                else:
                    self.task_tree.insert("", 0, iid=task_id, values=values)
            for task_id in self.task_tree.get_children():
                if task_id not in found:
                    self.task_tree.delete(task_id)
            active = sum(t.get("status") in ("queued", "running") for t in tasks)
            review = sum(t.get("status") == "succeeded" and t.get("review_status", "pending") == "pending" for t in tasks)
            self.task_summary.set(f"Tasks\n{active} active · {review} awaiting review · {len(tasks)} total")
            if self.selected_task in found:
                self._load_task(self.selected_task)
            return tasks
        except Exception as exc:
            if not quiet:
                self._error("Could not refresh tasks", exc)

    def _task_selected(self, _event=None):
        selected = self.task_tree.selection()
        if selected:
            try:
                self._load_task(selected[0])
            except Exception as exc:
                self._error("Could not load task", exc)

    def _load_task(self, task_id):
        task = self.hub.get_task(task_id)
        criteria_signature = tuple(str(c) for c in task.get("acceptance_criteria", []))
        signature = (task_id, task.get("updated_at"), task.get("status"), task.get("review_status"), task.get("result_text"), task.get("error"), criteria_signature)
        if signature == self.detail_signature:
            return
        new_task = task_id != self.selected_task
        self.selected_task = task_id
        self.detail_signature = signature
        text = f"Task: {task_id}\nStatus: {task.get('status', '')} · Review: {task.get('review_status', 'pending')}\n"
        text += f"Requested model: {task.get('provider', '')} / {task.get('model', '')}\nWorkspace: {task.get('workspace', '')}\n"
        if task.get("observed_model"):
            text += f"Provider-observed model: {task['observed_model']}\n"
        text += "\nRequested task\n" + str(task.get("prompt", ""))
        if task.get("skills"):
            text += "\n\nAssigned skill snapshots\n" + json.dumps(task["skills"], ensure_ascii=False, indent=2)
        text += "\n\nResult\n" + str(task.get("result_text") or "No output returned yet.")
        if task.get("error"):
            text += "\n\nRun error\n" + str(task["error"])
        self._put(self.output_box, text)
        self.artifacts.delete(0, "end")
        self.artifact_refs = []
        for artifact in task.get("artifacts", []):
            ref = artifact.get("path", artifact.get("relative_path", "")) if isinstance(artifact, dict) else str(artifact)
            if ref:
                self.artifact_refs.append(ref)
                self.artifacts.insert("end", Path(ref).name)
        self.cancel_button.configure(state="normal" if task.get("status") in ("queued", "running") else "disabled")
        if new_task or criteria_signature != getattr(self, "criteria_signature", None):
            self.criteria_signature = criteria_signature
            for child in self.criteria_frame.winfo_children():
                child.destroy()
            self.review_fields = []
            for row, criterion in enumerate(task.get("acceptance_criteria") or ["Requested deliverable returned with source-grounded evidence"]):
                criterion = str(criterion)
                verdict = tk.StringVar(value="not_checked")
                evidence = tk.StringVar()
                ttk.Label(self.criteria_frame, text=criterion, wraplength=430).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
                ttk.Combobox(self.criteria_frame, textvariable=verdict, values=("pass", "fail", "not_checked"), width=13, state="readonly").grid(row=row, column=1, padx=(0, 10))
                ttk.Entry(self.criteria_frame, textvariable=evidence, width=32).grid(row=row, column=2, sticky="ew")
                self.review_fields.append((criterion, verdict, evidence))
            self.criteria_frame.columnconfigure(2, weight=1)
            self.review_summary.delete("1.0", "end")
            self.boundary.set("")
            self.limitations.set("")
            self.decision.set("revision_required")

    def _cancel_task(self):
        if self.selected_task:
            try:
                self.hub.cancel_task(self.selected_task)
                self.status.set("Cancellation requested for the selected task.")
                self._refresh_tasks()
            except Exception as exc:
                self._error("Could not cancel task", exc)

    def _review(self):
        if not self.selected_task:
            return self._warning("Choose a task", "Select a task and inspect its output before recording a review.")
        summary = self.review_summary.get("1.0", "end-1c").strip()
        boundary = self.boundary.get().strip()
        criteria = [{"criterion": c, "verdict": v.get(), "evidence": e.get().strip()} for c, v, e in self.review_fields]
        if not self.lead_id.get().strip() or not summary:
            return self._warning("Add review evidence", "Enter a reviewer label and a concrete summary of what you inspected and checked.")
        if self.decision.get() == "accepted" and (not boundary or not criteria or any(c["verdict"] != "pass" or not c["evidence"] for c in criteria)):
            return self._warning("Acceptance needs evidence", "Mark every criterion pass, add specific evidence for each, and complete the boundary review.")
        try:
            evidence = {"summary": summary, "criteria": criteria, "boundary_review": boundary,
                        "limitations": [s.strip() for s in self.limitations.get().split(";") if s.strip()]}
            self.hub.review_task(self.selected_task, self.lead_id.get().strip(), self.decision.get(), evidence)
            self.status.set(f"Review recorded: {self.decision.get()}.")
            self._refresh_tasks()
        except Exception as exc:
            self._error("Review was not recorded", exc)

    def _open_artifact(self):
        selected = self.artifacts.curselection()
        if not self.selected_task or not selected:
            return self._warning("Choose an output", "Select a job output from the list first.")
        try:
            path = self.hub.artifact_path(self.selected_task, self.artifact_refs[selected[0]])
            if not Path(path).is_file():
                raise ValueError("This job output is no longer available.")
            if Path(path).suffix.lower() not in {".txt", ".md", ".json", ".csv", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
                raise ValueError("This preview opens documents and images only. Inspect other output types in the job folder before using them.")
            os.startfile(str(path))
        except Exception as exc:
            self._error("Could not open job output", exc)

    def _save_settings(self):
        config = copy.deepcopy(self.hub.config)
        providers = config.setdefault("providers", {})
        try:
            for name, (enabled, url, key) in self.setting_fields.items():
                item = providers.setdefault(name, {})
                item["enabled"] = bool(enabled.get())
                item["base_url"] = url.get().strip()
                if key.get().strip():
                    self.hub.secrets.set(item.get("credential", name), key.get().strip())
                    key.set("")
            self.hub.save_config(config)
            self.settings_status.set("Provider settings saved. Refresh models to check availability. New-key fields have been cleared.")
            self.status.set("Settings saved.")
        except Exception:
            for _, _, key in self.setting_fields.values():
                key.set("")
            messagebox.showerror("Could not save all settings", "Some settings or secrets could not be saved. Check the local configuration and Windows credential protection, then try again. Key fields have been cleared.", parent=self.root)

    def _copy_connection(self):
        if self.connection_json:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.connection_json)
            self.status.set("MCP connection JSON copied.")

    def _export_connection(self):
        if not self.connection_json:
            return
        filename = filedialog.asksaveasfilename(parent=self.root, title="Export MCP connection", defaultextension=".json", initialfile="local-agent-orchestrator-mcp.json", filetypes=[("JSON", "*.json")])
        if filename:
            try:
                Path(filename).write_text(self.connection_json + "\n", encoding="utf-8")
                self.status.set("MCP connection JSON exported.")
            except Exception as exc:
                self._error("Could not export connection", exc)

    def _warning(self, title, text):
        messagebox.showwarning(title, text, parent=self.root)

    def _error(self, title, exc):
        # Policy/validation errors are safe, actionable messages. Avoid displaying
        # arbitrary network errors, which can contain credential-bearing URLs.
        text = str(exc)[:700] if isinstance(exc, (ValueError, FileNotFoundError, PermissionError)) else "The action could not finish. Check the selected task, provider settings and local files, then try again."
        messagebox.showerror(title, text, parent=self.root)

    def close(self):
        self._closed = True
        if self._timer is not None:
            self.root.after_cancel(self._timer)
        self.root.destroy()


def run_gui(hub, *, mcp_executable: str = "", auto_close_ms: int | None = None) -> None:
    app = App(hub, mcp_executable=mcp_executable)
    if auto_close_ms is not None:
        app.root.after(max(1, int(auto_close_ms)), app.close)
    app.root.mainloop()
