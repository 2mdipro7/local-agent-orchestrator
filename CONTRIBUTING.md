# Contributing

Created and maintained by [Mehrab Mashrafi (@2mdipro7)](https://github.com/2mdipro7) · [Portfolio](https://2mdipro7.github.io/portfolio/).

Use Python 3.12 on Windows. Follow README.md to run tests and build. Open an issue with a small reproducible example before proposing a major provider or permission change. Pull requests should explain the user-visible behavior, relevant tests and limits. Keep contributions under the repository's MIT license.

Never commit API keys, local settings, job histories, prompts from real customer work, model weights or generated executables. Use synthetic fixtures and mocked provider calls in tests. Real paid-provider checks require your own explicit authorization and credentials; automated CI must not make such calls.

Preserve the 8,000-character assembled prompt cap, explicit cloud consent, workspace/input restrictions, cancellation accounting and evidence review. A model listing is not a guarantee of access. Describe tools actually available to a provider, and distinguish mocks from live validation. Avoid hardcoded personal paths and account-specific defaults. Any new data flow or changed permission needs a concrete explanation and regression coverage.

Security findings: see SECURITY.md. Keep discussions respectful and focused on the work.
