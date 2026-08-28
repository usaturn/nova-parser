"""縦ブロックfixtureに対してローカル方式とGeminiの矩形精度を比較する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path
from statistics import mean
from typing import Callable, Sequence

from google.genai import types

from nova_parser.gemini_backend import get_client
from nova_parser.regional_ocr.layout import compute_vertical_blocks
from nova_parser.regional_ocr.models import BlockRect

_MODEL = "gemini-3.5-flash-lite"
_PROMPT_CONTRACT_VERSION = "regional-layout-eval-v1"
_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "blocks": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "box_2d": {
                        "type": "ARRAY",
                        "items": {"type": "INTEGER"},
                        "minItems": 4,
                        "maxItems": 4,
                    }
                },
                "required": ["box_2d"],
            },
        }
    },
    "required": ["blocks"],
}
_GROUP_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "groups": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"candidate_ids": {"type": "ARRAY", "items": {"type": "INTEGER"}}},
                "required": ["candidate_ids"],
            },
        }
    },
    "required": ["groups"],
}
_REFERENCE_STEMS = {
    "WaresBrade": ("WaresBrade_P034", "WaresBrade_P040", "WaresBrade_P053"),
    "warse_rule": ("warse_rule_p18", "warse_rule_p42"),
    "warse_start": ("warse_start_p20", "warse_start_p42"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluation_cache_fingerprint(
    *,
    method: str,
    model: str,
    fixture: dict[str, object],
    image_path: Path,
    examples: Sequence[tuple[str, dict[str, object], Path]],
) -> str:
    """モデル入力とプロンプト契約を識別する安定したキャッシュ指紋を返す。"""
    manifest = {
        "prompt_contract_version": _PROMPT_CONTRACT_VERSION,
        "method": method,
        "model": model,
        "target": {"fixture": fixture, "image_sha256": _sha256(image_path)},
        "examples": [
            {"stem": stem, "fixture": example_fixture, "image_sha256": _sha256(example_path)}
            for stem, example_fixture, example_path in examples
        ],
    }
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_json_atomic(path: Path, payload: object) -> None:
    """同じdirectory内で置換し、途中までのJSONを残さない。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            temporary_path = Path(temporary.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def denormalize_boxes(
    boxes: Sequence[Sequence[int]],
    image_width: int,
    image_height: int,
) -> list[dict[str, int]]:
    """0〜1000の ``[ymin,xmin,ymax,xmax]`` をpixel矩形へ変換する。"""
    results: list[dict[str, int]] = []
    for box in boxes:
        if len(box) != 4:
            continue
        ymin, xmin, ymax, xmax = box
        left = max(0, min(image_width, round(xmin * image_width / 1000)))
        top = max(0, min(image_height, round(ymin * image_height / 1000)))
        right = max(0, min(image_width, round(xmax * image_width / 1000)))
        bottom = max(0, min(image_height, round(ymax * image_height / 1000)))
        if right <= left or bottom <= top:
            continue
        results.append({"x": left, "y": top, "width": right - left, "height": bottom - top})
    return results


def _iou(a: dict[str, int], b: dict[str, int]) -> float:
    ix = max(0, min(a["x"] + a["width"], b["x"] + b["width"]) - max(a["x"], b["x"]))
    iy = max(0, min(a["y"] + a["height"], b["y"] + b["height"]) - max(a["y"], b["y"]))
    intersection = ix * iy
    union = a["width"] * a["height"] + b["width"] * b["height"] - intersection
    return intersection / union if union else 0.0


def _maximum_threshold_matches(
    detected: Sequence[dict[str, int]],
    expected: Sequence[dict[str, int]],
    threshold: float,
) -> list[float]:
    """閾値以上の辺について最大数の1対1対応を返す。"""
    adjacency = [
        sorted(
            (
                (_iou(detection, target), expected_index)
                for expected_index, target in enumerate(expected)
                if _iou(detection, target) >= threshold
            ),
            reverse=True,
        )
        for detection in detected
    ]
    expected_to_detected: dict[int, int] = {}

    def augment(detected_index: int, visited: set[int]) -> bool:
        for _, expected_index in adjacency[detected_index]:
            if expected_index in visited:
                continue
            visited.add(expected_index)
            previous = expected_to_detected.get(expected_index)
            if previous is None or augment(previous, visited):
                expected_to_detected[expected_index] = detected_index
                return True
        return False

    for detected_index in range(len(detected)):
        augment(detected_index, set())
    return [
        _iou(detected[detected_index], expected[expected_index])
        for expected_index, detected_index in expected_to_detected.items()
    ]


def score_detections(
    detected: Sequence[dict[str, int]],
    expected: Sequence[dict[str, int]],
    *,
    threshold: float,
) -> dict[str, int | float]:
    """閾値を満たす最大数の1対1対応で矩形precision/recallを算出する。"""
    matches = _maximum_threshold_matches(detected, expected, threshold)
    true_positive = len(matches)
    return {
        "detected": len(detected),
        "expected": len(expected),
        "matched": len(matches),
        "true_positive": true_positive,
        "mean_iou": round(mean(matches), 4) if matches else 0.0,
        "precision": round(true_positive / len(detected), 4) if detected else 0.0,
        "recall": round(true_positive / len(expected), 4) if expected else 0.0,
    }


def groups_from_expected(
    candidates: Sequence[dict[str, int]],
    expected: Sequence[dict[str, int]],
) -> list[dict[str, list[int]]]:
    """正解矩形内に中心がある候補を、重複なしのfew-shot正解groupsへ変換する。"""
    assigned: set[int] = set()
    groups: list[dict[str, list[int]]] = []
    for target in expected:
        ids: list[int] = []
        for index, candidate in enumerate(candidates):
            if index in assigned:
                continue
            center_x = candidate["x"] + candidate["width"] / 2
            center_y = candidate["y"] + candidate["height"] / 2
            if (
                target["x"] <= center_x <= target["x"] + target["width"]
                and target["y"] <= center_y <= target["y"] + target["height"]
            ):
                ids.append(index)
                assigned.add(index)
        if ids:
            groups.append({"candidate_ids": ids})
    return groups


def merge_candidate_groups(
    candidates: Sequence[dict[str, int]],
    groups: Sequence[dict[str, Sequence[int]]],
) -> list[dict[str, int]]:
    """モデルが選んだ候補groupを外接矩形へ変換し、重複IDを無視する。"""
    used: set[int] = set()
    merged: list[dict[str, int]] = []
    for group in groups:
        ids = [index for index in group["candidate_ids"] if 0 <= index < len(candidates) and index not in used]
        if not ids:
            continue
        used.update(ids)
        blocks = [candidates[index] for index in ids]
        left = min(block["x"] for block in blocks)
        top = min(block["y"] for block in blocks)
        right = max(block["x"] + block["width"] for block in blocks)
        bottom = max(block["y"] + block["height"] for block in blocks)
        merged.append({"x": left, "y": top, "width": right - left, "height": bottom - top})
    return merged


def _local_candidates(fixture: dict[str, object]) -> list[dict[str, int]]:
    return [
        block.model_dump()
        for block in compute_vertical_blocks(
            int(fixture["image_width"]),
            int(fixture["image_height"]),
            [BlockRect(**block) for block in fixture["paragraph_blocks"]],
        )
    ]


def _normalized_expected(fixture: dict[str, object]) -> list[dict[str, list[int]]]:
    width = int(fixture["image_width"])
    height = int(fixture["image_height"])
    results = []
    for rect in fixture["expected_blocks"]:  # type: ignore[union-attr]
        results.append(
            {
                "box_2d": [
                    round(rect["y"] * 1000 / height),
                    round(rect["x"] * 1000 / width),
                    round((rect["y"] + rect["height"]) * 1000 / height),
                    round((rect["x"] + rect["width"]) * 1000 / width),
                ]
            }
        )
    return results


def _instructions(fixture: dict[str, object]) -> str:
    return f"""日本語書籍ページのOCR用「縦ブロック」を検出してください。これは段落抽出ではなく、
UIで1回クリックしてOCRするための大きな長方形cropの推定です。

- 横書き段落を、同じ視覚的な列・カード・囲み・連続領域ごとに縦方向へ結合する。
- 発話や段落ごとに分けず、可能な限り少数の大きな矩形にする。
- 独立した左右列、欄外注釈、別カード、上下段、図版に付随する独立本文は分離する。
- ヘッダー、フッター、ページ番号、罫線、イラストだけの領域は除外する。
- 文字を欠かさず、余白は最小限にする。結果は読み順で返す。
- box_2dは[ymin,xmin,ymax,xmax]をページ全体0〜1000に正規化した整数にする。

画像寸法: {fixture['image_width']}x{fixture['image_height']}
Cloud Visionの段落矩形（不完全な補助情報）:
{json.dumps(fixture['paragraph_blocks'], ensure_ascii=False)}"""


def _group_instructions(fixture: dict[str, object], candidates: Sequence[dict[str, int]]) -> str:
    listed = [{"id": index, **block} for index, block in enumerate(candidates)]
    return f"""日本語書籍ページのOCR用「縦ブロック」を作るため、ローカル候補を統合・除外してください。
これは段落抽出ではなく、UIで1回クリックしてOCRする大きな長方形cropです。

- 同じ視覚列で縦に続く候補は、途中に空白や見出しがあっても同じgroupへ統合する。
- 左右の独立列、欄外注釈、別カード、上下段だけを分ける。
- ヘッダー、フッター、ページ番号、罫線、図だけの候補は除外する。
- candidate IDは全groupsを通じて最大1回だけ使用する。
- 正しいcropを作る最小限のgroupsを読み順で返す。

画像寸法: {fixture['image_width']}x{fixture['image_height']}
候補: {json.dumps(listed, ensure_ascii=False)}"""


def _family(stem: str) -> str:
    if stem.startswith("WaresBrade_"):
        return "WaresBrade"
    if stem.startswith("warse_rule_"):
        return "warse_rule"
    if stem.startswith("warse_start_"):
        return "warse_start"
    return stem.split("_", 1)[0]


def _example_for(stem: str, fixtures: dict[str, dict[str, object]]) -> tuple[str, dict[str, object]]:
    candidates = sorted(name for name in fixtures if name != stem and _family(name) == _family(stem))
    if not candidates:
        raise ValueError(f"one-shot example is missing for {stem}")
    name = candidates[0]
    return name, fixtures[name]


def _image_part(path: Path) -> types.Part:
    mime_types = {".png": "image/png", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    try:
        mime_type = mime_types[path.suffix.lower()]
    except KeyError as error:
        raise ValueError(f"unsupported image type: {path.suffix}") from error
    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type)


def generate_json_with_token_retry(
    generate: Callable[[int], object],
) -> tuple[dict[str, object], list[object]]:
    """出力上限でJSONが切れた場合だけ上限を増やして1回再試行する。"""
    limits = (2048, 8192)
    responses: list[object] = []
    for index, max_output_tokens in enumerate(limits):
        response = generate(max_output_tokens)
        responses.append(response)
        try:
            parsed = json.loads(response.text)  # type: ignore[attr-defined]
        except json.JSONDecodeError:
            candidates = response.candidates or []  # type: ignore[attr-defined]
            finish_reason = candidates[0].finish_reason if candidates else None
            if finish_reason == types.FinishReason.MAX_TOKENS and index + 1 < len(limits):
                continue
            raise
        return parsed, responses
    raise RuntimeError("unreachable")


def generate_boxes_with_token_retry(
    generate: Callable[[int], object],
) -> tuple[list[list[int]], list[object]]:
    """矩形レスポンスを、出力上限時の再試行付きで生成する。"""
    parsed, responses = generate_json_with_token_retry(generate)
    return [item["box_2d"] for item in parsed["blocks"]], responses  # type: ignore[index]


def _usage_attempts(responses: Sequence[object]) -> list[dict[str, object] | None]:
    usages: list[dict[str, object] | None] = []
    for response in responses:
        usage_metadata = response.usage_metadata  # type: ignore[attr-defined]
        usages.append(usage_metadata.model_dump(mode="json") if usage_metadata else None)
    return usages


def _predict(
    fixture: dict[str, object],
    image_path: Path,
    *,
    model: str,
    example: tuple[dict[str, object], Path] | None,
) -> tuple[list[dict[str, int]], dict[str, object]]:
    target_content = types.Content(
        role="user",
        parts=[types.Part.from_text(text=_instructions(fixture)), _image_part(image_path)],
    )
    contents: list[types.Content] = []
    if example is not None:
        example_fixture, example_path = example
        contents.extend(
            [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text="次は正解例です。指示と粒度を学習してください。\n" + _instructions(example_fixture)
                        ),
                        _image_part(example_path),
                    ],
                ),
                types.Content(
                    role="model",
                    parts=[
                        types.Part.from_text(
                            text=json.dumps({"blocks": _normalized_expected(example_fixture)}, ensure_ascii=False)
                        )
                    ],
                ),
            ]
        )
    contents.append(target_content)
    start = time.perf_counter()

    def generate(max_output_tokens: int) -> object:
        return get_client().models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=_SCHEMA,
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                temperature=0,
                max_output_tokens=max_output_tokens,
            ),
        )

    normalized, responses = generate_boxes_with_token_retry(generate)
    detected = denormalize_boxes(normalized, int(fixture["image_width"]), int(fixture["image_height"]))
    usage_attempts = _usage_attempts(responses)
    metadata = {
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "normalized_blocks": normalized,
        "usage": usage_attempts[-1],
        "usage_attempts": usage_attempts,
    }
    return detected, metadata


