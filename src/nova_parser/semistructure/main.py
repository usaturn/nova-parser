"""半構造化パイプライン専用 CLI。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from nova_parser.gemini_backend import BackendUnavailableError, current_backend
from nova_parser.semistructure.llm import GeminiStructureClassifier
from nova_parser.semistructure.manifest import load_manifest
from nova_parser.semistructure.models import PipelineConfig
from nova_parser.semistructure.pipeline import PipelineReport, run_pipeline


def ensure_backend_available() -> None:
    """Gemini / Vertex の API キーが無ければ BackendUnavailableError を送出する。"""
    current_backend()


def build_parser() -> argparse.ArgumentParser:
    """CLI 引数パーサを構築する。"""
    parser = argparse.ArgumentParser(
        description="OCR regions.json を追跡可能な半構造化 JSONL へ変換する",
    )
    parser.add_argument("--manifest", type=Path, required=True, help="書籍マニフェスト JSON")
    parser.add_argument("--input-dir", type=Path, required=True, help="*.regions.json の入力ディレクトリ")
    parser.add_argument("--output-dir", type=Path, required=True, help="正本・派生・レビューの出力先")
    parser.add_argument(
        "--review-decisions",
        type=Path,
        default=None,
        help="人手レビュー判断 JSONL（任意）",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="ページ単位キャッシュの読み取りを無効化する（正本検証は常に実行）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="LLM を呼ばず入力検査と決定的正規化まで行い件数を表示する",
    )
    return parser


def format_report(report: PipelineReport) -> str:
    """dry-run / 通常実行の件数サマリを整形する。"""
    lines = [
        f"pages={report.pages} regions={report.regions}",
        f"llm_calls={report.llm_calls}",
        f"input_errors={report.input_errors}",
    ]
    if report.review_candidates:
        lines.append(f"review_candidates={report.review_candidates}")
    if report.failed_pages:
        pages = ",".join(str(page) for page in report.failed_pages)
        lines.append(f"failed_pages={pages}")
    if report.segments:
        lines.append(f"segments={report.segments}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    """CLI エントリポイント。argv=None なら sys.argv を使用する。"""
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    config = PipelineConfig(
        manifest_path=args.manifest,
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        review_decisions=args.review_decisions,
        no_cache=args.no_cache,
        dry_run=args.dry_run,
    )

    if config.dry_run:
        report = run_pipeline(config, classifier=None)
        print(format_report(report))
        return

    # 正本上書き前に API キー有無を検査する
    try:
        ensure_backend_available()
    except BackendUnavailableError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error

    manifest = load_manifest(config.manifest_path)
    classifier = GeminiStructureClassifier(
        manifest=manifest,
        failure_dir=config.output_dir / "failures",
    )
    report = run_pipeline(config, classifier=classifier)
    print(format_report(report))


if __name__ == "__main__":
    main()
