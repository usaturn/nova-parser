#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    find_run_dirs,
    list_output_files,
    load_eval_metadata,
    load_grading,
    load_metrics,
    load_timing,
    mean_stddev,
    write_json,
    write_text,
)

RAW_TO_GROUP = {
    "with_skill": "with_skill",
    "candidate": "with_skill",
    "new_skill": "with_skill",
    "baseline": "baseline",
    "without_skill": "baseline",
    "old_skill": "baseline",
}
CONFIG_ORDER = {"with_skill": 0, "baseline": 1}


def detect_configuration(run_dir: Path, workspace_root: Path) -> tuple[str, str]:
    relative_parts = run_dir.relative_to(workspace_root).parts
    for part in reversed(relative_parts):
        if part in RAW_TO_GROUP:
            return part, RAW_TO_GROUP[part]
    fallback = relative_parts[-1]
    return fallback, RAW_TO_GROUP.get(fallback, fallback)


def run_pass_rate(grading: dict[str, Any]) -> float:
    summary = grading.get("summary", {})
    if isinstance(summary, dict) and isinstance(summary.get("pass_rate"), (int, float)):
        return float(summary["pass_rate"])
    expectations = grading.get("expectations", [])
    if not expectations:
        return 0.0
    passed = sum(1 for item in expectations if item.get("passed"))
    return passed / len(expectations)


def build_run_record(workspace_root: Path, run_dir: Path) -> dict[str, Any]:
    metadata = load_eval_metadata(run_dir)
    grading = load_grading(run_dir)
    timing = load_timing(run_dir)
    metrics = load_metrics(run_dir)
    raw_configuration, configuration = detect_configuration(run_dir, workspace_root)
    summary = grading.get("summary", {}) if isinstance(grading.get("summary"), dict) else {}
    eval_name = (
        metadata.get("eval_name")
        or metadata.get("name")
        or metadata.get("slug")
        or run_dir.parent.name
    )

    duration_seconds = 0.0
    for key in ("total_duration_seconds", "executor_duration_seconds"):
        if isinstance(timing.get(key), (int, float)):
            duration_seconds = float(timing[key])
            break

    total_tokens = 0
    if isinstance(timing.get("total_tokens"), (int, float)):
        total_tokens = int(timing["total_tokens"])

    output_files = [path.name for path in list_output_files(run_dir / "outputs")]
    return {
        "run_id": str(run_dir.relative_to(workspace_root)),
        "eval_id": metadata.get("eval_id"),
        "eval_name": eval_name,
        "prompt": metadata.get("prompt", ""),
        "configuration": configuration,
        "source_configuration": raw_configuration,
        "expectations_total": int(summary.get("total", 0)),
        "expectations_passed": int(summary.get("passed", 0)),
        "pass_rate": round(run_pass_rate(grading), 4),
        "duration_seconds": round(duration_seconds, 4),
        "total_tokens": total_tokens,
        "output_files": output_files,
        "metrics": metrics,
    }


def aggregate_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    by_configuration: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        by_configuration.setdefault(run["configuration"], []).append(run)

    for configuration, config_runs in by_configuration.items():
        pass_rates = [run["pass_rate"] for run in config_runs]
        durations = [run["duration_seconds"] for run in config_runs]
        tokens = [run["total_tokens"] for run in config_runs]
        summary[configuration] = {
            "count": len(config_runs),
            "pass_rate": mean_stddev(pass_rates),
            "duration_seconds": mean_stddev(durations),
            "total_tokens": mean_stddev(tokens),
            "expectations_total": sum(run["expectations_total"] for run in config_runs),
            "expectations_passed": sum(run["expectations_passed"] for run in config_runs),
        }
    return summary


def compute_delta(summary: dict[str, Any]) -> dict[str, float]:
    with_skill = summary.get("with_skill")
    baseline = summary.get("baseline")
    if not with_skill or not baseline:
        return {}
    return {
        "pass_rate_mean": round(
            with_skill["pass_rate"]["mean"] - baseline["pass_rate"]["mean"], 4
        ),
        "duration_seconds_mean": round(
            with_skill["duration_seconds"]["mean"] - baseline["duration_seconds"]["mean"], 4
        ),
        "total_tokens_mean": round(
            with_skill["total_tokens"]["mean"] - baseline["total_tokens"]["mean"], 4
        ),
    }


def format_stat(block: dict[str, float], digits: int = 2) -> str:
    return f"{block['mean']:.{digits}f} ± {block['stddev']:.{digits}f}"


def generate_markdown(skill_name: str, benchmark: dict[str, Any]) -> str:
    lines = [f"# Benchmark for {skill_name}", ""]
    summary = benchmark.get("run_summary", {})
    if summary:
        lines.extend(
            [
                "| Configuration | Runs | Pass Rate | Duration (s) | Tokens |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for configuration in sorted(summary, key=lambda item: CONFIG_ORDER.get(item, 9)):
            block = summary[configuration]
            lines.append(
                "| "
                + f"{configuration} | {block['count']} | "
                + f"{format_stat(block['pass_rate'])} | "
                + f"{format_stat(block['duration_seconds'])} | "
                + f"{format_stat(block['total_tokens'], digits=0)} |"
            )
        lines.append("")

    delta = benchmark.get("delta", {})
    if delta:
        lines.extend(
            [
                "## Delta",
                "",
                f"- Pass rate mean: {delta['pass_rate_mean']:+.2f}",
                f"- Duration mean: {delta['duration_seconds_mean']:+.2f}s",
                f"- Token mean: {delta['total_tokens_mean']:+.0f}",
                "",
            ]
        )

    lines.extend(
        [
            "## Runs",
            "",
            "| Eval | Configuration | Pass Rate | Duration (s) | Tokens | Outputs |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for run in benchmark.get("runs", []):
        lines.append(
            "| "
            + f"{run['eval_name']} | {run['configuration']} | {run['pass_rate']:.2f} | "
            + f"{run['duration_seconds']:.2f} | {run['total_tokens']} | "
            + f"{', '.join(run['output_files']) or '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


def generate_benchmark(workspace_root: Path, skill_name: str, skill_path: str = "") -> dict[str, Any]:
    runs = [build_run_record(workspace_root, run_dir) for run_dir in find_run_dirs(workspace_root)]
    runs.sort(
        key=lambda run: (
            run["eval_id"] if isinstance(run["eval_id"], int) else 10**9,
            run["eval_name"],
            CONFIG_ORDER.get(run["configuration"], 9),
            run["run_id"],
        )
    )
    summary = aggregate_runs(runs)
    benchmark = {
        "skill_name": skill_name,
        "skill_path": skill_path,
        "workspace_root": str(workspace_root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
        "run_summary": summary,
        "delta": compute_delta(summary),
    }
    return benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate benchmark results for a skill workspace.")
    parser.add_argument("workspace_root", help="Path to the workspace iteration directory")
    parser.add_argument("--skill-name", default="", help="Display name for the benchmark")
    parser.add_argument("--skill-path", default="", help="Optional source skill path")
    args = parser.parse_args()

    workspace_root = Path(args.workspace_root).resolve()
    skill_name = args.skill_name or workspace_root.name
    benchmark = generate_benchmark(workspace_root, skill_name, args.skill_path)

    benchmark_json = workspace_root / "benchmark.json"
    benchmark_md = workspace_root / "benchmark.md"
    write_json(benchmark_json, benchmark)
    write_text(benchmark_md, generate_markdown(skill_name, benchmark))
    print(f"[OK] Wrote {benchmark_json}")
    print(f"[OK] Wrote {benchmark_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