def _predict_groups(
    fixture: dict[str, object],
    image_path: Path,
    *,
    model: str,
    examples: Sequence[tuple[str, dict[str, object], Path]],
) -> tuple[list[dict[str, int]], dict[str, object]]:
    contents: list[types.Content] = []
    for _, example_fixture, example_path in examples:
        example_candidates = _local_candidates(example_fixture)
        example_groups = groups_from_expected(example_candidates, example_fixture["expected_blocks"])
        contents.extend(
            [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(
                            text="これは正解例です。この統合粒度を学習してください。\n"
                            + _group_instructions(example_fixture, example_candidates)
                        ),
                        _image_part(example_path),
                    ],
                ),
                types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=json.dumps({"groups": example_groups}, ensure_ascii=False))],
                ),
            ]
        )
    candidates = _local_candidates(fixture)
    contents.append(
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text="上の正解例から最も近いレイアウトの粒度を適用してください。\n"
                    + _group_instructions(fixture, candidates)
                ),
                _image_part(image_path),
            ],
        )
    )
    start = time.perf_counter()
    def generate(max_output_tokens: int) -> object:
        return get_client().models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=_GROUP_SCHEMA,
                thinking_config=types.ThinkingConfig(thinking_level="minimal"),
                temperature=0,
                max_output_tokens=max_output_tokens,
            ),
        )

    parsed, responses = generate_json_with_token_retry(generate)
    groups = parsed["groups"]
    detected = merge_candidate_groups(candidates, groups)
    usage_attempts = _usage_attempts(responses)
    metadata = {
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "examples": [stem for stem, _, _ in examples],
        "groups": groups,
        "usage": usage_attempts[-1],
        "usage_attempts": usage_attempts,
    }
    return detected, metadata


