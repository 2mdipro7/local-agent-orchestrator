# Architecture banner

`architecture-banner.png` is an AI-generated explanatory illustration created for this community project. Provider marks identify integrations; they do not imply sponsorship or endorsement. It is a diagram, not an application screenshot or a claim that every depicted service/account is verified.

References: [OpenAI brand resources](https://openai.com/brand/), [Google Antigravity press resources](https://antigravity.google/press) and its [official icon](https://antigravity.google/assets/image/brand/antigravity-icon__full-color.png). The Antigravity icon was supplied as the image-generation reference. Claude is represented by its recognizable orange star mark. Generated representations may differ from official vector originals; all third-party marks remain their owners' property.

The diagram distinguishes compatible lead hosts from response-only workers. A lead discovers providers and submits a bounded request through local MCP. The orchestrator uses a configured CLI, local model server or optional API, stores the returned artifact and leaves acceptance to independent lead review. Workers cannot recursively delegate or approve themselves. ChatGPT web alone cannot start a local stdio server; it needs a supported local bridge. CLI sign-in and API credentials are separate. Local models can use CPU or GPU; cloud models run with their providers.

The current implementation and verified limits are described in the [README](../README.md), [host instructions](../HOST-CONNECTIONS.md) and [validation history](../TEST-RESULTS.md). Optional APIs include image-capable endpoints; no local image-generation weights are bundled.
