#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from generate_openai_yaml import write_openai_yaml

MAX_SKILL_NAME_LENGTH = 64
ALLOWED_RESOURCES = {"scripts", "references", "assets"}

SKILL_TEMPLATE = """---
name: {skill_name}
description: [TODO: Explain what the skill does and when Codex should use it. Put trigger guidance here, not in the body.]
---

# {skill_title}

## Overview

[TODO: Explain what this skill enables in 1-2 sentences.]

## Workflow

1. [TODO: First step]
2. [TODO: Second step]
3. [TODO: Validation or output expectations]

## Resources

[TODO: Describe scripts/, references/, assets/, and evals/ only if they exist.]

## Validation

- Run `scripts/quick_validate.py <skill-dir>` after meaningful edits.
- Add or update `evals/evals.json` if this skill benefits from repeatable checks.
"""

SCRIPT_TEMPLATE = """#!/usr/bin/env python3
\"\"\"Placeholder helper script for {skill_name}.\"\"\"


def main() -> None:
    print("Replace this placeholder with a real script or delete it.")


if __name__ == "__main__":
    main()
"""

REFERENCE_TEMPLATE = """# Reference Notes

Replace this file with reference material that another Codex instance should read on demand.
"""

ASSET_TEMPLATE = """This placeholder represents bundled assets that should be copied or reused in outputs."""

EVALS_TEMPLATE = {
    "skill_name": "{skill_name}",
    "evals": [
        {
            "id": 1,
            "name": "example-scenario",
            "prompt": "Describe a realistic user request here.",
            "expected_output": "Describe the successful outcome.",
            "files": [],
            "expectations": [
                "List one concrete thing the output should contain."
            ],
        }
    ],
}

TRIGGER_QUERIES_TEMPLATE = {
    "skill_name": "{skill_name}",
    "queries": [
        {
            "id": "q1",
            "query": "Describe a prompt that should trigger this skill.",
            "should_trigger": True,
            "expected_terms": [],
            "notes": "",
        },
        {
            "id": "q2",
            "query": "Describe a prompt that should not trigger this skill.",
            "should_trigger": False,
            "expected_terms": [],
            "notes": "",
        },
    ],
}


def normalize_skill_name(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value


def title_case_skill_name(skill_name: str) -> str:
    return " ".join(part.capitalize() for part in skill_name.split("-"))


def parse_resources(raw_resources: str) -> list[str]:
    if not raw_resources:
        return []
    resources = [item.strip() for item in raw_resources.split(",") if item.strip()]
    invalid = sorted({item for item in resources if item not in ALLOWED_RESOURCES})
    if invalid:
        allowed = ", ".join(sorted(ALLOWED_RESOURCES))
        raise ValueError(f"Unknown resource type(s): {', '.join(invalid)}. Allowed: {allowed}")
    deduped: list[str] = []
    seen: set[str] = set()
    for resource in resources:
        if resource not in seen:
            seen.add(resource)
            deduped.append(resource)
    return deduped


def create_resource_dirs(skill_dir: Path, skill_name: str, resources: list[str], examples: bool) -> None:
    for resource in resources:
        resource_dir = skill_dir / resource
        resource_dir.mkdir(parents=True, exist_ok=True)
        if not examples:
            continue
        if resource == "scripts":
            (resource_dir / "example.py").write_text(
                SCRIPT_TEMPLATE.format(skill_name=skill_name),
                encoding="utf-8",
            )
        elif resource == "references":
            (resource_dir / "overview.md").write_text(REFERENCE_TEMPLATE, encoding="utf-8")
        elif resource == "assets":
            (resource_dir / "placeholder.txt").write_text(ASSET_TEMPLATE, encoding="utf-8")


def create_eval_templates(skill_dir: Path, skill_name: str) -> None:
    import json

    evals_dir = skill_dir / "evals"
    evals_dir.mkdir(parents=True, exist_ok=True)
    evals_payload = json.dumps(
        {
            "skill_name": skill_name,
            "evals": EVALS_TEMPLATE["evals"],
        },
        indent=2,
    ).replace("{skill_name}", skill_name)
    (evals_dir / "evals.json").write_text(evals_payload + "\n", encoding="utf-8")

    trigger_payload = json.dumps(
        {
            "skill_name": skill_name,
            "queries": TRIGGER_QUERIES_TEMPLATE["queries"],
        },
        indent=2,
    ).replace("{skill_name}", skill_name)
    (evals_dir / "trigger_queries.json").write_text(trigger_payload + "\n", encoding="utf-8")


def init_skill(
    skill_name: str,
    path: Path,
    resources: list[str],
    interface_overrides: list[str],
    examples: bool,
    include_evals: bool,
) -> Path:
    skill_dir = path / skill_name
    if skill_dir.exists():
        raise FileExistsError(f"Skill directory already exists: {skill_dir}")
    skill_dir.mkdir(parents=True, exist_ok=False)

    skill_title = title_case_skill_name(skill_name)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        SKILL_TEMPLATE.format(skill_name=skill_name, skill_title=skill_title),
        encoding="utf-8",
    )

    write_openai_yaml(skill_dir, skill_name, interface_overrides, allow_implicit=True)
    create_resource_dirs(skill_dir, skill_name, resources, examples)
    if include_evals:
        create_eval_templates(skill_dir, skill_name)
    return skill_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize a new Codex skill.")
    parser.add_argument("skill_name", help="Hyphen-case skill name")
    parser.add_argument("--path", required=True, help="Parent directory for the skill")
    parser.add_argument(
        "--resources",
        default="scripts,references,assets",
        help="Comma-separated resource dirs to create",
    )
    parser.add_argument("--examples", action="store_true", help="Add placeholder files")
    parser.add_argument("--evals", action="store_true", help="Create eval templates")
    parser.add_argument(
        "--interface",
        action="append",
        default=[],
        help="Override openai.yaml values in key=value form",
    )
    args = parser.parse_args()

    skill_name = normalize_skill_name(args.skill_name)
    if not skill_name:
        raise SystemExit("Skill name is required")
    if skill_name != args.skill_name.strip().lower():
        print(f"[INFO] Normalized skill name to {skill_name}")
    if len(skill_name) > MAX_SKILL_NAME_LENGTH:
        raise SystemExit(
            f"Skill name is too long ({len(skill_name)}). Maximum is {MAX_SKILL_NAME_LENGTH}."
        )

    resources = parse_resources(args.resources)
    skill_dir = init_skill(
        skill_name=skill_name,
        path=Path(args.path).resolve(),
        resources=resources,
        interface_overrides=args.interface,
        examples=args.examples,
        include_evals=args.evals,
    )
    print(f"[OK] Created {skill_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
