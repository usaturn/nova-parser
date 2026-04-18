#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from common import (
    IMAGE_EXTENSIONS,
    TEXT_EXTENSIONS,
    find_run_dirs,
    list_output_files,
    load_eval_metadata,
    load_grading,
    load_json,
)

MIME_OVERRIDES = {
    ".svg": "image/svg+xml",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


def mime_type(path: Path) -> str:
    if path.suffix.lower() in MIME_OVERRIDES:
        return MIME_OVERRIDES[path.suffix.lower()]
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def embed_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return {
            "name": path.name,
            "type": "text",
            "content": path.read_text(encoding="utf-8", errors="replace"),
        }

    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    file_type = "binary"
    if suffix in IMAGE_EXTENSIONS:
        file_type = "image"
    elif suffix == ".pdf":
        file_type = "pdf"
    return {
        "name": path.name,
        "type": file_type,
        "mime": mime_type(path),
        "data_uri": f"data:{mime_type(path)};base64,{encoded}",
    }


def detect_configuration(run_dir: Path, workspace_root: Path) -> str:
    relative_parts = run_dir.relative_to(workspace_root).parts
    for part in reversed(relative_parts):
        if part in {"with_skill", "without_skill", "baseline", "old_skill", "candidate"}:
            return part
    return relative_parts[-1]


def run_key(run: dict[str, Any]) -> str:
    return f"{run.get('eval_id')}::{run.get('eval_name')}::{run.get('configuration')}"


def build_previous_map(previous_workspace: Path | None) -> dict[str, list[dict[str, Any]]]:
    if not previous_workspace or not previous_workspace.exists():
        return {}
    previous_runs = build_runs(previous_workspace, None)
    return {run_key(run): run["outputs"] for run in previous_runs}


def build_runs(
    workspace_root: Path,
    previous_outputs: dict[str, list[dict[str, Any]]] | None,
) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for run_dir in find_run_dirs(workspace_root):
        metadata = load_eval_metadata(run_dir)
        grading = load_grading(run_dir)
        transcript = ""
        for candidate in (run_dir / "transcript.md", run_dir / "outputs" / "transcript.md"):
            if candidate.exists():
                transcript = candidate.read_text(encoding="utf-8", errors="replace")
                break
        run = {
            "id": str(run_dir.relative_to(workspace_root)).replace(os.sep, "-"),
            "run_dir": str(run_dir),
            "eval_id": metadata.get("eval_id"),
            "eval_name": metadata.get("eval_name") or metadata.get("name") or run_dir.parent.name,
            "prompt": metadata.get("prompt", "(No prompt recorded)"),
            "configuration": detect_configuration(run_dir, workspace_root),
            "outputs": [embed_file(path) for path in list_output_files(run_dir / "outputs")],
            "grading": grading,
            "transcript": transcript,
        }
        if previous_outputs:
            run["previous_outputs"] = previous_outputs.get(run_key(run), [])
        runs.append(run)
    runs.sort(
        key=lambda item: (
            item["eval_id"] if isinstance(item["eval_id"], int) else 10**9,
            item["eval_name"],
            item["configuration"],
        )
    )
    return runs


def render_html(skill_name: str, runs: list[dict[str, Any]], benchmark: dict[str, Any]) -> str:
    payload = {
        "skillName": skill_name,
        "runs": runs,
        "benchmark": benchmark,
    }
    payload_json = json.dumps(payload)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{skill_name} Review</title>
  <style>
    :root {{
      --bg: #f7f5ee;
      --panel: #fffdf7;
      --border: #d6cfbf;
      --ink: #1f1d19;
      --muted: #5e5a50;
      --accent: #135d66;
      --accent-soft: #d8ecee;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Iowan Old Style", "Palatino Linotype", serif; color: var(--ink); background: linear-gradient(180deg, #ece8dd 0%, var(--bg) 35%, #f9f6ef 100%); }}
    header {{ padding: 28px 32px 12px; }}
    h1 {{ margin: 0 0 8px; font-size: 2rem; }}
    p {{ color: var(--muted); margin: 0; }}
    main {{ padding: 0 24px 24px; }}
    .tabs {{ display: flex; gap: 8px; margin: 8px 0 16px; }}
    .tabs button {{ border: 1px solid var(--border); background: var(--panel); color: var(--ink); padding: 10px 14px; border-radius: 999px; cursor: pointer; }}
    .tabs button.active {{ background: var(--accent); color: white; border-color: var(--accent); }}
    .panel {{ display: none; background: rgba(255, 253, 247, 0.92); border: 1px solid var(--border); border-radius: 20px; padding: 20px; box-shadow: 0 14px 40px rgba(32, 27, 15, 0.06); }}
    .panel.active {{ display: block; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; align-items: center; }}
    select, textarea {{ width: 100%; border: 1px solid var(--border); border-radius: 14px; background: white; color: var(--ink); padding: 12px; font: inherit; }}
    textarea {{ min-height: 140px; resize: vertical; }}
    .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
    .card {{ border: 1px solid var(--border); border-radius: 18px; background: white; padding: 16px; }}
    .card h3, .card h4 {{ margin-top: 0; }}
    .pill {{ display: inline-block; padding: 4px 10px; border-radius: 999px; background: var(--accent-soft); color: var(--accent); font-size: 0.9rem; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #f7f6f1; border-radius: 14px; padding: 12px; overflow: auto; }}
    img, iframe {{ width: 100%; border: 1px solid var(--border); border-radius: 14px; background: white; }}
    iframe {{ min-height: 360px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border); }}
    .muted {{ color: var(--muted); }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 12px; }}
    .actions button {{ border: 1px solid var(--accent); background: white; color: var(--accent); padding: 10px 14px; border-radius: 999px; cursor: pointer; }}
  </style>
</head>
<body>
  <header>
    <h1>{skill_name} Review Workspace</h1>
    <p>Inspect output artifacts, benchmark summaries, and capture qualitative notes for the next iteration.</p>
  </header>
  <main>
    <div class="tabs">
      <button data-panel="outputs" class="active">Outputs</button>
      <button data-panel="benchmark">Benchmark</button>
    </div>

    <section id="outputs" class="panel active">
      <div class="controls">
        <label style="min-width: 320px; flex: 1;">
          <span class="muted">Select a run</span>
          <select id="run-select"></select>
        </label>
        <div class="actions">
          <button id="download-feedback">Download feedback.json</button>
        </div>
      </div>
      <div id="run-container"></div>
    </section>

    <section id="benchmark" class="panel">
      <div id="benchmark-container"></div>
    </section>
  </main>
  <script>
    const payload = {payload_json};
    const feedbackStorageKey = `skill-review::${{payload.skillName}}`;
    const feedback = JSON.parse(localStorage.getItem(feedbackStorageKey) || "{{}}");

    function switchPanel(panelId) {{
      document.querySelectorAll(".tabs button").forEach((button) => {{
        button.classList.toggle("active", button.dataset.panel === panelId);
      }});
      document.querySelectorAll(".panel").forEach((panel) => {{
        panel.classList.toggle("active", panel.id === panelId);
      }});
    }}

    function renderOutput(output) {{
      if (output.type === "text") {{
        return `<div class="card"><h4>${{output.name}}</h4><pre>${{escapeHtml(output.content)}}</pre></div>`;
      }}
      if (output.type === "image") {{
        return `<div class="card"><h4>${{output.name}}</h4><img src="${{output.data_uri}}" alt="${{output.name}}"></div>`;
      }}
      if (output.type === "pdf") {{
        return `<div class="card"><h4>${{output.name}}</h4><iframe src="${{output.data_uri}}"></iframe></div>`;
      }}
      return `<div class="card"><h4>${{output.name}}</h4><a download="${{output.name}}" href="${{output.data_uri}}">Download artifact</a></div>`;
    }}

    function renderRun(run) {{
      const note = feedback[run.id] || "";
      const grading = run.grading || {{}};
      const gradingRows = (grading.expectations || []).map((item) => `
        <tr>
          <td>${{escapeHtml(item.text || "")}}</td>
          <td>${{item.passed ? "pass" : "fail"}}</td>
          <td>${{escapeHtml(item.evidence || "")}}</td>
        </tr>`).join("");
      const previousOutputs = (run.previous_outputs || []).map(renderOutput).join("");
      return `
        <div class="grid">
          <div class="card">
            <div class="pill">${{escapeHtml(run.configuration)}}</div>
            <h3>${{escapeHtml(run.eval_name)}}</h3>
            <p>${{escapeHtml(run.prompt)}}</p>
          </div>
          <div class="card">
            <h3>Feedback</h3>
            <textarea data-run-id="${{run.id}}" placeholder="Record what changed, what failed, or what to improve next.">${{escapeHtml(note)}}</textarea>
          </div>
        </div>
        <div class="grid" style="margin-top: 16px;">
          <div class="card">
            <h3>Outputs</h3>
            <div class="grid">${{run.outputs.map(renderOutput).join("") || "<p class=\\"muted\\">No output files found.</p>"}}</div>
          </div>
          <div class="card">
            <h3>Previous Iteration</h3>
            <div class="grid">${{previousOutputs || "<p class=\\"muted\\">No previous outputs matched this run.</p>"}}</div>
          </div>
        </div>
        <div class="grid" style="margin-top: 16px;">
          <div class="card">
            <h3>Formal Grades</h3>
            ${{
              gradingRows
                ? `<table><thead><tr><th>Expectation</th><th>Status</th><th>Evidence</th></tr></thead><tbody>${{gradingRows}}</tbody></table>`
                : '<p class="muted">No grading.json loaded for this run.</p>'
            }}
          </div>
          <div class="card">
            <h3>Transcript</h3>
            <pre>${{escapeHtml(run.transcript || "No transcript found.")}}</pre>
          </div>
        </div>
      `;
    }}

    function renderBenchmark() {{
      const benchmark = payload.benchmark || {{}};
      const container = document.getElementById("benchmark-container");
      const summary = benchmark.run_summary || {{}};
      const summaryRows = Object.entries(summary).map(([name, block]) => `
        <tr>
          <td>${{escapeHtml(name)}}</td>
          <td>${{block.count ?? 0}}</td>
          <td>${{formatStat(block.pass_rate)}}</td>
          <td>${{formatStat(block.duration_seconds)}}</td>
          <td>${{formatStat(block.total_tokens, 0)}}</td>
        </tr>`).join("");
      const delta = benchmark.delta || {{}};
      const deltaHtml = Object.keys(delta).length
        ? `<div class="card"><h3>Delta</h3><pre>${{escapeHtml(JSON.stringify(delta, null, 2))}}</pre></div>`
        : "";
      container.innerHTML = `
        <div class="grid">
          <div class="card">
            <h3>Summary</h3>
            ${{
              summaryRows
                ? `<table><thead><tr><th>Configuration</th><th>Runs</th><th>Pass Rate</th><th>Duration (s)</th><th>Tokens</th></tr></thead><tbody>${{summaryRows}}</tbody></table>`
                : '<p class="muted">No benchmark summary available.</p>'
            }}
          </div>
          ${{deltaHtml}}
        </div>
        <div class="card" style="margin-top: 16px;">
          <h3>Raw benchmark.json</h3>
          <pre>${{escapeHtml(JSON.stringify(benchmark, null, 2))}}</pre>
        </div>
      `;
    }}

    function formatStat(block, digits = 2) {{
      if (!block || typeof block.mean !== "number") {{
        return "0.00 ± 0.00";
      }}
      return `${{block.mean.toFixed(digits)}} ± ${{block.stddev.toFixed(digits)}}`;
    }}

    function escapeHtml(value) {{
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }}

    function renderSelectedRun() {{
      const select = document.getElementById("run-select");
      const run = payload.runs.find((item) => item.id === select.value);
      const container = document.getElementById("run-container");
      container.innerHTML = run ? renderRun(run) : '<p class="muted">No runs found.</p>';
      container.querySelectorAll("textarea[data-run-id]").forEach((textarea) => {{
        textarea.addEventListener("input", () => {{
          feedback[textarea.dataset.runId] = textarea.value;
          localStorage.setItem(feedbackStorageKey, JSON.stringify(feedback, null, 2));
        }});
      }});
    }}

    function populateRunSelect() {{
      const select = document.getElementById("run-select");
      select.innerHTML = payload.runs.map((run) => `
        <option value="${{run.id}}">${{run.eval_name}} · ${{run.configuration}}</option>`).join("");
      select.addEventListener("change", renderSelectedRun);
      if (payload.runs.length > 0) {{
        select.value = payload.runs[0].id;
      }}
      renderSelectedRun();
    }}

    document.querySelectorAll(".tabs button").forEach((button) => {{
      button.addEventListener("click", () => switchPanel(button.dataset.panel));
    }});

    document.getElementById("download-feedback").addEventListener("click", () => {{
      const blob = new Blob([JSON.stringify(feedback, null, 2)], {{ type: "application/json" }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "feedback.json";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }});

    populateRunSelect();
    renderBenchmark();
  </script>
</body>
</html>
"""


def write_review(
    workspace_root: Path,
    output_path: Path,
    skill_name: str,
    benchmark: dict[str, Any],
    previous_workspace: Path | None,
) -> None:
    previous_outputs = build_previous_map(previous_workspace)
    runs = build_runs(workspace_root, previous_outputs)
    output_path.write_text(render_html(skill_name, runs, benchmark), encoding="utf-8")


def serve_html(output_path: Path, port: int, open_browser: bool) -> None:
    directory = output_path.parent
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/{output_path.name}"
    print(f"[OK] Serving {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a self-contained review page for skill outputs.")
    parser.add_argument("workspace_root", help="Path to the workspace iteration directory")
    parser.add_argument("--skill-name", default="", help="Display name for the review page")
    parser.add_argument("--benchmark", help="Path to benchmark.json")
    parser.add_argument("--previous-workspace", help="Optional previous iteration workspace")
    parser.add_argument("--static", help="Write HTML to this path instead of workspace/review.html")
    parser.add_argument("--serve", action="store_true", help="Serve the generated HTML over HTTP")
    parser.add_argument("--port", type=int, default=8765, help="Port for --serve")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser when serving")
    args = parser.parse_args()

    workspace_root = Path(args.workspace_root).resolve()
    output_path = (
        Path(args.static).resolve() if args.static else workspace_root / "review.html"
    )
    benchmark_path = (
        Path(args.benchmark).resolve() if args.benchmark else workspace_root / "benchmark.json"
    )
    benchmark = load_json(benchmark_path, default={}) or {}
    previous_workspace = Path(args.previous_workspace).resolve() if args.previous_workspace else None
    skill_name = args.skill_name or workspace_root.name

    write_review(workspace_root, output_path, skill_name, benchmark, previous_workspace)
    print(f"[OK] Wrote {output_path}")
    if args.serve:
        serve_html(output_path, args.port, open_browser=not args.no_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
