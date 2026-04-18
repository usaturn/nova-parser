#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml as _yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:
    _yaml = None

STOPWORDS = {
    "a",
    "an",
    "and",
    "any",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "help",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "please",
    "that",
    "the",
    "this",
    "to",
    "use",
    "want",
    "when",
    "with",
    "you",
}

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".css",
    ".sh",
    ".toml",
    ".sql",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
METADATA_FILES = {"transcript.md", "user_notes.md", "metrics.json"}


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def mean_stddev(values: Iterable[float]) -> dict[str, float]:
    series = list(values)
    if not series:
        return {"mean": 0.0, "stddev": 0.0}
    if len(series) == 1:
        return {"mean": float(series[0]), "stddev": 0.0}
    return {
        "mean": float(statistics.mean(series)),
        "stddev": float(statistics.pstdev(series)),
    }


def parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if value.startswith('"') and value.endswith('"'):
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


BLOCK_SCALAR_INDICATORS = {"|", "|-", "|+", ">", ">-", ">+"}


def _line_indent(raw_line: str) -> int:
    return len(raw_line) - len(raw_line.lstrip(" "))


def _skip_ignored_lines(lines: list[str], index: int) -> int:
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped and not lines[index].lstrip().startswith("#"):
            break
        index += 1
    return index


def _fold_block_scalar(content_lines: list[str]) -> str:
    paragraphs: list[list[str]] = []
    current: list[str] = []
    for line in content_lines:
        if line == "":
            if current:
                paragraphs.append(current)
                current = []
            else:
                paragraphs.append([])
            continue
        current.append(line)
    if current:
        paragraphs.append(current)

    rendered: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            if rendered and rendered[-1] != "":
                rendered.append("")
            continue
        rendered.append(" ".join(part.strip() for part in paragraph))
    return "\n".join(rendered)


def _parse_block_scalar(
    lines: list[str],
    start: int,
    parent_indent: int,
    indicator: str,
) -> tuple[str, int]:
    index = start
    content_indent: int | None = None
    collected: list[str] = []

    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        current_indent = _line_indent(raw_line)

        if stripped == "":
            if content_indent is None:
                collected.append("")
            else:
                collected.append("")
            index += 1
            continue

        if current_indent <= parent_indent:
            break

        if content_indent is None:
            content_indent = current_indent
        if current_indent < content_indent:
            break

        collected.append(raw_line[content_indent:])
        index += 1

    if not collected:
        return "", index

    style = indicator[0]
    if style == ">":
        return _fold_block_scalar(collected), index
    return "\n".join(collected), index


def _parse_mapping_entry(
    lines: list[str],
    index: int,
    indent: int,
    content: str,
) -> tuple[str, Any, int]:
    key, separator, value = content.partition(":")
    if not separator:
        raise ValueError(f"Invalid mapping entry: {content}")

    key = key.strip()
    value = value.strip()
    next_index = index + 1

    if value in BLOCK_SCALAR_INDICATORS:
        scalar, next_index = _parse_block_scalar(lines, next_index, indent, value)
        return key, scalar, next_index

    if value:
        return key, parse_scalar(value), next_index

    lookahead = _skip_ignored_lines(lines, next_index)
    if lookahead < len(lines) and _line_indent(lines[lookahead]) > indent:
        child, next_index = _parse_yaml_lines(lines, lookahead, _line_indent(lines[lookahead]))
        return key, child, next_index
    return key, "", next_index


def _parse_list_item(
    lines: list[str],
    index: int,
    indent: int,
    item_text: str,
) -> tuple[Any, int]:
    next_index = index + 1
    if not item_text:
        lookahead = _skip_ignored_lines(lines, next_index)
        if lookahead < len(lines) and _line_indent(lines[lookahead]) > indent:
            return _parse_yaml_lines(lines, lookahead, _line_indent(lines[lookahead]))
        return "", next_index

    if ":" in item_text and not item_text.startswith(("'", '"')):
        key, value, next_index = _parse_mapping_entry(lines, index, indent, item_text)
        item: dict[str, Any] = {key: value}
        lookahead = _skip_ignored_lines(lines, next_index)
        if lookahead < len(lines) and _line_indent(lines[lookahead]) > indent:
            extra, next_index = _parse_yaml_lines(lines, lookahead, _line_indent(lines[lookahead]))
            if not isinstance(extra, dict):
                raise ValueError("List item mapping cannot be followed by a non-mapping block.")
            item.update(extra)
        return item, next_index

    return parse_scalar(item_text), next_index


def _parse_yaml_lines(lines: list[str], start: int, indent: int) -> tuple[Any, int]:
    container: Any | None = None
    index = start

    while index < len(lines):
        index = _skip_ignored_lines(lines, index)
        if index >= len(lines):
            break

        raw_line = lines[index]
        current_indent = _line_indent(raw_line)
        if current_indent < indent:
            break
        if current_indent > indent:
            raise ValueError(f"Unexpected indentation near: {raw_line.strip()}")

        content = raw_line[current_indent:]
        if content.startswith("- "):
            if container is None:
                container = []
            elif not isinstance(container, list):
                raise ValueError("Cannot mix mapping and list items at the same indentation.")
            item, index = _parse_list_item(lines, index, indent, content[2:].strip())
            container.append(item)
            continue

        if container is None:
            container = {}
        elif not isinstance(container, dict):
            raise ValueError("Cannot mix list items and mapping keys at the same indentation.")

        key, value, index = _parse_mapping_entry(lines, index, indent, content)
        container[key] = value

    if container is None:
        container = {}
    return container, index


