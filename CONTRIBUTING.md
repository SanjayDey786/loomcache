# Contributing to Loom

Thanks for considering a contribution — this is a young project and
there's a lot of surface area to help with (see the Roadmap in the
README for ideas).

## Setup

```bash
git clone https://github.com/SanjayDey786/loomtrace.git
cd loomtrace
pip install -e ".[dev]"
pytest
```

## Guidelines

- Keep the core (`loom/`) dependency-free. Optional integrations
  (Redis cache backend, LangChain adapter, etc.) should be optional
  extras, not hard dependencies.
- Every new behavior needs a test in `tests/`. `pytest` should pass
  with zero warnings before you open a PR.
- If you change hashing behavior (`loom/hashing.py`) or the
  `Node`/`Run` schema (`loom/run.py`), call it out explicitly in your
  PR description — it can silently invalidate everyone's existing
  caches and saved run files, which is a breaking change even if no
  public function signature changed.
- Favor small, focused PRs over large ones. If you want to work on
  something roadmap-sized (remote cache backend, LangChain adapter,
  UI), open an issue first to discuss the design.

## Reporting bugs / requesting features

Open a GitHub issue with a minimal reproduction where possible. For
bugs involving caching behavior specifically, include the two node
hashes you'd expect to be equal/different and why.
