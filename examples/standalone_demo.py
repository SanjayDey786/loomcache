"""
Loom demo — run this to see content-addressed caching, forking, and
diffing in action, with nothing but the standard library.

    python examples/standalone_demo.py

This simulates a 3-step research agent (plan -> search -> summarize)
using fake network calls (time.sleep) so it's runnable with zero API
keys. See examples/with_anthropic.py for the real-LLM version — the
Loom code itself doesn't change, only the step bodies do.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import loom  # noqa: E402


# ---------------------------------------------------------------------------
# Fake "network calls" standing in for a real LLM / search API.
# ---------------------------------------------------------------------------
def fake_llm_call(prompt: str) -> str:
    time.sleep(1.0)  # pretend this is a round-trip to an LLM API
    return f"[LLM output for: {prompt[:60]}]"


def fake_search(query: str) -> str:
    time.sleep(1.0)  # pretend this is a round-trip to a search/tool API
    return f"[3 search results for: {query}]"


# ---------------------------------------------------------------------------
# The actual agent pipeline. Note: this is completely ordinary Python.
# The only Loom-specific line in each function is the @loom.step decorator.
# ---------------------------------------------------------------------------
@loom.step
def plan(user_query: str) -> str:
    return fake_llm_call(f"Break down this research task into steps: {user_query}")


@loom.step
def research(plan_text: str) -> str:
    return fake_search(plan_text)


@loom.step
def summarize(research_results: str) -> str:
    return fake_llm_call(f"Summarize these findings: {research_results}")


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
    banner("RUN 1 -- cold cache: every step actually executes (~3s)")
    t0 = time.time()
    with loom.Run("research-agent") as run1:
        result1 = agent_pipeline("competitors of Anthropic in the API market")
    print(f"\nResult: {result1}")
    print(f"Wall time: {time.time() - t0:.2f}s")
    print(f"Stats: {run1.stats()}")
    run1.save()

    banner("RUN 2 -- identical input, warm cache: should be ~instant")
    t0 = time.time()
    with loom.Run("research-agent") as run2:
        result2 = agent_pipeline("competitors of Anthropic in the API market")
    print(f"\nResult: {result2}")
    print(f"Wall time: {time.time() - t0:.2f}s   <-- notice this is ~0s")
    print(f"Stats: {run2.stats()}")
    run2.save()

    banner("RUN 3 -- fork() with a DIFFERENT query: everything re-executes")
    t0 = time.time()
    run3 = run1.fork(agent_pipeline, user_query="pricing of Anthropic's API vs OpenAI")
    print(f"Wall time: {time.time() - t0:.2f}s   <-- new query -> all 3 steps rerun (~3s)")
    print(f"Stats: {run3.stats()}")
    run3.save()

    banner("RUN 4 -- SAME query again: fully served from cache, ~0s")
    t0 = time.time()
    with loom.Run("research-agent") as run4:
        result4 = agent_pipeline("competitors of Anthropic in the API market")
    print(f"Wall time: {time.time() - t0:.2f}s")
    print(f"Stats: {run4.stats()}")
    run4.save()

    banner("DIFF: run1 vs run3 (different initial query -> everything changes)")
    diffs = loom.diff_runs(run1, run3)
    print(loom.format_diff(diffs))

    banner("DIFF: run1 vs run4 (identical query -> no divergence)")
    same = loom.first_divergence(run1, run4)
    print("No divergence -- runs are identical." if same is None else same)

    banner("Done")
    print("Run manifests saved to .loom_runs/   |   cached outputs in .loom_cache/")
    print(f"Try:  loom show {run1.root / (run1.run_id + '.json')}")
    print(f"Try:  loom diff {run1.root / (run1.run_id + '.json')} {run3.root / (run3.run_id + '.json')}")
