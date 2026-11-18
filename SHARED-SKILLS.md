# Shared skills

Any connected MCP lead can discover and read the same local skill library, then assign selected guidance to a worker. The lead still chooses the task, model and review criteria.

## Library locations

The central library is `%LOCALAPPDATA%\LocalAgentOrchestrator\data\skills`. Create one folder per skill, containing a UTF-8 `SKILL.md` file. A minimal skill looks like this:

```markdown
---
name: clear-project-update
description: Write a short project update from supplied facts.
---

Lead with the current result. Separate completed work from planned work.
Include a next action only when the supplied facts identify one.
Do not invent progress, deadlines or promises.
```

With host discovery enabled, the app also searches:

- `%USERPROFILE%\.codex\skills` and `.codex\plugins\cache`. A configured `CODEX_HOME` replaces `.codex`.
- `%USERPROFILE%\.claude\skills` and `.claude\plugins\cache`.

Use **Skills → Add skill folder** for another local library. **Remove custom folders** removes these search locations from settings; it does not delete their files. Turning off host discovery leaves the central library and custom locations available. Existing host skills are read in place, not copied into the application or uploaded by discovery.

Discovery has depth, file-count and time limits. The catalog reports a truncated scan when a limit is reached. Files must be UTF-8 text and at most 32,000 bytes; each task can select up to eight skill files, including references. If a skill is missing, add its smaller containing library explicitly. Duplicate names, including plugin versions, retain distinct IDs and paths; the app does not silently choose a version for you.

## Lead workflow

1. Call `list_skills` with a short `query`. Use `next_offset` to page through results; `refresh=true` rescans the configured folders.
2. Call `read_skill` with the chosen `skill_id`. Check its instructions, origin and SHA-256 hash against the task.
3. Submit a bounded task using `skill_ids: ["<returned ID>"]`, specific acceptance criteria and the usual provider authorization.
4. Inspect the worker output and the job's `skills` metadata. Use `read_artifact` with each recorded `artifact` path to read the exact assigned snapshot.
5. Record a review against the task requirements and the relevant skill instructions. A successful worker run is not an accepted result.

Only explicitly selected skills enter the worker prompt. A lead can assign different skills to different workers or reuse one skill across them. The orchestrator supplies tools and guidance for this workflow; it cannot force a host assistant to choose a relevant skill or conduct a sound review.

## Referenced documents

`read_skill` accepts an optional `resource` for a relative text document referenced by `SKILL.md`. To include that document in a worker assignment, use `skill_resources: [{"skill_id": "<returned ID>", "relative_path": "references/checklist.md"}]` alongside the skill ID.

Resources must stay inside that skill's folder. Supported text extensions are `.md`, `.mdx`, `.rst` and `.txt`. External paths, linked folders, credentials, binary attachments and executable scripts are excluded. Reading a reference does not execute anything or authorize a tool mentioned in it.

## Assignment and privacy

The job freezes the files at submission time and records their hashes. A preview can become outdated if a file changes before submission; review the job snapshot when the exact version matters. Saved snapshots remain with local job history.

The complete prompt, including skills, referenced text, guardrails and task sources, must fit within 8,000 characters. A request that exceeds the limit fails before a worker starts. Select fewer skills or create a shorter, task-specific skill rather than assuming the app will shorten it.

Worker capabilities do not change. A skill cannot grant commands, project edits, external actions, subdelegation or self-approval. Native provider skill and hook loading remains disabled in the response-only adapters. Unsupported requirements must be reported to the lead.

Cloud assignments transmit selected skill text along with the task. Unselected skill bodies stay local during worker submission. Skill instructions must not contain secrets; local job files have the same Windows-user accessibility as other task records. Private libraries are not included in the public repository or release packages.
