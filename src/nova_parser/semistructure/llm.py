"""本文生成を許さないLLM構造推定アダプター。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol, cast

from nova_parser.ocr import FLASH_MODEL, JSONFailureArtifact, generate_json
from nova_parser.semistructure.models import (
    Audience,
    BookManifest,
    BookOutline,
    NormalizedBlock,
    OutlineSection,
    StructureProposal,
    StructureWindow,
)
from nova_parser.semistructure.prompts import (
    OUTLINE_INFERENCE_PROMPT,
    STRUCTURE_CLASSIFICATION_PROMPT,
)

PROMPT_CONTRACT_VERSION = "semistructure-reference-selection-v1"
GenerateJSON = Callable[..., dict[str, Any] | list[Any]]


class StructureClassifier(Protocol):
    """外部の構造推定を差し替えるための契約。"""

    classifier_id: str

    def infer_outline(self, blocks: Sequence[NormalizedBlock]) -> BookOutline:
        """書籍全体の粗い章構成を返す。"""
        ...

    def classify(self, window: StructureWindow) -> StructureProposal:
        """1つのページ窓を参照選択として分類する。"""
        ...


def build_structure_response_schema() -> dict[str, Any]:
    """本文を出力できないページ分類JSON Schemaを返す。"""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["segments"],
        "properties": {
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["block_ids", "section_path", "content_type", "audience", "entities"],
                    "properties": {
                        "block_ids": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string"},
                        },
                        "section_path": {"type": "array", "items": {"type": "string"}},
                        "content_type": {"type": "string", "minLength": 1},
                        "audience": {
                            "type": "string",
                            "enum": ["player", "gm", "shared", "unknown"],
                        },
                        "entities": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                        },
                        "field_confidence": {
                            "type": "object",
                            "additionalProperties": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                            },
                        },
                        "review_reasons": {"type": "array", "items": {"type": "string"}},
                        "parent_segment_id": {"type": ["string", "null"]},
                    },
                },
            }
        },
    }


def _build_outline_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["sections"],
        "properties": {
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "start_page", "end_page", "default_content_type"],
                    "properties": {
                        "title": {"type": "string", "minLength": 1},
                        "start_page": {"type": "integer", "minimum": 1},
                        "end_page": {"type": "integer", "minimum": 1},
                        "default_content_type": {"type": "string", "minLength": 1},
                        "section_path": {"type": "array", "items": {"type": "string"}},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                    },
                },
            }
        },
    }


def build_structure_windows(
    blocks: Sequence[NormalizedBlock],
    outline: BookOutline | None = None,
) -> list[StructureWindow]:
    """各中心ページに前後1ページだけを加えた重複生成しない窓を作る。"""
    ordered = sorted(blocks, key=lambda block: (block.page, block.draw_order))
    pages = sorted({block.page for block in ordered})
    return [
        StructureWindow(
            center_page=center_page,
            context_blocks=[block for block in ordered if abs(block.page - center_page) <= 1],
            allowed_block_ids=[block.block_id for block in ordered if block.page == center_page],
            outline=outline,
        )
        for center_page in pages
    ]


class GeminiStructureClassifier:
    """既存Gemini JSON backendを使う参照選択分類器。"""

    def __init__(
        self,
        *,
        manifest: BookManifest | None = None,
        generate_json: GenerateJSON = generate_json,
        model: str = FLASH_MODEL,
        failure_dir: Path = Path("Output"),
    ) -> None:
        self.manifest = manifest
        self._generate_json = generate_json
        self.model = model
        self.failure_dir = failure_dir
        self.classifier_id = f"gemini:{model}:{PROMPT_CONTRACT_VERSION}"
        self._outline: BookOutline | None = None

    def infer_outline(self, blocks: Sequence[NormalizedBlock]) -> BookOutline:
        """短いサンプルだけからアウトラインを一度推定し、失敗時はunknownへ戻す。"""
        if self._outline is not None:
            return self._outline
        if not blocks:
            raise ValueError("アウトライン推定には1件以上の block が必要です")

        payload = [
            {
                "page": block.page,
                "heading_candidate": block.normalized_text.splitlines()[0][:60],
                "excerpt": block.normalized_text[:120],
            }
            for block in blocks
        ]
        prompt = self._request_prompt(OUTLINE_INFERENCE_PROMPT, payload)
        try:
            result = self._generate_json(
                [prompt],
                model=self.model,
                temperature=0.0,
                response_json_schema=_build_outline_response_schema(),
                result_validator=self._outline_validator(blocks),
                failure_artifact=self._failure_artifact(
                    "outline",
                    blocks[0].book_id,
                    prompt,
                ),
            )
            if not isinstance(result, dict):
                raise ValueError("outline のトップレベルは object である必要があります")
            self._outline = BookOutline(
                book_id=blocks[0].book_id,
                sections=result["sections"],
            )
        except Exception:
            self._outline = self._unknown_outline(blocks)
        return self._outline

    def classify(self, window: StructureWindow) -> StructureProposal:
        """中心ページのブロックだけを参照可能な分類結果を返す。"""
        center_page = window.center_page
        allowed_id_set = set(window.allowed_block_ids)
        allowed = [block for block in window.context_blocks if block.block_id in allowed_id_set]

        payload = {
            "center_page": center_page,
            "returnable_block_ids": [block.block_id for block in allowed],
            "outline": window.outline.model_dump(mode="json") if window.outline else None,
            "blocks": [
                {
                    "block_id": block.block_id,
                    "page": block.page,
                    "draw_order": block.draw_order,
                    "raw_text": block.raw_text,
                    "normalized_text": block.normalized_text,
                    "inherited_audience": block.inherited_audience,
                    "context_only": block.page != center_page,
                }
                for block in window.context_blocks
            ],
        }
        prompt = self._request_prompt(STRUCTURE_CLASSIFICATION_PROMPT, payload)
        input_sha256 = f"sha256:{hashlib.sha256(prompt.encode()).hexdigest()}"
        result = self._generate_json(
            [prompt],
            model=self.model,
            temperature=0.0,
            response_json_schema=build_structure_response_schema(),
            result_validator=self._classification_validator(
                window.context_blocks,
                allowed,
                classifier_id=self.classifier_id,
                input_sha256=input_sha256,
            ),
            failure_artifact=self._failure_artifact(
                "classify",
                f"{allowed[0].book_id}-p{center_page}",
                prompt,
            ),
        )
        if not isinstance(result, dict):
            raise ValueError("structure proposal のトップレベルは object である必要があります")
        self._apply_audience_guardrail(result, allowed)
        result["classifier_id"] = self.classifier_id
        result["prompt_contract_version"] = PROMPT_CONTRACT_VERSION
        result["input_sha256"] = input_sha256
        return StructureProposal.model_validate(result)

    @staticmethod
    def _request_prompt(instruction: str, payload: Any) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return f"{instruction}\ncontract_version: {PROMPT_CONTRACT_VERSION}\ninput:\n{encoded}"

    def _failure_artifact(self, kind: str, source_name: str, prompt: str) -> JSONFailureArtifact:
        return JSONFailureArtifact(
            output_path=self.failure_dir / f"{source_name}.{kind}.gemini_json_error.json",
            mode=f"semistructure_{kind}",
            source_path=Path(source_name),
            prompt=prompt,
        )

    @staticmethod
    def _outline_validator(
        blocks: Sequence[NormalizedBlock],
    ) -> Callable[[dict[str, Any] | list[Any]], None]:
        book_id = blocks[0].book_id

        def validate(result: dict[str, Any] | list[Any]) -> None:
            if not isinstance(result, dict):
                raise ValueError("outline のトップレベルは object である必要があります")
            BookOutline(book_id=book_id, sections=result.get("sections", []))

        return validate

    @staticmethod
    def _classification_validator(
        all_blocks: Sequence[NormalizedBlock],
        allowed_blocks: Sequence[NormalizedBlock],
        *,
        classifier_id: str,
        input_sha256: str,
    ) -> Callable[[dict[str, Any] | list[Any]], None]:
        all_ids = {block.block_id for block in all_blocks}
        allowed_ids = {block.block_id for block in allowed_blocks}
        order = {block.block_id: index for index, block in enumerate(allowed_blocks)}
        block_by_id = {block.block_id: block for block in allowed_blocks}

        def validate(result: dict[str, Any] | list[Any]) -> None:
            if not isinstance(result, dict):
                raise ValueError("structure proposal のトップレベルは object である必要があります")
            proposal = StructureProposal.model_validate(
                {
                    **result,
                    "classifier_id": classifier_id,
                    "prompt_contract_version": PROMPT_CONTRACT_VERSION,
                    "input_sha256": input_sha256,
                }
            )
            returned: list[str] = []
            for segment in proposal.segments:
                for block_id in segment.block_ids:
                    if block_id not in all_ids:
                        raise ValueError(f"未知の block_id: {block_id}")
                    if block_id not in allowed_ids:
                        raise ValueError(f"中心ページ以外の block_id は返せません: {block_id}")
                    returned.append(block_id)
                selected_texts = [block_by_id[item].raw_text for item in segment.block_ids]
                for entity in segment.entities:
                    if not entity or not any(entity in text for text in selected_texts):
                        raise ValueError(f"entity は選択した原文に完全一致しません: {entity}")
            if len(returned) != len(set(returned)):
                raise ValueError("block_id の重複または順序変更は許可されません")
            if returned != sorted(returned, key=order.__getitem__):
                raise ValueError("block_id の順序変更は許可されません")

        return validate

    @staticmethod
    def _apply_audience_guardrail(
        result: dict[str, Any],
        allowed_blocks: Sequence[NormalizedBlock],
    ) -> None:
        block_by_id = {block.block_id: block for block in allowed_blocks}
        for raw_segment in cast(list[dict[str, Any]], result["segments"]):
            inherited_gm = any(
                block_by_id[block_id].inherited_audience == Audience.GM for block_id in raw_segment["block_ids"]
            )
            if inherited_gm and raw_segment["audience"] in {"player", "shared"}:
                raw_segment["audience"] = "gm"
                reasons = raw_segment.setdefault("review_reasons", [])
                if "audience_downgrade_candidate" not in reasons:
                    reasons.append("audience_downgrade_candidate")

    @staticmethod
    def _unknown_outline(blocks: Sequence[NormalizedBlock]) -> BookOutline:
        pages = [block.page for block in blocks]
        return BookOutline(
            book_id=blocks[0].book_id,
            sections=[
                OutlineSection(
                    title="unknown",
                    start_page=min(pages),
                    end_page=max(pages),
                    default_content_type="unknown",
                )
            ],
        )
