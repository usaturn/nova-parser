"""半構造化パイプラインの正本と中間表現。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nova_parser.regional_ocr.models import Rectangle


class DocumentType(StrEnum):
    """処理対象の文書種別。"""

    RULEBOOK = "rulebook"
    REPLAY = "replay"
    SCENARIO = "scenario"
    UNKNOWN = "unknown"


class Audience(StrEnum):
    """情報を開示できる対象。"""

    PLAYER = "player"
    GM = "gm"
    SHARED = "shared"
    UNKNOWN = "unknown"


class Confidence(StrEnum):
    """自動判定の信頼度。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewStatus(StrEnum):
    """人手レビューの状態。"""

    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
    APPROVED = "approved"
    REJECTED = "rejected"


class SourceSpan(BaseModel):
    """OCR領域内の半開文字範囲。"""

    page: int = Field(ge=1)
    rect_id: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """空または逆順の範囲を拒否する。"""
        if self.end <= self.start:
            raise ValueError("source span は非空の昇順範囲である必要があります")
        return self


class AudienceOverride(BaseModel):
    """ページ範囲に明示されたaudience既定値。"""

    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    audience: Audience

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """逆順のページ範囲を拒否する。"""
        if self.end_page < self.start_page:
            raise ValueError("audience range は昇順である必要があります")
        return self


class DocumentTypeOverride(BaseModel):
    """ページ範囲に明示された文書種別の上書き。"""

    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    document_type: DocumentType

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        """逆順のページ範囲を拒否する。"""
        if self.end_page < self.start_page:
            raise ValueError("document type override は昇順である必要があります")
        return self


class BookManifest(BaseModel):
    """書籍ごとに人が固定する入力設定。"""

    book_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    input_glob: str = "*.regions.json"
    page_pattern: str = r"p(?P<page>\d+)"
    default_document_type: DocumentType
    default_audience: Audience = Audience.SHARED
    audience_overrides: list[AudienceOverride] = Field(default_factory=list)
    document_type_overrides: list[DocumentTypeOverride] = Field(default_factory=list)
    schema_version: int = Field(default=1, ge=1)

    def resolve_document_type(self, page: int) -> DocumentType:
        """ページ番号から document_type_overrides を探索し、該当する DocumentType を返す。"""
        for override in self.document_type_overrides:
            if override.start_page <= page <= override.end_page:
                return override.document_type
        return self.default_document_type


class OcrRegion(BaseModel):
    """原文を変更せず保持するOCR領域。"""

    book_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    image_name: str = Field(min_length=1)
    rectangle: Rectangle
    raw_text: str
    ocr_status: Literal["pending", "done", "error"]

    @property
    def rect_id(self) -> str:
        """参照で頻用する領域IDを返す。"""
        return self.rectangle.rect_id

    @property
    def draw_order(self) -> int:
        """参照で頻用する描画順を返す。"""
        return self.rectangle.draw_order


class OcrPage(BaseModel):
    """入力ファイル1件に対応する検証済みOCRページ。"""

    book_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    image_name: str = Field(min_length=1)
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    regions: list[OcrRegion]
    source_sha256: str = Field(min_length=1)
    inherited_audience: Audience


class NormalizationOperation(BaseModel):
    """正規化本文へ適用した決定的な操作。"""

    type: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    details: dict[str, str] = Field(default_factory=dict)


class NormalizedBlock(BaseModel):
    """LLMへ渡す、原文へ逆引き可能な正規化ブロック。"""

    block_id: str = Field(min_length=1)
    book_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    draw_order: int = Field(ge=0)
    raw_text: str
    normalized_text: str
    source_spans: list[SourceSpan] = Field(min_length=1)
    operations: list[NormalizationOperation] = Field(default_factory=list)
    inherited_audience: Audience = Audience.SHARED
    review_reasons: list[str] = Field(default_factory=list)


