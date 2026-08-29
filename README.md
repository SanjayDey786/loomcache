```markdown
# Loom

**The smallest tool that gives any Python script content‑addressed caching, partial re‑execution, and node‑level diffing — without an orchestration platform.**

Loom treats every function call in your pipeline the way Bazel treats a build target or Git treats a commit: as a hashed, content‑addressed node in a dependency graph. Change one prompt buried deep in a pipeline, and Loom re‑runs **only** that step and everything downstream of it — not the whole pipeline.

> **v1.0 is here!** Remote caches (S3/Redis), LangChain adapter, Web UI, and async support are now included.

---

## Table of Contents

- [What Loom Solves](#what-loom-solves)
- [How It Works](#how-it-works)
- [Quick Start](#quick-start)
- [Key Features](#key-features)
  - [Core Caching & Execution](#core-caching--execution)
  - [Remote Cache Backends](#remote-cache-backends-s3--redis)
  - [LangChain / LangGraph Adapter](#langchain--langgraph-adapter)
  - [Web UI](#web-ui)
  - [Async Steps & Concurrency](#async-steps--concurrency)
- [CLI Reference](#cli-reference)
- [Installation](#installation)
- [Comparison with Existing Tools](#comparison-with-existing-tools)
- [Limitations (Read This)](#limitations-read-this)
- [Roadmap Status](#roadmap-status)
- [Contributing & Tests](#contributing--tests)
- [License](#license)

---

## What Loom Solves

If you’re hand‑rolling an agent script — not running it through a pipeline platform — you’ve likely faced these problems:

- Tweaking **one** prompt or **one** tool halfway through forces you to re‑run the **entire** pipeline — burning tokens, money, and wall‑clock time.
- When a pipeline’s output changes between two runs, you have no way to see **exactly where** the two runs diverged — you’re left diffing final text blobs and guessing.
- Debugging means adding print statements and re‑running the whole pipeline again, and again, and again.

**Loom solves this** by:

1. **Hashing** every step’s source code + arguments (and upstream node hashes) → deterministic cache keys.
2. **Caching** step outputs on disk (or S3/Redis) — identical calls return instantly.
3. **Recording** every run as a list of nodes, so you can `diff` two runs node‑by‑node.
4. **Forking** a run with a new input — only the changed step and its downstream steps re‑execute.

All of this works with **plain Python functions** – no special pipeline declarations, no extra infrastructure.

---

## How It Works

Every `@loom.step` call is hashed from:

1. **The source code of the step function itself** — so editing a prompt template inside the function body invalidates the cache automatically.
2. **Its arguments** — either their content hash, or, if an argument is itself the traced output of an upstream step, that step’s node hash. This turns a plain chain of Python function calls into a real hashable dependency graph — without any manual wiring.

```text
 user code                          Loom
 ---------                          ----
 @loom.step
 def plan(q):            ─────►    1. hash(source(plan) + q)
     ...                           2. cache lookup
                                          │
                                   hit ◄──┴──► miss
                                    │            │
                            return cached   execute plan(q)
                               output        cache + record
                                    │            │
                                    └─────┬──────┘
                                          ▼
                             tagged output (carries node hash)
                                          │
                          passed into the next @loom.step call
                                          ▼
                          hash includes the UPSTREAM node hash
                          (so changing `plan` invalidates every-
                           thing downstream of it automatically)

```

---

## Quick Start

```bash
pip install loomtrace

```

```python
import loom

@loom.step
def plan(query: str) -> str:
    return llm.call(f"Plan: {query}")

@loom.step
def execute(plan: str) -> str:
    return tool.run(plan)

with loom.Run("research-agent") as run:
    p = plan("find competitors of X")
    result = execute(p)

run.save()

```

Run that pipeline again unchanged — every step is served from cache in milliseconds. Change `plan`’s prompt or the input — only `plan` and its downstream steps re‑run.

---

## Key Features

### Core Caching & Execution

* `@loom.step` – caches any function.
* `loom.Run(name)` – context manager; records every step call.
* `run.save()` / `Run.load(path)` – persist/restore runs as JSON.
* `run.fork(pipeline_fn, **kwargs)` – re‑run with new inputs; unchanged steps are cached.
* `loom.diff_runs(a, b)` / `loom.first_divergence(a, b)` – node‑by‑node diff.
* `loom.DiskCache(root=...)` – default local cache; subclass `loom.Cache` for other backends.

### Remote Cache Backends (S3 / Redis)

```python
from loom import S3Cache, RedisCache

# S3
cache = S3Cache(bucket="my-bucket", prefix="loom/")

