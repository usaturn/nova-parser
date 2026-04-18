#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from common import read_skill_description, score_description, write_json, write_text


def load_queries(path: Path) -> tuple[str, list[dict[str, Any]]]:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    skill_name = payload.get("skill_name", "")
    queries = payload.get("queries", [])
    if not isinstance(queries, list):
        raise ValueError("trigger_queries.json must contain a queries array")
    return skill_name, queries


def evaluate_queries(
    description: str,
    queries: list[dict[str, Any]],
    threshold: float,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    positives = 0
    negatives = 0
    correct = 0
    total_coverage = 0.0

    for item in queries:
        query = str(item.get("query", "")).strip()
        should_trigger = bool(item.get("should_trigger"))
        expected_terms = item.get("expected_terms")
        evaluation = score_description(description, query, expected_terms, threshold=threshold)
        row = {
            "id": item.get("id"),
            "query": query,
            "should_trigger": should_trigger,
            "triggered": evaluation["triggered"],
            "correct": evaluation["triggered"] == should_trigger,
            "coverage": evaluation["coverage"],
            "matched_terms": evaluation["matched_terms"],
            "missing_terms": evaluation["missing_terms"],
            "notes": item.get("notes", ""),
        }
        if should_trigger:
            positives += 1
        else:
            negatives += 1
        if row["correct"]:
            correct += 1
        total_coverage += row["coverage"]
        results.append(row)

    count = len(results)
    false_positives = sum(1 for row in results if not row["should_trigger"] and row["triggered"])
    false_negatives = sum(1 for row in results if row["should_trigger"] and not row["triggered"])
    return {
        "summary": {
            "query_count": count,
            "positive_queries": positives,
            "negative_queries": negatives,
            "accuracy": round(correct / count, 4) if count else 0.0,
            "mean_coverage": round(total_coverage / count, 4) if count else 0.0,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
            "threshold": threshold,
        },
        "results": results,
    }


def render_markdown(skill_name: str, description: str, report: dict[str, Any]) -> str:
    lines = [
        f"# Trigger Evaluation for {skill_name}",
        "",
        "## Description Under Test",
        "",
        description,
        "",
        "## Summary",
        "",
    ]
    summary = report["summary"]
    lines.extend(
        [
            f"- Queries: {summary['query_count']}",
            f"- Accuracy: {summary['accuracy']:.2f}",
            f"- Mean coverage: {summary['mean_coverage']:.2f}",
            f"- False positives: {summary['false_positives']}",
            f"- False negatives: {summary['false_negatives']}",
            "",
            "## Results",
            "",
            "| Query | Expected | Triggered | Coverage | Missing Terms |",
            "|---|---|---|---:|---|",
        ]
    )
    for row in report["results"]:
        lines.append(
            "| "
            + f"{row['query']} | {'yes' if row['should_trigger'] else 'no'} | "
            + f"{'yes' if row['triggered'] else 'no'} | {row['coverage']:.2f} | "
            + f"{', '.join(row['missing_terms']) or '-'} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate how well a skill description triggers.")
    parser.add_argument("skill_dir", help="Path to the skill directory")
    parser.add_argument(
        "--queries",
        help="Path to trigger_queries.json (defaults to <skill>/evals/trigger_queries.json)",
    )
    parser.add_argument("--output", help="Optional JSON report path")
    parser.add_argument("--markdown", help="Optional markdown report path")
    parser.add_argument("--threshold", type=float, default=0.34, help="Coverage threshold")
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    queries_path = (
        Path(args.queries).resolve()
        if args.queries
        else skill_dir / "evals" / "trigger_queries.json"
    )
    skill_name, queries = load_queries(queries_path)
    description = read_skill_description(skill_dir)
    report = evaluate_queries(description, queries, args.threshold)
    payload = {
        "skill_name": skill_name or skill_dir.name,
        "skill_dir": str(skill_dir),
        "description": description,
        **report,
    }

    if args.output:
        write_json(Path(args.output).resolve(), payload)
    else:
        default_output = skill_dir / "evals" / "trigger_eval_report.json"
        write_json(default_output, payload)
        print(f"[OK] Wrote {default_output}")

    if args.markdown:
        write_text(Path(args.markdown).resolve(), render_markdown(payload["skill_name"], description, report))
    else:
        default_markdown = skill_dir / "evals" / "trigger_eval_report.md"
        write_text(default_markdown, render_markdown(payload["skill_name"], description, report))
        print(f"[OK] Wrote {default_markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
