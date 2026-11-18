# Security and data handling

## Security update: 0.3.2

The 18 November 2026 review reproduced executable-search, file-link and proxy-routing weaknesses, now fixed in **0.3.2**. Upgrade older previews using the current installer. Validation used synthetic files, local HTTP fixtures, source inspection and independent model review. It is not a third-party penetration-test certification. See [test evidence](TEST-RESULTS.md).

Windows provider executables must be native `.exe`/`.com` files in absolute PATH entries or configured by absolute path. The launch folder, relative PATH entries and `.cmd`/`.bat` wrappers are excluded. Installed binaries and explicit absolute PATH entries remain trusted.

Local model requests bypass ambient proxies. Remote HTTPS providers retain the owner's proxy/TLS configuration. Configure only trusted endpoints and credentials: a loopback port does not authenticate its owner, and another local process could occupy a stopped service's port. Credential names and destinations are owner configuration, not an independent authorization boundary.

Response-size, elapsed-time and cancellation checks run between chunks. A blocked DNS, connect or socket operation can still wait for its timeout. MCP frames are bounded before JSON decoding; oversized frames are discarded in bounded chunks.

Installer and data writes reject existing linked destinations and use exclusive temporary files. This blocks reproduced pre-planted-link attacks, but does not isolate the app from a process controlling the same profile or racing directory changes. External artifact viewers receive a path and retain their own file-handling risks.

Build packages are version- and hash-pinned. Advisory and antivirus checks cannot prove the absence of unknown vulnerabilities. Releases remain unsigned; published checksums verify file consistency, not publisher identity.

## Trust boundaries

Maintainer: [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7).

This is an early, unsigned Windows preview. It is not a tenant-isolation boundary or operating-system sandbox. Run it as your ordinary user. There is no public listener. MCP clients share the authority of that user; lead labels are audit labels, not authenticated identities.

API keys use CurrentUser DPAPI. Prompts, selected input snapshots, responses and history remain ordinary files in the data directory. Other processes running as the same Windows user may access them. Conventional secret-file filters cannot detect every secret. Review inputs before authorizing cloud/subscription work. Providers have their own data and billing policies. Requests can continue on an external server after cancellation/timeout.

For a suspected vulnerability, use the repository's private reporting option at https://github.com/2mdipro7/local-agent-orchestrator/security/advisories/new when available. Do not put credentials, private source files or exploit details involving another person's data in public issues. If private reporting is unavailable, open a minimal issue asking the maintainer for a private channel without sensitive details.

Only the latest preview receives fixes as capacity allows; no response-time guarantee is offered. Contributions should include a minimal synthetic reproducer and evidence of the affected boundary.

Claude workers explicitly exclude built-in tools and inherited MCP servers. Optional user hooks, skills and connectors are disabled only for the child; managed provider policy remains in force. Runtime output validates empty tool lists, successful completion and reported model identity. The child recursion marker blocks accidental re-entry into this MCP; it is not protection against another process running as the same user.

Since 0.2.0, Antigravity and Codex provide restricted response-only workers. Antigravity uses pre-tool denial hooks and session-only sensitive-action denies; reported denied/tool actions reject the response. Codex uses a version-specific narrowed capability catalog, disabled external MCP inventory, ephemeral execution and rejection of unexpected tool/action events. Its supported CLI version is `0.169.0-alpha.11.1`; other versions fail before inference. Existing host authentication and owner-configured lifecycle behavior remain distinct from model-requested tools. See TEST-RESULTS.md for tested controls and their limits.

Lead/MCP registration, model discovery and successful worker execution are separate capabilities. Installer registration preserves other settings, refuses conflicting or linked configuration paths, and keeps original-byte backups beside existing files. Backups can contain private host settings and are not for publication. Close hosts during setup: existing-file replacement detects observed concurrent edits but cannot lock every host writer. Creating a new configuration never overwrites a concurrently created file. Installing a local MCP server does not establish isolation from other processes running as the same Windows user.

Process-tree termination is bounded best effort; detached descendants and already-issued remote requests are not guaranteed stopped. Do not interpret timeouts or a completed process as proof of containment or lead acceptance.

Shared skills are discovered only from the central library, enabled Codex/Claude skill locations and owner-configured custom folders. MCP tools cannot change these folders. Skill reads reject linked paths and unsafe resource paths; resources must be explicitly named text documents referenced by the skill. These checks do not certify the trustworthiness of third-party instructions. Skills cannot enable worker tools, hooks or native skill loading. The selected text and its hash are saved with the job and count toward the complete prompt limit. Cloud authorization covers that selected content; review it before submission. Discovery metadata and skill reads are available to connected MCP leads under this Windows user's authority.
