# SignPath application and activation

Status, 19 November 2026: preparation only. No application has been submitted, no Foundation certificate has been issued, and no public release has been signed. Maintainer: Mehrab Mashrafi, [@2mdipro7](https://github.com/2mdipro7).

## Submit the free-program application

Open https://signpath.org/apply. The following answers match the current form. Review them, enter the email you want attached to your SignPath account, and submit the form yourself after reading its terms and data-consent statements. The marketing checkbox is optional. Do not put an email, identity document, API token or recovery code in this repository.

| Field | Prepared answer |
|---|---|
| Project Name | Local Agent Orchestrator |
| Repository URL | https://github.com/2mdipro7/local-agent-orchestrator |
| Homepage URL | https://github.com/2mdipro7/local-agent-orchestrator |
| Download URL | https://github.com/2mdipro7/local-agent-orchestrator/releases |
| Privacy Policy URL | https://github.com/2mdipro7/local-agent-orchestrator/blob/main/PRIVACY.md |
| Wikipedia URL | Leave blank; no article is claimed |
| Category | AI Tools |
| Maintainer Type | Choose the form's option for an individual/solo maintainer |
| Build System | GitHub Actions |
| First Name | Mehrab |
| Last Name | Mashrafi |
| Email | Supply your chosen account and notification email privately in the form |
| Company Name | Leave blank unless applying through an actual organization |
| Primary Discovery Channel | Choose the matching AI-assistant/other option; exact source: ChatGPT/Codex |

Tagline:

> A local Windows coordinator that lets AI assistants delegate bounded tasks to available models and share selected skills.

Description:

> Local Agent Orchestrator is an MIT-licensed Windows application and stdio MCP server. It connects compatible AI clients with separately installed model providers, so a lead assistant can submit a scoped task, inspect the response and record its review. Users choose the provider and selected source or skill content, and authorize cloud execution. Worker tasks return responses rather than unrestricted command execution. The app runs in the user's Windows profile and has no public listener or maintainer telemetry. External model clients and model weights are not bundled.

Reputation:

> This is a new, actively maintained project with public source and downloadable Windows previews. We do not claim widespread adoption, independent certification or media coverage. Reviewable evidence includes our public release history, GitHub-hosted Windows test/build workflow, documented security fixes and validation reports. We understand that these do not establish the same reputation as an established user community, and that Foundation acceptance is discretionary.
>
> Source and history: https://github.com/2mdipro7/local-agent-orchestrator
>
> Releases: https://github.com/2mdipro7/local-agent-orchestrator/releases
>
> Hosted builds: https://github.com/2mdipro7/local-agent-orchestrator/actions
>
> Validation: https://github.com/2mdipro7/local-agent-orchestrator/blob/main/TEST-RESULTS.md
>
> Security: https://github.com/2mdipro7/local-agent-orchestrator/blob/main/SECURITY.md

If the form requires an existing SignPath attribution, point to our pending-status [Code signing policy](../CODE-SIGNING.md) and explain that approval is being requested. Do not change the text to claim signing already exists. SignPath may ask for more history or independent adoption evidence before accepting this young project; neither payment nor fabricated popularity is a substitute.

## Questions to include in follow-up with SignPath

- Is a solo maintainer holding the documented author, outside-contribution reviewer and signing-approver roles acceptable? We do not claim independent human review of our own changes.
- Can the Microsoft runtime/API-set DLLs inside official CPython Windows builds remain under your system-library exception? See [component map](../signing/COMPONENTS.md); the preparation workflow produces `bundled-inventory.json` with actual member hashes.
- Can the Foundation approve this two-stage PyInstaller onefile workflow and its exact-file artifact configurations? The worker is signed before embedding; the app is signed afterwards. Each request needs manual approval. No upstream DLL is individually signed under this project's identity.
- Confirm the production certificate's exact subject, timestamp configuration, permitted source refs and manually approved signing policy. We have not guessed these values or claimed your portal accepts the templates.

## Account actions after acceptance

1. Complete your SignPath invitation and MFA setup. Confirm MFA is enabled for GitHub and anyone else receiving repository/signing authority. Keep recovery codes private.
2. Install the official [SignPath GitHub app](https://github.com/apps/signpath) for **only this repository**. Review its requested permissions. Link the predefined `GitHub.com` trusted build system and enable origin verification in the SignPath project.
3. Create the project slug `local-agent-orchestrator`. Create artifact configurations `worker` and `app` from [worker.xml](../signing/worker.xml) and [app.xml](../signing/app.xml). Upload the corresponding `signpath-worker-input-*` and `signpath-app-input-*` workflow artifacts as samples and have SignPath validate the configurations. These uploads are ZIP artifacts with one named executable, not raw EXEs. Keep exact filename, product, version and company restrictions. Do not add a wildcard that signs upstream DLLs.
4. Create the policy slug `release-signing`, using the **Foundation-approved production certificate**, required manual approval and a submitter that cannot approve. Restrict source to this repository and the reviewed `main` branch. Require GitHub-hosted builds and origin verification in the service, not just in YAML. Confirm timestamping with SignPath.
5. Create the GitHub Environment [`signpath-release`](https://github.com/2mdipro7/local-agent-orchestrator/settings/environments), restrict it to `main`, and add the maintainer as required reviewer if supported by the repository's plan. A solo maintainer may need self-review permitted for this environment; SignPath's separate manual approval still applies. Do not imply two independent human reviewers exist.
6. In that environment add **secret** `SIGNPATH_API_TOKEN`, scoped only to submitting signing requests for this project/policy. Add **variables** `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_EXPECTED_SUBJECT` (the exact full subject from the issued Foundation certificate), and finally `SIGNPATH_ENABLED=true`. Do not use repository-wide secrets, paste tokens into chat, or enable signing before composition/role approval.

No account, token, certificate, GitHub app access or production enable flag is created by this preparation work.

## Run preparation now, production signing later

The [SignPath workflow](../.github/workflows/signpath.yml) runs manually on `main`. Its default `sign=false` builds unsigned sample artifacts, tests metadata, checks the embedded worker and portable package, and records bundled components. It sends no signing request and does not publish a GitHub release. Those sample files are for application review, not replacements for the published installer.

For the first signed release, use a **new version**, for example 0.3.3 if still unused. Update `agenthub/__init__.py` and release documentation, review and commit the change on `main`, and push the matching `v<version>` tag pointing to that exact commit. Do not create the GitHub release yet. The signing preflight rejects an absent/mismatched tag or an already-published release version.

Run the workflow from that `main` commit with `sign=true`. Approve the worker request in SignPath, then approve the application request after its build. Each action waits up to 15 minutes; the job has a 45-minute limit. Stay available for both approvals. A timeout stops the run. Check and cancel any outstanding request in SignPath before retrying; a timed-out workflow is not proof that the service-side request was cancelled.

The workflow verifies Windows trust status, embedded Authenticode signature type, exact approved subject, timestamp presence and product/version metadata. It compares the embedded worker and portable EXEs byte-for-byte with the verified files. The Setup download is an identical copy of the signed GUI executable. It then runs the frozen GUI/MCP smoke checks and creates final checksums.

After both requests and all checks succeed, inspect the artifact from **that run** and publish its exact bytes as the new GitHub release. Never rebuild after signing. Keep the source commit, workflow URL, signing request IDs and checksums with the release. The workflow deliberately has no automatic publication permission. Update the public signing status and attribution only after actual signed files are verified. A trusted signature does not promise that SmartScreen will immediately trust a new publisher.

## Reference documentation

- https://signpath.org/terms
- https://docs.signpath.io/trusted-build-systems/github
- https://docs.signpath.io/artifact-configuration/reference
- https://docs.signpath.io/artifact-configuration/syntax