def parse_yaml_block(text: str) -> Any:
    if _yaml is not None:
        return _yaml.safe_load(text)

    lines = text.splitlines()
    start = _skip_ignored_lines(lines, 0)
    if start >= len(lines):
        return {}
    parsed, index = _parse_yaml_lines(lines, start, _line_indent(lines[start]))
    index = _skip_ignored_lines(lines, index)
    if index != len(lines):
        raise ValueError("Could not parse the complete YAML block.")
    return parsed


def dump_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def dump_yaml_block(payload: Any, indent: int = 0) -> str:
    if _yaml is not None:
        return _yaml.safe_dump(
            payload,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        ).rstrip()

    lines: list[str] = []
    pad = " " * indent
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.append(dump_yaml_block(value, indent + 2))
            else:
                lines.append(f"{pad}{key}: {dump_scalar(value)}")
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.append(dump_yaml_block(item, indent + 2))
            else:
                lines.append(f"{pad}- {dump_scalar(item)}")
    return "\n".join(lines)


def read_frontmatter(skill_md: Path) -> tuple[dict[str, Any], str]:
    content = read_text(skill_md)
    match = re.match(r"^---\n(.*?)\n---\n?(.*)$", content, re.DOTALL)
    if not match:
        raise ValueError(f"Invalid SKILL.md frontmatter in {skill_md}")
    frontmatter = parse_yaml_block(match.group(1)) or {}
    if not isinstance(frontmatter, dict):
        raise ValueError(f"Frontmatter must be a mapping in {skill_md}")
    body = match.group(2)
    return frontmatter, body


def load_skill_info(skill_dir: Path) -> tuple[dict[str, Any], str]:
    return read_frontmatter(skill_dir / "SKILL.md")


def read_skill_name(skill_dir: Path) -> str:
    frontmatter, _ = load_skill_info(skill_dir)
    name = frontmatter.get("name", "")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Missing skill name in {skill_dir / 'SKILL.md'}")
    return name.strip()


def read_skill_description(skill_dir: Path) -> str:
    frontmatter, _ = load_skill_info(skill_dir)
    description = frontmatter.get("description", "")
    if not isinstance(description, str):
        raise ValueError(f"Invalid description in {skill_dir / 'SKILL.md'}")
    return description.strip()


def update_skill_description(skill_dir: Path, new_description: str) -> None:
    skill_md = skill_dir / "SKILL.md"
    frontmatter, body = load_skill_info(skill_dir)
    frontmatter["description"] = new_description.strip()
    frontmatter_text = dump_yaml_block(frontmatter).strip()
    write_text(skill_md, f"---\n{frontmatter_text}\n---\n\n{body.lstrip()}")


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9.+-]*", text.lower())
    return [token for token in tokens if token not in STOPWORDS]


def score_description(
    description: str,
    query: str,
    expected_terms: list[str] | None = None,
    threshold: float = 0.34,
) -> dict[str, Any]:
    description_terms = set(tokenize(description))
    query_terms = set(expected_terms or tokenize(query))
    if not query_terms:
        return {
            "coverage": 0.0,
            "triggered": False,
            "matched_terms": [],
            "missing_terms": [],
        }
    matched_terms = sorted(description_terms & query_terms)
    missing_terms = sorted(query_terms - description_terms)
    coverage = len(matched_terms) / len(query_terms)
    triggered = coverage >= threshold or len(missing_terms) == 0
    return {
        "coverage": round(coverage, 4),
        "triggered": triggered,
        "matched_terms": matched_terms,
        "missing_terms": missing_terms,
    }


def find_run_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    run_dirs = sorted({outputs.parent for outputs in root.rglob("outputs") if outputs.is_dir()})
    return run_dirs


def load_eval_metadata(run_dir: Path) -> dict[str, Any]:
    for candidate in (run_dir / "eval_metadata.json", run_dir.parent / "eval_metadata.json"):
        data = load_json(candidate)
        if isinstance(data, dict):
            return data
    return {}


def load_grading(run_dir: Path) -> dict[str, Any]:
    for candidate in (run_dir / "grading.json", run_dir.parent / "grading.json"):
        data = load_json(candidate)
        if isinstance(data, dict):
            return data
    return {}


def load_timing(run_dir: Path) -> dict[str, Any]:
    for candidate in (run_dir / "timing.json", run_dir.parent / "timing.json"):
        data = load_json(candidate)
        if isinstance(data, dict):
            return data
    return {}


def load_metrics(run_dir: Path) -> dict[str, Any]:
    metrics_path = run_dir / "outputs" / "metrics.json"
    data = load_json(metrics_path)
    return data if isinstance(data, dict) else {}


def list_output_files(outputs_dir: Path) -> list[Path]:
    if not outputs_dir.is_dir():
        return []
    return sorted(
        [
            path
            for path in outputs_dir.iterdir()
            if path.is_file() and path.name not in METADATA_FILES
        ]
    )
