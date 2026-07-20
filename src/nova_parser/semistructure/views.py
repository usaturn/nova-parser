"""正本セグメントから Ruri 向け検索・トピック入力を派生する。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from nova_parser.semistructure.models import Audience, EmbeddingInput, SemanticSegment

AudienceMode = Literal["player", "gm", "all"]

# プレイヤー向け派生から除外する audience
_PLAYER_EXCLUDED = frozenset({Audience.GM, Audience.UNKNOWN})


@dataclass(frozen=True, slots=True)
class DerivedViews:
    """検索用・トピック用の派生埋め込み入力セット。"""

    retrieval: list[EmbeddingInput]
    topic: list[EmbeddingInput]


def build_retrieval_view(
    segment: SemanticSegment,
    *,
    title: str | None = None,
) -> EmbeddingInput:
    """検索（RAG）用の埋め込み入力を組み立てる。

    行順は固定:
    検索文書: 書籍: {title}
    章節: {section_path joined by " > "}
    種別: {content_type}
    本文: {normalized_text}

    `title` 未指定時は `book_id` を書籍名として使う。
    短文を 100 文字以上へ水増ししない。種別はプレフィックスで明示する。
    """
    book_title = title if title is not None else segment.book_id
    section = " > ".join(segment.section_path)
    text = "\n".join(
        [
            f"検索文書: 書籍: {book_title}",
            f"章節: {section}",
            f"種別: {segment.content_type}",
            f"本文: {segment.normalized_text}",
        ]
    )
    return EmbeddingInput(
        segment_id=segment.segment_id,
        input_type="document",
        text=text,
        book_id=segment.book_id,
        audience=segment.audience,
        content_type=segment.content_type,
        source_spans=list(segment.source_spans),
    )


def build_topic_view(segment: SemanticSegment) -> EmbeddingInput:
    """トピック（類似探索・分類）用の埋め込み入力を組み立てる。

    行順は固定:
    トピック: {entities joined by "、"}
    章節: {section_path joined by " > "}
    種別: {content_type}
    本文: {normalized_text}

    entities が空でも `トピック: ` 行は残す。短文の水増しはしない。
    """
    entities = "、".join(segment.entities)
    section = " > ".join(segment.section_path)
    text = "\n".join(
        [
            f"トピック: {entities}",
            f"章節: {section}",
            f"種別: {segment.content_type}",
            f"本文: {segment.normalized_text}",
        ]
    )
    return EmbeddingInput(
        segment_id=segment.segment_id,
        input_type="topic",
        text=text,
        book_id=segment.book_id,
        audience=segment.audience,
        content_type=segment.content_type,
        source_spans=list(segment.source_spans),
    )


def build_views(
    segments: Sequence[SemanticSegment],
    *,
    audience_mode: AudienceMode = "all",
    book_titles: Mapping[str, str] | None = None,
) -> DerivedViews:
    """セグメント列から検索・トピック双方の派生ビューを構築する。

    Parameters
    ----------
    segments:
        正本セグメント列。入力順を保持する。
    audience_mode:
        - ``player``: `Audience.GM` / `Audience.UNKNOWN` を除外
        - ``gm`` / ``all``: 全 audience を含む
    book_titles:
        `book_id` → 表示タイトル。検索ビューの「書籍:」行に使う。
        未指定またはキー無しの場合は `book_id` を使う。
    """
    titles = book_titles or {}
    retrieval: list[EmbeddingInput] = []
    topic: list[EmbeddingInput] = []

    for segment in segments:
        if not _is_visible(segment.audience, audience_mode):
            continue
        title = titles.get(segment.book_id)
        retrieval.append(build_retrieval_view(segment, title=title))
        topic.append(build_topic_view(segment))

    return DerivedViews(retrieval=retrieval, topic=topic)


def _is_visible(audience: Audience, audience_mode: AudienceMode) -> bool:
    """audience_mode に応じて派生対象か判定する。"""
    if audience_mode == "player":
        return audience not in _PLAYER_EXCLUDED
    return True