# Redis
cache = RedisCache(url="redis://localhost:6379/0", key_prefix="loom:")

with loom.Run("pipeline", cache=cache) as run:
    ...

```

### LangChain / LangGraph Adapter

```python
from loom.langchain import wrap_runnable
from langchain.chains import LLMChain

chain = LLMChain(...)
cached_chain = wrap_runnable(chain, name="my_chain")

with loom.Run("lc_run") as run:
    result = cached_chain.invoke({"input": "Hello"})

```

### Web UI

```bash
loom web --runs-dir .loom_runs --port 5000

```

Then open `http://localhost:5000` to browse runs, inspect nodes, and diff runs visually.

### Async Steps & Concurrency

```python
import asyncio
import loom

@loom.async_step
async def fetch_data(query: str) -> str:
    await asyncio.sleep(0.1)
    return f"Data for {query}"

async def main():
    async with loom.AsyncRun("async_demo") as run:
        results = await loom.gather(
            fetch_data("A"),
            fetch_data("B")
        )
    run.save()

asyncio.run(main())

```

---

## CLI Reference

| Command | Description |
| --- | --- |
| `loom show <run.json>` | List all nodes in a run |
| `loom diff <a.json> <b.json>` | Node‑by‑node diff |
| `loom stats <run.json>` | Cache hit rate and timing |
| `loom web` | Launch the web UI |

---

## Installation

```bash
pip install loomtrace

```

Optional extras:

```bash
pip install loomtrace[s3]        # S3 support
pip install loomtrace[redis]     # Redis support
pip install loomtrace[langchain] # LangChain adapter
pip install loomtrace[web]       # Web UI (Flask)
pip install loomtrace[all]       # all of the above

```

---

## Comparison with Existing Tools

> **Honest take**: content‑addressed step caching with automatic invalidation is not a new idea. ZenML and Dagster both already do it, well, in production. Loom is a **smaller, single‑purpose** version for standalone scripts.

| Tool | Category | What it does | Where it differs from Loom |
| --- | --- | --- | --- |
| **ZenML** | ML pipeline platform | Hashes step code, parameters, and artifacts; caches outputs; invalidates on code changes | Full platform: artifact store, stack config, UI, ML‑lifecycle features. You declare pipelines/steps in its framework. |
| **Dagster** | Data orchestrator | Op/asset memoization with version‑based cache keys; built‑in lineage and scheduling | Full platform — assets, sensors, a runtime you deploy, not a single importable decorator. |
| LangSmith / Langfuse / Helicone | LLM observability | Log, trace, and visualize LLM calls after the fact | Doesn’t cache or re‑execute — every re‑run still costs full price and time. |
| MLflow | Experiment tracking | Tracks metrics, params, and artifacts | Not content‑addressed caching; no automatic partial re‑execution. |
| DVC | Data/pipeline versioning | Content‑addressed, Git‑like caching for **file‑based** pipelines | Built around files and CLI pipeline stages, not live in‑process Python call graphs. |
| Bazel / Nix | Build systems | Content‑addressed, incremental builds | Not Python‑ or agent‑aware; infrastructure‑level, not a pip‑installable library. |
| **Loom** | Single‑purpose library | Same core idea (hash code + args, cache, invalidate on change) **+** node‑level diff, but as one dependency‑free decorator with no platform | Smaller, narrower — for standalone scripts. |

**The takeaway**: if you already use ZenML or Dagster, their caching is more mature — use it. Loom exists for the case: *“I have a standalone agent script, I don’t want to adopt an orchestration platform, and I want dependency edges inferred automatically from plain Python.”*

---

## Limitations (Read This)

* **Steps should be pure.** Caching assumes output depends only on declared inputs. Hidden side effects (global mutation, reading `time.time()`) won’t be tracked correctly.
* **Value tagging covers most types, not all.** `str`, `tuple`, `frozenset`, `list`, `dict`, `set`, and any object with `__dict__` are tagged directly. `int`, `float`, `bool` (fixed C layout) fall back to a transparent `TracedBox` wrapper – documented, not a silent failure.
* **`fork()` re‑invokes your pipeline function** – it does not resume from a checkpoint. Speed comes from cache hits, just like Bazel/DVC.
* **No distributed cache** – but the `Cache` interface is pluggable; `S3Cache` and `RedisCache` ship today.
* **Async is supported**, but parallel DAG execution is basic (`gather`). True multi‑branch concurrency is planned.

---

## Contributing & Tests

Contributions welcome — see `CONTRIBUTING.md`. Run the test suite with:

```bash
pip install -e ".[dev,all]"
pytest tests/

```

---

## License

MIT — see `LICENSE`.