class OutlineSection(BaseModel):
    """書籍全体から推定した章節候補。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    default_content_type: str = Field(min_length=1)
    section_path: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM

    @model_validator(mode="after")
    def validate_page_range(self) -> Self:
        """終了ページが開始ページより前の章範囲を拒否する。"""
        if self.end_page < self.start_page:
            raise ValueError("outline section は昇順のページ範囲である必要があります")
        return self


class BookOutline(BaseModel):
    """書籍全体の粗い章構成。"""

    model_config = ConfigDict(extra="forbid")

    book_id: str = Field(min_length=1)
    sections: list[OutlineSection] = Field(default_factory=list)


class ProposalSegment(BaseModel):
    """LLMが本文生成なしで返す意味境界と分類。"""

    model_config = ConfigDict(extra="forbid")

    block_ids: list[str] = Field(min_length=1)
    section_path: list[str] = Field(default_factory=list)
    content_type: str = Field(min_length=1)
    audience: Audience
    entities: list[str] = Field(default_factory=list)
    field_confidence: dict[str, Confidence] = Field(default_factory=dict)
    review_reasons: list[str] = Field(default_factory=list)
    parent_segment_id: str | None = None


class StructureProposal(BaseModel):
    """1つの処理窓に対する構造推定結果。"""

    model_config = ConfigDict(extra="forbid")

    segments: list[ProposalSegment] = Field(default_factory=list)
    classifier_id: str = Field(min_length=1)
    prompt_contract_version: str = Field(min_length=1)
    input_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class StructureWindow(BaseModel):
    """前後文脈を含めて分類器へ渡す正規化ブロック窓。"""

    center_page: int = Field(ge=1)
    context_blocks: list[NormalizedBlock] = Field(min_length=1)
    allowed_block_ids: list[str] = Field(min_length=1)
    outline: BookOutline | None = None

    @model_validator(mode="after")
    def validate_allowed_blocks(self) -> Self:
        """返却許可IDを文脈内の中心ページブロックだけに限定する。"""
        context_book_ids = {block.book_id for block in self.context_blocks}
        if len(context_book_ids) != 1:
            raise ValueError("context_blocks に別の書籍を混在できません")
        context_book_id = next(iter(context_book_ids))
        if self.outline is not None and self.outline.book_id != context_book_id:
            raise ValueError("outline の book_id が context_blocks と一致しません")
        if len(self.allowed_block_ids) != len(set(self.allowed_block_ids)):
            raise ValueError("allowed_block_ids に重複があります")
        context_by_id = {block.block_id: block for block in self.context_blocks}
        missing = [block_id for block_id in self.allowed_block_ids if block_id not in context_by_id]
        if missing:
            raise ValueError(f"allowed_block_ids が context_blocks に存在しません: {missing}")
        off_center = [
            block_id for block_id in self.allowed_block_ids if context_by_id[block_id].page != self.center_page
        ]
        if off_center:
            raise ValueError(f"中心ページ以外の block_id は許可できません: {off_center}")
        return self


class SemanticSegment(BaseModel):
    """半構造化後の正本JSONLレコード。"""

    schema_version: int = Field(default=1, ge=1)
    segment_id: str = Field(min_length=1)
    parent_segment_id: str | None = None
    book_id: str = Field(min_length=1)
    document_type: DocumentType
    section_path: list[str] = Field(default_factory=list)
    content_type: str = Field(min_length=1)
    audience: Audience
    inherited_audience: Audience = Audience.SHARED
    source_spans: list[SourceSpan] = Field(min_length=1)
    raw_text: str
    normalized_text: str
    entities: list[str] = Field(default_factory=list)
    normalization_ops: list[NormalizationOperation] = Field(default_factory=list)
    field_confidence: dict[str, Confidence] = Field(default_factory=dict)
    processing: dict[str, str] = Field(default_factory=dict)
    review_status: ReviewStatus = ReviewStatus.NOT_REQUIRED

    @model_validator(mode="after")
    def validate_audience_inheritance(self) -> Self:
        """未承認のGM情報がplayer/sharedへ降格することを拒否する。"""
        is_downgrade = self.inherited_audience == Audience.GM and self.audience in {
            Audience.PLAYER,
            Audience.SHARED,
        }
        if is_downgrade and self.review_status != ReviewStatus.APPROVED:
            raise ValueError("GM範囲を継承したセグメントのaudience降格には承認が必要です")
        return self


class ReviewItem(BaseModel):
    """人が確認すべき判定とその原文コンテキスト。"""

    review_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    reasons: list[str] = Field(min_length=1)
    source_spans: list[SourceSpan] = Field(min_length=1)
    raw_text: str
    normalized_text: str
    image_name: str | None = None
    context_before: str = ""
    context_after: str = ""
    status: ReviewStatus = ReviewStatus.REQUIRED


class ReviewDecision(BaseModel):
    """再処理時にも再適用できる人手レビュー判断。"""

    review_id: str = Field(min_length=1)
    segment_id: str = Field(min_length=1)
    status: Literal[ReviewStatus.APPROVED, ReviewStatus.REJECTED]
    input_hash: str = Field(min_length=1)
    processing_version: str = Field(min_length=1)
    decided_by: str = Field(min_length=1)
    comment: str = ""


class EmbeddingInput(BaseModel):
    """検索前フィルタと原文逆引き情報を保持した埋め込み入力。"""

    segment_id: str = Field(min_length=1)
    input_type: Literal["document", "topic"]
    text: str = Field(min_length=1)
    book_id: str = Field(min_length=1)
    audience: Audience
    content_type: str = Field(min_length=1)
    source_spans: list[SourceSpan] = Field(min_length=1)


class PipelineConfig(BaseModel):
    """半構造化パイプラインの入出力設定。"""

    manifest_path: Path
    input_dir: Path
    output_dir: Path
    review_decisions: Path | None = None
    no_cache: bool = False
    dry_run: bool = False
