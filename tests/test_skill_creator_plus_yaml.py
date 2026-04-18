"""skill-creator-plus の YAML frontmatter 互換性テスト。"""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path


SKILL_COMMON = Path(
    "/workspaces/nova-parser/.agents/skills/skill-creator-plus/scripts/common.py"
)
SKILL_VALIDATOR = Path(
    "/workspaces/nova-parser/.agents/skills/skill-creator-plus/scripts/quick_validate.py"
)


def _write_skill(tmp_path: Path, description_block: str) -> Path:
    skill_dir = tmp_path / "sample-skill"
    (skill_dir / "agents").mkdir(parents=True)
    skill_md = (
        "---\n"
        "name: sample-skill\n"
        f"description: {description_block}\n"
        "metadata:\n"
        "  short-description: Sample skill for validator coverage\n"
        "---\n\n"
        "# Sample Skill\n"
    )
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    (skill_dir / "agents" / "openai.yaml").write_text(
        textwrap.dedent(
            """\
            interface:
              display_name: "Sample Skill"
              short_description: "Sample skill for validator coverage"
              default_prompt: "Use $sample-skill to do the sample task."
            policy:
              allow_implicit_invocation: true
            """
        ),
        encoding="utf-8",
    )
    return skill_dir


def test_read_frontmatter_supports_folded_multiline_description_via_python3(tmp_path):
    skill_dir = _write_skill(
        tmp_path,
        textwrap.indent(
            textwrap.dedent(
                """\
                >-
                  Retrieves up-to-date documentation, API references,
                  and code examples for any developer technology.

                  Always use this skill for library-specific questions.
                """
            ).rstrip(),
            "  ",
        ).lstrip(),
    )

    result = subprocess.run(
        [
            "python3",
            "-c",
            textwrap.dedent(
                f"""\
                import importlib.util
                import json
                from pathlib import Path

                spec = importlib.util.spec_from_file_location("skill_common", {str(SKILL_COMMON)!r})
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                frontmatter, _ = mod.read_frontmatter(Path({str(skill_dir / "SKILL.md")!r}))
                print(json.dumps(frontmatter, ensure_ascii=False))
                """
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["name"] == "sample-skill"
    assert payload["metadata"]["short-description"] == "Sample skill for validator coverage"
    assert (
        payload["description"]
        == "Retrieves up-to-date documentation, API references, and code examples for any developer technology.\nAlways use this skill for library-specific questions."
    )


def test_quick_validate_accepts_literal_multiline_description_via_python3(tmp_path):
    skill_dir = _write_skill(
        tmp_path,
        textwrap.indent(
            textwrap.dedent(
                """\
                |-
                  First line of the description.

                  Second paragraph stays on its own line.
                """
            ).rstrip(),
            "  ",
        ).lstrip(),
    )

    result = subprocess.run(
        ["python3", str(SKILL_VALIDATOR), str(skill_dir)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Skill is valid." in result.stdout
