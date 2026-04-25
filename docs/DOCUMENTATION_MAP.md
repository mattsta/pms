# Documentation Map

This file separates the live operator/integration docs from archived planning,
audit, and historical material.

## Start Here

If you are new to PMS, read these in order:

1. [`README.md`](../README.md)
2. [`docs/IMMEDIATE_START_GO.md`](IMMEDIATE_START_GO.md)
3. [`docs/MACHINE_INTERFACE_GUIDE.md`](MACHINE_INTERFACE_GUIDE.md)
4. [`docs/END_TO_END_WORKFLOWS.md`](END_TO_END_WORKFLOWS.md)

That sequence gives you:

- what PMS is
- how to get a live workspace quickly
- how the machine-readable surface is meant to be used
- how the graph behaves under real workflows

## Live Operator Docs

Use these for day-to-day PMS usage:

- [`README.md`](../README.md)
- [`GETTING_STARTED.md`](../GETTING_STARTED.md)
- [`docs/IMMEDIATE_START_GO.md`](IMMEDIATE_START_GO.md)
- [`docs/WORKFLOWS.md`](WORKFLOWS.md)
- [`docs/CLAUDO_BOOTSTRAP_WORKFLOW.md`](CLAUDO_BOOTSTRAP_WORKFLOW.md)
- [`docs/DASHBOARD_USAGE.md`](DASHBOARD_USAGE.md)
- [`examples/real_world/README.md`](../examples/real_world/README.md)

## Live Machine Interface Docs

Use these when you are integrating against CLI, API, MCP, or clients:

- [`docs/MACHINE_INTERFACE_GUIDE.md`](MACHINE_INTERFACE_GUIDE.md)
- [`docs/CLIENT_GUIDE.md`](CLIENT_GUIDE.md)
- [`docs/WEB_API.md`](WEB_API.md)
- [`docs/API_REFERENCE.md`](API_REFERENCE.md)
- [`docs/API_ENDPOINT_CATALOG.md`](API_ENDPOINT_CATALOG.md)
- [`docs/API_RESPONSE_CONTRACTS.md`](API_RESPONSE_CONTRACTS.md)
- [`docs/CAPABILITIES_REFERENCE.md`](CAPABILITIES_REFERENCE.md)
- [`docs/CLAUDO_INTEROP.md`](CLAUDO_INTEROP.md)
- [`docs/CLAUDO_BOOTSTRAP_WORKFLOW.md`](CLAUDO_BOOTSTRAP_WORKFLOW.md)
- [`docs/RUNNERS_AND_ENV.md`](RUNNERS_AND_ENV.md)
- [`client-rust/README.md`](../client-rust/README.md)

## Live Design Docs

Use these when you need the current architecture and contract model:

- [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
- [`docs/ID_CONTRACT_ARCHITECTURE.md`](ID_CONTRACT_ARCHITECTURE.md)
- [`docs/VOCABULARY_GOVERNANCE.md`](VOCABULARY_GOVERNANCE.md)
- [`docs/ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md`](ACTOR_IDENTITY_PERSONA_GRAPH_ARCHITECTURE.md)
- [`docs/WRITE_COORDINATION_ARCHITECTURE.md`](WRITE_COORDINATION_ARCHITECTURE.md)
- [`docs/MULTI_AGENT_SYSTEM.md`](MULTI_AGENT_SYSTEM.md)
- [`docs/OUTPUT_CONTRACTS.md`](OUTPUT_CONTRACTS.md)
- [`docs/CLI_EXPORTS.md`](CLI_EXPORTS.md)

## Live Agent / Automation Docs

These are still active usage artifacts rather than historical notes:

- [`docs/AGENT_INTEGRATION_GUIDE.md`](AGENT_INTEGRATION_GUIDE.md)
- [`docs/END_TO_END_WORKFLOWS.md`](END_TO_END_WORKFLOWS.md)
- [`docs/AGENT_PROMPT_INTERACTIVE_PLAN.md`](AGENT_PROMPT_INTERACTIVE_PLAN.md)
- [`docs/AGENT_PROMPT_MINIMAL.md`](AGENT_PROMPT_MINIMAL.md)
- [`docs/AGENT_PROMPT_MCP_LOOP.md`](AGENT_PROMPT_MCP_LOOP.md)
- [`docs/TOOL_DEVELOPMENT.md`](TOOL_DEVELOPMENT.md)
- [`docs/EXTENSIONS.md`](EXTENSIONS.md)

## Live Examples

Use these when you want runnable starting points instead of more prose:

- [`examples/real_world/README.md`](../examples/real_world/README.md)
- [`examples/plugins/README.md`](../examples/plugins/README.md)
- [`examples/plugins/PLUGINS.md`](../examples/plugins/PLUGINS.md)
- [`examples/plugins/tutorials/01-your-first-plugin.md`](../examples/plugins/tutorials/01-your-first-plugin.md)
- [`examples/plugins/tutorials/02-event-driven-automation.md`](../examples/plugins/tutorials/02-event-driven-automation.md)
- [`examples/plugins/tutorials/03-dsl-no-python.md`](../examples/plugins/tutorials/03-dsl-no-python.md)
- [`examples/plugins/tutorials/04-real-world-integration.md`](../examples/plugins/tutorials/04-real-world-integration.md)
- [`examples/plugins/tutorials/05-self-building-plugins.md`](../examples/plugins/tutorials/05-self-building-plugins.md)

## What Was Archived

Planning docs, audit logs, superseded scenario writeups, duplicate reference
material, and other historical notes now live under:

- [`docs/archive/README.md`](archive/README.md)

Use the archive only when you explicitly want historical context or prior audit
evidence. It is not the primary operator or integration path.

## What Not To Read First

Do not start with these unless you already know why you need them:

- [`docs/API_REFERENCE.md`](API_REFERENCE.md)
- [`docs/CAPABILITIES_REFERENCE.md`](CAPABILITIES_REFERENCE.md)
- [`docs/archive/README.md`](archive/README.md)

They are useful, but they are not first-contact docs.

## Recommended Public-Release Reading Order

For a public reader evaluating PMS:

1. [`README.md`](../README.md)
2. [`docs/IMMEDIATE_START_GO.md`](IMMEDIATE_START_GO.md)
3. [`docs/MACHINE_INTERFACE_GUIDE.md`](MACHINE_INTERFACE_GUIDE.md)
4. [`docs/END_TO_END_WORKFLOWS.md`](END_TO_END_WORKFLOWS.md)
5. [`examples/real_world/README.md`](../examples/real_world/README.md)
6. [`docs/CLIENT_GUIDE.md`](CLIENT_GUIDE.md)
7. [`docs/WEB_API.md`](WEB_API.md)
8. [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
9. [`docs/archive/README.md`](archive/README.md) if you want historical context

That order keeps the live product understandable before the deeper historical
material appears.
