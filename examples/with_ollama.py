"""
Loom demo with a local LLM via Ollama (or any OpenAI-compatible API).

This demonstrates the exact same agent pipeline (plan -> research -> summarize)
using a real local model. Caching works just like with Anthropic/OpenAI.

Requirements:
    pip install openai
    # and ensure Ollama is running with a model pulled:
    # ollama pull llama3.1

Run:
    python examples/with_ollama.py

Run it a second time with the same topic and it will cost $0 and take
~0 seconds -- everything is served from the local cache.
Change the `topic` argument and only the affected steps re-run.
Change the `model` or the system prompt and the cache invalidates automatically.
"""

import os
import sys
import time

# Add parent directory to path so we can import loom
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import loom

# ---------------------------------------------------------------------------
# Configuration – change these to use any model / API endpoint
# ---------------------------------------------------------------------------

# For Ollama: http://localhost:11434/v1
# For LM Studio: http://localhost:1234/v1
# For OpenAI: https://api.openai.com/v1 (set OPENAI_API_KEY)
BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
API_KEY = os.getenv("LLM_API_KEY", "ollama")  # Ollama ignores the key, but requires some string
MODEL = os.getenv("LLM_MODEL", "gpt-oss:20b")    # or "mistral", "phi3", "gpt-oss:20b", etc.

# ---------------------------------------------------------------------------

try:
    from openai import OpenAI
except ImportError:
    raise SystemExit("Install the openai SDK first:  pip install openai")

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)


@loom.step
def call_llm(prompt: str, model: str = MODEL) -> str:
    """
    One Loom step that calls the LLM.

    The cache key includes:
      - The source code of this function (so if you edit the prompt template, cache invalidates)
      - The `prompt` argument
      - The `model` argument

    If you change the model name, this step re-runs automatically.
    """
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a helpful research assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=300,
    )
    return resp.choices[0].message.content


@loom.step
def plan(user_query: str) -> str:
    """Break the user query into a step-by-step research plan."""
    return call_llm(
        f"Break down this research task into clear, actionable steps (as a bullet list): {user_query}"
    )


@loom.step
def research(plan_text: str) -> str:
    """Simulate research by asking the LLM to gather information based on the plan."""
    return call_llm(
        f"Based on this research plan, provide detailed findings and facts:\n\n{plan_text}"
    )


@loom.step
def summarize(research_results: str) -> str:
    """Summarize the research findings into a concise final output."""
    return call_llm(
        f"Summarize these research findings into a clear, concise final report:\n\n{research_results}"
    )


def agent_pipeline(user_query: str) -> str:
    p = plan(user_query)
    r = research(p)
    s = summarize(r)
    return s


def banner(text: str) -> None:
    print("\n" + "=" * 72)
    print(text)
    print("=" * 72)


if __name__ == "__main__":
    print(f"Using model: {MODEL}")
    print(f"Endpoint: {BASE_URL}\n")

    banner("RUN 1 -- cold cache: every step actually executes (will take a few seconds)")
    t0 = time.time()
    with loom.Run("ollama-agent") as run1:
        result1 = agent_pipeline("key differences between Python and JavaScript")
    print(f"\nResult: {result1}")
    print(f"Wall time: {time.time() - t0:.2f}s")
    print(f"Stats: {run1.stats()}")
    run1.save()

    banner("RUN 2 -- identical input, warm cache: should be ~instant")
    t0 = time.time()
    with loom.Run("ollama-agent") as run2:
        result2 = agent_pipeline("key differences between Python and JavaScript")
    print(f"\nResult: {result2}")
    print(f"Wall time: {time.time() - t0:.2f}s   <-- notice this is ~0s")
    print(f"Stats: {run2.stats()}")
    run2.save()

    banner("RUN 3 -- fork() with a DIFFERENT query: only affected steps re-execute")
    t0 = time.time()
    run3 = run1.fork(
        agent_pipeline,
        user_query="best practices for asynchronous programming in Python"
    )
    print(f"Wall time: {time.time() - t0:.2f}s")
    print(f"Stats: {run3.stats()}")
    run3.save()

    banner("RUN 4 -- SAME query again: fully served from cache, ~0s")
    t0 = time.time()
    with loom.Run("ollama-agent") as run4:
        result4 = agent_pipeline("key differences between Python and JavaScript")
    print(f"Wall time: {time.time() - t0:.2f}s")
    print(f"Stats: {run4.stats()}")
    run4.save()

    banner("DIFF: run1 vs run3 (different query -> first step changes)")
    diffs = loom.diff_runs(run1, run3)
    print(loom.format_diff(diffs))

    banner("DIFF: run1 vs run4 (identical query -> no divergence)")
    same = loom.first_divergence(run1, run4)
    print("No divergence -- runs are identical." if same is None else same)

    banner("Done")
    print("Run manifests saved to .loom_runs/   |   cached outputs in .loom_cache/")
    print(f"Try:  loom show {run1.root / (run1.run_id + '.json')}")