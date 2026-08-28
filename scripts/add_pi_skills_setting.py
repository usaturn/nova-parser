#!/usr/bin/env python3
"""pi のグローバル settings.json の skills 配列に、このリポジトリの .claude/skills を冪等に追記するスクリプト。

- リポジトリルートは .git ディレクトリを親方向に遡って自動検出する
- ~/.pi/agent/settings.json 内の相対パスは ~/.pi/agent 基準で解決されるため、
  絶対パスで追記する
- 同じパスが既に skills 配列にあれば変更しない（冪等）
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

DEFAULT_PI_SETTINGS = Path.home() / ".pi" / "agent" / "settings.json"


def find_repo_root(start: Path) -> Path:
    """start から親を遡り、.git を含む最初のディレクトリをリポジトリルートとして返す。"""
    current = start.resolve()
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            raise FileNotFoundError(f"{start} から遡っても .git が見つかりません")
        current = current.parent


def add_claude_skills(settings_path: Path, repo_root: Path) -> bool:
    """settings.json の skills 配列に <repo_root>/.claude/skills を絶対パスで追記する。

    変更があった場合 True、既に登録済みで変更が無い場合 False を返す。
    """
    repo_root = repo_root.resolve()
    skill_path = str(repo_root / ".claude" / "skills")
    if not (repo_root / ".claude" / "skills").is_dir():
        raise FileNotFoundError(f"{skill_path} が存在しません")

    # 既存 JSON を読み込み（なければ空 dict）
    data = {}
    if settings_path.exists():
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    # 冪等性: 既に登録済みなら中断
    skills = data.get("skills")
    if skills is not None and skill_path in skills:
        print(f"{skill_path} は既に skills 配列に登録されています。変更なし。")
        return False

    skills = list(skills) if skills is not None else []
    skills.append(skill_path)
    data["skills"] = skills

    # バックアップ
    if settings_path.exists():
        backup = str(settings_path) + ".bak"
        shutil.copy2(settings_path, backup)
        print(f"バックアップ作成: {backup}")

    # 原子的書き換え
    dir_name = settings_path.parent
    dir_name.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix="settings.json.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        if settings_path.exists():
            shutil.copymode(settings_path, tmp_path)
        os.replace(tmp_path, settings_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    print(f"{skill_path} を skills 配列に登録しました: {settings_path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="pi のグローバル settings.json に .claude/skills を冪等に追記する"
    )
    parser.add_argument(
        "--pi-settings",
        type=Path,
        default=DEFAULT_PI_SETTINGS,
        help=f"pi の設定ファイルパス（既定: {DEFAULT_PI_SETTINGS}）",
    )
    args = parser.parse_args()

    repo_root = find_repo_root(Path(__file__).parent)
    add_claude_skills(args.pi_settings, repo_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