def _load_fixtures(fixture_dir: Path) -> dict[str, dict[str, object]]:
    return {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in sorted(fixture_dir.glob("*.json"))}


def _aggregate(rows: Sequence[dict[str, object]], threshold: float) -> dict[str, int | float]:
    detected = sum(int(row["detected"]) for row in rows)
    expected = sum(int(row["expected"]) for row in rows)
    true_positive = sum(int(row["true_positive"]) for row in rows)
    return {
        "pages": len(rows),
        "detected": detected,
        "expected": expected,
        "true_positive": true_positive,
        "precision": round(true_positive / detected, 4) if detected else 0.0,
        "recall": round(true_positive / expected, 4) if expected else 0.0,
        "iou_threshold": threshold,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample_dir", type=Path, nargs="?", default=Path("Images/TEST"))
    parser.add_argument("--fixture-dir", type=Path, default=Path("tests/fixtures/regional_layout_test"))
    parser.add_argument("--output-dir", type=Path, default=Path("Output/TEST/layout-eval"))
    parser.add_argument(
        "--method",
        choices=("local", "gemini-zero", "gemini-one", "gemini-group-fewshot"),
        required=True,
    )
    parser.add_argument("--model", default=_MODEL)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    fixtures = _load_fixtures(args.fixture_dir)
    result_dir = args.output_dir / args.method
    result_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    for stem, fixture in fixtures.items():
        expected = fixture["expected_blocks"]
        result_path = result_dir / f"{stem}.json"
        if args.method == "local":
            detected = _local_candidates(fixture)
            metadata: dict[str, object] = {}
        else:
            image_path = args.sample_dir / str(fixture["image_name"])
            example = None
            fingerprint_examples: list[tuple[str, dict[str, object], Path]] = []
            if args.method == "gemini-one":
                example_stem, example_fixture = _example_for(stem, fixtures)
                example_path = args.sample_dir / str(example_fixture["image_name"])
                example = (example_fixture, example_path)
                fingerprint_examples = [(example_stem, example_fixture, example_path)]
            examples: list[tuple[str, dict[str, object], Path]] = []
            if args.method == "gemini-group-fewshot":
                reference_stems = _REFERENCE_STEMS[_family(stem)]
                examples = [
                    (
                        reference_stem,
                        fixtures[reference_stem],
                        args.sample_dir / str(fixtures[reference_stem]["image_name"]),
                    )
                    for reference_stem in reference_stems
                    if reference_stem != stem
                ]
                fingerprint_examples = examples
            fingerprint = evaluation_cache_fingerprint(
                method=args.method,
                model=args.model,
                fixture=fixture,
                image_path=image_path,
                examples=fingerprint_examples,
            )
            cached = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None
            cached_metadata = cached.get("metadata", {}) if cached else {}
            if cached is not None and cached_metadata.get("cache_fingerprint") == fingerprint:
                detected = cached["detected_blocks"]
                metadata = cached_metadata
            else:
                metadata = {
                    "cache_fingerprint": fingerprint,
                    "method": args.method,
                    "model": args.model,
                    "prompt_contract_version": _PROMPT_CONTRACT_VERSION,
                }
                if args.method == "gemini-one":
                    metadata["example"] = fingerprint_examples[0][0]
                if args.method == "gemini-group-fewshot":
                    detected, call_metadata = _predict_groups(
                        fixture,
                        image_path,
                        model=args.model,
                        examples=examples,
                    )
                else:
                    detected, call_metadata = _predict(
                        fixture,
                        image_path,
                        model=args.model,
                        example=example,
                    )
                metadata.update(call_metadata)
        score = score_detections(detected, expected, threshold=args.iou_threshold)
        row = {"stem": stem, **score, "detected_blocks": detected, "metadata": metadata}
        _write_json_atomic(result_path, row)
        rows.append(row)
        print(f"{stem}: TP={score['true_positive']}/{score['expected']} detected={score['detected']}", flush=True)
    summary = {"method": args.method, "model": args.model, **_aggregate(rows, args.iou_threshold)}
    _write_json_atomic(result_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
