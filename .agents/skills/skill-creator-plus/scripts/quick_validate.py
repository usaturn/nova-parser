#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import parse_yaml_block

MAX_SKILL_NAME_LENGTH = 64
ALLOWED_FRONTMATTER = {"name", "description", "license", "allowed-tools", "metadata"}


def validate_frontmatter(skill_md: Path, errors: list[str]) -> None:
    content = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", content, re.DOTALL)
    if not match:
        errors.append("SKILL.md must start with YAML frontmatter.")
        return
    try:
        frontmatter = parse_yaml_block(match.group(1))
    except ValueError as exc:
        errors.append(f"Invalid YAML frontmatter: {exc}")
        return
    if not isinstance(frontmatter, dict):
        errors.append("Frontmatter must be a YAML mapping.")
        return

    unexpected = sorted(set(frontmatter) - ALLOWED_FRONTMATTER)
    if unexpected:
        errors.append(
            "Unexpected frontmatter keys: "
            + ", ".join(unexpected)
            + ". Allowed keys: "
            + ", ".join(sorted(ALLOWED_FRONTMATTER))
        )

    name = frontmatter.get("name")
    description = frontmatter.get("description")
    if not isinstance(name, str) or not name.strip():
        errors.append("Frontmatter must include a non-empty string 'name'.")
    elif not re.match(r"^[a-z0-9-]+$", name):
        errors.append("Skill name must be hyphen-case: lowercase letters, digits, hyphens.")
    elif len(name) > MAX_SKILL_NAME_LENGTH:
        errors.append(
            f"Skill name is too long ({len(name)}). Maximum is {MAX_SKILL_NAME_LENGTH}."
        )

    if not isinstance(description, str) or not description.strip():
        errors.append("Frontmatter must include a non-empty string 'description'.")
    elif len(description) > 1024:
        errors.append("Description must be 1024 characters or fewer.")
    elif "<" in description or ">" in description:
        errors.append("Description cannot contain angle brackets.")


def validate_openai_yaml(skill_dir: Path, errors: list[str]) -> None:
    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if not openai_yaml.exists():
        errors.append("agents/openai.yaml is missing.")
        return
    try:
        payload = parse_yaml_block(openai_yaml.read_text(encoding="utf-8"))
    except ValueError as exc:
        errors.append(f"Invalid agents/openai.yaml: {exc}")
        return
    if not isinstance(payload, dict):
        errors.append("agents/openai.yaml must be a YAML mapping.")
        return
    interface = payload.get("interface")
    if not isinstance(interface, dict):
        errors.append("agents/openai.yaml must contain interface: mapping.")
        return
    display_name = interface.get("display_name")
    short_description = interface.get("short_description")
    if not isinstance(display_name, str) or not display_name.strip():
        errors.append("interface.display_name must be a non-empty string.")
    if not isinstance(short_description, str) or not short_description.strip():
        errors.append("interface.short_description must be a non-empty string.")
    elif not 25 <= len(short_description) <= 64:
        errors.append("interface.short_description must be 25-64 characters.")

    default_prompt = interface.get("default_prompt")
    if default_prompt is not None and (
        not isinstance(default_prompt, str) or "$" not in default_prompt
    ):
        errors.append("interface.default_prompt must be a string that references $skill-name.")

    policy = payload.get("policy", {})
    if policy and not isinstance(policy, dict):
        errors.append("policy must be a mapping when present.")
    elif "allow_implicit_invocation" in policy and not isinstance(
        policy["allow_implicit_invocation"], bool
    ):
        errors.append("policy.allow_implicit_invocation must be a boolean.")


def validate_evals_json(path: Path, errors: list[str]) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path.name} is not valid JSON: {exc}")
        return
    if not isinstance(payload, dict):
        errors.append(f"{path.name} must contain a top-level object.")
        return
    if not isinstance(payload.get("skill_name"), str) or not payload["skill_name"].strip():
        errors.append(f"{path.name} must contain a non-empty string skill_name.")
    evals = payload.get("evals")
    if not isinstance(evals, list) or not evals:
        errors.append(f"{path.name} must contain a non-empty evals array.")
        return
    for index, item in enumerate(evals, start=1):
        if not isinstance(item, dict):
            errors.append(f"{path.name} eval #{index} must be an object.")
            continue
        if not isinstance(item.get("id"), int):
            errors.append(f"{path.name} eval #{index} must include integer id.")
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            errors.append(f"{path.name} eval #{index} must include non-empty name.")
        if not isinstance(item.get("prompt"), str) or not item["prompt"].strip():
            errors.append(f"{path.name} eval #{index} must include non-empty prompt.")
        if not isinstance(item.get("expected_output"), str) or not item["expected_output"].strip():
            errors.append(
                f"{path.name} eval #{index} must include non-empty expected_output."
            )
        if "files" in item and not isinstance(item["files"], list):
            errors.append(f"{path.name} eval #{index} files must be an array.")
        if "expectations" in item and not isinstance(item["expectations"], list):
            errors.append(f"{path.name} eval #{index} expectations must be an array.")


def validate_trigger_queries(path: Path, errors: list[str]) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path.name} is not valid JSON: {exc}")
        return
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        errors.append(f"{path.name} must contain a non-empty queries array.")
        return
    for index, item in enumerate(queries, start=1):
        if not isinstance(item, dict):
            errors.append(f"{path.name} query #{index} must be an object.")
            continue
        if not isinstance(item.get("id"), str) or not item["id"].strip():
            errors.append(f"{path.name} query #{index} must include string id.")
        if not isinstance(item.get("query"), str) or not item["query"].strip():
            errors.append(f"{path.name} query #{index} must include non-empty query.")
        if not isinstance(item.get("should_trigger"), bool):
            errors.append(f"{path.name} query #{index} must include boolean should_trigger.")


def validate_skill(skill_dir: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return False, ["SKILL.md not found."]
    validate_frontmatter(skill_md, errors)
    validate_openai_yaml(skill_dir, errors)

    evals_dir = skill_dir / "evals"
    evals_json = evals_dir / "evals.json"
    trigger_queries = evals_dir / "trigger_queries.json"
    if evals_json.exists():
        validate_evals_json(evals_json, errors)
    if trigger_queries.exists():
        validate_trigger_queries(trigger_queries, errors)
    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Codex skill bundle.")
    parser.add_argument("skill_dir", help="Path to the skill directory")
    args = parser.parse_args()

    valid, errors = validate_skill(Path(args.skill_dir).resolve())
    if valid:
        print("Skill is valid.")
        return 0
    print("Validation failed:")
    for error in errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
