#!/usr/bin/env python3
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from quick_validate import validate_skill

EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    "dist",
    "node_modules",
}
EXCLUDED_FILE_NAMES = {".DS_Store", "feedback.json", "review.html"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp"}


def should_exclude(path: Path, skill_root: Path) -> bool:
    relative = path.relative_to(skill_root)
    if any(part in EXCLUDED_DIR_NAMES for part in relative.parts):
        return True
    if relative.name in EXCLUDED_FILE_NAMES:
        return True
    if relative.suffix in EXCLUDED_SUFFIXES:
        return True
    if relative.parts and relative.parts[0].endswith("-workspace"):
        return True
    return False


def package_skill(skill_dir: Path, output_dir: Path | None = None) -> Path:
    valid, errors = validate_skill(skill_dir)
    if not valid:
        raise ValueError("Validation failed:\n" + "\n".join(f"- {error}" for error in errors))

    destination_dir = output_dir or Path.cwd()
    destination_dir.mkdir(parents=True, exist_ok=True)
    archive_path = destination_dir / f"{skill_dir.name}.skill"

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(skill_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if should_exclude(file_path, skill_dir):
                continue
            archive.write(file_path, arcname=file_path.relative_to(skill_dir.parent))
    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Package a Codex skill as a .skill archive.")
    parser.add_argument("skill_dir", help="Path to the skill directory")
    parser.add_argument("output_dir", nargs="?", help="Optional output directory")
    args = parser.parse_args()

    archive_path = package_skill(
        Path(args.skill_dir).resolve(),
        Path(args.output_dir).resolve() if args.output_dir else None,
    )
    print(f"[OK] Wrote {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
