# PMS Plugin System - Examples & Learning Path

Welcome to the PMS plugin system! This directory contains everything you need to learn, from your first plugin to advanced self-building meta-plugins.

## Quick Navigation

| I want to...                   | Go to...                                                                |
| ------------------------------ | ----------------------------------------------------------------------- |
| Learn plugins from scratch     | [Tutorials](#learning-path)                                             |
| See a simple example           | [simple/hello-world](simple/hello-world/)                               |
| Create a plugin without Python | [simple/math-dsl.tools](simple/math-dsl.tools)                          |
| Build a real utility           | [intermediate/file-utils](intermediate/file-utils/)                     |
| Integrate with APIs            | [advanced/github-integration](advanced/github-integration/)             |
| Create self-building plugins   | [self-building/plugin-factory](self-building/plugin-factory/)           |
| Orchestrate multiple plugins   | [integration/workflow-orchestrator](integration/workflow-orchestrator/) |
| Learn testing                  | [testing/](testing/)                                                    |
| Read the full guide            | [PLUGINS.md](PLUGINS.md)                                                |

---

## Learning Path

Follow these tutorials in order for the best learning experience:

### Level 1: Foundations (30 minutes)

1. **[Tutorial 1: Your First Plugin](tutorials/01-your-first-plugin.md)**
   - Create, validate, test, and use a complete plugin
   - Understand manifests and tool functions
   - Learn the plugin lifecycle

2. **[Tutorial 3: DSL-Only Plugins](tutorials/03-dsl-no-python.md)**
   - Create tools without writing Python
   - Learn the DSL syntax
   - Quick prototyping techniques

### Level 2: Real-World Features (45 minutes)

3. **[Tutorial 2: Event-Driven Automation](tutorials/02-event-driven-automation.md)**
   - Subscribe to PMS events
   - React to task/project changes
   - Build automated workflows

4. **[Tutorial 4: API Integration](tutorials/04-real-world-integration.md)**
   - Connect to external services
   - Handle caching and errors
   - Cross-system synchronization

### Level 3: Advanced Patterns (30 minutes)

5. **[Tutorial 5: Self-Building Plugins](tutorials/05-self-building-plugins.md)**
   - Create plugins that create plugins
   - Self-monitoring and self-healing
   - Meta-programming patterns

---

## Example Plugins by Complexity

### Simple Examples

| Plugin                                  | Description              | Key Concepts               |
| --------------------------------------- | ------------------------ | -------------------------- |
| [hello-world](simple/hello-world/)      | Simplest possible plugin | Manifest, tools, lifecycle |
| [math-dsl.tools](simple/math-dsl.tools) | DSL-only plugin          | No Python required         |

### Intermediate Examples

| Plugin                                 | Description           | Key Concepts                |
| -------------------------------------- | --------------------- | --------------------------- |
| [file-utils](intermediate/file-utils/) | File system utilities | Capabilities, config, hooks |

### Advanced Examples

| Plugin                                             | Description                 | Key Concepts                |
| -------------------------------------------------- | --------------------------- | --------------------------- |
| [github-integration](advanced/github-integration/) | Full GitHub API integration | API, caching, secrets, sync |

### Self-Building Examples

| Plugin                                          | Description           | Key Concepts               |
| ----------------------------------------------- | --------------------- | -------------------------- |
| [plugin-factory](self-building/plugin-factory/) | Creates other plugins | Code generation, templates |

### Integration Examples

| Plugin                                                      | Description            | Key Concepts             |
| ----------------------------------------------------------- | ---------------------- | ------------------------ |
| [workflow-orchestrator](integration/workflow-orchestrator/) | Multi-plugin pipelines | Orchestration, data flow |
| [data-pipeline](integration/data-pipeline/)                 | ETL transformations    | Extract, transform, load |

---

## Feature Matrix

What each example demonstrates:

| Feature                    | hello-world | math-dsl | file-utils | github | factory | orchestrator |
| -------------------------- | :---------: | :------: | :--------: | :----: | :-----: | :----------: |
| Basic tools                |      ✓      |    ✓     |     ✓      |   ✓    |    ✓    |      ✓       |
| DSL syntax                 |             |    ✓     |            |        |         |              |
| Capabilities               |             |          |     ✓      |   ✓    |    ✓    |              |
| Configuration              |             |          |     ✓      |   ✓    |    ✓    |      ✓       |
| Event hooks                |             |          |     ✓      |   ✓    |         |      ✓       |
| Caching                    |             |          |            |   ✓    |         |              |
| External APIs              |             |          |            |   ✓    |         |              |
| Cross-system sync          |             |          |            |   ✓    |         |      ✓       |
| Code generation            |             |          |            |        |    ✓    |              |
| Self-monitoring            |             |          |            |        |         |              |
| Multi-plugin orchestration |             |          |            |        |         |      ✓       |

---

## Quick Start Commands

```bash
# Create a new plugin (5 templates available)
pms plugin new my-plugin --template basic

# Validate your plugin
pms plugin validate ./my-plugin

# Test your plugin
pms plugin test ./my-plugin

# Start using it
pms plugin discover ./my-plugin
pms plugin start my-plugin
pms plugin call my-plugin.my_tool --arg input="test"

# See all plugin commands
pms plugin --help
```

---

## Plugin Templates

Use `pms plugin new` with these templates:

| Template         | Use Case               | Creates                     |
| ---------------- | ---------------------- | --------------------------- |
| `basic`          | Simple utilities       | 1 tool, basic structure     |
| `api`            | REST API integration   | CRUD operations, networking |
| `file-processor` | File manipulation      | Read/write capabilities     |
| `automation`     | Event-driven workflows | Event hooks                 |
| `dsl`            | Declarative tools      | DSL file only, no Python    |

Example:

```bash
pms plugin new slack-bot --template api --description "Slack integration"
```

---

## Testing Your Plugins

### Quick Test

```bash
pms plugin test ./my-plugin --verbose
```

### Write Unit Tests

See [testing/test_hello_world.py](testing/test_hello_world.py) for examples:

```python
import pytest
from pms.plugins.testing import PluginTestHarness

@pytest.fixture
def harness(tmp_path):
    return PluginTestHarness(tmp_path)

@pytest.mark.asyncio
async def test_my_tool(harness):
    await harness.load_plugin("./my-plugin")
    result = await harness.call_tool("my-plugin.my_tool", arg="value")
    assert result["status"] == "success"
```

---

## Directory Structure

```
examples/plugins/
├── README.md                    # This file
├── PLUGINS.md                   # Comprehensive reference guide
│
├── tutorials/                   # Step-by-step learning
│   ├── 01-your-first-plugin.md
│   ├── 02-event-driven-automation.md
│   ├── 03-dsl-no-python.md
│   ├── 04-real-world-integration.md
│   └── 05-self-building-plugins.md
│
├── simple/                      # Beginner examples
│   ├── hello-world/
│   │   ├── plugin.json
│   │   └── main.py
│   └── math-dsl.tools
│
├── intermediate/                # Real-world utilities
│   └── file-utils/
│       ├── plugin.json
│       └── main.py
│
├── advanced/                    # Production-quality examples
│   └── github-integration/
│       ├── plugin.json
│       └── main.py
│
├── self-building/               # Meta-programming examples
│   └── plugin-factory/
│       ├── plugin.json
│       └── main.py
│
├── integration/                 # Multi-plugin examples
│   ├── workflow-orchestrator/
│   │   ├── plugin.json
│   │   └── main.py
│   └── data-pipeline/
│       ├── plugin.json
│       └── main.py
│
└── testing/                     # Test examples
    ├── test_hello_world.py
    └── test_integration.py
```

---

## Key Concepts Summary

### Plugin Types

- **Extension**: Adds tools to PMS (most common)
- **Integration**: Connects to external systems
- **Runtime**: System-level capabilities

### Capabilities

```json
"capabilities": ["filesystem_read", "filesystem_write", "network", "events", "subprocess"]
```

### Lifecycle States

```
DISCOVERED → LOADED → INITIALIZED → RUNNING → STOPPED
```

### Event Hooks

```python
async def on_task_created(task_id: str, title: str, **kwargs):
    """React when tasks are created."""
    pass
```

### DSL vs Python

| DSL                 | Python          |
| ------------------- | --------------- |
| Simple calculations | Complex logic   |
| Quick prototypes    | Production code |
| No dependencies     | External APIs   |
| Instant creation    | Full control    |

---

## Need Help?

1. Check the [PLUGINS.md](PLUGINS.md) reference guide
2. Look at similar examples in this directory
3. Use `pms plugin validate` to check your plugin
4. Use `pms plugin test` for automated verification

---

## Contributing

Found a bug or want to add an example?

1. Follow the patterns in existing examples
2. Include both `plugin.json` and `main.py`
3. Add documentation (README or comments)
4. Include test coverage
5. Submit a PR!

---

Happy plugin building! 🔌
