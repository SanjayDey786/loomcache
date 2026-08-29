"""
Real-world example: the exact same Loom pattern, wired up to the actual
Anthropic API instead of a fake call.

Requires:
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...

Run:
    python examples/with_anthropic.py

Run it a second time with the same topic and it will cost $0 and take
~0 seconds -- everything is served from the local cache. Change the
`topic` argument and only the affected steps re-hit the API.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import loom  # noqa: E402

try:
    import anthropic
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Install the anthropic SDK first:  pip install anthropic") from exc


client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment


@loom.step
def call_claude(prompt: str, model: str = "claude-sonnet-4-6") -> str:
    """Every distinct (prompt, model) pair is cached on disk. Change
    either one and only this node -- and anything downstream of it --
    re-executes and re-hits the API."""
    msg = client.messages.create(
        model=model,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


@loom.step
def extract_key_points(text: str) -> str:
    return call_claude(
        f"Extract the 3 key points from this text as a bullet list:\n\n{text}"
    )


def pipeline(topic: str) -> str:
    draft = call_claude(f"Write a short paragraph about {topic}")
    points = extract_key_points(draft)
    return points


if __name__ == "__main__":
    with loom.Run("claude-pipeline") as run:
        out = pipeline("the future of AI agents")

    print(out)
    print("\nStats:", run.stats())
    path = run.save()
    print(f"Saved run to {path}")
    print(
        "\nRun this script again unchanged -> $0 cost, ~instant. "
        "Change the topic string -> only the affected steps re-hit the API."
    )
