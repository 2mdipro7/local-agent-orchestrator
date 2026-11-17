# Security and data handling

Maintainer: [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7).

Version 0 is an early, unsigned Windows preview. It is not a tenant-isolation boundary or operating-system sandbox. Run it as your ordinary user. There is no public listener. MCP clients share the authority of that user; lead labels are audit labels, not authenticated identities.

API keys use CurrentUser DPAPI. Prompts, selected input snapshots, responses and history remain ordinary files in the data directory. Other processes running as the same Windows user may access them. Conventional secret-file filters cannot detect every secret. Review inputs before authorizing cloud/subscription work. Providers have their own data and billing policies. Requests can continue on an external server after cancellation/timeout.

For a suspected vulnerability, use the repository's private reporting option at https://github.com/2mdipro7/local-agent-orchestrator/security/advisories/new when available. Do not put credentials, private source files or exploit details involving another person's data in public issues. If private reporting is unavailable, open a minimal issue asking the maintainer for a private channel without sensitive details.

Only the latest preview receives fixes as capacity allows; no response-time guarantee is offered. Contributions should include a minimal synthetic reproducer and evidence of the affected boundary.

Claude workers explicitly exclude built-in tools and inherited MCP servers. Optional user hooks, skills and connectors are disabled only for the child; managed provider policy remains in force. Runtime output validates empty tool lists, successful completion and reported model identity. The child recursion marker blocks accidental re-entry into this MCP; it is not protection against another process running as the same user.

Antigravity and Codex worker generation is unavailable until their respective tool-control gaps are resolved. Their lead/MCP connections and model discovery are separate capabilities. Process-tree termination is bounded best effort; detached descendants and already-issued remote requests are not guaranteed stopped. Do not interpret timeouts or a completed process as proof of containment or lead acceptance.
