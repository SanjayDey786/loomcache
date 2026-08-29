"""Web UI for Loom – browse runs, view nodes, diff runs.

Launch with:

    loom web --runs-dir .loom_runs --port 5000
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from loom.diff import diff_runs, format_diff
from loom.run import Run

try:
    from flask import Flask, jsonify, render_template_string, request
except ImportError:
    Flask = None  # type: ignore


HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Loom Web UI</title>
    <style>
        body { font-family: sans-serif; margin: 20px; }
        .node { margin: 5px 0; padding: 5px; border-left: 3px solid #ccc; }
        .hit { border-left-color: green; }
        .miss { border-left-color: red; }
        .diff { white-space: pre; font-family: monospace; }
        .run-list { display: flex; flex-wrap: wrap; gap: 20px; }
        .run-card { border: 1px solid #ddd; padding: 10px; border-radius: 5px; width: 300px; }
    </style>
</head>
<body>
    <h1>Loom Runs</h1>
    <div class="run-list">
        {% for run in runs %}
        <div class="run-card">
            <h3>{{ run.name }} ({{ run.run_id }})</h3>
            <p>Created: {{ run.created_at }}</p>
            <p>Nodes: {{ run.nodes|length }}</p>
            <a href="/run/{{ run.run_id }}">View</a>
        </div>
        {% endfor %}
    </div>

    <h2>Run Details</h2>
    <div id="run-detail"></div>

    <h2>Diff</h2>
    <form id="diff-form">
        <select name="run_a" id="run_a">
            {% for run in runs %}<option value="{{ run.run_id }}">{{ run.name }}</option>{% endfor %}
        </select>
        <select name="run_b" id="run_b">
            {% for run in runs %}<option value="{{ run.run_id }}">{{ run.name }}</option>{% endfor %}
        </select>
        <button type="submit">Diff</button>
    </form>
    <pre id="diff-output"></pre>

    <script>
        document.getElementById('diff-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const a = document.getElementById('run_a').value;
            const b = document.getElementById('run_b').value;
            const res = await fetch(`/diff?run_a=${a}&run_b=${b}`);
            const text = await res.text();
            document.getElementById('diff-output').textContent = text;
        });

        // Load run details on click
        document.querySelectorAll('.run-card a').forEach(link => {
            link.addEventListener('click', async (e) => {
                e.preventDefault();
                const res = await fetch(link.href);
                const data = await res.json();
                const detail = document.getElementById('run-detail');
                detail.innerHTML = `<h3>${data.name}</h3><pre>${JSON.stringify(data, null, 2)}</pre>`;
            });
        });
    </script>
</body>
</html>
"""


def create_app(runs_dir: str = ".loom_runs") -> Flask:
    if Flask is None:
        raise ImportError("Install Flask: pip install loomtrace[web]")

    app = Flask(__name__)

    @app.route("/")
    def index():
        runs_path = Path(runs_dir)
        run_files = list(runs_path.glob("*.json"))
        runs = []
        for f in run_files:
            try:
                run = Run.load(f)
                runs.append({
                    "run_id": run.run_id,
                    "name": run.name,
                    "created_at": run.created_at,
                    "nodes": run.nodes,
                })
            except Exception:
                continue
        return render_template_string(HTML_TEMPLATE, runs=runs)

    @app.route("/run/<run_id>")
    def run_detail(run_id):
        run_path = Path(runs_dir) / f"{run_id}.json"
        if not run_path.exists():
            return jsonify({"error": "Run not found"}), 404
        run = Run.load(run_path)
        return jsonify(run.to_dict())

    @app.route("/diff")
    def diff_view():
        run_a_id = request.args.get("run_a")
        run_b_id = request.args.get("run_b")
        if not run_a_id or not run_b_id:
            return "Missing run IDs", 400
        run_a_path = Path(runs_dir) / f"{run_a_id}.json"
        run_b_path = Path(runs_dir) / f"{run_b_id}.json"
        if not run_a_path.exists() or not run_b_path.exists():
            return "Run not found", 404
        run_a = Run.load(run_a_path)
        run_b = Run.load(run_b_path)
        diffs = diff_runs(run_a, run_b)
        return format_diff(diffs), 200, {"Content-Type": "text/plain"}

    return app


def serve(runs_dir: str = ".loom_runs", host: str = "127.0.0.1", port: int = 5000):
    app = create_app(runs_dir)
    app.run(host=host, port=port, debug=False)