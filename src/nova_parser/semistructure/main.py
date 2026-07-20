"""半構造化パイプライン専用 CLI。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from nova_parser.gemini_backend import BackendUnavailableError, current_backend
from nova_parser.semistructure.evaluate import evaluate_gold_against_output, format_structure_metrics
from nova_parser.semistructure.llm import GeminiStructureClassifier, StructureClassifier
from nova_parser.semistructure.manifest import load_manifest
from nova_parser.semistructure.models import PipelineConfig
from nova_parser.semistructure.pipeline import PipelineReport, run_pipeline


def ensure_backend_available() -> None:
    """Gemini / Vertex の API キーが無ければ BackendUnavailableError を送出する。"""
    current_backend()


def build_classifier(config: PipelineConfig) -> StructureClassifier:
    """マニフェストと出力先から本番用 StructureClassifier を構築する。

    テストではこの関数を差し替えて FakeClassifier 等を注入する。
    """
    manifest = load_manifest(config.manifest_path)
    return GeminiStructureClassifier(
        manifest=manifest,
        failure_dir=config.output_dir / "failures",
    )


def build_parser() -> argparse.ArgumentParser:
    """CLI 引数パーサを構築する。"""
    parser = argparse.ArgumentParser(
        description="OCR regions.json を追跡可能な半構造化 JSONL へ変換する",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="書籍マニフェスト JSON（--evaluate-gold のみのときは不要）",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="*.regions.json の入力ディレクトリ（--evaluate-gold のみのときは不要）",
    )
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
    parser.add_argument(
        "--evaluate-gold",
        type=Path,
        default=None,
        help=(
            "正解 gold-segments.jsonl（またはそれを含むディレクトリ）。"
            "指定時は output-dir/segments.jsonl と構造比較してメトリクスを表示する"
        ),
    )
    return parser


def format_report(report: PipelineReport) -> str:
    """dry-run / 通常実行の件数サマリを整形する。"""
    lines = [
        f"pages={report.pages} regions={report.regions}",
        f"llm_calls={report.llm_calls}",
        f"input_errors={report.input_errors}",
    ]
    if not report.dry_run:
        lines.append(f"source_coverage={report.source_coverage * 100:.2f}%")
        lines.append(f"validation_errors={report.validation_errors}")
        lines.append(f"segments={report.segments}")
    if report.review_required or report.review_candidates:
        required = report.review_required or report.review_candidates
        lines.append(f"review_required={required}")
    if report.failed_pages:
        pages = ",".join(str(page) for page in report.failed_pages)
        lines.append(f"failed_pages={pages}")
    return "\n".join(lines)


def exit_code_for_report(report: PipelineReport) -> int:
    """実行結果からプロセス終了コードを決定する。

    - 0: 成功（部分ページの LLM 失敗でも fallback があれば成功）
    - 2: 入力エラー
    - 3: 全ページで LLM が失敗
    - 4: 正本（provenance）検証エラー
    """
    if report.input_errors > 0:
        return 2
    if report.pages > 0 and report.failed_pages and len(report.failed_pages) >= report.pages:
        return 3
    if report.validation_errors > 0:
        return 4
    return 0


def _run_evaluate_gold(gold_path: Path, output_dir: Path, *, dry_run: bool = False) -> int:
    """output-dir/segments.jsonl と gold を比較して表示する。

    dry-run 経路では正本を新規に書かないため、既存 segments.jsonl が無い場合は
    評価をスキップして明確なメッセージを出す。
    成功時 0、評価不能時 1。
    """
    actual_path = Path(output_dir) / "segments.jsonl"
    if dry_run and not actual_path.is_file():
        print(
            "evaluate-gold: dry-run では正本を書かないため、"
            f"既存の segments.jsonl が必要です（見つかりません: {actual_path}）",
            file=sys.stderr,
        )
        return 0
    try:
        metrics = evaluate_gold_against_output(gold_path, output_dir)
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(format_structure_metrics(metrics))
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI エントリポイント。argv=None なら sys.argv を使用する。終了コードを返す。"""
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)

    # 評価のみ: 既存の正本と gold を比較して終了する
    if args.evaluate_gold is not None and args.manifest is None and args.input_dir is None:
        return _run_evaluate_gold(args.evaluate_gold, args.output_dir, dry_run=False)

    if args.manifest is None or args.input_dir is None:
        parser.error("--manifest と --input-dir はパイプライン実行時に必須です")

    config = PipelineConfig(
        manifest_path=args.manifest,
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        review_decisions=args.review_decisions,
        no_cache=args.no_cache,
        dry_run=args.dry_run,
    )

    if config.dry_run:
        try:
            report = run_pipeline(config, classifier=None)
        except (ValueError, FileNotFoundError, OSError) as error:
            print(str(error), file=sys.stderr)
            return 2
        print(format_report(report))
        # dry-run は正本を書かないが、既存 segments.jsonl があれば評価を続行する
        if args.evaluate_gold is not None:
            evaluate_code = _run_evaluate_gold(args.evaluate_gold, args.output_dir, dry_run=True)
            if evaluate_code != 0:
                return evaluate_code
        return exit_code_for_report(report)

    # 正本上書き前に API キー有無を検査する
    try:
        ensure_backend_available()
    except BackendUnavailableError as error:
        print(str(error), file=sys.stderr)
        return 1

    try:
        classifier = build_classifier(config)
        report = run_pipeline(config, classifier=classifier)
    except (ValueError, FileNotFoundError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 2

    print(format_report(report))

    # パイプライン後に gold 比較を続ける
    if args.evaluate_gold is not None:
        evaluate_code = _run_evaluate_gold(args.evaluate_gold, args.output_dir, dry_run=False)
        if evaluate_code != 0:
            return evaluate_code

    return exit_code_for_report(report)


if __name__ == "__main__":
    raise SystemExit(main())
