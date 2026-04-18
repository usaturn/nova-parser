#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import read_skill_name

ACRONYMS = {"API", "CLI", "CI", "LLM", "MCP", "PDF", "PR", "SQL", "UI", "URL"}
SMALL_WORDS = {"and", "or", "to", "up", "with"}
BRANDS = {
    "github": "GitHub",
    "openai": "OpenAI",
    "openapi": "OpenAPI",
    "fastapi": "FastAPI",
    "sqlite": "SQLite",
}
ALLOWED_INTERFACE_KEYS = {
    "display_name",
    "short_description",
    "default_prompt",
    "icon_small",
    "icon_large",
    "brand_color",
}


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Expected boolean value, got {value!r}")


def format_display_name(skill_name: str) -> str:
    words = [word for word in skill_name.split("-") if word]
    formatted: list[str] = []
    for index, word in enumerate(words):
        upper = word.upper()
        lower = word.lower()
        if upper in ACRONYMS:
            formatted.append(upper)
        elif lower in BRANDS:
            formatted.append(BRANDS[lower])
        elif index > 0 and lower in SMALL_WORDS:
            formatted.append(lower)
        else:
            formatted.append(word.capitalize())
    return " ".join(formatted)


def generate_short_description(display_name: str) -> str:
    candidates = [
        f"Build and improve {display_name}",
        f"Help with {display_name} tasks",
        f"{display_name} creation helper",
        f"{display_name} workflow helper",
    ]
    for candidate in candidates:
        if 25 <= len(candidate) <= 64:
            return candidate
    return candidates[-1][:64].rstrip()


def parse_interface_overrides(raw_items: list[str]) -> tuple[dict[str, str], list[str]]:
    overrides: dict[str, str] = {}
    ordered_optional: list[str] = []
    for item in raw_items:
        if "=" not in item:
            raise ValueError(f"Invalid interface override: {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key not in ALLOWED_INTERFACE_KEYS:
            allowed = ", ".join(sorted(ALLOWED_INTERFACE_KEYS))
            raise ValueError(f"Unknown interface field {key!r}. Allowed: {allowed}")
        overrides[key] = value
        if key not in {"display_name", "short_description"} and key not in ordered_optional:
            ordered_optional.append(key)
    return overrides, ordered_optional


def write_openai_yaml(
    skill_dir: Path,
    skill_name: str,
    interface_items: list[str],
    allow_implicit: bool = True,
) -> Path:
    overrides, optional_order = parse_interface_overrides(interface_items)
    display_name = overrides.get("display_name") or format_display_name(skill_name)
    short_description = overrides.get("short_description") or generate_short_description(display_name)
    if not 25 <= len(short_description) <= 64:
        raise ValueError("short_description must be 25-64 characters long")

    if "default_prompt" not in overrides:
        overrides["default_prompt"] = f"Use ${skill_name} to help with {display_name.lower()}."
        if "default_prompt" not in optional_order:
            optional_order.append("default_prompt")

    lines = [
        "interface:",
        f"  display_name: {yaml_quote(display_name)}",
        f"  short_description: {yaml_quote(short_description)}",
    ]
    for key in optional_order:
        lines.append(f"  {key}: {yaml_quote(overrides[key])}")
    lines.extend(
        [
            "policy:",
            f"  allow_implicit_invocation: {'true' if allow_implicit else 'false'}",
        ]
    )

    output_path = skill_dir / "agents" / "openai.yaml"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate agents/openai.yaml for a skill.")
    parser.add_argument("skill_dir", help="Path to the skill directory")
    parser.add_argument("--name", help="Override skill name from SKILL.md")
    parser.add_argument(
        "--interface",
        action="append",
        default=[],
        help="Interface override in key=value format",
    )
    parser.add_argument(
        "--allow-implicit",
        default="true",
        help="Whether to allow implicit invocation (true/false)",
    )
    args = parser.parse_args()

    skill_dir = Path(args.skill_dir).resolve()
    skill_name = args.name or read_skill_name(skill_dir)
    allow_implicit = parse_bool(args.allow_implicit)
    output_path = write_openai_yaml(skill_dir, skill_name, args.interface, allow_implicit)
    print(f"[OK] Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
