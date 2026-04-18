#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from common import read_skill_description, tokenize, update_skill_description, write_json, write_text
from run_trigger_eval import evaluate_queries, load_queries


def shorten_query(query: str, limit: int = 80) -> str:
    compact = " ".join(query.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def build_candidate_description(
    skill_name: str,
    current_description: str,
    queries: list[dict],
    report: dict,
) -> tuple[str, list[str]]:
    prefix = current_description.split("Use when", 1)[0].strip()
    if not prefix or prefix.startswith("[TODO"):
        prefix = f"Help Codex with {skill_name.replace('-', ' ')} work."
    if not prefix.endswith("."):
        prefix = prefix.rstrip(".") + "."

    missing_counter: Counter[str] = Counter()
    positive_queries: list[str] = []
    for item, result in zip(queries, report["results"]):
        if item.get("should_trigger"):
            positive_queries.append(item["query"])
        if item.get("should_trigger") and (not result["correct"] or result["coverage"] < 0.5):
            for term in result["missing_terms"]:
                missing_counter[term] += 1

    if not missing_counter:
        for item in queries:
            if item.get("should_trigger"):
                for term in tokenize(item["query"]):
                    missing_counter[term] += 1

    top_terms = [term for term, _ in missing_counter.most_common(8)]
    sample_queries = [shorten_query(query, limit=64) for query in positive_queries[:3]]
    trigger_sentence = (
        "Use when Codex needs help with "
        + ", ".join(top_terms)
        + ", or closely related requests."
        if top_terms
        else "Use when Codex needs help with the workflows covered by this skill."
    )
    examples_sentence = ""
    if sample_queries:
        examples_sentence = " Strong trigger examples include: " + "; ".join(sample_queries) + "."

    candidate = prefix + " " + trigger_sentence + examples_sentence
    if len(candidate) > 1024:
        candidate = (prefix + " " + trigger_sentence)[:1024].rstrip()
    return candidate, top_terms


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest a stronger skill description.")
    parser.add_argument("skill_dir", help="Path to the skill directory")
    parser.add_argument(
        "--queries",
        help="Path to trigger_queries.json (defaults to <skill>/evals/trigger_queries.json)",
    )
    parser.add_argument("--output", help="Optional JSON output path")
    parser.add_argument("--text-output", help="Optional text output path")
    parser.add_argument("--apply", action="store_true", help="Write the suggested description to SKILL.md")
    parser.add_argument("--threshold", type=float, default=0.34, help="Coverage threshold")
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    queries_path = (
        Path(args.queries).resolve()
        if args.queries
        else skill_dir / "evals" / "trigger_queries.json"
    )
    skill_name, queries = load_queries(queries_path)
    current_description = read_skill_description(skill_dir)
    baseline_report = evaluate_queries(current_description, queries, args.threshold)
    suggested_description, added_terms = build_candidate_description(
        skill_name or skill_dir.name,
        current_description,
        queries,
        baseline_report,
    )
    suggested_report = evaluate_queries(suggested_description, queries, args.threshold)

    payload = {
        "skill_name": skill_name or skill_dir.name,
        "current_description": current_description,
        "suggested_description": suggested_description,
        "added_terms": added_terms,
        "current_summary": baseline_report["summary"],
        "suggested_summary": suggested_report["summary"],
        "queries_path": str(queries_path),
    }

    output_path = (
        Path(args.output).resolve()
        if args.output
        else skill_dir / "evals" / "description_optimization.json"
    )
    write_json(output_path, payload)
    print(f"[OK] Wrote {output_path}")

    text_path = (
        Path(args.text_output).resolve()
        if args.text_output
        else skill_dir / "evals" / "suggested_description.txt"
    )
    write_text(text_path, suggested_description + "\n")
    print(f"[OK] Wrote {text_path}")

    if args.apply:
        update_skill_description(skill_dir, suggested_description)
        print(f"[OK] Updated {skill_dir / 'SKILL.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
