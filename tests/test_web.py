import tempfile
from pathlib import Path

import pytest

try:
    from flask import Flask
except ImportError:
    Flask = None

from loom.web import create_app
from loom import Run, step


@pytest.mark.skipif(Flask is None, reason="Flask not installed")
def test_web_app_routes():
    with tempfile.TemporaryDirectory() as tmp:
        runs_dir = Path(tmp) / "runs"
        runs_dir.mkdir()

        # Create a dummy run
        @step
        def f(x): return x + 1

        with Run("web_test", cache=None, root=runs_dir) as r:
            f(1)
        r.save()

        app = create_app(runs_dir=str(runs_dir))
        client = app.test_client()

        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Loom Runs" in resp.data

        resp = client.get(f"/run/{r.run_id}")
        assert resp.status_code == 200
        data = resp.json
        assert data["name"] == "web_test"

        # Diff endpoint
        # Create second run with different input
        with Run("web_test2", cache=None, root=runs_dir) as r2:
            f(2)
        r2.save()

        resp = client.get(f"/diff?run_a={r.run_id}&run_b={r2.run_id}")
        assert resp.status_code == 200
        # Check that the diff output contains the '~' symbol for changed node
        assert "~" in resp.data.decode()